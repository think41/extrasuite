"""Serde module: Document ↔ folder of files (XML or markdown).

Public API:
    serialize(bundle, output_path, format='xml') → list[Path]
    deserialize(base, folder) → DocumentWithComments   — 3-way merge (markdown) or direct (xml)
    from_document(doc) → (IndexXml, dict[folder, TabFiles])
    to_document(tabs, document_id) → Document
"""

from __future__ import annotations

import zipfile
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

# Directories to skip when creating the pristine zip
_PRISTINE_DIR = ".pristine"
_RAW_DIR = ".raw"
_SKIP_DIRS = {_PRISTINE_DIR, _RAW_DIR}

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
    tab_xml_map: dict[str, TabXml] = {}
    for folder, tab_files in tabs.items():
        folder_map[tab_files.tab.id] = folder
        tab_xml_map[tab_files.tab.id] = tab_files.tab

    index = build_index(doc, folder_map, tab_xml_map)
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
    import re

    from ._to_markdown import document_to_markdown
    from ._utils import sanitize_tab_name

    doc = bundle.document
    per_tab = document_to_markdown(doc)

    # Build index (same structure as XML, but format="markdown")
    index = build_index(doc)
    index.format = "markdown"
    # Patch folder names into the index tabs
    tab_list = doc.tabs or []
    for i, idx_tab in enumerate(index.tabs):
        if i < len(tab_list):
            props = tab_list[i].tab_properties
            title = (props.title or "Tab 1") if props else "Tab 1"
            idx_tab.folder = sanitize_tab_name(title)

    created: list[Path] = []
    output_path.mkdir(parents=True, exist_ok=True)

    # Write per-tab .md files at root level (e.g. Tab_1.md, not Tab_1/document.md)
    heading_re = re.compile(r"^(#{1,6})\s+.+$")
    tab_toc: dict[str, list[tuple[int, str]]] = {}  # folder → [(lineno, heading_line)]

    for folder, files in per_tab.items():
        content = files.get("document.md", "")
        tab_path = output_path / f"{folder}.md"
        tab_path.write_text(content, encoding="utf-8")
        created.append(tab_path)

        # Scan for headings with line numbers for index.md
        headings: list[tuple[int, str]] = []
        for lineno, line in enumerate(content.splitlines(), 1):
            if heading_re.match(line):
                headings.append((lineno, line))
        tab_toc[folder] = headings

    # Write index.md — human-readable TOC with line numbers per tab
    doc_title = doc.title or "Document"
    md_lines: list[str] = [f"# {doc_title}", ""]
    for idx_tab in index.all_tabs_flat():
        md_lines.append(f"## {idx_tab.title}")
        md_lines.append("")
        md_lines.append(f"File: `{idx_tab.folder}.md`")
        md_lines.append("")
        headings = tab_toc.get(idx_tab.folder, [])
        if headings:
            md_lines.append("| Line | Heading |")
            md_lines.append("|------|---------|")
            for lineno, heading_line in headings:
                # Escape pipe characters inside table cells
                safe = heading_line.replace("|", "\\|")
                md_lines.append(f"| {lineno} | {safe} |")
        else:
            md_lines.append("*(no headings)*")
        md_lines.append("")

    index_md_path = output_path / "index.md"
    index_md_path.write_text("\n".join(md_lines), encoding="utf-8")
    created.append(index_md_path)

    # Write index.xml for format detection by deserialize (do not edit)
    index_path = output_path / "index.xml"
    index_path.write_text(index.to_xml_string(), encoding="utf-8")
    created.append(index_path)

    # Write comments.xml (unchanged format)
    comments_path = output_path / "comments.xml"
    comments_path.write_text(comments_to_xml(bundle.comments), encoding="utf-8")
    created.append(comments_path)

    # Write .pristine/document.zip so deserialize can compute the 3-way merge
    pristine_path = _write_pristine_zip(output_path)
    created.append(pristine_path)

    return created


def _write_pristine_zip(folder: Path) -> Path:
    """Zip serde output (excluding .pristine/ and .raw/) into .pristine/document.zip.

    Args:
        folder: The document folder to zip

    Returns:
        Path to the created zip file
    """
    pristine_dir = folder / _PRISTINE_DIR
    pristine_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pristine_dir / "document.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_dir():
                continue
            try:
                rel = path.relative_to(folder)
            except ValueError:
                continue
            if rel.parts[0] in _SKIP_DIRS:
                continue
            zf.write(path, rel)

    return zip_path


