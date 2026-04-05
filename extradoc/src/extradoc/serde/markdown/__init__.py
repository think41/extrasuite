"""Markdown serde: Document ↔ markdown folder.

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
from .._utils import sanitize_tab_name
from ._from_markdown import markdown_to_document
from ._to_markdown import document_to_markdown

_PRISTINE_DIR = ".pristine"
_PRISTINE_ZIP = "document.zip"
_RAW_DIR = ".raw"
_SKIP_DIRS = {_PRISTINE_DIR, _RAW_DIR}


class MarkdownSerde:
    """Markdown implementation of the Serde protocol."""

    def serialize(self, bundle: DocumentWithComments, folder: Path) -> None:
        """Write DocumentWithComments to markdown folder structure.

        Writes content files, .pristine/document.zip, and
        .raw/document.json for round-trip fidelity.
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

        # Write per-tab .md files at root level (e.g. Tab_1.md)
        heading_re = re.compile(r"^(#{1,6})\s+.+$")
        tab_toc: dict[str, list[tuple[int, str]]] = {}

        for folder_name, files in per_tab.items():
            content = files.get("document.md", "")
            tab_path = folder / f"{folder_name}.md"
            tab_path.write_text(content, encoding="utf-8")

            headings: list[tuple[int, str]] = []
            for lineno, line in enumerate(content.splitlines(), 1):
                if heading_re.match(line):
                    headings.append((lineno, line))
            tab_toc[folder_name] = headings

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
                    safe = heading_line.replace("|", "\\|")
                    md_lines.append(f"| {lineno} | {safe} |")
            else:
                md_lines.append("*(no headings)*")
            md_lines.append("")

        index_md_path = folder / "index.md"
        index_md_path.write_text("\n".join(md_lines), encoding="utf-8")

        # Write index.xml for format detection
        index_path = folder / "index.xml"
        index_path.write_text(index.to_xml_string(), encoding="utf-8")

        # Write comments.xml
        comments_path = folder / "comments.xml"
        comments_path.write_text(comments_to_xml(bundle.comments), encoding="utf-8")

        # Write .raw/document.json — transport-accurate base for reconciliation
        raw_dir = folder / _RAW_DIR
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_doc_path = raw_dir / "document.json"
        raw_doc_path.write_text(
            json.dumps(
                bundle.document.model_dump(by_alias=True, exclude_none=True),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Write .pristine/document.zip
        _write_pristine_zip(folder)

    def deserialize(self, folder: Path) -> DeserializeResult:
        """Read the folder and return base + desired documents.

        Base is loaded from .raw/document.json (written by serialize).
        Desired is computed via 3-way merge: diff(pristine, current) applied to base.
        """
        base_bundle = self._load_base(folder)
        pristine_bundle = self._load_pristine(folder)

        # Parse current (mine) folder
        mine_bundle = self._parse(folder)

        # 3-way merge
        desired_bundle = _three_way_merge(pristine_bundle, mine_bundle, base_bundle)

        return DeserializeResult(base=base_bundle, desired=desired_bundle)

    def _load_base(self, folder: Path) -> DocumentWithComments:
        """Load the transport-accurate base from .raw/document.json."""
        raw_doc_path = folder / _RAW_DIR / "document.json"
        raw_data = json.loads(raw_doc_path.read_text(encoding="utf-8"))
        doc = Document.model_validate(raw_data)
        pristine_bundle = self._load_pristine(folder)
        return DocumentWithComments(document=doc, comments=pristine_bundle.comments)

    def _load_pristine(self, folder: Path) -> DocumentWithComments:
        """Extract and parse .pristine/document.zip."""
        pristine_zip = folder / _PRISTINE_DIR / _PRISTINE_ZIP
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(pristine_zip, "r") as zf:
                zf.extractall(tmp)
            pristine_folder = Path(tmp)
            pristine_index = IndexXml.from_xml_string(
                (pristine_folder / "index.xml").read_text(encoding="utf-8")
            )
            return _parse_markdown(pristine_folder, pristine_index)

    def _parse(self, folder: Path) -> DocumentWithComments:
        """Read a markdown-format folder into a DocumentWithComments."""
        index_path = folder / "index.xml"
        index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))
        return _parse_markdown(folder, index)


def _parse_markdown(folder: Path, index: IndexXml) -> DocumentWithComments:
    """Internal: read a markdown-format folder into a DocumentWithComments."""
    tab_content: dict[str, str] = {}
    tab_ids: dict[str, str] = {}
    known_folders: set[str] = set()
    for index_tab in index.all_tabs_flat():
        md_path = folder / f"{index_tab.folder}.md"
        if not md_path.exists():
            md_path = folder / index_tab.folder / "document.md"
        source = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        tab_content[index_tab.folder] = source
        tab_ids[index_tab.folder] = index_tab.id
        known_folders.add(index_tab.folder)

    _READ_ONLY = {"index"}
    for md_path in sorted(folder.glob("*.md")):
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
    )

    comments_path = folder / "comments.xml"
    if comments_path.exists():
        file_comments = comments_from_xml(comments_path.read_text(encoding="utf-8"))
    else:
        file_comments = FileComments(file_id=index.id)

    return DocumentWithComments(document=document, comments=file_comments)


def _write_pristine_zip(folder: Path) -> None:
    """Zip content files (excluding .pristine/ and .raw/) into .pristine/document.zip."""
    pristine_dir = folder / _PRISTINE_DIR
    pristine_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pristine_dir / _PRISTINE_ZIP

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


def _three_way_merge(
    ancestor: DocumentWithComments,
    mine: DocumentWithComments,
    base: DocumentWithComments,
) -> DocumentWithComments:
    """Compute desired = apply_ops(base, diff(ancestor, mine))."""
    from extradoc.reconcile_v3.api import diff as reconcile_diff

    from .._apply_ops import apply_ops_to_document

    ancestor_dict = ancestor.document.model_dump(by_alias=True, exclude_none=True)
    mine_dict = mine.document.model_dump(by_alias=True, exclude_none=True)
    base_dict = base.document.model_dump(by_alias=True, exclude_none=True)

    ops = reconcile_diff(ancestor_dict, mine_dict)
    desired_dict = apply_ops_to_document(base_dict, ops)

    # Inject mine's synthetic list defs so the reconciler picks the right preset
    mine_tabs = mine_dict.get("tabs") or []
    desired_tabs = desired_dict.get("tabs") or []
    for mine_tab in mine_tabs:
        mine_props = mine_tab.get("tabProperties") or {}
        mine_tab_id = str(mine_props.get("tabId", ""))
        mine_dt = mine_tab.get("documentTab") or {}
        mine_lists = mine_dt.get("lists") or {}
        if not mine_lists:
            continue
        for d_tab in desired_tabs:
            d_props = d_tab.get("tabProperties") or {}
            if str(d_props.get("tabId", "")) == mine_tab_id:
                d_dt = d_tab.setdefault("documentTab", {})
                d_lists = d_dt.setdefault("lists", {})
                for list_id, list_def in mine_lists.items():
                    if list_id not in d_lists:
                        d_lists[list_id] = list_def
                break

    desired_document = base.document.__class__.model_validate(desired_dict)

    return DocumentWithComments(document=desired_document, comments=mine.comments)


__all__ = [
    "MarkdownSerde",
]
