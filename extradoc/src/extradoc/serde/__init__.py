"""Serde module: Document ↔ folder of XML files.

Public API:
    serialize(doc, output_path) → list[Path]
    deserialize(folder) → Document
    from_document(doc) → (IndexXml, dict[folder, (TabXml, StylesXml)])
    to_document(tabs, document_id) → Document
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._from_xml import tabs_to_document
from ._index import build_index
from ._models import IndexXml, TabXml
from ._styles import StylesXml
from ._to_xml import document_to_xml

if TYPE_CHECKING:
    from pathlib import Path

    from extradoc.api_types._generated import Document


def from_document(
    doc: Document,
) -> tuple[IndexXml, dict[str, tuple[TabXml, StylesXml]]]:
    """Convert Document to XML models (no file I/O).

    Returns:
        (index_xml, {folder_name: (tab_xml, styles_xml)})
    """
    tabs = document_to_xml(doc)

    # Build folder_map: tab_id → folder_name for index generation
    folder_map: dict[str, str] = {}
    for folder, (tab_xml, _) in tabs.items():
        folder_map[tab_xml.id] = folder

    index = build_index(doc, folder_map)
    return index, tabs


def to_document(
    tabs: dict[str, tuple[TabXml, StylesXml]],
    document_id: str = "",
    title: str = "",
) -> Document:
    """Convert XML models to Document (no file I/O, no indices).

    Args:
        tabs: dict mapping folder_name → (TabXml, StylesXml)
        document_id: Optional document ID
        title: Optional document title

    Returns:
        Document without indices. Call reindex_document() if needed.
    """
    return tabs_to_document(tabs, document_id=document_id, title=title)


def serialize(doc: Document, output_path: Path) -> list[Path]:
    """Write Document to folder structure (index.xml + per-tab folders).

    Args:
        doc: The Document to serialize
        output_path: Root directory to write into

    Returns:
        List of created file paths
    """
    index, tabs = from_document(doc)
    created: list[Path] = []

    output_path.mkdir(parents=True, exist_ok=True)

    # Write index.xml
    index_path = output_path / "index.xml"
    index_path.write_text(index.to_xml_string(), encoding="utf-8")
    created.append(index_path)

    # Write per-tab folders
    for folder, (tab_xml, styles_xml) in tabs.items():
        tab_dir = output_path / folder
        tab_dir.mkdir(parents=True, exist_ok=True)

        doc_path = tab_dir / "document.xml"
        doc_path.write_text(tab_xml.to_xml_string(), encoding="utf-8")
        created.append(doc_path)

        styles_path = tab_dir / "styles.xml"
        styles_path.write_text(styles_xml.to_xml_string(), encoding="utf-8")
        created.append(styles_path)

    return created


def deserialize(folder: Path) -> Document:
    """Read folder structure back into a Document (without indices).

    Args:
        folder: Root directory containing index.xml and per-tab folders

    Returns:
        Document without indices. Call reindex_document() if needed.
    """
    index_path = folder / "index.xml"
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))

    tabs: dict[str, tuple[TabXml, StylesXml]] = {}
    for index_tab in index.tabs:
        tab_dir = folder / index_tab.folder
        doc_path = tab_dir / "document.xml"
        styles_path = tab_dir / "styles.xml"

        tab_xml = TabXml.from_xml_string(doc_path.read_text(encoding="utf-8"))
        styles_xml = StylesXml.from_xml_string(styles_path.read_text(encoding="utf-8"))
        tabs[index_tab.folder] = (tab_xml, styles_xml)

    return tabs_to_document(
        tabs,
        document_id=index.id,
        title=index.title,
    )


__all__ = [
    "IndexXml",
    "StylesXml",
    "TabXml",
    "deserialize",
    "from_document",
    "serialize",
    "to_document",
]
