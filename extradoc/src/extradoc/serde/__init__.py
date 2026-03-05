"""Serde module: Document ↔ folder of files (XML or markdown).

Public API:
    serialize(bundle, output_path, format='xml') → list[Path]
    deserialize(folder) → DocumentWithComments   — auto-detects format from index.xml
    from_document(doc) → (IndexXml, dict[folder, TabFiles])
    to_document(tabs, document_id) → Document
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeVar

from extradoc.api_types._generated import Document
from extradoc.comments._inject import inject_comment_refs, strip_comment_refs
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.comments._xml import from_xml as comments_from_xml
from extradoc.comments._xml import to_xml as comments_to_xml

from ._from_xml import tabs_to_document
from ._index import build_index
from ._models import IndexXml, TabFiles, TabXml
from ._styles import StylesXml
from ._tab_extras import (
    DocStyleXml,
    InlineObjectsXml,
    NamedRangesXml,
    NamedStylesXml,
    PositionedObjectsXml,
)
from ._to_xml import document_to_xml

if TYPE_CHECKING:
    from pathlib import Path

# Minimal styles.xml used when a new tab folder has no styles.xml yet.
# This is equivalent to an empty <styles /> — no custom paragraph classes,
# no custom list-level classes.  The reconciler treats absent custom styles
# identically on both the base and desired sides, so the diff is still valid.
_MINIMAL_STYLES_XML = '<?xml version="1.0" encoding="UTF-8"?>\n<styles />'


def from_document(
    doc: Document,
) -> tuple[IndexXml, dict[str, TabFiles]]:
    """Convert Document to XML models (no file I/O).

    Returns:
        (index_xml, {folder_name: TabFiles})
    """
    tabs = document_to_xml(doc)

    # Build folder_map: tab_id → folder_name for index generation
    folder_map: dict[str, str] = {}
    for folder, tab_files in tabs.items():
        folder_map[tab_files.tab.id] = folder

    index = build_index(doc, folder_map)
    return index, tabs


def to_document(
    tabs: dict[str, TabFiles],
    document_id: str = "",
    title: str = "",
) -> Document:
    """Convert XML models to Document (no file I/O, no indices).

    Args:
        tabs: dict mapping folder_name → TabFiles
        document_id: Optional document ID
        title: Optional document title

    Returns:
        Document without indices. Call reindex_document() if needed.
    """
    return tabs_to_document(tabs, document_id=document_id, title=title)


def serialize(
    bundle: DocumentWithComments | Document,
    output_path: Path,
    format: Literal["xml", "markdown"] = "xml",
) -> list[Path]:
    """Write DocumentWithComments (or plain Document) to folder structure.

    When passed a plain Document, creates an empty FileComments and serializes
    without any comment injection. When passed a DocumentWithComments, injects
    <comment-ref> tags and writes comments.xml.

    Args:
        bundle: The DocumentWithComments (or plain Document) to serialize
        output_path: Root directory to write into
        format: Output format — "xml" (default) or "markdown"

    Returns:
        List of created file paths
    """
    # Normalize to DocumentWithComments
    if isinstance(bundle, Document):
        bundle = DocumentWithComments(
            document=bundle,
            comments=FileComments(file_id=bundle.document_id or ""),
        )

    if format == "markdown":
        return _serialize_markdown(bundle, output_path)

    index, tabs = from_document(bundle.document)
    created: list[Path] = []

    output_path.mkdir(parents=True, exist_ok=True)

    # Write index.xml
    index_path = output_path / "index.xml"
    index_path.write_text(index.to_xml_string(), encoding="utf-8")
    created.append(index_path)

    # Write per-tab folders
    for folder, tab_files in tabs.items():
        tab_dir = output_path / folder
        tab_dir.mkdir(parents=True, exist_ok=True)

        # Serialize document.xml, then inject comment-refs
        doc_xml_str = tab_files.tab.to_xml_string()
        doc_xml_str = inject_comment_refs(doc_xml_str, bundle.comments)

        doc_path = tab_dir / "document.xml"
        doc_path.write_text(doc_xml_str, encoding="utf-8")
        created.append(doc_path)

        styles_path = tab_dir / "styles.xml"
        styles_path.write_text(tab_files.styles.to_xml_string(), encoding="utf-8")
        created.append(styles_path)

        # Write optional per-tab extras
        for filename, extra in [
            ("docstyle.xml", tab_files.doc_style),
            ("namedstyles.xml", tab_files.named_styles),
            ("objects.xml", tab_files.inline_objects),
            ("positionedObjects.xml", tab_files.positioned_objects),
            ("namedranges.xml", tab_files.named_ranges),
        ]:
            if extra is not None:
                extra_path = tab_dir / filename
                extra_path.write_text(extra.to_xml_string(), encoding="utf-8")
                created.append(extra_path)

    # Write comments.xml at folder root
    comments_path = output_path / "comments.xml"
    comments_path.write_text(comments_to_xml(bundle.comments), encoding="utf-8")
    created.append(comments_path)

    return created


def _serialize_markdown(bundle: DocumentWithComments, output_path: Path) -> list[Path]:
    """Write a Document to folder structure using markdown format."""
    from ._to_markdown import document_to_markdown

    doc = bundle.document
    per_tab = document_to_markdown(doc)

    # Build index (same structure as XML, but format="markdown")
    folder_map: dict[str, str] = {}
    for folder in per_tab:
        # We need tab_id → folder mapping; use tab index order
        pass
    index = build_index(doc)
    index.format = "markdown"
    # Patch folder names into the index tabs
    tab_list = doc.tabs or []
    from ._utils import sanitize_tab_name
    for i, idx_tab in enumerate(index.tabs):
        if i < len(tab_list):
            props = tab_list[i].tab_properties
            title = (props.title or "Tab 1") if props else "Tab 1"
            idx_tab.folder = sanitize_tab_name(title)

    created: list[Path] = []
    output_path.mkdir(parents=True, exist_ok=True)

    index_path = output_path / "index.xml"
    index_path.write_text(index.to_xml_string(), encoding="utf-8")
    created.append(index_path)

    for folder, files in per_tab.items():
        tab_dir = output_path / folder
        tab_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            p = tab_dir / filename
            p.write_text(content, encoding="utf-8")
            created.append(p)

    # Write comments.xml (unchanged format)
    comments_path = output_path / "comments.xml"
    comments_path.write_text(comments_to_xml(bundle.comments), encoding="utf-8")
    created.append(comments_path)

    return created


def deserialize(folder: Path) -> DocumentWithComments:
    """Read folder structure back into a DocumentWithComments.

    Auto-detects format from index.xml (format="markdown" or default "xml").
    Strips <comment-ref> tags from each tab's document.xml before parsing.
    Reads comments.xml if present.

    Args:
        folder: Root directory containing index.xml and per-tab folders

    Returns:
        DocumentWithComments without indices. Call reindex_document() if needed.
    """
    index_path = folder / "index.xml"
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))

    if index.format == "markdown":
        return _deserialize_markdown(folder, index)

    tabs: dict[str, TabFiles] = {}
    for index_tab in index.all_tabs_flat():
        tab_dir = folder / index_tab.folder
        doc_path = tab_dir / "document.xml"
        styles_path = tab_dir / "styles.xml"

        # Strip comment-refs before parsing
        raw_xml = doc_path.read_text(encoding="utf-8")
        clean_xml = strip_comment_refs(raw_xml)

        tab_xml = TabXml.from_xml_string(clean_xml)
        if styles_path.exists():
            styles_xml = StylesXml.from_xml_string(
                styles_path.read_text(encoding="utf-8")
            )
        else:
            styles_xml = StylesXml.from_xml_string(_MINIMAL_STYLES_XML)
        tf = TabFiles(tab=tab_xml, styles=styles_xml)

        # Read optional per-tab extras
        tf.doc_style = _read_extra(tab_dir / "docstyle.xml", DocStyleXml)
        tf.named_styles = _read_extra(tab_dir / "namedstyles.xml", NamedStylesXml)
        tf.inline_objects = _read_extra(tab_dir / "objects.xml", InlineObjectsXml)
        tf.positioned_objects = _read_extra(
            tab_dir / "positionedObjects.xml", PositionedObjectsXml
        )
        tf.named_ranges = _read_extra(tab_dir / "namedranges.xml", NamedRangesXml)

        tabs[index_tab.folder] = tf

    document = tabs_to_document(
        tabs,
        document_id=index.id,
        title=index.title,
        revision_id=index.revision,
    )

    # Read comments.xml
    comments_path = folder / "comments.xml"
    if comments_path.exists():
        file_comments = comments_from_xml(comments_path.read_text(encoding="utf-8"))
    else:
        file_comments = FileComments(file_id=index.id)

    return DocumentWithComments(document=document, comments=file_comments)


def _deserialize_markdown(folder: Path, index: IndexXml) -> DocumentWithComments:
    """Read a markdown-format folder into a DocumentWithComments."""
    from ._from_markdown import markdown_to_document

    tab_content: dict[str, str] = {}
    tab_ids: dict[str, str] = {}
    for index_tab in index.all_tabs_flat():
        tab_dir = folder / index_tab.folder
        md_path = tab_dir / "document.md"
        source = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        tab_content[index_tab.folder] = source
        tab_ids[index_tab.folder] = index_tab.id

    document = markdown_to_document(
        tab_content,
        document_id=index.id,
        title=index.title,
        revision_id=index.revision,
        tab_ids=tab_ids,
    )

    comments_path = folder / "comments.xml"
    if comments_path.exists():
        file_comments = comments_from_xml(comments_path.read_text(encoding="utf-8"))
    else:
        file_comments = FileComments(file_id=index.id)

    return DocumentWithComments(document=document, comments=file_comments)


_T = TypeVar("_T")


def _read_extra(path: Path, cls: type[_T]) -> _T | None:
    """Read an optional extra XML file, returning None if it doesn't exist."""
    if path.exists():
        return cls.from_xml_string(path.read_text(encoding="utf-8"))  # type: ignore[attr-defined, no-any-return]
    return None


__all__ = [
    "IndexXml",
    "StylesXml",
    "TabFiles",
    "TabXml",
    "deserialize",
    "from_document",
    "serialize",
    "to_document",
]
