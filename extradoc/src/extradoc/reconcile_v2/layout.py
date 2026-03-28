"""Resolve semantic edit locations into narrow body-layout coordinates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document


@dataclass(frozen=True, slots=True)
class ParagraphLocation:
    start_index: int
    end_index: int
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
class SectionBoundaryLocation:
    delete_start_index: int
    delete_end_index: int
    section_break_start_index: int
    section_break_end_index: int


@dataclass(slots=True)
class SectionLayout:
    block_locations: list[ParagraphLocation | ListLocation] = field(default_factory=list)
    incoming_boundary: SectionBoundaryLocation | None = None


@dataclass(frozen=True, slots=True)
class BodyLayout:
    tab_id: str
    sections: tuple[SectionLayout, ...]


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

    for element in content:
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

        flush_list()
        if not visible_text.strip():
            pending_empty_para = (element["startIndex"], element["endIndex"])
            continue

        pending_empty_para = None
        current_section.block_locations.append(
            ParagraphLocation(
                start_index=element["startIndex"],
                end_index=element["endIndex"],
                text=visible_text,
            )
        )

    flush_list()
    return BodyLayout(tab_id=tab_id, sections=tuple(sections))
