"""Lower narrow semantic edits into Docs API requests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extradoc.indexer import utf16_len
from extradoc.reconcile_v2.diff import (
    AppendListItemsEdit,
    DeleteSectionEdit,
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertSectionEdit,
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
from extradoc.reconcile_v2.layout import (
    BodyLayout,
    ListLocation,
    ParagraphLocation,
    TableLocation,
    build_body_layout,
    build_story_layouts,
    paragraph_slice,
    resolve_position_to_index,
)
from extradoc.reconcile_v2.requests import (
    bullet_preset_for_kind,
    make_create_named_range,
    make_create_paragraph_bullets,
    make_delete_content_range,
    make_delete_named_range,
    make_delete_paragraph_bullets,
    make_delete_table_column,
    make_delete_table_row,
    make_insert_section_break,
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
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document


def lower_document_edits(base: Document, edits: list[SemanticEdit]) -> list[dict[str, Any]]:
    """Lower the supported semantic edits into batchUpdate request dicts."""
    requests: list[dict[str, Any]] = []
    layouts: dict[str, BodyLayout] = {}
    story_layouts = build_story_layouts(base)
    for edit in edits:
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
        elif isinstance(edit, ReplaceParagraphSliceEdit):
            story = story_layouts[edit.story_id]
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
            inserted_text = "\n".join(fragment.text for fragment in edit.inserted_paragraphs)
            if inserted_text:
                requests.append(
                    make_insert_text_in_story(
                        index=delete_start,
                        tab_id=story.route.tab_id,
                        segment_id=story.route.segment_id,
                        text=inserted_text,
                    )
                )
        elif isinstance(edit, ReplaceNamedRangesEdit):
            if edit.before_count:
                requests.append(make_delete_named_range(name=edit.name))
            for anchor in edit.desired_ranges:
                start_route, start_index = resolve_position_to_index(
                    story_layouts,
                    anchor.start,
                )
                end_route, end_index = resolve_position_to_index(
                    story_layouts,
                    anchor.end,
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
    return requests


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


def _table_cell_text_start(story_layouts: dict[str, Any], story_id: str) -> int:
    story = story_layouts.get(story_id)
    if story is None or not story.paragraphs:
        raise UnsupportedSpikeError(
            f"Could not resolve inserted table-cell anchor from story {story_id}"
        )
    return story.paragraphs[0].text_start_index
