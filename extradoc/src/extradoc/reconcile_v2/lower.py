"""Lower narrow semantic edits into Docs API requests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extradoc.indexer import utf16_len
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile_v2.diff import (
    AppendListItemsEdit,
    CreateFootnoteEdit,
    CreateSectionAttachmentEdit,
    DeleteListBlockEdit,
    DeleteSectionAttachmentEdit,
    DeleteSectionEdit,
    DeleteTableBlockEdit,
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertListBlockEdit,
    InsertSectionEdit,
    InsertTableBlockEdit,
    InsertTableColumnEdit,
    InsertTableRowEdit,
    MergeTableCellsEdit,
    RelevelListItemsEdit,
    ReplaceListSpecEdit,
    ReplaceNamedRangesEdit,
    ReplaceParagraphSliceEdit,
    SemanticEdit,
    UnmergeTableCellsEdit,
    UpdateParagraphRoleEdit,
    UpdateTableCellStyleEdit,
    UpdateTableColumnPropertiesEdit,
    UpdateTablePinnedHeaderRowsEdit,
    UpdateTableRowStyleEdit,
)
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.ir import ParagraphIR, TableIR, TextSpanIR
from extradoc.reconcile_v2.layout import (
    BodyLayout,
    ListLocation,
    ParagraphLocation,
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
    desired_story_layouts = build_story_layouts(desired) if desired is not None else None
    desired_body_layouts: dict[str, BodyLayout] = {}
    content_edited_story_ids = _edited_story_ids(edits)
    content_edits = [edit for edit in edits if not isinstance(edit, ReplaceNamedRangesEdit)]

    edit_index = 0
    while edit_index < len(content_edits):
        group_end = _body_insert_group_end(content_edits, edit_index)
        if group_end - edit_index > 1:
            group = content_edits[edit_index:group_end]
            layout = layouts.setdefault(group[0].tab_id, build_body_layout(base, tab_id=group[0].tab_id))
            requests.extend(
                _lower_body_insert_group(
                    base=base,
                    layout=layout,
                    edits=group,
                    desired=desired,
                )
            )
            edit_index = group_end
            continue
        edit = content_edits[edit_index]
        layout = layouts.setdefault(edit.tab_id, build_body_layout(base, tab_id=edit.tab_id))
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
        elif isinstance(edit, InsertListBlockEdit):
            story = story_layouts[f"{edit.tab_id}:body"]
            insert_index, prefix_newline, suffix_newline = _body_insert_site_for_edit(
                base,
                layout,
                edit,
            )
            list_text = "\n".join(
                ("\t" * item.level) + item.text for item in edit.items
            )
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
                base,
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
        elif isinstance(edit, DeleteTableBlockEdit):
            table_location = _table_at(layout, edit.section_index, edit.block_index)
            requests.append(
                make_delete_content_range(
                    start_index=table_location.start_index,
                    end_index=table_location.end_index,
                    tab_id=edit.tab_id,
                )
            )
        elif isinstance(edit, AppendListItemsEdit):
            list_location = _list_at(layout, edit.section_index, edit.block_index)
            insert_text = "".join(
                ("\t" * item.level) + item.text + "\n" for item in edit.appended_items
            )
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
            cumulative_after_levels = 0
            for item_index, item_location in enumerate(list_location.items):
                before_level = edit.before_levels[item_index]
                after_level = edit.after_levels[item_index]
                current_index = item_location.start_index + cumulative_after_levels
                if after_level > before_level:
                    requests.append(
                        make_insert_text(
                            index=current_index,
                            tab_id=edit.tab_id,
                            text="\t" * (after_level - before_level),
                        )
                    )
                elif after_level < before_level:
                    requests.append(
                        make_delete_content_range(
                            start_index=current_index,
                            end_index=current_index + (before_level - after_level),
                            tab_id=edit.tab_id,
                        )
                    )
                cumulative_after_levels += after_level
            requests.append(
                make_create_paragraph_bullets(
                    start_index=list_location.start_index,
                    end_index=list_location.end_index + sum(edit.after_levels),
                    tab_id=edit.tab_id,
                    bullet_preset=bullet_preset_for_kind(edit.list_kind),
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
                raise UnsupportedSpikeError(
                    f"Unsupported section attachment kind: {edit.attachment_kind}"
                )
        elif isinstance(edit, CreateSectionAttachmentEdit):
            raise UnsupportedSpikeError(
                "reconcile_v2 section attachment creation requires batch planning; "
                "use lower_semantic_diff_batches() or reconcile()"
            )
        elif isinstance(edit, CreateFootnoteEdit):
            raise UnsupportedSpikeError(
                "reconcile_v2 footnote creation requires batch planning; "
                "use lower_semantic_diff_batches() or reconcile()"
            )
        elif isinstance(edit, ReplaceParagraphSliceEdit):
            story = story_layouts[edit.story_id]
            inserted_text = "\n".join(fragment.text for fragment in edit.inserted_paragraphs)
            prefix_newline = False
            suffix_newline = False
            if edit.delete_block_count > 0:
                paragraphs = paragraph_slice(
                    story,
                    section_index=edit.section_index,
                    start_block_index=edit.start_block_index,
                    delete_block_count=edit.delete_block_count,
                )
                delete_start = paragraphs[0].text_start_index
                delete_end = paragraphs[-1].text_end_index
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
                        base,
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
                    raise UnsupportedSpikeError(
                        "reconcile_v2 table spike supports inserted-row content only for non-terminal row inserts"
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
                    raise UnsupportedSpikeError(
                        "reconcile_v2 table spike supports inserted-column content only for non-terminal column inserts"
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
        if edit.before_count:
            requests.append(make_delete_named_range(name=edit.name))
        for anchor in edit.desired_ranges:
            layout_source = story_layouts
            body_layout_source = layouts
            document_source = base
            if (
                desired_story_layouts is not None
                and (
                    anchor.start.story_id in content_edited_story_ids
                    or anchor.end.story_id in content_edited_story_ids
                )
            ):
                layout_source = desired_story_layouts
                body_layout_source = desired_body_layouts
                document_source = desired
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
                    f"Named range {edit.name} crosses routes in unsupported spike slice"
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
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.delete_block_count == 0
        and edit.section_index is not None
        and edit.story_id == f"{edit.tab_id}:body"
    ):
        return (
            edit.tab_id,
            edit.section_index,
            edit.start_block_index,
            edit.body_anchor_block_index,
        )
    return None


def _body_insert_group_end(edits: list[SemanticEdit], start_index: int) -> int:
    anchor = _body_insert_anchor(edits[start_index])
    if anchor is None:
        return start_index + 1
    end_index = start_index + 1
    while end_index < len(edits) and _body_insert_anchor(edits[end_index]) == anchor:
        end_index += 1
    return end_index


def _lower_body_insert_group(
    *,
    base: Document,
    layout: BodyLayout,
    edits: list[SemanticEdit],
    desired: Document | None,
) -> list[dict[str, Any]]:
    anchor = _body_insert_anchor(edits[0])
    if anchor is None:
        raise ValueError("Body insert group requires a shared body anchor")
    if desired is None:
        raise UnsupportedSpikeError(
            "reconcile_v2 body insert grouping requires desired document layouts"
        )
    tab_id, _section_index, _block_index, _raw_anchor_index = anchor
    insert_index, prefix_newline, suffix_newline = _body_insert_site_for_edit(
        base,
        layout,
        edits[0],
    )
    final_fragments = [_body_insert_fragment(edit) for edit in reversed(edits)]
    structural_requests: list[dict[str, Any]] = []

    for execution_index, fragment in enumerate(reversed(final_fragments)):
        final_index = len(final_fragments) - 1 - execution_index
        needs_prefix = final_index == 0 and prefix_newline
        needs_suffix = final_index < len(final_fragments) - 1 or suffix_newline
        if fragment[0] == "paragraphs":
            text = "\n".join(_paragraph_text(paragraph) for paragraph in fragment[1])
            if needs_prefix:
                text = f"\n{text}"
            if needs_suffix:
                text = f"{text}\n"
            structural_requests.append(
                make_insert_text(
                    index=insert_index,
                    tab_id=tab_id,
                    text=text,
                )
            )
        elif fragment[0] == "list":
            list_edit = fragment[1]
            text = "\n".join(
                ("\t" * item.level) + item.text for item in list_edit.items
            )
            if needs_prefix:
                text = f"\n{text}"
            if needs_suffix:
                text = f"{text}\n"
            structural_requests.append(
                make_insert_text(
                    index=insert_index,
                    tab_id=tab_id,
                    text=text,
                )
            )
        elif fragment[0] == "table":
            structural_requests.extend(
                _lower_blocks_into_fresh_story(
                    [fragment[1]],
                    story_start_index=insert_index,
                    tab_id=tab_id,
                    segment_id=None,
                )
            )
        else:  # pragma: no cover
            raise AssertionError(fragment[0])

    shadow_blocks = _shadow_body_insert_blocks(
        base=base,
        tab_id=tab_id,
        section_index=anchor[1],
        block_index=anchor[2],
        fragment_count=_body_insert_fragment_shadow_block_count(final_fragments),
        structural_requests=structural_requests,
    )
    paragraph_style_locations: list[tuple[ParagraphIR, tuple[int, int]]] = []
    style_ops: list[tuple[int, dict[str, Any]]] = []
    shadow_index = 0

    for fragment in final_fragments:
        if fragment[0] == "paragraphs":
            for paragraph in fragment[1]:
                block = shadow_blocks[shadow_index]
                if not isinstance(block, ParagraphLocation):
                    raise UnsupportedSpikeError(
                        "Grouped body insert shadow layout did not resolve a paragraph block"
                    )
                paragraph_style_locations.append(
                    (paragraph, (block.start_index, block.end_index))
                )
                if paragraph.role != "NORMAL_TEXT":
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
                shadow_index += 1
            continue

        if fragment[0] == "list":
            list_edit = fragment[1]
            item_blocks = shadow_blocks[
                shadow_index : shadow_index + len(list_edit.items)
            ]
            if (
                len(item_blocks) != len(list_edit.items)
                or not item_blocks
                or not all(isinstance(block, ParagraphLocation) for block in item_blocks)
            ):
                raise UnsupportedSpikeError(
                    "Grouped body insert shadow layout did not resolve list item paragraphs"
                )
            first_block = item_blocks[0]
            last_block = item_blocks[-1]
            style_ops.append(
                (
                    first_block.start_index,
                    make_create_paragraph_bullets(
                        start_index=first_block.start_index,
                        end_index=last_block.end_index,
                        tab_id=tab_id,
                        bullet_preset=bullet_preset_for_kind(list_edit.list_kind),
                    ),
                )
            )
            shadow_index += len(list_edit.items)
            continue

        if fragment[0] == "table":
            block = shadow_blocks[shadow_index]
            if not isinstance(block, TableLocation):
                raise UnsupportedSpikeError(
                    "Grouped body insert shadow layout did not resolve a table block"
                )
            shadow_index += 1
            continue

    style_ops.sort(key=lambda item: item[0], reverse=True)
    requests = list(structural_requests)
    requests.extend(request for _, request in style_ops)
    requests.extend(
        _lower_inserted_text_styles(
            route=StoryRoute(tab_id=tab_id, segment_id=None),
            paragraph_locations=tuple(paragraph_style_locations),
        )
    )
    return requests


def _body_insert_fragment_shadow_block_count(
    fragments: list[tuple[str, tuple[ParagraphIR, ...] | InsertListBlockEdit | TableIR]],
) -> int:
    count = 0
    for kind, payload in fragments:
        if kind == "paragraphs":
            count += len(payload)
        elif kind == "list":
            count += len(payload.items)
        else:
            count += 1
    return count


def _shadow_body_insert_blocks(
    *,
    base: Document,
    tab_id: str,
    section_index: int,
    block_index: int,
    fragment_count: int,
    structural_requests: list[dict[str, Any]],
) -> tuple[ParagraphLocation | ListLocation | TableLocation, ...]:
    shadow = MockGoogleDocsAPI(base)
    shadow._batch_update_raw(structural_requests)
    shadow_layout = build_body_layout(shadow.get(), tab_id=tab_id)
    section_blocks = shadow_layout.sections[section_index].block_locations
    inserted_blocks = tuple(section_blocks[block_index : block_index + fragment_count])
    if len(inserted_blocks) != fragment_count:
        raise UnsupportedSpikeError(
            "Grouped body insert shadow layout did not produce the expected block count"
        )
    return inserted_blocks


def _body_insert_fragment(
    edit: SemanticEdit,
) -> tuple[str, tuple[ParagraphIR, ...] | InsertListBlockEdit | TableIR]:
    if isinstance(edit, ReplaceParagraphSliceEdit):
        return (
            "paragraphs",
            tuple(fragment.paragraph for fragment in edit.inserted_paragraphs),
        )
    if isinstance(edit, InsertListBlockEdit):
        return ("list", edit)
    if isinstance(edit, InsertTableBlockEdit):
        return ("table", edit.table)
    raise TypeError(f"Unsupported body insert edit in grouped lowering: {type(edit).__name__}")


def _paragraph_at(
    layout: BodyLayout,
    section_index: int,
    block_index: int,
) -> ParagraphLocation:
    block = layout.sections[section_index].block_locations[block_index]
    if not isinstance(block, ParagraphLocation):
        raise TypeError(f"Expected paragraph at section {section_index} block {block_index}")
    return block


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


def _body_insert_site_for_edit(
    base: Document,
    layout: BodyLayout,
    edit: SemanticEdit,
) -> tuple[int, bool, bool]:
    anchor = _body_insert_anchor(edit)
    if anchor is None:
        raise TypeError(f"Unsupported body insert edit: {type(edit).__name__}")
    tab_id, section_index, block_index, raw_block_index = anchor
    if raw_block_index is None:
        return _body_block_insertion_site(
            layout,
            section_index=section_index,
            block_index=block_index,
        )
    return _raw_body_block_insertion_site(
        base,
        tab_id=tab_id,
        section_index=section_index,
        raw_block_index=raw_block_index,
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
        return target.start_index, False, True
    if not blocks:
        return 1, False, False
    previous = blocks[block_index - 1]
    if isinstance(previous, ParagraphLocation):
        return previous.text_end_index, True, False
    return previous.end_index, False, False


def _raw_body_block_insertion_site(
    document: Document,
    *,
    tab_id: str,
    section_index: int,
    raw_block_index: int,
) -> tuple[int, bool, bool]:
    sections = _raw_body_sections(document, tab_id=tab_id)
    blocks = sections[section_index]
    if raw_block_index < len(blocks):
        target = blocks[raw_block_index]
        if target["kind"] == "paragraph":
            if len(blocks) == 1 and target["text"] == "":
                return int(target["text_start"]), False, False
            return int(target["text_start"]), False, True
        return int(target["start"]), False, True
    if not blocks:
        return 1, False, False
    previous = blocks[raw_block_index - 1]
    if previous["kind"] == "paragraph":
        return int(previous["text_end"]), True, False
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


def _edited_story_ids(edits: list[SemanticEdit]) -> set[str]:
    story_ids = {
        edit.story_id for edit in edits if isinstance(edit, ReplaceParagraphSliceEdit)
    }
    for edit in edits:
        if isinstance(edit, InsertTableBlockEdit):
            story_ids.update(_table_story_ids(edit.table))
    return story_ids


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
        item_text = ("\t" * item.level) + item.text
        range_end = cursor + utf16_len(item_text) + 1
        cursor = range_end
    return range_start, range_end


def _lower_inserted_text_styles(
    *,
    route: Any,
    paragraph_locations: tuple[tuple[ParagraphIR, tuple[int, int]], ...],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
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
            style_dict, fields = _text_style_delta(inline.explicit_text_style)
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


def _text_style_delta(style: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    fields = tuple(sorted(key for key, value in style.items() if value is not None))
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
    if all(isinstance(block, ParagraphIR) for block in blocks):
        paragraphs = tuple(blocks)
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
    if len(blocks) == 1 and isinstance(blocks[0], TableIR):
        return _lower_table_into_fresh_story(
            blocks[0],
            story_start_index=story_start_index,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    raise UnsupportedSpikeError(
        "reconcile_v2 currently supports fresh-story insertion only for paragraph runs "
        "or a single recursively-populated table block"
    )


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
        raise UnsupportedSpikeError(
            "reconcile_v2 currently requires rectangular tables for mixed body insertion"
        )
    if table.pinned_header_rows or table.merge_regions:
        raise UnsupportedSpikeError(
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
                raise UnsupportedSpikeError(
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
        raise UnsupportedSpikeError(
            f"Could not resolve inserted table-cell anchor from story {story_id}"
        )
    return story.paragraphs[0].text_start_index
