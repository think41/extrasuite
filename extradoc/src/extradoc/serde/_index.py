"""Generate IndexXml from a Document."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._models import IndexHeading, IndexTab, IndexXml
from ._utils import sanitize_tab_name

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Document,
        DocumentTab,
        Paragraph,
        Tab,
    )

# Named styles that appear in the index outline
_OUTLINE_STYLES: dict[str, str] = {
    "TITLE": "title",
    "SUBTITLE": "subtitle",
    "HEADING_1": "h1",
    "HEADING_2": "h2",
    "HEADING_3": "h3",
}


def build_index(doc: Document, folder_map: dict[str, str] | None = None) -> IndexXml:
    """Build an IndexXml from a Document.

    Args:
        doc: The Document to index.
        folder_map: Optional mapping from tab_id → folder_name.
            If not provided, folder names are derived from tab titles.

    Returns:
        IndexXml with document overview.
    """
    index = IndexXml(
        id=doc.document_id or "",
        title=doc.title or "",
        revision=doc.revision_id,
    )

    for tab in doc.tabs or []:
        index.tabs.append(_build_index_tab(tab, folder_map))

    return index


def _build_index_tab(tab: Tab, folder_map: dict[str, str] | None) -> IndexTab:
    """Build an IndexTab from a Tab, recursively handling child_tabs."""
    tab_props = tab.tab_properties
    tab_id = (tab_props.tab_id or "t.0") if tab_props else "t.0"
    tab_title = (tab_props.title or "Tab 1") if tab_props else "Tab 1"

    if folder_map:
        folder = folder_map.get(tab_id, sanitize_tab_name(tab_title))
    else:
        folder = sanitize_tab_name(tab_title)

    headings = _extract_outline(tab.document_tab) if tab.document_tab else []

    parent_tab_id = tab_props.parent_tab_id if tab_props else None
    nesting_level = tab_props.nesting_level if tab_props else None
    icon_emoji = tab_props.icon_emoji if tab_props else None

    child_tabs: list[IndexTab] = []
    for child_tab in tab.child_tabs or []:
        child_tabs.append(_build_index_tab(child_tab, folder_map))

    return IndexTab(
        id=tab_id,
        title=tab_title,
        folder=folder,
        headings=headings,
        parent_tab_id=parent_tab_id,
        nesting_level=nesting_level,
        icon_emoji=icon_emoji,
        child_tabs=child_tabs,
    )


def _extract_outline(doc_tab: DocumentTab) -> list[IndexHeading]:
    """Extract heading outline from a DocumentTab (title, subtitle, h1-h3)."""
    headings: list[IndexHeading] = []
    if not doc_tab.body or not doc_tab.body.content:
        return headings

    for se in doc_tab.body.content:
        if not se.paragraph:
            continue
        para = se.paragraph
        ps = para.paragraph_style
        if not ps or not ps.named_style_type:
            continue

        tag = _OUTLINE_STYLES.get(ps.named_style_type.value)
        if not tag:
            continue

        text = _paragraph_text(para)
        if text:
            headings.append(IndexHeading(tag=tag, text=text))

    return headings


def _paragraph_text(para: Paragraph) -> str:
    """Extract plain text from a paragraph."""
    parts: list[str] = []
    for pe in para.elements or []:
        if pe.text_run and pe.text_run.content:
            parts.append(pe.text_run.content.rstrip("\n"))
    return "".join(parts)
