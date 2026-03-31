"""Resolve semantic edit locations into narrow layout coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from extradoc.indexer import utf16_len
from extradoc.reconcile_v2.ir import PositionEdge, PositionIR

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document


@dataclass(frozen=True, slots=True)
class InlineSlotLocation:
    kind: str
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class ParagraphLocation:
    start_index: int
    end_index: int
    text_start_index: int
    text_end_index: int
    text: str
    inline_slots: tuple[InlineSlotLocation, ...] = ()


@dataclass(frozen=True, slots=True)
class ListItemLocation:
    start_index: int
    end_index: int
    text: str


@dataclass(frozen=True, slots=True)
class ListLocation:
    start_index: int
    end_index: int
    items: tuple[ListItemLocation, ...]
    list_id: str


@dataclass(frozen=True, slots=True)
class TableLocation:
    start_index: int
    end_index: int
    row_count: int
    column_count: int


@dataclass(frozen=True, slots=True)
class PageBreakLocation:
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class SectionBoundaryLocation:
    delete_start_index: int
    delete_end_index: int
    section_break_start_index: int
    section_break_end_index: int


@dataclass(slots=True)
class SectionLayout:
    block_locations: list[ParagraphLocation | ListLocation | TableLocation | PageBreakLocation] = field(
        default_factory=list
    )
    incoming_boundary: SectionBoundaryLocation | None = None


@dataclass(frozen=True, slots=True)
class BodyLayout:
    tab_id: str
    sections: tuple[SectionLayout, ...]


@dataclass(frozen=True, slots=True)
class StoryRoute:
    tab_id: str
    segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class StoryParagraphLocation:
    section_index: int | None
    block_index: int
    node_path: tuple[int, ...]
    start_index: int
    end_index: int
    text_start_index: int
    text_end_index: int
    text: str
    inline_slots: tuple[InlineSlotLocation, ...] = ()


@dataclass(frozen=True, slots=True)
class StoryLayout:
    story_id: str
    route: StoryRoute
    paragraphs: tuple[StoryParagraphLocation, ...]


def build_body_layout(document: Document, *, tab_id: str) -> BodyLayout:
    """Build a canonicalized body layout for one tab."""
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

    content = raw_tab.get("documentTab", {}).get("body", {}).get("content", [])
    sections: list[SectionLayout] = []
    current_section = SectionLayout()
    sections.append(current_section)

    pending_empty_para: tuple[int, int] | None = None
    pending_list: list[ListItemLocation] = []
    pending_list_id: str | None = None

    def flush_list() -> None:
        nonlocal pending_list, pending_list_id
        if pending_list:
            current_section.block_locations.append(
                ListLocation(
                    start_index=pending_list[0].start_index,
                    end_index=pending_list[-1].end_index,
                    items=tuple(pending_list),
                    list_id=pending_list_id or "",
                )
            )
            pending_list = []
            pending_list_id = None

    def _is_table_element(element: object) -> bool:
        return isinstance(element, dict) and element.get("table") is not None

    for index, element in enumerate(content):
        if "sectionBreak" in element:
            flush_list()
            if element.get("startIndex") is None:
                continue
            if pending_empty_para is None:
                raise ValueError("Expected carrier paragraph before internal section break")
            next_section = SectionLayout(
                incoming_boundary=SectionBoundaryLocation(
                    delete_start_index=pending_empty_para[0],
                    delete_end_index=element["endIndex"],
                    section_break_start_index=element["startIndex"],
                    section_break_end_index=element["endIndex"],
                )
            )
            sections.append(next_section)
            current_section = next_section
            pending_empty_para = None
            continue

        paragraph = element.get("paragraph")
        table = element.get("table")
        if table is not None:
            flush_list()
            pending_empty_para = None
            current_section.block_locations.append(
                TableLocation(
                    start_index=element["startIndex"],
                    end_index=element["endIndex"],
                    row_count=table.get("rows", 0),
                    column_count=table.get("columns", 0),
                )
            )
            continue

        if paragraph is None:
            flush_list()
            pending_empty_para = None
            continue

        text = "".join(
            child.get("textRun", {}).get("content", "")
            for child in paragraph.get("elements", [])
        )
        visible_text = text[:-1] if text.endswith("\n") else text
        text_start_index, text_end_index = _paragraph_text_run_range(
            paragraph,
            fallback_start=element["startIndex"],
        )
        inline_slots = _paragraph_inline_slots(
            paragraph,
            fallback_start=element["startIndex"],
        )
        if any(child.get("pageBreak") is not None for child in paragraph.get("elements", [])):
            flush_list()
            pending_empty_para = None
            current_section.block_locations.append(
                PageBreakLocation(
                    start_index=element["startIndex"],
                    end_index=element["endIndex"],
                )
            )
            continue
        bullet = paragraph.get("bullet")
        if bullet:
            pending_empty_para = None
            list_id = bullet.get("listId", "")
            item = ListItemLocation(
                start_index=element["startIndex"],
                end_index=element["endIndex"],
                text=visible_text,
            )
            if pending_list and pending_list_id == list_id:
                pending_list.append(item)
            else:
                flush_list()
                pending_list = [item]
                pending_list_id = list_id
            continue

        prev_element = content[index - 1] if index > 0 else None
        next_element = content[index + 1] if index + 1 < len(content) else None
        if (
            not visible_text.strip()
            and (_is_table_element(prev_element) or _is_table_element(next_element))
        ):
            pending_empty_para = None
            continue

        flush_list()
        if not visible_text.strip():
            pending_empty_para = (element["startIndex"], element["endIndex"])
        else:
            pending_empty_para = None
        current_section.block_locations.append(
            ParagraphLocation(
                start_index=element["startIndex"],
                end_index=element["endIndex"],
                text_start_index=text_start_index,
                text_end_index=text_end_index,
                text=visible_text,
                inline_slots=inline_slots,
            )
        )

    flush_list()
    return BodyLayout(tab_id=tab_id, sections=tuple(sections))


def build_story_layouts(document: Document) -> dict[str, StoryLayout]:
    """Build paragraph-level layouts for body, segment, and table-cell stories."""
    raw_document = document.model_dump(by_alias=True, exclude_none=True)
    layouts: dict[str, StoryLayout] = {}
    for tab_ordinal, raw_tab in enumerate(raw_document.get("tabs", [])):
        props = raw_tab.get("tabProperties", {})
        tab_id = props.get("tabId") or f"tab-{tab_ordinal}"
        document_tab = raw_tab.get("documentTab", {})

        body_story_id = f"{tab_id}:body"
        layouts[body_story_id] = StoryLayout(
            story_id=body_story_id,
            route=StoryRoute(tab_id=tab_id),
            paragraphs=tuple(
                _collect_story_paragraphs(
                    elements=document_tab.get("body", {}).get("content", []),
                    story_id=body_story_id,
                    route=StoryRoute(tab_id=tab_id),
                    layouts=layouts,
                    sectioned_body=True,
                )
            ),
        )

        for story_kind, catalog_name in (
            ("header", "headers"),
            ("footer", "footers"),
            ("footnote", "footnotes"),
        ):
            for story_ref, transport_story in document_tab.get(catalog_name, {}).items():
                story_id = f"{tab_id}:{story_kind}:{story_ref}"
                layouts[story_id] = StoryLayout(
                    story_id=story_id,
                    route=StoryRoute(tab_id=tab_id, segment_id=story_ref),
                    paragraphs=tuple(
                        _collect_story_paragraphs(
                            elements=transport_story.get("content", []),
                            story_id=story_id,
                            route=StoryRoute(tab_id=tab_id, segment_id=story_ref),
                            layouts=layouts,
                            sectioned_body=False,
                        )
                    ),
                )
    return layouts


def paragraph_slice(
    story_layout: StoryLayout,
    *,
    section_index: int | None,
    start_block_index: int,
    delete_block_count: int,
) -> tuple[StoryParagraphLocation, ...]:
    """Return paragraph locations for a contiguous semantic paragraph slice."""
    block_indexes = set(range(start_block_index, start_block_index + delete_block_count))
    paragraphs = tuple(
        paragraph
        for paragraph in story_layout.paragraphs
        if paragraph.section_index == section_index
        and paragraph.node_path == ()
        and paragraph.block_index in block_indexes
    )
    if len(paragraphs) != delete_block_count:
        raise ValueError(
            f"Could not resolve paragraph slice story={story_layout.story_id} "
            f"section={section_index} start={start_block_index} count={delete_block_count}"
        )
    return paragraphs


def paragraph_insertion_site(
    story_layout: StoryLayout,
    *,
    section_index: int | None,
    block_index: int,
) -> tuple[int, bool, bool]:
    """Return a transport insertion site for a zero-width paragraph edit.

    Returns ``(index, prefix_newline, suffix_newline)`` where the boolean flags
    indicate whether the inserted paragraph text should be prefixed/suffixed
    with a newline to preserve paragraph boundaries at the insertion anchor.
    """
    section_paragraphs = tuple(
        paragraph
        for paragraph in story_layout.paragraphs
        if paragraph.section_index == section_index and paragraph.node_path == ()
    )
    target = next(
        (paragraph for paragraph in section_paragraphs if paragraph.block_index == block_index),
        None,
    )
    if target is not None:
        # Canonical empty stories still have one carrier paragraph in transport.
        # Insert into that carrier directly and let its existing terminal newline
        # terminate the inserted content.
        if len(section_paragraphs) == 1 and target.text == "":
            return target.text_start_index, False, False
        return target.text_start_index, False, True

    previous = None
    for paragraph in section_paragraphs:
        if paragraph.block_index < block_index:
            previous = paragraph
        else:
            break
    if previous is not None:
        return previous.text_end_index, True, False

    if story_layout.paragraphs:
        first = story_layout.paragraphs[0]
        return first.text_start_index, False, True

    # New body stories start after the mandatory opening section break. Segment
    # stories start at index 0.
    return (1 if story_layout.route.segment_id is None else 0), False, False


def resolve_position_to_index(
    story_layouts: dict[str, StoryLayout],
    position: PositionIR,
) -> tuple[StoryRoute, int]:
    """Resolve a logical position back to a transport location index."""
    story = story_layouts.get(position.story_id)
    if story is None:
        raise ValueError(f"Unknown story id {position.story_id!r}")

    path = position.path
    paragraph = next(
        (
            candidate
            for candidate in story.paragraphs
            if candidate.section_index == path.section_index
            and candidate.block_index == path.block_index
            and candidate.node_path == path.node_path
        ),
        None,
    )
    if paragraph is None:
        raise ValueError(
            f"Could not resolve paragraph for story={position.story_id!r} "
            f"section={path.section_index} block={path.block_index} node_path={path.node_path}"
        )

    if path.text_offset_utf16 is not None:
        return story.route, paragraph.text_start_index + path.text_offset_utf16
    if path.edge == PositionEdge.BEFORE:
        return story.route, paragraph.text_start_index
    if path.edge == PositionEdge.AFTER:
        return story.route, paragraph.text_end_index
    raise ValueError(f"Unsupported logical position shape: {position}")


def _collect_story_paragraphs(
    *,
    elements: list[dict],
    story_id: str,
    route: StoryRoute,
    layouts: dict[str, StoryLayout],
    sectioned_body: bool,
) -> list[StoryParagraphLocation]:
    paragraphs: list[StoryParagraphLocation] = []
    block_index = 0
    cursor = 0
    section_index = 0 if sectioned_body else None
    saw_initial_section_break = False
    i = 0

    while i < len(elements):
        element = elements[i]
        start_index = _element_start_index(element, cursor)
        end_index = _element_end_index(element, start_index)

        if "sectionBreak" in element and sectioned_body:
            if saw_initial_section_break:
                section_index = 0 if section_index is None else section_index + 1
                block_index = 0
            else:
                saw_initial_section_break = True
            cursor = end_index
            i += 1
            continue

        paragraph = element.get("paragraph")
        if paragraph is not None:
            bullet = paragraph.get("bullet")
            if bullet and bullet.get("listId"):
                list_id = bullet["listId"]
                item_index = 0
                while i < len(elements):
                    candidate = elements[i]
                    candidate_paragraph = candidate.get("paragraph")
                    candidate_bullet = candidate_paragraph.get("bullet") if candidate_paragraph else None
                    if (
                        candidate_paragraph is None
                        or candidate_bullet is None
                        or candidate_bullet.get("listId") != list_id
                    ):
                        break
                    item_start = _element_start_index(candidate, cursor)
                    item_end = _element_end_index(candidate, item_start)
                    paragraphs.append(
                        _make_story_paragraph_location(
                            paragraph_element=candidate_paragraph,
                            section_index=section_index,
                            block_index=block_index,
                            node_path=(item_index,),
                            start_index=item_start,
                            end_index=item_end,
                        )
                    )
                    cursor = item_end
                    item_index += 1
                    i += 1
                block_index += 1
                continue

            text = "".join(
                child.get("textRun", {}).get("content", "")
                for child in paragraph.get("elements", [])
            )
            visible_text = text[:-1] if text.endswith("\n") else text
            prev_element = elements[i - 1] if i > 0 else None
            next_element = elements[i + 1] if i + 1 < len(elements) else None
            if not visible_text.strip() and (
                _is_table_structural_element(prev_element)
                or _is_table_structural_element(next_element)
            ):
                cursor = end_index
                i += 1
                continue

            paragraphs.append(
                _make_story_paragraph_location(
                    paragraph_element=paragraph,
                    section_index=section_index,
                    block_index=block_index,
                    node_path=(),
                    start_index=start_index,
                    end_index=end_index,
                )
            )
            cursor = end_index
            block_index += 1
            i += 1
            continue

        table = element.get("table")
        if table is not None:
            for row_index, row in enumerate(table.get("tableRows", [])):
                for column_index, cell in enumerate(row.get("tableCells", [])):
                    cell_story_id = (
                        f"{story_id}:table:{block_index}:r{row_index}:c{column_index}"
                    )
                    layouts[cell_story_id] = StoryLayout(
                        story_id=cell_story_id,
                        route=route,
                        paragraphs=tuple(
                            _collect_story_paragraphs(
                                elements=cell.get("content", []),
                                story_id=cell_story_id,
                                route=route,
                                layouts=layouts,
                                sectioned_body=False,
                            )
                        ),
                    )
            cursor = end_index
            block_index += 1
            i += 1
            continue

        cursor = end_index
        block_index += 1
        i += 1

    return paragraphs


def _make_story_paragraph_location(
    *,
    paragraph_element: dict,
    section_index: int | None,
    block_index: int,
    node_path: tuple[int, ...],
    start_index: int,
    end_index: int,
) -> StoryParagraphLocation:
    text = "".join(
        child.get("textRun", {}).get("content", "")
        for child in paragraph_element.get("elements", [])
    )
    visible_text = text[:-1] if text.endswith("\n") else text
    text_start_index, text_end_index = _paragraph_text_run_range(
        paragraph_element,
        fallback_start=start_index,
    )
    inline_slots = _paragraph_inline_slots(
        paragraph_element,
        fallback_start=start_index,
    )
    return StoryParagraphLocation(
        section_index=section_index,
        block_index=block_index,
        node_path=node_path,
        start_index=start_index,
        end_index=end_index,
        text_start_index=text_start_index,
        text_end_index=text_end_index,
        text=visible_text,
        inline_slots=inline_slots,
    )


def _paragraph_text_run_range(
    paragraph: dict,
    *,
    fallback_start: int,
) -> tuple[int, int]:
    full_text = "".join(
        element.get("textRun", {}).get("content", "")
        for element in paragraph.get("elements", [])
    )
    visible_text = full_text[:-1] if full_text.endswith("\n") else full_text
    text_runs = [
        element
        for element in paragraph.get("elements", [])
        if element.get("textRun") is not None
        and (element["textRun"].get("content") or "") != "\n"
    ]
    if not text_runs:
        return fallback_start, fallback_start
    start_index = text_runs[0].get("startIndex", fallback_start)
    last_run = text_runs[-1]
    end_index = last_run.get("endIndex", start_index + utf16_len(visible_text))
    last_content = last_run.get("textRun", {}).get("content", "")
    if last_content.endswith("\n"):
        end_index = max(start_index, end_index - utf16_len("\n"))
    return start_index, end_index


def _paragraph_inline_slots(
    paragraph: dict,
    *,
    fallback_start: int,
) -> tuple[InlineSlotLocation, ...]:
    slots: list[InlineSlotLocation] = []
    for element in paragraph.get("elements", []):
        start_index = element.get("startIndex", fallback_start)
        end_index = element.get("endIndex", start_index)
        text_run = element.get("textRun")
        if text_run is not None:
            content = text_run.get("content", "")
            visible = content[:-1] if content.endswith("\n") else content
            if not visible:
                continue
            slots.append(
                InlineSlotLocation(
                    kind="text",
                    start_index=start_index,
                    end_index=start_index + utf16_len(visible),
                )
            )
            continue
        if element.get("pageBreak") is not None:
            continue
        if element.get("footnoteReference") is not None:
            kind = "footnote"
        elif element.get("inlineObjectElement") is not None:
            kind = "inline_object"
        elif element.get("autoText") is not None:
            kind = "auto_text"
        else:
            kind = "opaque"
        slots.append(
            InlineSlotLocation(
                kind=kind,
                start_index=start_index,
                end_index=end_index,
            )
        )
    return tuple(slots)


def _element_start_index(element: dict, fallback: int) -> int:
    if element.get("startIndex") is not None:
        return element["startIndex"]

    paragraph = element.get("paragraph")
    if paragraph and paragraph.get("elements"):
        first = paragraph["elements"][0]
        if first.get("startIndex") is not None:
            return first["startIndex"]

    return fallback


def _element_end_index(element: dict, fallback: int) -> int:
    if element.get("endIndex") is not None:
        return element["endIndex"]

    paragraph = element.get("paragraph")
    if paragraph and paragraph.get("elements"):
        last = paragraph["elements"][-1]
        if last.get("endIndex") is not None:
            return last["endIndex"]

    return fallback


def _is_table_structural_element(element: dict | None) -> bool:
    return bool(element and element.get("table") is not None)
