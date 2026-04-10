"""Markdown serde: Document <-> markdown folder.

Provides MarkdownSerde, the markdown implementation of the Serde protocol.
"""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.comments._xml import from_xml as comments_from_xml
from extradoc.comments._xml import to_xml as comments_to_xml
from extradoc.serde import DeserializeResult

from .._index import build_index
from .._models import IndexXml
from .._utils import build_heading_maps, sanitize_tab_name
from ._from_markdown import markdown_to_document
from ._to_markdown import document_to_markdown

_INTERNAL_DIR = ".extrasuite"
_TABS_DIR = "tabs"
_SKIP_DIRS = {_INTERNAL_DIR}

# Legacy layout constants (backward compat)
_LEGACY_PRISTINE_DIR = ".pristine"
_LEGACY_RAW_DIR = ".raw"
_LEGACY_SKIP_DIRS = {_LEGACY_PRISTINE_DIR, _LEGACY_RAW_DIR}


def _is_new_layout(folder: Path) -> bool:
    """Detect whether folder uses the new tabs/ layout."""
    return (folder / _TABS_DIR).is_dir()


class MarkdownSerde:
    """Markdown implementation of the Serde protocol."""

    def serialize(self, bundle: DocumentWithComments, folder: Path) -> None:
        """Write DocumentWithComments to markdown folder structure.

        Writes content files, .extrasuite/ internal state, and
        tabs/<Name>.md for each tab.
        """
        doc = bundle.document
        per_tab = document_to_markdown(doc)

        # Build index (same structure as XML, but format="markdown")
        index = build_index(doc)
        index.format = "markdown"
        tab_list = doc.tabs or []
        for i, idx_tab in enumerate(index.tabs):
            if i < len(tab_list):
                props = tab_list[i].tab_properties
                title = (props.title or "Tab 1") if props else "Tab 1"
                idx_tab.folder = sanitize_tab_name(title)

        folder.mkdir(parents=True, exist_ok=True)

        # Create tabs/ directory and write per-tab .md files
        tabs_dir = folder / _TABS_DIR
        tabs_dir.mkdir(parents=True, exist_ok=True)

        heading_re = re.compile(r"^(#{1,6})\s+.+$")
        tab_toc: dict[str, list[tuple[int, str, str | None]]] = {}

        for folder_name, files in per_tab.items():
            content = files.get("document.md", "")
            tab_path = tabs_dir / f"{folder_name}.md"
            tab_path.write_text(content, encoding="utf-8")

            heading_lines: list[tuple[int, str]] = []
            for lineno, line in enumerate(content.splitlines(), 1):
                if heading_re.match(line):
                    heading_lines.append((lineno, line))
            tab_toc[folder_name] = [(ln, line, None) for ln, line in heading_lines]

        # Enrich tab_toc with heading IDs from the index (extracted from API response)
        for idx_tab in index.all_tabs_flat():
            folder_name = idx_tab.folder
            toc_entries = tab_toc.get(folder_name, [])
            api_headings = idx_tab.headings
            enriched: list[tuple[int, str, str | None]] = []
            api_iter = iter(api_headings)
            for lineno, heading_line, _ in toc_entries:
                api_h = next(api_iter, None)
                enriched.append((lineno, heading_line, api_h.heading_id if api_h else None))
            tab_toc[folder_name] = enriched

        # Write index.md with frontmatter and TOC
        doc_title = doc.title or "Document"
        md_lines: list[str] = [
            "---",
            f"document_id: {doc.document_id or ''}",
            f"title: {doc_title}",
            "---",
            "",
            f"# {doc_title}",
            "",
        ]
        for idx_tab in index.all_tabs_flat():
            md_lines.append(f"## {idx_tab.title}")
            md_lines.append("")
            md_lines.append(f"File: `tabs/{idx_tab.folder}.md`")
            md_lines.append("")
            headings = tab_toc.get(idx_tab.folder, [])
            if headings:
                md_lines.append("| Line | Heading |")
                md_lines.append("|------|---------|")
                for lineno, heading_line, _ in headings:
                    safe = heading_line.replace("|", "\\|")
                    md_lines.append(f"| {lineno} | {safe} |")
            else:
                md_lines.append("*(no headings)*")
            md_lines.append("")

        index_md_path = folder / "index.md"
        index_md_path.write_text("\n".join(md_lines), encoding="utf-8")

        # Write internal state to .extrasuite/
        internal_dir = folder / _INTERNAL_DIR
        internal_dir.mkdir(parents=True, exist_ok=True)

        # index.xml (for format detection and heading ID storage)
        index_path = internal_dir / "index.xml"
        index_path.write_text(index.to_xml_string(), encoding="utf-8")

        # comments.xml at root
        comments_path = folder / "comments.xml"
        comments_path.write_text(comments_to_xml(bundle.comments), encoding="utf-8")

        # .extrasuite/document.json — transport-accurate base for reconciliation
        raw_doc_path = internal_dir / "document.json"
        raw_doc_path.write_text(
            json.dumps(
                bundle.document.model_dump(by_alias=True, exclude_none=True),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # .extrasuite/pristine.zip
        _write_pristine_zip(folder)

    def deserialize(self, folder: Path) -> DeserializeResult:
        """Read the folder and return base + desired documents.

        Base is loaded from .extrasuite/document.json (or legacy .raw/).
        Desired is computed via 3-way merge: diff(pristine, current) applied to base.
        """
        base_bundle = self._load_base(folder)

        _, heading_name_to_id = build_heading_maps(base_bundle.document)

        pristine_bundle = self._load_pristine(folder)
        mine_bundle = self._parse(folder, heading_name_to_id=heading_name_to_id)

        desired_bundle = _three_way_merge(pristine_bundle, mine_bundle, base_bundle)

        return DeserializeResult(base=base_bundle, desired=desired_bundle)

    def _load_base(self, folder: Path) -> DocumentWithComments:
        """Load the transport-accurate base from .extrasuite/document.json or legacy .raw/."""
        new_layout = _is_new_layout(folder)
        if new_layout:
            raw_doc_path = folder / _INTERNAL_DIR / "document.json"
        else:
            raw_doc_path = folder / _LEGACY_RAW_DIR / "document.json"
        raw_data = json.loads(raw_doc_path.read_text(encoding="utf-8"))
        doc = Document.model_validate(raw_data)
        pristine_bundle = self._load_pristine(folder)
        return DocumentWithComments(document=doc, comments=pristine_bundle.comments)

    def _load_pristine(
        self, folder: Path, *, heading_name_to_id: dict[str, tuple[str, str | None]] | None = None
    ) -> DocumentWithComments:
        """Extract and parse .extrasuite/pristine.zip or legacy .pristine/document.zip."""
        new_layout = _is_new_layout(folder)
        if new_layout:
            pristine_zip = folder / _INTERNAL_DIR / "pristine.zip"
        else:
            pristine_zip = folder / _LEGACY_PRISTINE_DIR / "document.zip"
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(pristine_zip, "r") as zf:
                zf.extractall(tmp)
            pristine_folder = Path(tmp)
            pristine_index = IndexXml.from_xml_string(
                (pristine_folder / _index_xml_path_in_folder(pristine_folder)).read_text(encoding="utf-8")
            )
            return _parse_markdown(pristine_folder, pristine_index, heading_name_to_id=heading_name_to_id)

    def _parse(
        self, folder: Path, *, heading_name_to_id: dict[str, tuple[str, str | None]] | None = None
    ) -> DocumentWithComments:
        """Read a markdown-format folder into a DocumentWithComments."""
        index_xml_path = folder / _index_xml_path_in_folder(folder)
        index = IndexXml.from_xml_string(index_xml_path.read_text(encoding="utf-8"))
        return _parse_markdown(folder, index, heading_name_to_id=heading_name_to_id)


def _index_xml_path_in_folder(folder: Path) -> Path:
    """Return the relative path to index.xml within a folder (new or legacy layout)."""
    new_path = Path(_INTERNAL_DIR) / "index.xml"
    if (folder / new_path).exists():
        return new_path
    return Path("index.xml")


def _parse_markdown(
    folder: Path,
    index: IndexXml,
    *,
    heading_name_to_id: dict[str, tuple[str, str | None]] | None = None,
) -> DocumentWithComments:
    """Internal: read a markdown-format folder into a DocumentWithComments."""
    new_layout = _is_new_layout(folder)
    tabs_dir = folder / _TABS_DIR if new_layout else folder

    tab_content: dict[str, str] = {}
    tab_ids: dict[str, str] = {}
    known_folders: set[str] = set()
    for index_tab in index.all_tabs_flat():
        md_path = tabs_dir / f"{index_tab.folder}.md"
        if not md_path.exists() and not new_layout:
            # Legacy fallback: tab folder with document.md inside
            md_path = folder / index_tab.folder / "document.md"
        source = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        tab_content[index_tab.folder] = source
        tab_ids[index_tab.folder] = index_tab.id
        known_folders.add(index_tab.folder)

    # Discover orphan .md files (new tabs)
    _READ_ONLY = {"index"}
    for md_path in sorted(tabs_dir.glob("*.md")):
        stem = md_path.stem
        if stem in _READ_ONLY or stem in known_folders:
            continue
        tab_content[stem] = md_path.read_text(encoding="utf-8")

    document = markdown_to_document(
        tab_content,
        document_id=index.id,
        title=index.title,
        revision_id=index.revision,
        tab_ids=tab_ids,
        heading_name_to_id=heading_name_to_id,
    )

    comments_path = folder / "comments.xml"
    if comments_path.exists():
        file_comments = comments_from_xml(comments_path.read_text(encoding="utf-8"))
    else:
        file_comments = FileComments(file_id=index.id)

    return DocumentWithComments(document=document, comments=file_comments)


def _write_pristine_zip(folder: Path) -> None:
    """Zip content files into .extrasuite/pristine.zip.

    Includes tabs/, index.md, comments.xml, and a copy of index.xml
    (needed for pristine deserialization). Excludes .extrasuite/ itself
    to avoid recursive nesting.
    """
    internal_dir = folder / _INTERNAL_DIR
    internal_dir.mkdir(parents=True, exist_ok=True)
    zip_path = internal_dir / "pristine.zip"

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

        # Include index.xml from .extrasuite/ at root of zip so pristine
        # extraction can find it (the extracted folder won't have .extrasuite/)
        index_xml_src = internal_dir / "index.xml"
        if index_xml_src.exists():
            zf.write(index_xml_src, Path("index.xml"))


def _three_way_merge(
    ancestor: DocumentWithComments,
    mine: DocumentWithComments,
    base: DocumentWithComments,
) -> DocumentWithComments:
    """Compute desired = apply_ops(base, diff(ancestor, mine))."""
    from extradoc.diffmerge import apply as apply_ops_to_document
    from extradoc.diffmerge import diff as reconcile_diff

    base_dict = base.document.model_dump(by_alias=True, exclude_none=True)

    ops = reconcile_diff(ancestor.document, mine.document)
    desired_dict = apply_ops_to_document(base_dict, ops)

    desired_document = base.document.__class__.model_validate(desired_dict)

    # Merge inline_objects from mine into desired.
    for d_tab, m_tab in zip(desired_document.tabs or [], mine.document.tabs or [], strict=False):
        m_dt = m_tab.document_tab
        d_dt = d_tab.document_tab
        if m_dt and m_dt.inline_objects and d_dt:
            referenced_ids: set[str] = set()
            for se in (d_dt.body.content or []) if d_dt.body else []:
                if se.paragraph:
                    for pe in se.paragraph.elements or []:
                        ioe = pe.inline_object_element
                        if ioe and ioe.inline_object_id:
                            referenced_ids.add(ioe.inline_object_id)
            merged = dict(d_dt.inline_objects or {})
            for obj_id, obj in m_dt.inline_objects.items():
                if obj_id in referenced_ids and obj_id not in merged:
                    merged[obj_id] = obj
            d_dt.inline_objects = merged

    return DocumentWithComments(document=desired_document, comments=mine.comments)


__all__ = [
    "MarkdownSerde",
]