def deserialize(
    base_or_folder: DocumentWithComments | Path,
    folder: Path | None = None,
) -> DocumentWithComments:
    """Read folder structure back into a DocumentWithComments.

    Supports two call signatures:

        # Legacy (XML format — no base needed):
        deserialize(folder: Path) -> DocumentWithComments

        # New 3-way merge (markdown format):
        deserialize(base: DocumentWithComments, folder: Path) -> DocumentWithComments

    For the **markdown format**, performs a 3-way merge:
        ancestor = parse(.pristine/document.zip)
        mine     = parse(current folder)
        ops      = diff(ancestor, mine)
        desired  = apply_ops_to_document(base, ops)

    Things the markdown SERDE doesn't model (headers, footers, DocumentStyle,
    InlineObjects, etc.) produce zero ops and are copied unchanged from base.

    When .pristine/document.zip is absent (legacy or XML folders), the function
    falls back to the old behaviour: deserializes the folder directly and returns
    it as the result.

    Args:
        base_or_folder: Either a DocumentWithComments (new 3-way merge path)
            or a Path (legacy single-argument path).
        folder: Required when base_or_folder is a DocumentWithComments.

    Returns:
        DocumentWithComments without indices. Call reindex_document() if needed.
    """
    # Normalise arguments
    if isinstance(base_or_folder, DocumentWithComments):
        base: DocumentWithComments | None = base_or_folder
        if folder is None:
            raise TypeError(
                "deserialize(base, folder): folder argument is required "
                "when base is a DocumentWithComments"
            )
        the_folder: Path = folder
    else:
        base = None
        the_folder = base_or_folder

    index_path = the_folder / "index.xml"
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))

    if index.format == "markdown":
        if base is not None:
            return _deserialize_markdown_3way(base, the_folder, index)
        return _deserialize_markdown(the_folder, index)

    tabs: dict[str, TabFiles] = {}
    for index_tab in index.all_tabs_flat():
        tab_dir = the_folder / index_tab.folder
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
    comments_path = the_folder / "comments.xml"
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
    known_folders: set[str] = set()
    for index_tab in index.all_tabs_flat():
        # New layout: <folder_stem>.md at root (e.g. Tab_1.md)
        md_path = folder / f"{index_tab.folder}.md"
        if not md_path.exists():
            # Fallback: old layout <tab_folder>/document.md
            md_path = folder / index_tab.folder / "document.md"
        source = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        tab_content[index_tab.folder] = source
        tab_ids[index_tab.folder] = index_tab.id
        known_folders.add(index_tab.folder)

    # Detect new .md files not tracked in index.xml — these become new tabs on push.
    # Files are added after indexed tabs so they appear at the end of the document.
    _READ_ONLY = {"index"}
    for md_path in sorted(folder.glob("*.md")):
        stem = md_path.stem
        if stem in _READ_ONLY or stem in known_folders:
            continue
        tab_content[stem] = md_path.read_text(encoding="utf-8")
        # No tab_ids entry → markdown_to_document assigns a synthetic ID →
        # reconciler treats it as a new tab and emits addDocumentTab.

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


def _deserialize_markdown_3way(
    base: DocumentWithComments,
    folder: Path,
    index: IndexXml,
) -> DocumentWithComments:
    """3-way merge deserialize for markdown format.

    Algorithm:
        ancestor  = parse(.pristine/document.zip)
        mine      = parse(current folder)
        ops       = diff(ancestor, mine)
        desired   = apply_ops_to_document(base, ops)

    When .pristine/document.zip is absent, falls back to direct parse (no merge).
    """
    import tempfile

    from extradoc.reconcile_v3.api import diff as reconcile_diff

    from ._apply_ops import apply_ops_to_document

    pristine_zip = folder / _PRISTINE_DIR / "document.zip"

    if not pristine_zip.exists():
        # Legacy folder: no pristine zip — fall back to direct parse
        return _deserialize_markdown(folder, index)

    # Parse current (mine) folder
    mine_bundle = _deserialize_markdown(folder, index)
    mine_doc_dict = mine_bundle.document.model_dump(by_alias=True, exclude_none=True)

    # Extract and parse pristine (ancestor) folder
    with tempfile.TemporaryDirectory() as tmp:
        import zipfile as _zf

        with _zf.ZipFile(pristine_zip, "r") as zf:
            zf.extractall(tmp)
        from pathlib import Path as _Path

        pristine_folder = _Path(tmp)
        ancestor_bundle = _deserialize_markdown(
            pristine_folder,
            IndexXml.from_xml_string(
                (pristine_folder / "index.xml").read_text(encoding="utf-8")
            ),
        )
    ancestor_doc_dict = ancestor_bundle.document.model_dump(
        by_alias=True, exclude_none=True
    )

    # Compute ops: what changed from ancestor to mine?
    ops = reconcile_diff(ancestor_doc_dict, mine_doc_dict)

    # Apply ops to base (the live document)
    base_doc_dict = base.document.model_dump(by_alias=True, exclude_none=True)
    desired_doc_dict = apply_ops_to_document(base_doc_dict, ops)

    desired_document = base.document.__class__.model_validate(desired_doc_dict)

    # Merge comments: use mine's comments (they reflect the agent's edits)
    desired_comments = mine_bundle.comments

    return DocumentWithComments(document=desired_document, comments=desired_comments)


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
