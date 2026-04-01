"""Lower narrow semantic edits into Docs API requests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extradoc.indexer import utf16_len
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.mock.exceptions import ValidationError
from extradoc.reconcile_v2.diff import (
    AppendListItemsEdit,
    CreateFootnoteEdit,
    CreateSectionAttachmentEdit,
    DeleteListBlockEdit,
    DeletePageBreakBlockEdit,
    DeleteSectionAttachmentEdit,
    DeleteSectionEdit,
    DeleteTableBlockEdit,
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertListBlockEdit,
    InsertPageBreakBlockEdit,
    InsertSectionEdit,
    InsertTableBlockEdit,
    InsertTableColumnEdit,
    InsertTableRowEdit,
    MergeTableCellsEdit,
    RelevelListItemsEdit,
    ReplaceListSpecEdit,
    ReplaceNamedRangesEdit,
    ReplaceParagraphSliceEdit,
    ReplaceParagraphTextEdit,
    SemanticEdit,
    UnmergeTableCellsEdit,
    UpdateListItemRolesEdit,
    UpdateParagraphRoleEdit,
    UpdateTableCellStyleEdit,
    UpdateTableColumnPropertiesEdit,
    UpdateTablePinnedHeaderRowsEdit,
    UpdateTableRowStyleEdit,
)
from extradoc.reconcile_v2.errors import ReconcileInvariantError, UnsupportedReconcileV2Error
from extradoc.reconcile_v2.ir import ParagraphIR, TableIR, TextSpanIR
from extradoc.reconcile_v2.layout import (
    BodyLayout,
    InlineSlotLocation,
    ListLocation,
    PageBreakLocation,
    ParagraphLocation,
    StoryParagraphLocation,
    StoryRoute,
    TableLocation,
    build_body_layout,
    build_story_layouts,
    paragraph_insertion_site,
    paragraph_slice,
    resolve_position_to_index,
)
from extradoc.reconcile_v2.requests import (
    bullet_preset_for_kind,
    make_create_named_range,
    make_create_paragraph_bullets,
    make_delete_content_range,
    make_delete_footer,
    make_delete_header,
    make_delete_named_range,
    make_delete_paragraph_bullets,
    make_delete_table_column,
    make_delete_table_row,
    make_insert_page_break,
    make_insert_section_break,
    make_insert_table,
    make_insert_table_column,
    make_insert_table_row,
    make_insert_text,
    make_insert_text_in_story,
    make_merge_table_cells,
    make_pin_table_header_rows,
    make_unmerge_table_cells,
    make_update_paragraph_role,
    make_update_paragraph_style,
    make_update_table_cell_style,
    make_update_table_column_properties,
    make_update_table_row_style,
    make_update_text_style,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document


def lower_document_edits(
    base: Document,
    edits: list[SemanticEdit],
    *,
    desired: Document | None = None,
) -> list[dict[str, Any]]:
    """Lower the supported semantic edits into batchUpdate request dicts."""
    requests: list[dict[str, Any]] = []
    layouts: dict[str, BodyLayout] = {}
    story_layouts = build_story_layouts(base)
    desired_story_layouts = None
    desired_body_layouts: dict[str, BodyLayout] = {}
    shadow_document: Document | None = None
    shadow_story_layouts: dict[str, object] | None = None
    shadow_body_layouts: dict[str, BodyLayout] = {}
    shadow_request_count = -1
    content_edited_story_ids = _edited_story_ids(edits)
    indexed_content_edits = [
        (index, edit) for index, edit in enumerate(edits) if not isinstance(edit, ReplaceNamedRangesEdit)
    ]
    indexed_content_edits.sort(key=lambda item: _content_edit_order_key(item[0], item[1]))
    content_edits = [edit for _, edit in indexed_content_edits]

    edit_index = 0
    while edit_index < len(content_edits):
        current_document = base
        current_story_layouts = story_layouts
        current_body_layouts = layouts
        if requests:
            (
                shadow_document,
                shadow_story_layouts,
                shadow_body_layouts,
                shadow_request_count,
            ) = _ensure_shadow_state(
                base=base,
                requests=requests,
                shadow_document=shadow_document,
                shadow_story_layouts=shadow_story_layouts,
                shadow_request_count=shadow_request_count,
            )
            if shadow_document is not None and shadow_story_layouts is not None:
                current_document = shadow_document
                current_story_layouts = shadow_story_layouts
                current_body_layouts = shadow_body_layouts
        group_end = _body_insert_group_end(
            content_edits,
            edit_index,
            current_document=current_document,
            current_body_layouts=current_body_layouts,
        )
        if group_end - edit_index > 1:
            group = content_edits[edit_index:group_end]
            requests.extend(
                _lower_body_insert_group(
                    base=base,
                    prior_requests=requests,
                    edits=group,
                    desired=desired,
                )
            )
            edit_index = group_end
            continue
        edit = content_edits[edit_index]
        layout = current_body_layouts.setdefault(
            edit.tab_id,
            build_body_layout(current_document, tab_id=edit.tab_id),
        )
        if isinstance(edit, UpdateParagraphRoleEdit):
            paragraph = _paragraph_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_update_paragraph_role(
                    start_index=paragraph.start_index,
                    end_index=paragraph.end_index,
                    tab_id=edit.tab_id,
                    role=edit.after_role,
                )
            )
        elif isinstance(edit, ReplaceParagraphTextEdit):
            if (
                edit.story_id == f"{edit.tab_id}:body"
                and edit.section_index is not None
            ):
                paragraph = _paragraph_at(layout, edit.section_index, edit.block_index)
            else:
                paragraph = _story_paragraph_at(
                    current_story_layouts[edit.story_id],
                    section_index=edit.section_index,
                    block_index=edit.block_index,
                )
            route = (
                StoryRoute(tab_id=edit.tab_id, segment_id=None)
                if edit.story_id == f"{edit.tab_id}:body"
                else current_story_layouts[edit.story_id].route
            )
            if any(slot.kind != "text" for slot in paragraph.inline_slots):
                requests.extend(
                    _lower_paragraph_text_replace_preserving_inline_anchors(
                        route=route,
                        paragraph=paragraph,
                        desired_paragraph=edit.desired_paragraph,
                    )
                )
            else:
                if paragraph.text_end_index > paragraph.text_start_index:
                    requests.append(
                        make_delete_content_range(
                            start_index=paragraph.text_start_index,
                            end_index=paragraph.text_end_index,
                            tab_id=edit.tab_id,
                            segment_id=route.segment_id,
                        )
                    )
                replacement_text = _paragraph_text(edit.desired_paragraph)
                if replacement_text:
                    requests.append(
                        make_insert_text_in_story(
                            index=paragraph.text_start_index,
                            tab_id=route.tab_id,
                            segment_id=route.segment_id,
                            text=replacement_text,
                        )
                    )
                    requests.extend(
                        _lower_inserted_text_styles(
                            route=route,
                            paragraph_locations=(
                                (
                                    edit.desired_paragraph,
                                    (
                                        paragraph.text_start_index,
                                        paragraph.text_start_index + utf16_len(replacement_text),
                                    ),
                                ),
                            ),
                        )
                    )
        elif isinstance(edit, InsertListBlockEdit):
            story = current_story_layouts[f"{edit.tab_id}:body"]
            insert_index, prefix_newline, suffix_newline = _body_insert_site_for_edit(
                current_document,
                layout,
                edit,
            )
            list_text = "\n".join(_list_item_text(item) for item in edit.items)
            if list_text:
                if prefix_newline:
                    list_text = f"\n{list_text}"
                if suffix_newline:
                    list_text = f"{list_text}\n"
                requests.append(
                    make_insert_text(
                        index=insert_index,
                        tab_id=edit.tab_id,
                        text=list_text,
                    )
                )
                bullet_start, bullet_end = _inserted_list_range(
                    start_index=insert_index,
                    items=edit.items,
                    prefix_newline=prefix_newline,
                )
                requests.append(
                    make_create_paragraph_bullets(
                        start_index=bullet_start,
                        end_index=bullet_end,
                        tab_id=edit.tab_id,
                        bullet_preset=bullet_preset_for_kind(edit.list_kind),
                    )
                )
                requests.extend(
                    _inserted_list_level_requests(
                        tab_id=edit.tab_id,
                        start_index=insert_index,
                        items=edit.items,
                        prefix_newline=prefix_newline,
                    )
                )
        elif isinstance(edit, DeleteListBlockEdit):
            list_location = _list_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_delete_content_range(
                    start_index=list_location.start_index,
                    end_index=list_location.end_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, InsertTableBlockEdit):
            insert_index, _prefix_newline, _suffix_newline = _body_insert_site_for_edit(
                current_document,
                layout,
                edit,
            )
            requests.extend(
                _lower_blocks_into_fresh_story(
                    [edit.table],
                    story_start_index=insert_index,
                    tab_id=edit.tab_id,
                    segment_id=None,
                )
            )
        elif isinstance(edit, InsertPageBreakBlockEdit):
            insert_index, _prefix_newline, _suffix_newline = _body_insert_site_for_edit(
                current_document,
                layout,
                edit,
            )
            requests.append(
                make_insert_page_break(
                    index=insert_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, DeleteTableBlockEdit):
            if edit.body_anchor_block_index is not None:
                table_range = _raw_body_block_range(
                    current_document,
                    tab_id=edit.tab_id,
                    section_index=edit.section_index,
                    raw_block_index=edit.body_anchor_block_index,
                    expected_kind="table",
                )
                start_index = table_range["start"]
                end_index = table_range["end"]
            else:
                table_location = _table_at(layout, edit.section_index, edit.block_index)
                start_index = table_location.start_index
                end_index = table_location.end_index
            requests.append(
                make_delete_content_range(
                    start_index=start_index,
                    end_index=end_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, DeletePageBreakBlockEdit):
            if edit.body_anchor_block_index is not None:
                page_break_range = _raw_body_block_range(
                    current_document,
                    tab_id=edit.tab_id,
                    section_index=edit.section_index,
                    raw_block_index=edit.body_anchor_block_index,
                    expected_kind="pagebreak",
                )
                start_index = page_break_range["start"]
                end_index = page_break_range["end"]
            else:
                page_break = _page_break_at(layout, edit.section_index, edit.block_index)
                start_index = page_break.start_index
                end_index = page_break.end_index
            requests.append(
                make_delete_content_range(
                    start_index=start_index,
                    end_index=end_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, AppendListItemsEdit):
            list_location = _list_at(layout, edit.section_index, edit.block_index)
            insert_text = "".join(_list_item_text(item) + "\n" for item in edit.appended_items)
            insert_index = list_location.end_index
            requests.append(
                make_insert_text(
                    index=insert_index,
                    tab_id=edit.tab_id,
                    text=insert_text,
                )
            )
            requests.append(
                make_create_paragraph_bullets(
                    start_index=insert_index,
                    end_index=insert_index + utf16_len(insert_text),
                    tab_id=edit.tab_id,
                    bullet_preset=bullet_preset_for_kind(edit.list_kind),
                )
            )
            requests.extend(
                _inserted_list_level_requests(
                    tab_id=edit.tab_id,
                    start_index=insert_index,
                    items=edit.appended_items,
                    prefix_newline=False,
                )
            )
        elif isinstance(edit, ReplaceListSpecEdit):
            list_location = _list_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_delete_paragraph_bullets(
                    start_index=list_location.start_index,
                    end_index=list_location.end_index,
                    tab_id=edit.tab_id,
                )
            )
            requests.append(
                make_create_paragraph_bullets(
                    start_index=list_location.start_index,
                    end_index=list_location.end_index,
                    tab_id=edit.tab_id,
                    bullet_preset=bullet_preset_for_kind(edit.after_kind),
                )
            )
        elif isinstance(edit, RelevelListItemsEdit):
            list_location = _list_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_delete_paragraph_bullets(
                    start_index=list_location.start_index,
                    end_index=list_location.end_index,
                    tab_id=edit.tab_id,
                )
            )
            requests.append(
                make_create_paragraph_bullets(
                    start_index=list_location.start_index,
                    end_index=list_location.end_index,
                    tab_id=edit.tab_id,
                    bullet_preset=bullet_preset_for_kind(edit.list_kind),
                )
            )
            for item_index, item_location in enumerate(list_location.items):
                after_level = edit.after_levels[item_index]
                paragraph_style = _list_level_paragraph_style(after_level)
                if paragraph_style is None:
                    continue
                requests.append(
                    make_update_paragraph_style(
                        start_index=item_location.start_index,
                        end_index=item_location.end_index,
                        tab_id=edit.tab_id,
                        paragraph_style=paragraph_style,
                        fields=tuple(paragraph_style.keys()),
                    )
                )
        elif isinstance(edit, UpdateListItemRolesEdit):
            list_location = _list_at(layout, edit.section_index, edit.block_index)
            for item_index, after_role in zip(
                edit.item_indexes,
                edit.after_roles,
                strict=True,
            ):
                item_location = list_location.items[item_index]
                requests.append(
                    make_update_paragraph_role(
                        start_index=item_location.start_index,
                        end_index=item_location.end_index,
                        tab_id=edit.tab_id,
                        role=after_role,
                    )
                )
        elif isinstance(edit, InsertSectionEdit):
            next_block = layout.sections[edit.section_index].block_locations[
                edit.split_after_block_index + 1
            ]
            requests.append(
                make_insert_section_break(
                    index=next_block.start_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, DeleteSectionEdit):
            boundary = layout.sections[edit.section_index].incoming_boundary
            if boundary is None:
                raise ValueError(
                    f"Section {edit.section_index} in tab {edit.tab_id} has no incoming boundary"
                )
            requests.append(
                make_delete_content_range(
                    start_index=boundary.delete_start_index,
                    end_index=boundary.delete_end_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, DeleteSectionAttachmentEdit):
            if edit.attachment_kind == "headers":
                requests.append(
                    make_delete_header(header_id=edit.story_id, tab_id=edit.tab_id)
                )
            elif edit.attachment_kind == "footers":
                requests.append(
                    make_delete_footer(footer_id=edit.story_id, tab_id=edit.tab_id)
                )
            else:
                raise UnsupportedReconcileV2Error(
                    f"Unsupported section attachment kind: {edit.attachment_kind}"
                )
        elif isinstance(edit, CreateSectionAttachmentEdit):
            raise ReconcileInvariantError(
                "reconcile_v2 section attachment creation requires batch planning; "
                "use lower_semantic_diff_batches() or reconcile()"
            )
        elif isinstance(edit, CreateFootnoteEdit):
            raise ReconcileInvariantError(
                "reconcile_v2 footnote creation requires batch planning; "
                "use lower_semantic_diff_batches() or reconcile()"
            )
        elif isinstance(edit, ReplaceParagraphSliceEdit):
            story = current_story_layouts[edit.story_id]
            inserted_text = "\n".join(fragment.text for fragment in edit.inserted_paragraphs)
            prefix_newline = False
            suffix_newline = False
            if edit.delete_block_count > 0:
                if (
                    story.route.segment_id is None
                    and edit.section_index is not None
                    and edit.story_id == f"{edit.tab_id}:body"
                ):
                    paragraphs = _body_paragraph_slice(
                        layout,
                        section_index=edit.section_index,
                        start_block_index=edit.start_block_index,
                        delete_block_count=edit.delete_block_count,
                    )
                    delete_start = paragraphs[0].text_start_index
                    delete_end = paragraphs[-1].text_end_index
                else:
                    paragraphs = paragraph_slice(
                        story,
                        section_index=edit.section_index,
                        start_block_index=edit.start_block_index,
                        delete_block_count=edit.delete_block_count,
                    )
                    delete_start = paragraphs[0].text_start_index
                    delete_end = _story_paragraph_delete_end(
                        story_id=edit.story_id,
                        paragraphs=paragraphs,
                    )
                if delete_end > delete_start:
                    requests.append(
                        make_delete_content_range(
                            start_index=delete_start,
                            end_index=delete_end,
                            tab_id=story.route.tab_id,
                            segment_id=story.route.segment_id,
                        )
                    )
            else:
                if (
                    story.route.segment_id is None
                    and edit.section_index is not None
                    and edit.story_id == f"{edit.tab_id}:body"
                ):
                    delete_start, prefix_newline, suffix_newline = _body_insert_site_for_edit(
                        current_document,
                        layout,
                        edit,
                    )
                else:
                    delete_start, prefix_newline, suffix_newline = paragraph_insertion_site(
                        story,
                        section_index=edit.section_index,
                        block_index=edit.start_block_index,
                    )
                if inserted_text:
                    if prefix_newline:
                        inserted_text = f"\n{inserted_text}"
                    if suffix_newline:
                        inserted_text = f"{inserted_text}\n"
            if inserted_text:
                requests.append(
                    make_insert_text_in_story(
                        index=delete_start,
                        tab_id=story.route.tab_id,
                        segment_id=story.route.segment_id,
                        text=inserted_text,
                    )
                )
                paragraph_locations = _inserted_paragraph_locations(
                    start_index=delete_start,
                    paragraphs=tuple(
                        fragment.paragraph for fragment in edit.inserted_paragraphs
                    ),
                    prefix_newline=prefix_newline,
                )
                for paragraph, (paragraph_start, paragraph_end) in paragraph_locations:
                    if paragraph.role != "NORMAL_TEXT":
                        requests.append(
                            make_update_paragraph_role(
                                start_index=paragraph_start,
                                end_index=paragraph_end,
                                tab_id=story.route.tab_id,
                                role=paragraph.role,
                            )
                        )
                requests.extend(
                    _lower_inserted_text_styles(
                        route=story.route,
                        paragraph_locations=paragraph_locations,
                    )
                )
        elif isinstance(edit, InsertTableRowEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_insert_table_row(
                    table_start_index=table.start_index,
                    row_index=edit.row_index,
                    insert_below=edit.insert_below,
                    tab_id=edit.tab_id,
                )
            )
            if any(edit.inserted_cells):
                insert_index = edit.row_index + 1 if edit.insert_below else edit.row_index
                if insert_index >= table.row_count:
                    raise UnsupportedReconcileV2Error(
                        "reconcile_v2 supports inserted-row content only for non-terminal row inserts"
                    )
                anchor = _table_cell_text_start(
                    story_layouts,
                    f"{edit.tab_id}:body:table:{edit.block_index}:r{insert_index}:c0",
                )
                for column_index, text in enumerate(edit.inserted_cells):
                    if text:
                        requests.append(
                            make_insert_text(
                                index=anchor + (2 * column_index),
                                tab_id=edit.tab_id,
                                text=text,
                            )
                        )
        elif isinstance(edit, DeleteTableRowEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_delete_table_row(
                    table_start_index=table.start_index,
                    row_index=edit.row_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, InsertTableColumnEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_insert_table_column(
                    table_start_index=table.start_index,
                    column_index=edit.column_index,
                    insert_right=edit.insert_right,
                    tab_id=edit.tab_id,
                )
            )
            if any(edit.inserted_cells):
                insert_index = edit.column_index + 1 if edit.insert_right else edit.column_index
                if insert_index >= table.column_count:
                    raise UnsupportedReconcileV2Error(
                        "reconcile_v2 supports inserted-column content only for non-terminal column inserts"
                    )
                for row_index, text in enumerate(edit.inserted_cells):
                    if not text:
                        continue
                    anchor = _table_cell_text_start(
                        story_layouts,
                        f"{edit.tab_id}:body:table:{edit.block_index}:r{row_index}:c{insert_index}",
                    )
                    requests.append(
                        make_insert_text(
                            index=anchor + (2 * row_index),
                            tab_id=edit.tab_id,
                            text=text,
                        )
                    )
        elif isinstance(edit, DeleteTableColumnEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_delete_table_column(
                    table_start_index=table.start_index,
                    column_index=edit.column_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, MergeTableCellsEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_merge_table_cells(
                    table_start_index=table.start_index,
                    row_index=edit.row_index,
                    column_index=edit.column_index,
                    row_span=edit.row_span,
                    column_span=edit.column_span,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, UnmergeTableCellsEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_unmerge_table_cells(
                    table_start_index=table.start_index,
                    row_index=edit.row_index,
                    column_index=edit.column_index,
                    row_span=edit.row_span,
                    column_span=edit.column_span,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, UpdateTablePinnedHeaderRowsEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_pin_table_header_rows(
                    table_start_index=table.start_index,
                    pinned_header_rows_count=edit.pinned_header_rows,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, UpdateTableRowStyleEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_update_table_row_style(
                    table_start_index=table.start_index,
                    row_index=edit.row_index,
                    style=edit.style,
                    fields=edit.fields,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, UpdateTableColumnPropertiesEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_update_table_column_properties(
                    table_start_index=table.start_index,
                    column_index=edit.column_index,
                    properties=edit.properties,
                    fields=edit.fields,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, UpdateTableCellStyleEdit):
            table = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_update_table_cell_style(
                    table_start_index=table.start_index,
                    row_index=edit.row_index,
                    column_index=edit.column_index,
                    style=edit.style,
                    fields=edit.fields,
                    tab_id=edit.tab_id,
                )
            )
        edit_index += 1

    for edit in [edit for edit in edits if isinstance(edit, ReplaceNamedRangesEdit)]:
        if edit.before_count and not edit.name.startswith("extradoc:"):
            requests.append(make_delete_named_range(name=edit.name))
        for anchor in edit.desired_ranges:
            layout_source = story_layouts
            body_layout_source = layouts
            document_source = base
            if (
                desired is not None
                and (
                    anchor.start.story_id in content_edited_story_ids
                    or anchor.end.story_id in content_edited_story_ids
                )
            ):
                if requests:
                    try:
                        (
                            shadow_document,
                            shadow_story_layouts,
                            shadow_body_layouts,
                            shadow_request_count,
                        ) = _ensure_shadow_state(
                            base=base,
                            requests=requests,
                            shadow_document=shadow_document,
                            shadow_story_layouts=shadow_story_layouts,
                            shadow_request_count=shadow_request_count,
                        )
                    except ValidationError:
                        shadow_document = None
                        shadow_story_layouts = None
                        shadow_body_layouts = {}
                        shadow_request_count = -1
                special_range = (
                    _resolve_special_table_named_range(
                        document=shadow_document,
                        body_layouts=shadow_body_layouts,
                        anchor=anchor,
                        name=edit.name,
                    )
                    if shadow_document is not None
                    else None
                )
                if special_range is not None:
                    start_route, start_index, end_index = special_range
                    end_route = start_route
                else:
                    if desired_story_layouts is None:
                        if desired is None:
                            raise ValueError(
                                "Desired story layouts are required for edited named ranges"
                            )
                        desired_story_layouts = build_story_layouts(desired)
                    start_route, start_index = _resolve_position_for_named_range(
                        story_layouts=desired_story_layouts,
                        body_layouts=desired_body_layouts,
                        document=desired,
                        position=anchor.start,
                    )
                    end_route, end_index = _resolve_position_for_named_range(
                        story_layouts=desired_story_layouts,
                        body_layouts=desired_body_layouts,
                        document=desired,
                        position=anchor.end,
                    )
                    if not _named_range_fits_current_document(
                        base=base,
                        requests=requests,
                        route=start_route,
                        start_index=start_index,
                        end_index=end_index,
                        shadow_document=shadow_document,
                    ):
                        if shadow_document is None:
                            (
                                shadow_document,
                                shadow_story_layouts,
                                shadow_body_layouts,
                                shadow_request_count,
                            ) = _ensure_shadow_state(
                                base=base,
                                requests=requests,
                                shadow_document=shadow_document,
                                shadow_story_layouts=shadow_story_layouts,
                                shadow_request_count=shadow_request_count,
                            )
                        layout_source = (
                            shadow_story_layouts
                            if shadow_story_layouts is not None
                            else story_layouts
                        )
                        body_layout_source = shadow_body_layouts
                        document_source = shadow_document if shadow_document is not None else base
                        start_route, start_index = _resolve_position_for_named_range(
                            story_layouts=layout_source,
                            body_layouts=body_layout_source,
                            document=document_source,
                            position=anchor.start,
                        )
                        end_route, end_index = _resolve_position_for_named_range(
                            story_layouts=layout_source,
                            body_layouts=body_layout_source,
                            document=document_source,
                            position=anchor.end,
                        )
            else:
                start_route, start_index = _resolve_position_for_named_range(
                    story_layouts=layout_source,
                    body_layouts=body_layout_source,
                    document=document_source,
                    position=anchor.start,
                )
                end_route, end_index = _resolve_position_for_named_range(
                    story_layouts=layout_source,
                    body_layouts=body_layout_source,
                    document=document_source,
                    position=anchor.end,
                )
            if start_route != end_route:
                raise ValueError(
                    f"Named range {edit.name} crosses routes in an unsupported reconcile_v2 path"
                )
            requests.append(
                make_create_named_range(
                    name=edit.name,
                    start_index=start_index,
                    end_index=end_index,
                    tab_id=start_route.tab_id,
                    segment_id=start_route.segment_id,
                )
            )
    return requests


def _body_insert_anchor(edit: SemanticEdit) -> tuple[str, int, int, int | None] | None:
    if isinstance(edit, InsertListBlockEdit):
        return (
            edit.tab_id,
            edit.section_index,
            edit.block_index,
            edit.body_anchor_block_index,
        )
    if isinstance(edit, InsertTableBlockEdit):
        return (
            edit.tab_id,
            edit.section_index,
            edit.block_index,
            edit.body_anchor_block_index,
        )
    if isinstance(edit, InsertPageBreakBlockEdit):
        return (
            edit.tab_id,
            edit.section_index,
            edit.block_index,
            edit.body_anchor_block_index,
        )
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.section_index is not None
        and edit.story_id == f"{edit.tab_id}:body"
        and (
            edit.delete_block_count == 0
            or (edit.delete_block_count > 0 and not edit.inserted_paragraphs)
        )
    ):
        return (
            edit.tab_id,
            edit.section_index,
            edit.start_block_index,
            edit.body_anchor_block_index,
        )
    return None


def _body_insert_group_end(
    edits: list[SemanticEdit],
    start_index: int,
    *,
    current_document: Document,
    current_body_layouts: dict[str, BodyLayout],
) -> int:
    anchor = _body_insert_anchor(edits[start_index])
    if anchor is None:
        return start_index + 1
    if not _is_groupable_body_insert(edits[start_index]):
        return start_index + 1
    if isinstance(edits[start_index], InsertPageBreakBlockEdit):
        return start_index + 1
    if _is_empty_body_insert_anchor(
        current_document=current_document,
        current_body_layouts=current_body_layouts,
        anchor=anchor,
    ):
        end_index = start_index + 1
        while end_index < len(edits):
            next_anchor = _body_insert_anchor(edits[end_index])
            if (
                next_anchor is None
                or not _is_groupable_body_insert(edits[end_index])
                or _is_delete_then_insert_group_root(edits[end_index])
                or isinstance(edits[end_index], InsertPageBreakBlockEdit)
                or next_anchor[:2] != anchor[:2]
            ):
                break
            end_index += 1
        return end_index
    if _is_delete_then_insert_group_root(edits[start_index]):
        end_index = start_index + 1
        while end_index < len(edits) and _body_insert_anchor(edits[end_index]) == anchor:
            if (
                not _is_groupable_body_insert(edits[end_index])
                or _is_delete_then_insert_group_root(edits[end_index])
                or isinstance(edits[end_index], InsertPageBreakBlockEdit)
            ):
                break
            end_index += 1
        return end_index
    end_index = start_index + 1
    while end_index < len(edits) and _body_insert_anchor(edits[end_index]) == anchor:
        if (
            not _is_groupable_body_insert(edits[end_index])
            or isinstance(edits[end_index], InsertPageBreakBlockEdit)
        ):
            break
        end_index += 1
    return end_index


def _is_empty_body_insert_anchor(
    *,
    current_document: Document,
    current_body_layouts: dict[str, BodyLayout],
    anchor: tuple[str, int, int, int | None],
) -> bool:
    tab_id, section_index, _block_index, _raw_anchor_index = anchor
    layout = current_body_layouts.setdefault(
        tab_id,
        build_body_layout(current_document, tab_id=tab_id),
    )
    section_blocks = layout.sections[section_index].block_locations
    if not section_blocks:
        return True
    return (
        len(section_blocks) == 1
        and isinstance(section_blocks[0], ParagraphLocation)
        and section_blocks[0].text == ""
    )


def _is_groupable_body_insert(edit: SemanticEdit) -> bool:
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.section_index is not None
        and edit.story_id == f"{edit.tab_id}:body"
        and (
            edit.delete_block_count == 0
            or (edit.delete_block_count > 0 and not edit.inserted_paragraphs)
        )
    ):
        return True
    return isinstance(edit, InsertListBlockEdit | InsertTableBlockEdit | InsertPageBreakBlockEdit)


def _is_delete_then_insert_group_root(edit: SemanticEdit) -> bool:
    return (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.section_index is not None
        and edit.story_id == f"{edit.tab_id}:body"
        and edit.delete_block_count > 0
        and not edit.inserted_paragraphs
    )


def _content_edit_order_key(
    original_index: int,
    edit: SemanticEdit,
) -> tuple[object, ...]:
    non_body_anchor = _existing_non_body_story_anchor(edit)
    if non_body_anchor is not None:
        story_id, section_index, block_index = non_body_anchor
        table_cell_key = _table_cell_story_order_key(story_id)
        if table_cell_key is not None:
            return (0, *table_cell_key, section_index, -block_index, original_index)
        return (0, story_id, section_index, -block_index, original_index)
    body_anchor = _existing_body_edit_anchor(edit)
    if body_anchor is not None:
        tab_id, section_index, block_index = body_anchor
        return (1, tab_id, section_index, -block_index, original_index)
    return (2, original_index)


def _existing_non_body_story_anchor(
    edit: SemanticEdit,
) -> tuple[str, int | None, int] | None:
    if isinstance(edit, ReplaceParagraphTextEdit) and edit.story_id != f"{edit.tab_id}:body":
        return (edit.story_id, edit.section_index, edit.block_index)
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.story_id != f"{edit.tab_id}:body"
    ):
        return (edit.story_id, edit.section_index, edit.start_block_index)
    return None


def _table_cell_story_order_key(story_id: str) -> tuple[str, int, int] | None:
    if ":table:" not in story_id or ":r" not in story_id or ":c" not in story_id:
        return None
    try:
        prefix, row_part, col_part = story_id.rsplit(":", 2)
        row_index = int(row_part.removeprefix("r"))
        col_index = int(col_part.removeprefix("c"))
    except ValueError:
        return None
    return (prefix, -row_index, -col_index)


def _existing_body_edit_anchor(
    edit: SemanticEdit,
) -> tuple[str, int, int] | None:
    if (
        isinstance(edit, ReplaceParagraphTextEdit)
        and edit.story_id == f"{edit.tab_id}:body"
        and edit.section_index is not None
    ):
        return (edit.tab_id, edit.section_index, edit.block_index)
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.story_id == f"{edit.tab_id}:body"
        and edit.section_index is not None
        and edit.delete_block_count > 0
    ):
        return (edit.tab_id, edit.section_index, edit.start_block_index)
    if isinstance(
        edit,
        (
            UpdateParagraphRoleEdit,
            UpdateListItemRolesEdit,
            AppendListItemsEdit,
            ReplaceListSpecEdit,
            RelevelListItemsEdit,
            DeleteListBlockEdit,
            DeletePageBreakBlockEdit,
            DeleteTableBlockEdit,
        ),
    ):
        return (edit.tab_id, edit.section_index, edit.block_index)
    if isinstance(edit, InsertSectionEdit):
        return (edit.tab_id, edit.section_index, edit.split_after_block_index)
    return None


def _lower_body_insert_group(
    *,
    base: Document,
    prior_requests: list[dict[str, Any]],
    edits: list[SemanticEdit],
    desired: Document | None,
) -> list[dict[str, Any]]:
    anchor = _body_insert_anchor(edits[0])
    if anchor is None:
        raise ValueError("Body insert group requires a shared body anchor")
    if desired is None:
        raise ReconcileInvariantError(
            "reconcile_v2 body insert grouping requires desired document layouts"
        )
    tab_id, _section_index, _block_index, _raw_anchor_index = anchor
    delete_root = edits[0] if _is_delete_then_insert_group_root(edits[0]) else None
    insert_edits = edits[1:] if delete_root is not None else edits
    if not insert_edits:
        return []
    insertion_fragments = [_body_insert_fragment(edit) for edit in insert_edits]
    final_fragments = list(reversed(insertion_fragments))
    structural_requests: list[dict[str, Any]] = []
    shadow = MockGoogleDocsAPI(base)
    if prior_requests:
        shadow._batch_update_raw(prior_requests)
    if isinstance(delete_root, ReplaceParagraphSliceEdit):
        current_doc = shadow.get()
        current_layout = build_body_layout(current_doc, tab_id=tab_id)
        raw_start_block_index = (
            delete_root.body_anchor_block_index
            if delete_root.body_anchor_block_index is not None
            else delete_root.start_block_index
        )
        paragraphs = _body_paragraph_slice(
            current_layout,
            section_index=delete_root.section_index,
            start_block_index=raw_start_block_index,
            delete_block_count=delete_root.delete_block_count,
        )
        delete_start = paragraphs[0].text_start_index
        delete_end = paragraphs[-1].text_end_index
        if delete_end > delete_start:
            delete_request = make_delete_content_range(
                start_index=delete_start,
                end_index=delete_end,
                tab_id=tab_id,
            )
            structural_requests.append(delete_request)
            shadow._batch_update_raw([delete_request])
    current_doc = shadow.get()
    current_layout = build_body_layout(current_doc, tab_id=tab_id)
    _, prefix_newline, suffix_newline = _body_insert_site_for_group_anchor(
        document=current_doc,
        _layout=current_layout,
        tab_id=tab_id,
        section_index=anchor[1],
        block_index=anchor[2],
        raw_block_index=anchor[3],
    )
    fixed_insert_index: int | None = None
    if _body_group_anchor_targets_fixed_structural_block(
        document=current_doc,
        tab_id=tab_id,
        section_index=anchor[1],
        block_index=anchor[2],
        raw_block_index=anchor[3],
    ):
        fixed_insert_index, _, _ = _body_insert_site_for_group_anchor(
            document=current_doc,
            _layout=current_layout,
            tab_id=tab_id,
            section_index=anchor[1],
            block_index=anchor[2],
            raw_block_index=anchor[3],
        )
    for final_index, fragment in enumerate(insertion_fragments):
        if fixed_insert_index is not None:
            insert_index = fixed_insert_index
            current_prefix = False
            current_suffix = False
        else:
            current_doc = shadow.get()
            current_layout = build_body_layout(current_doc, tab_id=tab_id)
            insert_index, current_prefix, current_suffix = _body_insert_site_for_group_anchor(
                document=current_doc,
                _layout=current_layout,
                tab_id=tab_id,
                section_index=anchor[1],
                block_index=anchor[2],
                raw_block_index=None,
            )
        needs_prefix = (final_index == 0 and prefix_newline) or current_prefix
        needs_suffix = (
            final_index < len(insertion_fragments) - 1
            or suffix_newline
            or current_suffix
        )
        fragment_requests: list[dict[str, Any]] = []
        if fragment[0] == "paragraphs":
            text = "\n".join(_paragraph_text(paragraph) for paragraph in fragment[1])
            if needs_prefix:
                text = f"\n{text}"
            if needs_suffix:
                text = f"{text}\n"
            fragment_requests.append(
                make_insert_text(
                    index=insert_index,
                    tab_id=tab_id,
                    text=text,
                )
            )
        elif fragment[0] == "list":
            list_edit = fragment[1]
            text = "\n".join(_list_item_text(item) for item in list_edit.items)
            if needs_prefix:
                text = f"\n{text}"
            if needs_suffix:
                text = f"{text}\n"
            fragment_requests.append(
                make_insert_text(
                    index=insert_index,
                    tab_id=tab_id,
                    text=text,
                )
            )
        elif fragment[0] == "table":
            fragment_requests.extend(
                _lower_blocks_into_fresh_story(
                    [fragment[1]],
                    story_start_index=insert_index,
                    tab_id=tab_id,
                    segment_id=None,
                )
            )
        elif fragment[0] == "pagebreak":
            fragment_requests.append(
                make_insert_page_break(
                    index=insert_index,
                    tab_id=tab_id,
                )
            )
        else:  # pragma: no cover
            raise AssertionError(fragment[0])
        structural_requests.extend(fragment_requests)
        shadow._batch_update_raw(fragment_requests)

    shadow_layout = build_body_layout(shadow.get(), tab_id=tab_id)
    shadow_blocks = _shadow_inserted_blocks_from_layout(
        shadow_layout=shadow_layout,
        section_index=anchor[1],
        block_index=anchor[2],
        fragment_count=_body_insert_fragment_shadow_block_count(final_fragments),
    )
    paragraph_style_locations: list[tuple[ParagraphIR, tuple[int, int]]] = []
    style_ops: list[tuple[int, dict[str, Any]]] = []
    list_ops: list[tuple[int, dict[str, Any]]] = []
    shadow_index = 0

    for fragment in final_fragments:
        if fragment[0] == "paragraphs":
            for paragraph in fragment[1]:
                block, next_index = _consume_shadow_block_type(
                    shadow_blocks,
                    shadow_index,
                    ParagraphLocation,
                )
                if block is None:
                    raise ReconcileInvariantError(
                        "Grouped body insert shadow layout did not resolve a paragraph block"
                    )
                paragraph_style_locations.append(
                    (paragraph, (block.start_index, block.end_index))
                )
                style_ops.append(
                    (
                        block.start_index,
                        make_update_paragraph_role(
                            start_index=block.start_index,
                            end_index=block.end_index,
                            tab_id=tab_id,
                            role=paragraph.role,
                        ),
                    )
                )
                shadow_index = next_index
            continue

        if fragment[0] == "list":
            list_paragraphs: list[ParagraphLocation] = []
            next_index = shadow_index
            for _item in fragment[1].items:
                block, next_index = _consume_shadow_block_type(
                    shadow_blocks,
                    next_index,
                    ParagraphLocation,
                )
                if block is None:
                    break
                list_paragraphs.append(block)
            if len(list_paragraphs) != len(fragment[1].items):
                raise ReconcileInvariantError(
                    "Grouped body insert shadow layout did not resolve a list block"
                )
            list_ops.append(
                (
                    list_paragraphs[0].start_index,
                    make_create_paragraph_bullets(
                        start_index=list_paragraphs[0].start_index,
                        end_index=list_paragraphs[-1].end_index,
                        tab_id=tab_id,
                        bullet_preset=bullet_preset_for_kind(fragment[1].list_kind),
                    ),
                )
            )
            for item, paragraph in zip(fragment[1].items, list_paragraphs, strict=True):
                paragraph_style = _list_level_paragraph_style(item.level)
                if paragraph_style is None:
                    continue
                style_ops.append(
                    (
                        paragraph.start_index,
                        make_update_paragraph_style(
                            start_index=paragraph.start_index,
                            end_index=paragraph.end_index,
                            tab_id=tab_id,
                            paragraph_style=paragraph_style,
                            fields=tuple(paragraph_style.keys()),
                        ),
                    )
                )
            shadow_index = next_index
            continue

        if fragment[0] == "table":
            block, next_index = _consume_shadow_block_type(
                shadow_blocks,
                shadow_index,
                TableLocation,
            )
            if block is None:
                raise ReconcileInvariantError(
                    "Grouped body insert shadow layout did not resolve a table block"
                )
            style_ops.extend(
                (block.start_index, request)
                for request in _inserted_table_style_requests(
                    fragment[1],
                    table_start_index=block.start_index,
                    tab_id=tab_id,
                )
            )
            shadow_index = next_index
            continue
        if fragment[0] == "pagebreak":
            block, next_index = _consume_shadow_block_type(
                shadow_blocks,
                shadow_index,
                PageBreakLocation,
            )
            if block is None:
                raise ReconcileInvariantError(
                    "Grouped body insert shadow layout did not resolve a page break block"
                )
            shadow_index = next_index
            continue

    style_ops.sort(key=lambda item: item[0], reverse=True)
    list_ops.sort(key=lambda item: item[0], reverse=True)
    requests = list(structural_requests)
    requests.extend(request for _, request in list_ops)
    requests.extend(request for _, request in style_ops)
    requests.extend(
        _lower_inserted_text_styles(
            route=StoryRoute(tab_id=tab_id, segment_id=None),
            paragraph_locations=tuple(paragraph_style_locations),
        )
    )
    return requests


def _body_group_anchor_targets_fixed_structural_block(
    *,
    document: Document,
    tab_id: str,
    section_index: int,
    block_index: int,
    raw_block_index: int | None,
) -> bool:
    raw_sections = _raw_body_sections(document, tab_id=tab_id)
    raw_blocks = raw_sections[section_index]
    target_raw_index = raw_block_index
    if target_raw_index is None:
        target_raw_index = _canonical_to_raw_body_block_index(raw_blocks, block_index)
    if target_raw_index >= len(raw_blocks):
        return False
    return raw_blocks[target_raw_index]["kind"] == "pagebreak"


def _body_insert_fragment_shadow_block_count(
    fragments: list[tuple[str, tuple[ParagraphIR, ...] | InsertListBlockEdit | TableIR | None]],
) -> int:
    count = 0
    for kind, payload in fragments:
        if kind == "paragraphs":
            count += len(payload)
        elif kind == "list":
            count += 1
        else:
            count += 1
    return count


def _shadow_inserted_blocks_from_layout(
    *,
    shadow_layout: BodyLayout,
    section_index: int,
    block_index: int,
    fragment_count: int,
) -> tuple[ParagraphLocation | ListLocation | TableLocation | PageBreakLocation, ...]:
    section_blocks = shadow_layout.sections[section_index].block_locations
    inserted_blocks = tuple(section_blocks[block_index:])
    if len(inserted_blocks) < fragment_count:
        raise ReconcileInvariantError(
            "Grouped body insert shadow layout did not produce the expected block count"
        )
    return inserted_blocks


def _consume_shadow_block_type(
    blocks: tuple[ParagraphLocation | ListLocation | TableLocation | PageBreakLocation, ...],
    start_index: int,
    expected_type: type[object],
) -> tuple[object | None, int]:
    for index in range(start_index, len(blocks)):
        block = blocks[index]
        if isinstance(block, expected_type):
            return block, index + 1
    return None, start_index


def _body_insert_fragment(
    edit: SemanticEdit,
) -> tuple[str, tuple[ParagraphIR, ...] | InsertListBlockEdit | TableIR | None]:
    if isinstance(edit, ReplaceParagraphSliceEdit):
        return (
            "paragraphs",
            tuple(fragment.paragraph for fragment in edit.inserted_paragraphs),
        )
    if isinstance(edit, InsertListBlockEdit):
        return ("list", edit)
    if isinstance(edit, InsertTableBlockEdit):
        return ("table", edit.table)
    if isinstance(edit, InsertPageBreakBlockEdit):
        return ("pagebreak", None)
    raise TypeError(f"Unsupported body insert edit in grouped lowering: {type(edit).__name__}")


def _story_paragraph_delete_end(
    *,
    story_id: str,
    paragraphs: tuple[StoryParagraphLocation, ...],
) -> int:
    delete_end = paragraphs[-1].text_end_index
    if ":table:" not in story_id:
        return delete_end
    # Table cells must retain their terminal newline sentinel. When a slice
    # spans to the logical end of the cell story, stop before the last raw
    # paragraph terminator instead of deleting through it.
    return min(delete_end, max(paragraphs[-1].start_index, paragraphs[-1].end_index - 1))


def _body_paragraph_slice(
    layout: BodyLayout,
    *,
    section_index: int,
    start_block_index: int,
    delete_block_count: int,
) -> tuple[ParagraphLocation, ...]:
    blocks = layout.sections[section_index].block_locations[
        start_block_index : start_block_index + delete_block_count
    ]
    paragraphs = tuple(
        block for block in blocks if isinstance(block, ParagraphLocation)
    )
    if len(paragraphs) != delete_block_count:
        raise ValueError(
            f"Could not resolve body paragraph slice section={section_index} "
            f"start={start_block_index} count={delete_block_count}"
        )
    return paragraphs


def _paragraph_at(
    layout: BodyLayout,
    section_index: int,
    block_index: int,
) -> ParagraphLocation:
    block = layout.sections[section_index].block_locations[block_index]
    if not isinstance(block, ParagraphLocation):
        raise TypeError(f"Expected paragraph at section {section_index} block {block_index}")
    return block


def _story_paragraph_at(
    story_layout: Any,
    *,
    section_index: int | None,
    block_index: int,
) -> Any:
    paragraph = next(
        (
            paragraph
            for paragraph in story_layout.paragraphs
            if paragraph.section_index == section_index
            and paragraph.block_index == block_index
            and paragraph.node_path == ()
        ),
        None,
    )
    if paragraph is None:
        raise TypeError(
            f"Expected story paragraph at section {section_index} block {block_index}"
        )
    return paragraph


def _list_at(layout: BodyLayout, section_index: int, block_index: int) -> ListLocation:
    block = layout.sections[section_index].block_locations[block_index]
    if not isinstance(block, ListLocation):
        raise TypeError(f"Expected list at section {section_index} block {block_index}")
    return block


def _table_at(layout: BodyLayout, section_index: int, block_index: int) -> TableLocation:
    block = layout.sections[section_index].block_locations[block_index]
    if not isinstance(block, TableLocation):
        raise TypeError(f"Expected table at section {section_index} block {block_index}")
    return block


def _page_break_at(
    layout: BodyLayout,
    section_index: int,
    block_index: int,
) -> PageBreakLocation:
    block = layout.sections[section_index].block_locations[block_index]
    if not isinstance(block, PageBreakLocation):
        raise TypeError(f"Expected page break at section {section_index} block {block_index}")
    return block


def _body_insert_site_for_edit(
    base: Document,
    _layout: BodyLayout,
    edit: SemanticEdit,
) -> tuple[int, bool, bool]:
    anchor = _body_insert_anchor(edit)
    if anchor is None:
        raise TypeError(f"Unsupported body insert edit: {type(edit).__name__}")
    tab_id, section_index, block_index, raw_block_index = anchor
    if raw_block_index is None:
        return _canonical_body_block_insertion_site(
            base,
            tab_id=tab_id,
            section_index=section_index,
            block_index=block_index,
        )
    return _raw_body_block_insertion_site(
        base,
        tab_id=tab_id,
        section_index=section_index,
        raw_block_index=raw_block_index,
    )


def _body_insert_site_for_group_anchor(
    *,
    document: Document,
    _layout: BodyLayout,
    tab_id: str,
    section_index: int,
    block_index: int,
    raw_block_index: int | None,
) -> tuple[int, bool, bool]:
    if raw_block_index is not None:
        sections = _raw_body_sections(document, tab_id=tab_id)
        raw_blocks = sections[section_index]
        if raw_block_index < len(raw_blocks):
            raw_kind = raw_blocks[raw_block_index]["kind"]
            if raw_kind in {"toc", "opaque"}:
                return _raw_body_block_insertion_site(
                    document,
                    tab_id=tab_id,
                    section_index=section_index,
                    raw_block_index=raw_block_index,
                )
    return _canonical_body_block_insertion_site(
        document,
        tab_id=tab_id,
        section_index=section_index,
        block_index=block_index,
    )


def _body_block_insertion_site(
    layout: BodyLayout,
    *,
    section_index: int,
    block_index: int,
) -> tuple[int, bool, bool]:
    blocks = layout.sections[section_index].block_locations
    if block_index < len(blocks):
        target = blocks[block_index]
        if isinstance(target, ParagraphLocation):
            if len(blocks) == 1 and target.text == "":
                return target.text_start_index, False, False
            return target.text_start_index, False, True
        if block_index > 0 and isinstance(blocks[block_index - 1], ParagraphLocation):
            previous = blocks[block_index - 1]
            if previous.text == "":
                return previous.text_start_index, False, False
            return previous.text_end_index, True, False
        if target.start_index > 1:
            return target.start_index - 1, False, False
        return target.start_index, False, True
    if not blocks:
        return 1, False, False
    previous = blocks[block_index - 1]
    if isinstance(previous, ParagraphLocation):
        return previous.text_end_index, True, False
    if isinstance(previous, ListLocation):
        return max(previous.start_index, previous.end_index - 1), False, False
    return previous.end_index, False, False


def _canonical_body_block_insertion_site(
    document: Document,
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
) -> tuple[int, bool, bool]:
    raw_sections = _raw_body_sections(document, tab_id=tab_id)
    raw_blocks = raw_sections[section_index]
    raw_block_index = _canonical_to_raw_body_block_index(raw_blocks, block_index)
    return _raw_body_block_insertion_site(
        document,
        tab_id=tab_id,
        section_index=section_index,
        raw_block_index=raw_block_index,
    )


def _raw_body_block_insertion_site(
    document: Document,
    *,
    tab_id: str,
    section_index: int,
    raw_block_index: int,
) -> tuple[int, bool, bool]:
    sections = _raw_body_sections(document, tab_id=tab_id)
    blocks = sections[section_index]
    raw_block_index = min(raw_block_index, len(blocks))
    if raw_block_index < len(blocks):
        target = blocks[raw_block_index]
        if target["kind"] == "paragraph":
            if len(blocks) == 1 and target["text"] == "":
                return int(target["text_start"]), False, False
            return int(target["text_start"]), False, True
        if raw_block_index > 0 and blocks[raw_block_index - 1]["kind"] == "paragraph":
            previous = blocks[raw_block_index - 1]
            if previous["text"] == "":
                return int(previous["text_start"]), False, False
            return int(previous["text_end"]), True, False
        target_start = int(target["start"])
        if target_start > 1:
            return target_start - 1, False, False
        return target_start, False, True
    if not blocks:
        return 1, False, False
    previous = blocks[raw_block_index - 1]
    if previous["kind"] == "paragraph":
        return int(previous["text_end"]), True, False
    if previous["kind"] == "list":
        return max(int(previous["start"]), int(previous["end"]) - 1), False, False
    return int(previous["end"]), False, False


def _raw_body_sections(document: Document, *, tab_id: str) -> list[list[dict[str, object]]]:
    raw_tab = next(
        (
            tab
            for tab in document.model_dump(by_alias=True, exclude_none=True).get("tabs", [])
            if tab.get("tabProperties", {}).get("tabId") == tab_id
        ),
        None,
    )
    if raw_tab is None:
        raise ValueError(f"Unknown tab id {tab_id}")
    sections: list[list[dict[str, object]]] = [[]]
    for element in raw_tab.get("documentTab", {}).get("body", {}).get("content", []):
        if "sectionBreak" in element:
            if sections[-1]:
                sections.append([])
            continue
        start_index = int(element.get("startIndex", 0))
        end_index = int(element.get("endIndex", start_index))
        if "paragraph" in element:
            if any(
                child.get("pageBreak") is not None
                for child in element["paragraph"].get("elements", [])
            ):
                sections[-1].append(
                    {"kind": "pagebreak", "start": start_index, "end": end_index}
                )
                continue
            text = "".join(
                run.get("textRun", {}).get("content", "")
                for run in element["paragraph"].get("elements", [])
            )
            sections[-1].append(
                {
                    "kind": "paragraph",
                    "start": start_index,
                    "end": end_index,
                    "text_start": start_index,
                    "text_end": end_index - 1,
                    "text": text.removesuffix("\n"),
                }
            )
        elif "table" in element:
            sections[-1].append({"kind": "table", "start": start_index, "end": end_index})
        elif "tableOfContents" in element:
            sections[-1].append({"kind": "toc", "start": start_index, "end": end_index})
        else:
            sections[-1].append({"kind": "opaque", "start": start_index, "end": end_index})
    return sections


def _canonical_to_raw_body_block_index(
    raw_blocks: list[dict[str, object]],
    block_index: int,
) -> int:
    keep_mask = _raw_transport_block_keep_mask(raw_blocks)
    kept_indices = [index for index, keep in enumerate(keep_mask) if keep]
    if not kept_indices:
        return 0
    if block_index < len(kept_indices):
        return kept_indices[block_index]
    return len(raw_blocks)


def _raw_transport_block_keep_mask(
    raw_blocks: list[dict[str, object]],
) -> list[bool]:
    keep_mask = [True] * len(raw_blocks)
    for index, block in enumerate(raw_blocks):
        if not _is_raw_transport_carrier_paragraph(block):
            continue
        prev_is_structural = index > 0 and _is_raw_transport_carrier_anchor(raw_blocks[index - 1])
        next_is_structural = (
            index + 1 < len(raw_blocks) and _is_raw_transport_carrier_anchor(raw_blocks[index + 1])
        )
        if prev_is_structural or next_is_structural:
            keep_mask[index] = False
    run_start = 0
    while run_start < len(raw_blocks):
        if not _is_raw_transport_carrier_paragraph(raw_blocks[run_start]):
            run_start += 1
            continue
        run_end = run_start
        while run_end + 1 < len(raw_blocks) and _is_raw_transport_carrier_paragraph(
            raw_blocks[run_end + 1]
        ):
            run_end += 1
        prev_is_structural = run_start > 0 and _is_raw_transport_carrier_anchor(
            raw_blocks[run_start - 1]
        )
        next_is_structural = run_end + 1 < len(raw_blocks) and _is_raw_transport_carrier_anchor(
            raw_blocks[run_end + 1]
        )
        if prev_is_structural or next_is_structural:
            for index in range(run_start, run_end + 1):
                keep_mask[index] = False
        run_start = run_end + 1
    saw_noncarrier = any(
        not _is_raw_transport_carrier_paragraph(block) for block in raw_blocks
    )
    if saw_noncarrier:
        for index, block in enumerate(raw_blocks):
            if not keep_mask[index] or not _is_raw_transport_carrier_paragraph(block):
                break
            keep_mask[index] = False
    for index in range(len(raw_blocks) - 1, -1, -1):
        if not keep_mask[index] or not _is_raw_transport_carrier_paragraph(raw_blocks[index]):
            break
        keep_mask[index] = False
    return keep_mask


def _is_raw_transport_carrier_paragraph(block: dict[str, object]) -> bool:
    return block["kind"] == "paragraph" and block.get("text") == ""


def _is_raw_transport_carrier_anchor(block: dict[str, object]) -> bool:
    return block["kind"] in {"table", "pagebreak", "page_break"}


def _raw_body_block_range(
    document: Document,
    *,
    tab_id: str,
    section_index: int,
    raw_block_index: int,
    expected_kind: str,
) -> dict[str, int]:
    sections = _raw_body_sections(document, tab_id=tab_id)
    block = sections[section_index][raw_block_index]
    if block["kind"] != expected_kind:
        raise TypeError(
            f"Expected raw body {expected_kind} at section {section_index} "
            f"block {raw_block_index}, found {block['kind']}"
        )
    return {"start": int(block["start"]), "end": int(block["end"])}


def _edited_story_ids(edits: list[SemanticEdit]) -> set[str]:
    story_ids = {
        edit.story_id for edit in edits if isinstance(edit, ReplaceParagraphSliceEdit)
    }
    for edit in edits:
        if isinstance(edit, InsertTableBlockEdit):
            story_ids.update(_table_story_ids(edit.table))
    return story_ids


def _ensure_shadow_state(
    *,
    base: Document,
    requests: list[dict[str, Any]],
    shadow_document: Document | None,
    shadow_story_layouts: dict[str, object] | None,
    shadow_request_count: int,
) -> tuple[Document | None, dict[str, object] | None, dict[str, BodyLayout], int]:
    if not requests:
        return None, None, {}, -1
    if (
        shadow_document is not None
        and shadow_story_layouts is not None
        and shadow_request_count == len(requests)
    ):
        return shadow_document, shadow_story_layouts, {}, shadow_request_count
    shadow = MockGoogleDocsAPI(base)
    shadow._batch_update_raw(requests)
    current_document = shadow.get()
    current_story_layouts = build_story_layouts(current_document)
    return current_document, current_story_layouts, {}, len(requests)


def _named_range_fits_current_document(
    *,
    base: Document,
    requests: list[dict[str, Any]],
    route: StoryRoute,
    start_index: int,
    end_index: int,
    shadow_document: Document | None,
) -> bool:
    if start_index >= end_index:
        return False
    if shadow_document is None:
        if not requests:
            current_document = base
        else:
            try:
                shadow = MockGoogleDocsAPI(base)
                shadow._batch_update_raw(requests)
                current_document = shadow.get()
            except ValidationError:
                return True
    else:
        current_document = shadow_document
    segment_end = _story_route_end_index(current_document, route)
    return end_index <= segment_end


def _story_route_end_index(document: Document, route: StoryRoute) -> int:
    raw = document.model_dump(by_alias=True, exclude_none=True)
    raw_tab = next(
        (
            tab
            for tab in raw.get("tabs", [])
            if tab.get("tabProperties", {}).get("tabId") == route.tab_id
        ),
        None,
    )
    if raw_tab is None:
        raise ValueError(f"Unknown tab id {route.tab_id!r}")
    document_tab = raw_tab.get("documentTab", {})
    if route.segment_id is None:
        content = document_tab.get("body", {}).get("content", [])
    else:
        content = None
        for container_name in ("headers", "footers", "footnotes"):
            container = document_tab.get(container_name, {})
            if route.segment_id in container:
                content = container[route.segment_id].get("content", [])
                break
        if content is None:
            raise ValueError(f"Unknown segment id {route.segment_id!r}")
    if not content:
        return 1 if route.segment_id is None else 0
    return int(content[-1].get("endIndex", 0))


def _resolve_special_table_named_range(
    *,
    document: Document | None,
    body_layouts: dict[str, BodyLayout],
    anchor: Any,
    name: str,
) -> tuple[StoryRoute, int, int] | None:
    if document is None or not name.startswith("extradoc:"):
        return None
    start = anchor.start.path
    end = anchor.end.path
    if (
        not anchor.start.story_id.endswith(":body")
        or anchor.start.story_id != anchor.end.story_id
        or start.section_index is None
        or start.section_index != end.section_index
        or start.block_index is None
        or end.block_index is None
        or start.node_path
        or end.node_path
        or start.inline_index is not None
        or end.inline_index is not None
        or start.text_offset_utf16 is not None
        or end.text_offset_utf16 is not None
        or start.edge.value not in {"BEFORE", "AFTER"}
        or end.edge.value != "BEFORE"
    ):
        return None
    table_block_index = (
        start.block_index if start.edge.value == "BEFORE" else start.block_index + 1
    )
    if end.block_index != table_block_index + 1:
        return None
    tab_id = anchor.start.story_id.removesuffix(":body")
    layout = body_layouts.setdefault(tab_id, build_body_layout(document, tab_id=tab_id))
    blocks = layout.sections[start.section_index].block_locations
    if table_block_index >= len(blocks):
        return None
    block = blocks[table_block_index]
    if not isinstance(block, TableLocation):
        return None
    return StoryRoute(tab_id=tab_id), block.start_index, block.end_index


def _resolve_position_for_named_range(
    *,
    story_layouts: dict[str, Any],
    body_layouts: dict[str, BodyLayout],
    document: Document | None,
    position: Any,
) -> tuple[StoryRoute, int]:
    if (
        document is not None
        and not position.path.node_path
        and position.path.inline_index is None
        and position.path.text_offset_utf16 is None
        and position.story_id.endswith(":body")
        and position.path.section_index is not None
    ):
        tab_id = position.story_id.removesuffix(":body")
        layout = body_layouts.setdefault(tab_id, build_body_layout(document, tab_id=tab_id))
        return StoryRoute(tab_id=tab_id), _resolve_body_block_boundary_index(
            layout,
            section_index=position.path.section_index,
            block_index=position.path.block_index,
            edge=position.path.edge,
        )
    try:
        return resolve_position_to_index(story_layouts, position)
    except ValueError:
        if (
            document is None
            or position.path.node_path
            or position.path.inline_index is not None
            or position.path.text_offset_utf16 is not None
            or not position.story_id.endswith(":body")
            or position.path.section_index is None
        ):
            raise
        tab_id = position.story_id.removesuffix(":body")
        layout = body_layouts.setdefault(tab_id, build_body_layout(document, tab_id=tab_id))
        return StoryRoute(tab_id=tab_id), _resolve_body_block_boundary_index(
            layout,
            section_index=position.path.section_index,
            block_index=position.path.block_index,
            edge=position.path.edge,
        )


def _resolve_body_block_boundary_index(
    layout: BodyLayout,
    *,
    section_index: int,
    block_index: int,
    edge: Any,
) -> int:
    blocks = layout.sections[section_index].block_locations
    if edge.value == "BEFORE":
        if block_index < len(blocks):
            block = blocks[block_index]
            return block.start_index
        if blocks:
            return blocks[-1].end_index
        return 1
    if edge.value == "AFTER":
        if block_index < len(blocks):
            block = blocks[block_index]
            return block.end_index
        if blocks:
            return blocks[-1].end_index
        return 1
    raise ValueError("Unsupported body block boundary position without text offset")


def _table_story_ids(table: TableIR) -> set[str]:
    story_ids: set[str] = set()
    for row in table.rows:
        for cell in row.cells:
            story_ids.add(cell.content.id)
            for block in cell.content.blocks:
                if isinstance(block, TableIR):
                    story_ids.update(_table_story_ids(block))
    return story_ids


def _inserted_paragraph_locations(
    *,
    start_index: int,
    paragraphs: tuple[ParagraphIR, ...],
    prefix_newline: bool,
) -> tuple[tuple[ParagraphIR, tuple[int, int]], ...]:
    cursor = start_index + (1 if prefix_newline else 0)
    locations: list[tuple[ParagraphIR, tuple[int, int]]] = []
    for paragraph in paragraphs:
        text_end = cursor + utf16_len(_paragraph_text(paragraph))
        paragraph_end = text_end + 1
        locations.append((paragraph, (cursor, paragraph_end)))
        cursor = paragraph_end
    return tuple(locations)


def _inserted_list_range(
    *,
    start_index: int,
    items: tuple[Any, ...],
    prefix_newline: bool,
) -> tuple[int, int]:
    cursor = start_index + (1 if prefix_newline else 0)
    range_start = cursor
    range_end = cursor
    for item in items:
        item_text = _list_item_text(item)
        range_end = cursor + utf16_len(item_text) + 1
        cursor = range_end
    return range_start, range_end


def _inserted_list_level_requests(
    *,
    tab_id: str,
    start_index: int,
    items: tuple[Any, ...],
    prefix_newline: bool,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    cursor = start_index + (1 if prefix_newline else 0)
    for item in items:
        item_text = _list_item_text(item)
        paragraph_end = cursor + utf16_len(item_text) + 1
        paragraph_style = _list_level_paragraph_style(item.level)
        if paragraph_style is not None:
            requests.append(
                make_update_paragraph_style(
                    start_index=cursor,
                    end_index=paragraph_end,
                    tab_id=tab_id,
                    paragraph_style=paragraph_style,
                    fields=tuple(paragraph_style.keys()),
                )
            )
        cursor = paragraph_end
    return requests


def _list_item_text(item: Any) -> str:
    return item.text


def _list_level_paragraph_style(level: int) -> dict[str, Any] | None:
    style: dict[str, Any] = {"namedStyleType": "NORMAL_TEXT"}
    if level > 0:
        style.update(
            {
                "indentFirstLine": {"magnitude": 18 + level * 36, "unit": "PT"},
                "indentStart": {"magnitude": 36 + level * 36, "unit": "PT"},
            }
        )
    return style


def _lower_inserted_text_styles(
    *,
    route: Any,
    paragraph_locations: tuple[tuple[ParagraphIR, tuple[int, int]], ...],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    reset_unstyled = getattr(route, "segment_id", None) is None
    for paragraph, (paragraph_start, _paragraph_end) in paragraph_locations:
        cursor = paragraph_start
        style_ranges: list[tuple[int, int, dict[str, Any], tuple[str, ...]]] = []
        pending_range: tuple[int, int, dict[str, Any], tuple[str, ...]] | None = None
        for inline in paragraph.inlines:
            if not isinstance(inline, TextSpanIR):
                if pending_range is not None:
                    style_ranges.append(pending_range)
                    pending_range = None
                continue
            run_len = utf16_len(inline.text)
            run_start = cursor
            run_end = cursor + run_len
            cursor = run_end
            style_dict, fields = _text_style_delta(
                inline.explicit_text_style,
                reset_unstyled=reset_unstyled and paragraph.role == "NORMAL_TEXT",
            )
            if not fields:
                if pending_range is not None:
                    style_ranges.append(pending_range)
                    pending_range = None
                continue
            if (
                pending_range is not None
                and pending_range[1] == run_start
                and pending_range[2] == style_dict
                and pending_range[3] == fields
            ):
                pending_range = (pending_range[0], run_end, style_dict, fields)
            else:
                if pending_range is not None:
                    style_ranges.append(pending_range)
                pending_range = (run_start, run_end, style_dict, fields)
        if pending_range is not None:
            style_ranges.append(pending_range)
        for start_index, end_index, style_dict, fields in reversed(style_ranges):
            requests.append(
                make_update_text_style(
                    start_index=start_index,
                    end_index=end_index,
                    tab_id=route.tab_id,
                    segment_id=route.segment_id,
                    text_style=style_dict,
                    fields=fields,
                )
            )
    return requests


def _lower_paragraph_text_replace_preserving_inline_anchors(
    *,
    route: StoryRoute,
    paragraph: ParagraphLocation | StoryParagraphLocation,
    desired_paragraph: ParagraphIR,
) -> list[dict[str, Any]]:
    anchor_slots = tuple(slot for slot in paragraph.inline_slots if slot.kind != "text")
    desired_buckets = _desired_text_buckets(desired_paragraph)
    if len(desired_buckets) != len(anchor_slots) + 1:
        raise UnsupportedReconcileV2Error(
            "reconcile_v2 could not align inline anchors while replacing paragraph text"
        )
    if (
        len(anchor_slots) == 1
        and paragraph.inline_slots
        and paragraph.inline_slots[0].kind == "text"
    ):
        specialized = _lower_single_anchor_paragraph_text_replace(
            route=route,
            paragraph=paragraph,
            anchor_slot=anchor_slots[0],
            desired_buckets=desired_buckets,
            paragraph_role=desired_paragraph.role,
        )
        if specialized is not None:
            return specialized

    requests: list[dict[str, Any]] = []
    for slot in reversed(paragraph.inline_slots):
        if slot.kind != "text" or slot.end_index <= slot.start_index:
            continue
        requests.append(
            make_delete_content_range(
                start_index=slot.start_index,
                end_index=slot.end_index,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
            )
        )

    if paragraph.inline_slots:
        leading_anchor = paragraph.inline_slots[0].start_index
    else:
        leading_anchor = paragraph.text_start_index
    bucket_anchor_indexes = [leading_anchor, *(slot.end_index for slot in anchor_slots)]

    style_requests: list[dict[str, Any]] = []
    for anchor_index, bucket in reversed(
        list(zip(bucket_anchor_indexes, desired_buckets, strict=True))
    ):
        bucket_text = "".join(span.text for span in bucket)
        if not bucket_text:
            continue
        requests.append(
            make_insert_text_in_story(
                index=anchor_index,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
                text=bucket_text,
            )
        )
        style_requests.extend(
            _lower_inserted_text_bucket_styles(
                route=route,
                start_index=anchor_index,
                bucket=bucket,
                paragraph_role=desired_paragraph.role,
            )
        )
    requests.extend(style_requests)
    return requests


def _lower_single_anchor_paragraph_text_replace(
    *,
    route: StoryRoute,
    paragraph: ParagraphLocation | StoryParagraphLocation,
    anchor_slot: InlineSlotLocation,
    desired_buckets: tuple[tuple[TextSpanIR, ...], ...],
    paragraph_role: str,
) -> list[dict[str, Any]] | None:
    pre_anchor_text_slots = [
        slot
        for slot in paragraph.inline_slots
        if slot.kind == "text" and slot.end_index <= anchor_slot.start_index
    ]
    if not pre_anchor_text_slots:
        return None
    leading_slot = pre_anchor_text_slots[0]
    trailing_text_slots = [
        slot
        for slot in paragraph.inline_slots
        if slot.kind == "text" and slot.start_index >= anchor_slot.end_index
    ]

    requests: list[dict[str, Any]] = []
    anchor_end = anchor_slot.end_index
    for slot in reversed(trailing_text_slots):
        if slot.end_index <= slot.start_index:
            continue
        requests.append(
            make_delete_content_range(
                start_index=slot.start_index,
                end_index=slot.end_index,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
            )
        )
    deleted_before_anchor = 0
    for slot in reversed(pre_anchor_text_slots[1:]):
        if slot.end_index <= slot.start_index:
            continue
        requests.append(
            make_delete_content_range(
                start_index=slot.start_index,
                end_index=slot.end_index,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
            )
        )
        deleted_before_anchor += slot.end_index - slot.start_index
    anchor_end -= deleted_before_anchor

    trailing_bucket = desired_buckets[1]
    trailing_text = "".join(span.text for span in trailing_bucket)
    if trailing_text:
        requests.append(
            make_insert_text_in_story(
                index=anchor_end,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
                text=trailing_text,
            )
        )
        requests.extend(
            _lower_inserted_text_bucket_styles(
                route=route,
                start_index=anchor_end,
                bucket=trailing_bucket,
                paragraph_role=paragraph_role,
            )
        )

    leading_bucket = desired_buckets[0]
    leading_text = "".join(span.text for span in leading_bucket)
    if leading_text:
        requests.append(
            make_insert_text_in_story(
                index=leading_slot.start_index,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
                text=leading_text,
            )
        )
        requests.extend(
            _lower_inserted_text_bucket_styles(
                route=route,
                start_index=leading_slot.start_index,
                bucket=leading_bucket,
                paragraph_role=paragraph_role,
            )
        )
    if leading_slot.end_index > leading_slot.start_index:
        delete_start = leading_slot.start_index + utf16_len(leading_text)
        delete_end = delete_start + (leading_slot.end_index - leading_slot.start_index)
        requests.append(
            make_delete_content_range(
                start_index=delete_start,
                end_index=delete_end,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
            )
        )
    return requests


def _desired_text_buckets(desired_paragraph: ParagraphIR) -> tuple[tuple[TextSpanIR, ...], ...]:
    buckets: list[list[TextSpanIR]] = [[]]
    for inline in desired_paragraph.inlines:
        if isinstance(inline, TextSpanIR):
            buckets[-1].append(inline)
            continue
        buckets.append([])
    return tuple(tuple(bucket) for bucket in buckets)


def _lower_inserted_text_bucket_styles(
    *,
    route: StoryRoute,
    start_index: int,
    bucket: tuple[TextSpanIR, ...],
    paragraph_role: str | None = None,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    reset_unstyled = route.segment_id is None and paragraph_role == "NORMAL_TEXT"
    style_ranges: list[tuple[int, int, dict[str, Any], tuple[str, ...]]] = []
    pending_range: tuple[int, int, dict[str, Any], tuple[str, ...]] | None = None
    cursor = start_index
    for inline in bucket:
        run_len = utf16_len(inline.text)
        run_start = cursor
        run_end = cursor + run_len
        cursor = run_end
        style_dict, fields = _text_style_delta(
            inline.explicit_text_style,
            reset_unstyled=reset_unstyled,
        )
        if not fields:
            if pending_range is not None:
                style_ranges.append(pending_range)
                pending_range = None
            continue
        if (
            pending_range is not None
            and pending_range[1] == run_start
            and pending_range[2] == style_dict
            and pending_range[3] == fields
        ):
            pending_range = (pending_range[0], run_end, style_dict, fields)
        else:
            if pending_range is not None:
                style_ranges.append(pending_range)
            pending_range = (run_start, run_end, style_dict, fields)
    if pending_range is not None:
        style_ranges.append(pending_range)
    for range_start, range_end, style_dict, fields in reversed(style_ranges):
        requests.append(
            make_update_text_style(
                start_index=range_start,
                end_index=range_end,
                tab_id=route.tab_id,
                segment_id=route.segment_id,
                text_style=style_dict,
                fields=fields,
            )
        )
    return requests


_NORMAL_TEXT_RESET_FIELDS = (
    "backgroundColor",
    "baselineOffset",
    "bold",
    "fontSize",
    "foregroundColor",
    "italic",
    "link",
    "smallCaps",
    "strikethrough",
    "underline",
    "weightedFontFamily",
)


def _text_style_delta(
    style: dict[str, Any],
    *,
    reset_unstyled: bool = False,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    fields = tuple(sorted(key for key, value in style.items() if value is not None))
    if not fields and reset_unstyled:
        return {}, _NORMAL_TEXT_RESET_FIELDS
    return {key: style[key] for key in fields}, fields


def _paragraph_text(paragraph: ParagraphIR) -> str:
    return "".join(
        inline.text for inline in paragraph.inlines if isinstance(inline, TextSpanIR)
    )


def _lower_blocks_into_fresh_story(
    blocks: list[Any],
    *,
    story_start_index: int,
    tab_id: Any,
    segment_id: Any,
) -> list[dict[str, Any]]:
    if not blocks:
        return []
    requests: list[dict[str, Any]] = []
    for fragment in reversed(_fresh_story_fragments(blocks)):
        if all(isinstance(block, ParagraphIR) for block in fragment):
            requests.extend(
                _lower_paragraph_run_into_fresh_story(
                    tuple(fragment),
                    story_start_index=story_start_index,
                    tab_id=tab_id,
                    segment_id=segment_id,
                )
            )
            continue
        if len(fragment) == 1 and isinstance(fragment[0], TableIR):
            requests.extend(
                _lower_table_into_fresh_story(
                    fragment[0],
                    story_start_index=story_start_index,
                    tab_id=tab_id,
                    segment_id=segment_id,
                )
            )
            continue
        raise UnsupportedReconcileV2Error(
            "reconcile_v2 currently supports fresh-story insertion only for "
            "paragraph runs and table blocks"
        )
    return requests


def _fresh_story_fragments(blocks: list[Any]) -> list[list[Any]]:
    fragments: list[list[Any]] = []
    paragraph_run: list[Any] = []
    for block in blocks:
        if isinstance(block, ParagraphIR):
            paragraph_run.append(block)
            continue
        if paragraph_run:
            fragments.append(paragraph_run)
            paragraph_run = []
        if isinstance(block, TableIR):
            fragments.append([block])
            continue
        raise UnsupportedReconcileV2Error(
            "reconcile_v2 currently supports fresh-story insertion only for "
            "paragraphs and tables"
        )
    if paragraph_run:
        fragments.append(paragraph_run)
    return fragments


def _lower_paragraph_run_into_fresh_story(
    paragraphs: tuple[ParagraphIR, ...],
    *,
    story_start_index: int,
    tab_id: Any,
    segment_id: Any,
) -> list[dict[str, Any]]:
    inserted_text = "\n".join(_paragraph_text(block) for block in paragraphs)
    if not inserted_text:
        return []
    requests: list[dict[str, Any]] = [
        make_insert_text_in_story(
            index=story_start_index,
            tab_id=tab_id,
            segment_id=segment_id,
            text=inserted_text,
        )
    ]
    paragraph_locations = _inserted_paragraph_locations(
        start_index=story_start_index,
        paragraphs=paragraphs,
        prefix_newline=False,
    )
    for paragraph, (paragraph_start, paragraph_end) in paragraph_locations:
        if paragraph.role != "NORMAL_TEXT":
            requests.append(
                make_update_paragraph_role(
                    start_index=paragraph_start,
                    end_index=paragraph_end,
                    tab_id=tab_id,
                    role=paragraph.role,
                )
            )
    requests.extend(
        _lower_inserted_text_styles(
            route=type("Route", (), {"tab_id": tab_id, "segment_id": segment_id})(),
            paragraph_locations=paragraph_locations,
        )
    )
    return requests


def _lower_table_into_fresh_story(
    table: TableIR,
    *,
    story_start_index: int,
    tab_id: Any,
    segment_id: Any,
) -> list[dict[str, Any]]:
    row_count = len(table.rows)
    column_count = max((len(row.cells) for row in table.rows), default=0)
    if row_count == 0 or column_count == 0:
        return []
    if any(len(row.cells) != column_count for row in table.rows):
        raise UnsupportedReconcileV2Error(
            "reconcile_v2 currently requires rectangular tables for mixed body insertion"
        )
    if table.pinned_header_rows or table.merge_regions:
        raise UnsupportedReconcileV2Error(
            "reconcile_v2 currently supports only plain unmerged table insertion "
            "for mixed body edits"
        )
    requests: list[dict[str, Any]] = [
        make_insert_table(
            rows=row_count,
            columns=column_count,
            tab_id=tab_id,
            segment_id=segment_id,
            index=story_start_index,
        )
    ]
    for row_index in range(row_count - 1, -1, -1):
        row = table.rows[row_index]
        for column_index in range(column_count - 1, -1, -1):
            cell = row.cells[column_index]
            if cell.row_span != 1 or cell.column_span != 1 or cell.merge_head is not None:
                raise UnsupportedReconcileV2Error(
                    "reconcile_v2 currently supports only unmerged-cell table insertion"
                )
            cell_start = story_start_index + 4 + row_index * (1 + 2 * column_count) + 2 * column_index
            requests.extend(
                _lower_blocks_into_fresh_story(
                    cell.content.blocks,
                    story_start_index=cell_start,
                    tab_id=tab_id,
                    segment_id=segment_id,
                )
            )
    return requests


def _table_cell_text_start(story_layouts: dict[str, Any], story_id: str) -> int:
    story = story_layouts.get(story_id)
    if story is None or not story.paragraphs:
        raise ReconcileInvariantError(
            f"Could not resolve inserted table-cell anchor from story {story_id}"
        )
    return story.paragraphs[0].text_start_index


def _inserted_table_style_requests(
    table: TableIR,
    *,
    table_start_index: int,
    tab_id: str,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    if table.pinned_header_rows:
        requests.append(
            make_pin_table_header_rows(
                table_start_index=table_start_index,
                pinned_header_rows_count=table.pinned_header_rows,
                tab_id=tab_id,
            )
        )
    for row_index, row in enumerate(table.rows):
        row_fields = _style_fields(row.style)
        if row_fields:
            requests.append(
                make_update_table_row_style(
                    table_start_index=table_start_index,
                    row_index=row_index,
                    style={field: row.style[field] for field in row_fields},
                    fields=row_fields,
                    tab_id=tab_id,
                )
            )
    for column_index, properties in enumerate(table.column_properties):
        property_fields = _style_fields(properties)
        if property_fields:
            requests.append(
                make_update_table_column_properties(
                    table_start_index=table_start_index,
                    column_index=column_index,
                    properties={field: properties[field] for field in property_fields},
                    fields=property_fields,
                    tab_id=tab_id,
                )
            )
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row.cells):
            style = _inserted_cell_style_payload(cell.style)
            style_fields = _style_fields(style)
            if not style_fields:
                continue
            requests.append(
                make_update_table_cell_style(
                    table_start_index=table_start_index,
                    row_index=row_index,
                    column_index=column_index,
                    style={field: style[field] for field in style_fields},
                    fields=style_fields,
                    tab_id=tab_id,
                )
            )
    return requests


def _style_fields(style: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(key for key, value in style.items() if value is not None))


def _inserted_cell_style_payload(style: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in style.items()
        if key not in {"rowSpan", "columnSpan"} and value is not None
    }
