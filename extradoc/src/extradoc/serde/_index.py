"""Generate IndexXml from a Document and serialized tab models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._models import IndexHeading, IndexTab, IndexXml, ParagraphXml
from ._utils import sanitize_tab_name

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document, Tab

    from ._models import TabXml

# Named styles that appear in the index outline
_OUTLINE_STYLES: dict[str, str] = {
    "TITLE": "title",
    "SUBTITLE": "subtitle",
    "HEADING_1": "h1",
    "HEADING_2": "h2",
    "HEADING_3": "h3",
}


def build_index(
    doc: Document,
    folder_map: dict[str, str] | None = None,
    tab_xml_map: dict[str, TabXml] | None = None,
) -> IndexXml:
    """Build an IndexXml from a Document.

    Args:
        doc: The Document to index.
        folder_map: Optional mapping from tab_id → folder_name.
            If not provided, folder names are derived from tab titles.
        tab_xml_map: Optional mapping from tab_id → serialized TabXml.
            When present, heading XPaths are derived from the exact on-disk XML
            shape instead of the Google Docs API structure.

    Returns:
        IndexXml with document overview.
    """
    index = IndexXml(
        id=doc.document_id or "",
        title=doc.title or "",
        revision=doc.revision_id,
    )

    for tab in doc.tabs or []:
        index.tabs.append(_build_index_tab(tab, folder_map, tab_xml_map or {}))

    return index


def _build_index_tab(
    tab: Tab,
    folder_map: dict[str, str] | None,
    tab_xml_map: dict[str, TabXml],
) -> IndexTab:
    """Build an IndexTab from a Tab, recursively handling child_tabs."""
    tab_props = tab.tab_properties
    tab_id = (tab_props.tab_id or "t.0") if tab_props else "t.0"
    tab_title = (tab_props.title or "Tab 1") if tab_props else "Tab 1"

    if folder_map:
        folder = folder_map.get(tab_id, sanitize_tab_name(tab_title))
    else:
        folder = sanitize_tab_name(tab_title)

    tab_xml = tab_xml_map.get(tab_id)
    headings = _extract_outline(tab_xml) if tab_xml is not None else _extract_outline_from_tab(tab)

    parent_tab_id = tab_props.parent_tab_id if tab_props else None
    nesting_level = tab_props.nesting_level if tab_props else None
    icon_emoji = tab_props.icon_emoji if tab_props else None

    child_tabs: list[IndexTab] = []
    for child_tab in tab.child_tabs or []:
        child_tabs.append(_build_index_tab(child_tab, folder_map, tab_xml_map))

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


def _extract_outline(tab_xml: TabXml | None) -> list[IndexHeading]:
    """Extract indexed headings from the serialized TabXml body."""
    headings: list[IndexHeading] = []
    if tab_xml is None:
        return headings

    counts: dict[str, int] = {}
    for block in tab_xml.body:
        if not isinstance(block, ParagraphXml):
            continue
        tag = block.tag
        if tag not in _OUTLINE_STYLES.values():
            continue
        counts[tag] = counts.get(tag, 0) + 1
        text = _paragraph_text(block.inlines)
        if text:
            headings.append(
                IndexHeading(
                    tag=tag,
                    text=text,
                    xpath=f"/tab/body/{tag}[{counts[tag]}]",
                    heading_id=block.heading_id,
                )
            )

    return headings


def _extract_outline_from_tab(tab: Tab) -> list[IndexHeading]:
    """Extract indexed headings directly from an API Tab object.

    Used by MarkdownSerde, which has the full Document but no TabXml models.
    Returns headings in document order with their heading_ids (stable opaque IDs
    assigned by Google Docs, invariant across heading text renames).
    """
    from extradoc.api_types._generated import ParagraphStyleNamedStyleType

    _style_to_tag: dict[str, str] = {
        "TITLE": "title",
        "SUBTITLE": "subtitle",
        "HEADING_1": "h1",
        "HEADING_2": "h2",
        "HEADING_3": "h3",
    }
    headings: list[IndexHeading] = []
    counts: dict[str, int] = {}

    dt = tab.document_tab if tab else None
    body = dt.body if dt else None
    for se in body.content or [] if body else []:
        para = se.paragraph
        if not para:
            continue
        ps = para.paragraph_style
        if not ps:
            continue
        style_name = (ps.named_style_type.value if isinstance(
            ps.named_style_type, ParagraphStyleNamedStyleType
        ) else (ps.named_style_type or "")) if ps.named_style_type else ""
        tag = _style_to_tag.get(style_name)
        if not tag:
            continue
        text = "".join(
            (pe.text_run.content or "").rstrip("\n")
            for pe in (para.elements or [])
            if pe.text_run and pe.text_run.content
        ).strip()
        if not text:
            continue
        counts[tag] = counts.get(tag, 0) + 1
        headings.append(
            IndexHeading(
                tag=tag,
                text=text,
                xpath=f"/tab/body/{tag}[{counts[tag]}]",
                heading_id=ps.heading_id,
            )
        )

    return headings


def _paragraph_text(inlines: list[Any]) -> str:
    """Extract plain text from a paragraph."""
    parts: list[str] = []
    for inline in inlines:
        text = getattr(inline, "text", None)
        if text:
            parts.append(text.rstrip("\n"))
            continue
        children = getattr(inline, "children", None)
        if children:
            parts.extend(
                child.text.rstrip("\n")
                for child in children
                if getattr(child, "text", None)
            )
    return "".join(parts)
