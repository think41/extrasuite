"""Resolve semantic edit locations into narrow layout coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from extradoc.reconcile_v2.ir import PositionEdge, PositionIR

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document


@dataclass(frozen=True, slots=True)
class ParagraphLocation:
    start_index: int
    end_index: int
    text_start_index: int
    text_end_index: int
    text: str


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
class SectionBoundaryLocation:
    delete_start_index: int
    delete_end_index: int
    section_break_start_index: int
    section_break_end_index: int


@dataclass(slots=True)
class SectionLayout:
    block_locations: list[ParagraphLocation | ListLocation | TableLocation] = field(
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

        if (
            not current_section.block_locations
            and not visible_text.strip()
            and index + 1 < len(content)
            and content[index + 1].get("table") is not None
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
                text_start_index=element["startIndex"],
                text_end_index=element["endIndex"] - 1,
                text=visible_text,
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
            if (
                block_index == 0
                and not visible_text.strip()
                and i + 1 < len(elements)
                and elements[i + 1].get("table") is not None
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
    return StoryParagraphLocation(
        section_index=section_index,
        block_index=block_index,
        node_path=node_path,
        start_index=start_index,
        end_index=end_index,
        text_start_index=start_index,
        text_end_index=max(start_index, end_index - 1),
        text=visible_text,
    )


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
