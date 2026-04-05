"""XML serde: Document ↔ XML folder.

Provides XmlSerde, the XML implementation of the Serde protocol.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import TypeVar

from extradoc.api_types._generated import Document
from extradoc.comments._inject import inject_comment_refs, strip_comment_refs
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.comments._xml import from_xml as comments_from_xml
from extradoc.comments._xml import to_xml as comments_to_xml
from extradoc.serde import DeserializeResult

from .._index import build_index
from .._models import IndexXml, TabFiles, TabXml
from .._styles import StylesXml
from .._tab_extras import (
    DocStyleXml,
    InlineObjectsXml,
    NamedRangesXml,
    NamedStylesXml,
    PositionedObjectsXml,
)
from ._from_xml import tabs_to_document
from ._to_xml import document_to_xml

# Minimal styles.xml used when a new tab folder has no styles.xml yet.
_MINIMAL_STYLES_XML = '<?xml version="1.0" encoding="UTF-8"?>\n<styles />'

_PRISTINE_DIR = ".pristine"
_PRISTINE_ZIP = "document.zip"
_RAW_DIR = ".raw"
_SKIP_DIRS = {_PRISTINE_DIR, _RAW_DIR}

_T = TypeVar("_T")


class XmlSerde:
    """XML implementation of the Serde protocol."""

    def serialize(self, bundle: DocumentWithComments, folder: Path) -> None:
        """Write DocumentWithComments to XML folder structure.

        Writes content files, .pristine/document.zip, and
        .raw/document.json for round-trip fidelity.
        """
        index, tabs = from_document(bundle.document)

        folder.mkdir(parents=True, exist_ok=True)

        # Write index.xml
        index_path = folder / "index.xml"
        index_path.write_text(index.to_xml_string(), encoding="utf-8")

        # Write per-tab folders
        for folder_name, tab_files in tabs.items():
            tab_dir = folder / folder_name
            tab_dir.mkdir(parents=True, exist_ok=True)

            doc_xml_str = tab_files.tab.to_xml_string()
            doc_xml_str = inject_comment_refs(doc_xml_str, bundle.comments)

            doc_path = tab_dir / "document.xml"
            doc_path.write_text(doc_xml_str, encoding="utf-8")

            styles_path = tab_dir / "styles.xml"
            styles_path.write_text(tab_files.styles.to_xml_string(), encoding="utf-8")

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

        # Write comments.xml at folder root
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

        # Comment ops are handled by the caller (DocsClient.diff)
        return DeserializeResult(base=base_bundle, desired=desired_bundle)

    def _load_base(self, folder: Path) -> DocumentWithComments:
        """Load the transport-accurate base from .raw/document.json."""
        raw_doc_path = folder / _RAW_DIR / "document.json"
        raw_data = json.loads(raw_doc_path.read_text(encoding="utf-8"))
        doc = Document.model_validate(raw_data)
        # Use pristine comments as base comments
        pristine_bundle = self._load_pristine(folder)
        return DocumentWithComments(document=doc, comments=pristine_bundle.comments)

    def _load_pristine(self, folder: Path) -> DocumentWithComments:
        """Extract and parse .pristine/document.zip."""
        pristine_zip = folder / _PRISTINE_DIR / _PRISTINE_ZIP
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(pristine_zip, "r") as zf:
                zf.extractall(tmp)
            return self._parse(Path(tmp))

    def _parse(self, folder: Path) -> DocumentWithComments:
        """Read an XML-format folder into a DocumentWithComments."""
        index_path = folder / "index.xml"
        index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))

        tabs: dict[str, TabFiles] = {}
        for index_tab in index.all_tabs_flat():
            tab_dir = folder / index_tab.folder
            doc_path = tab_dir / "document.xml"
            styles_path = tab_dir / "styles.xml"

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

        comments_path = folder / "comments.xml"
        if comments_path.exists():
            file_comments = comments_from_xml(comments_path.read_text(encoding="utf-8"))
        else:
            file_comments = FileComments(file_id=index.id)

        return DocumentWithComments(document=document, comments=file_comments)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def from_document(
    doc: Document,
) -> tuple[IndexXml, dict[str, TabFiles]]:
    """Convert Document to XML models (no file I/O)."""
    tabs = document_to_xml(doc)

    folder_map: dict[str, str] = {}
    tab_xml_map: dict[str, TabXml] = {}
    for folder_name, tab_files in tabs.items():
        folder_map[tab_files.tab.id] = folder_name
        tab_xml_map[tab_files.tab.id] = tab_files.tab

    index = build_index(doc, folder_map, tab_xml_map)
    return index, tabs


def to_document(
    tabs: dict[str, TabFiles],
    document_id: str = "",
    title: str = "",
) -> Document:
    """Convert XML models to Document (no file I/O, no indices)."""
    return tabs_to_document(tabs, document_id=document_id, title=title)


def _read_extra(path: Path, cls: type[_T]) -> _T | None:
    """Read an optional extra XML file, returning None if it doesn't exist."""
    if path.exists():
        return cls.from_xml_string(path.read_text(encoding="utf-8"))  # type: ignore[attr-defined, no-any-return]
    return None


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
    from extradoc.diffmerge import apply as apply_ops_to_document
    from extradoc.diffmerge import diff as reconcile_diff

    base_dict = base.document.model_dump(by_alias=True, exclude_none=True)

    ops = reconcile_diff(ancestor.document, mine.document)
    desired_dict = apply_ops_to_document(base_dict, ops)
    desired_document = base.document.__class__.model_validate(desired_dict)

    return DocumentWithComments(document=desired_document, comments=mine.comments)


__all__ = [
    "XmlSerde",
    "from_document",
    "to_document",
]
