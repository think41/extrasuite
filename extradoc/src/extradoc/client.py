"""DocsClient - main interface for extradoc pull/diff/push operations.

Orchestrates pull/diff/push using serde + reconcile + comments packages.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import extradoc.serde as serde
from extradoc.api_types._generated import (
    Document,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    TableCell,
    TextRun,
    TextStyle,
)
from extradoc.comments._diff import diff_comments
from extradoc.comments._from_raw import from_raw as comments_from_raw
from extradoc.comments._types import (
    CommentOperations,
    DocumentWithComments,
)
from extradoc.reconcile import reconcile, reindex_document, resolve_deferred_ids
from extradoc.serde._models import IndexXml
from extradoc.serde._utils import hex_to_optional_color, optional_color_to_hex

if TYPE_CHECKING:
    from extradoc.api_types._generated import BatchUpdateDocumentRequest
    from extradoc.transport import Transport

logger = logging.getLogger(__name__)

# Directory / file constants
RAW_DIR = ".raw"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "document.zip"


@dataclass
class PushResult:
    """Result of a push operation."""

    success: bool
    document_id: str
    changes_applied: int
    message: str = ""
    replies_created: int = 0
    comments_resolved: int = 0


@dataclass
class DiffResult:
    """Internal result of diff() — input for push()."""

    document_id: str
    batches: list[BatchUpdateDocumentRequest]
    comment_ops: CommentOperations


class DocsClient:
    """Main client for Google Docs pull/diff/push operations."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def pull(
        self,
        document_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
        format: str = "xml",
    ) -> list[Path]:
        """Pull a document from Google Docs to local files.

        Args:
            document_id: The document identifier
            output_path: Parent directory for the output folder
            save_raw: Whether to save raw API responses to .raw/ folder
            format: Output format — "xml" (default) or "markdown"

        Returns:
            List of file paths written
        """
        output_path = Path(output_path)

        # Fetch document and comments in parallel
        document_data = await self._transport.get_document(document_id)
        raw_comments = await self._transport.list_comments(document_id)

        # Parse into typed models
        doc = Document.model_validate(document_data.raw)
        file_comments = comments_from_raw(document_id, raw_comments)
        bundle = DocumentWithComments(document=doc, comments=file_comments)

        document_dir = output_path / document_id
        document_dir.mkdir(parents=True, exist_ok=True)

        # Serialize bundle to folder
        written_files = serde.serialize(bundle, document_dir, format=format)

        # Optionally save raw API responses
        if save_raw:
            raw_dir = document_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)

            raw_doc_path = raw_dir / "document.json"
            raw_doc_path.write_text(
                json.dumps(document_data.raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_doc_path)

            if raw_comments:
                raw_comments_path = raw_dir / "comments.json"
                raw_comments_path.write_text(
                    json.dumps(
                        {"comments": raw_comments}, indent=2, ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                written_files.append(raw_comments_path)

        # Create pristine zip from the serde output
        pristine_path = _create_pristine_zip(document_dir)
        written_files.append(pristine_path)

        return written_files

    def diff(self, folder: str | Path) -> DiffResult:
        """Compare current files against pristine and generate batch requests.

        This is local-only and does not make any API calls.

        For markdown-format folders: if .raw/document.json exists, the raw
        Google Docs API response is used as the base document.  This gives
        accurate real-API startIndex values so the reconciler generates valid
        deleteContentRange/updateTextStyle requests.  Without it the mock
        reindexer's table-overhead undercount causes deleteContentRange to
        start before the true cell boundary and the API rejects the request.

        Args:
            folder: Path to document folder (containing index.xml)

        Returns:
            DiffResult with document_id, batches, and comment_ops
        """
        folder = Path(folder)
        document_id = _read_document_id(folder)

        with tempfile.TemporaryDirectory() as tmp:
            _extract_pristine_zip(folder, Path(tmp))
            base_bundle = serde.deserialize(Path(tmp))

        desired_bundle = serde.deserialize(folder)

        # For markdown format, prefer the raw API JSON as the base document so
        # that generated requests carry real startIndex values rather than the
        # mock reindexer's approximations.  The raw JSON already has valid
        # indices — do NOT call reindex_document() on it, as that would
        # overwrite accurate API indices with mock-computed approximations.
        raw_doc_path = folder / RAW_DIR / "document.json"
        if raw_doc_path.exists():
            index_path = folder / "index.xml"
            index = serde.IndexXml.from_xml_string(
                index_path.read_text(encoding="utf-8")
            )
            if index.format == "markdown":
                raw_data = json.loads(raw_doc_path.read_text(encoding="utf-8"))
                base = Document.model_validate(raw_data)
                # Strip inherited paragraph style defaults from the raw JSON base
                # so it is consistent with the markdown-serde-derived desired document.
                # Without this, the reconciler generates spurious updateParagraphStyle
                # requests for every unchanged paragraph (e.g. lineSpacing, direction).
                _normalize_raw_base_para_styles(base)
                desired = reindex_document(desired_bundle.document)
                batches = reconcile(base, desired)
                comment_ops = diff_comments(
                    base_bundle.comments, desired_bundle.comments
                )
                return DiffResult(
                    document_id=document_id,
                    batches=batches,
                    comment_ops=comment_ops,
                )

        base = reindex_document(base_bundle.document)
        desired = reindex_document(desired_bundle.document)
        batches = reconcile(base, desired)

        comment_ops = diff_comments(base_bundle.comments, desired_bundle.comments)

        return DiffResult(
            document_id=document_id,
            batches=batches,
            comment_ops=comment_ops,
        )

    async def push(self, folder: str | Path, *, force: bool = False) -> PushResult:
        """Push local changes to Google Docs.

        Comment operations execute before document changes so that anchor
        positions (relative to the current live document) are not shifted
        by document mutations.

        Args:
            folder: Path to document folder
            force: Reserved for future use

        Returns:
            PushResult with success status and details
        """
        _ = force
        folder = Path(folder)
        result = self.diff(folder)

        if not result.batches and not result.comment_ops.has_operations:
            return PushResult(
                success=True,
                document_id=result.document_id,
                changes_applied=0,
                message="No changes to apply",
            )

        # --- 1. Comment operations (Drive API — before document changes) ---
        replies_created = 0
        comments_resolved = 0
        edits_applied = 0
        ops = result.comment_ops

        for r in ops.new_replies:
            await self._transport.create_reply(
                result.document_id, r.comment_id, r.content
            )
            replies_created += 1

        for s in ops.resolves:
            await self._transport.create_reply(
                result.document_id, s.comment_id, "", action="resolve"
            )
            comments_resolved += 1

        for e in ops.edits:
            await self._transport.edit_comment(
                result.document_id, e.comment_id, e.content
            )
            edits_applied += 1

        for d in ops.deletes:
            await self._transport.delete_comment(result.document_id, d.comment_id)

        for re_ in ops.reply_edits:
            await self._transport.edit_reply(
                result.document_id, re_.comment_id, re_.reply_id, re_.content
            )
            edits_applied += 1

        # --- 2. Document batches (Docs API — reconcile output) ---
        prior_responses: list[dict] = []  # type: ignore[type-arg]
        changes_applied = 0

        for i, batch in enumerate(result.batches):
            if i > 0:
                batch = resolve_deferred_ids(prior_responses, batch)
            resp = await self._transport.batch_update(
                result.document_id,
                [
                    r.model_dump(by_alias=True, exclude_none=True)
                    for r in (batch.requests or [])
                ],
            )
            prior_responses.append(resp)
            changes_applied += len(batch.requests or [])

        # Build result message
        parts: list[str] = []
        if changes_applied:
            parts.append(f"{changes_applied} document changes")
        if replies_created:
            parts.append(f"{replies_created} replies added")
        if comments_resolved:
            parts.append(f"{comments_resolved} comments resolved")
        if edits_applied:
            parts.append(f"{edits_applied} comment edits")

        message = "Applied " + ", ".join(parts) if parts else "No changes to apply"

        return PushResult(
            success=True,
            document_id=result.document_id,
            changes_applied=changes_applied,
            message=message,
            replies_created=replies_created,
            comments_resolved=comments_resolved,
        )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _normalize_raw_base_para_styles(doc: Document) -> None:
    """Normalise the raw API JSON base document so it is consistent with the
    markdown-serde-derived desired document.

    Two classes of normalisation are applied:

    1. **Paragraph style reduction** — The markdown serde only ever sets
       ``namedStyleType`` on paragraph styles.  All other fields (lineSpacing,
       avoidWidowAndOrphan, spaceAbove, direction, alignment, …) come from the
       raw API as inherited or table-default values that markdown cannot express.
       Without stripping them, reconcile() generates hundreds of spurious
       updateParagraphStyle requests for every unchanged paragraph.

    2. **Inter-table separator paragraph removal** — The real Google Docs API
       automatically inserts an empty ``\\n`` paragraph between two adjacent
       tables (and after every table insertion).  The markdown serde does not
       produce these separator paragraphs, so the base would have them but the
       desired would not.  Leaving them in triggers spurious DELETE + INSERT
       sequences for unchanged callout/codeblock tables, causing insertTable
       requests to target invalid positions.

    The structural content (tables, named ranges) and all index values are
    unchanged — the raw JSON is still used for accurate startIndex/endIndex
    values in deleteContentRange requests.
    """
    if not doc.tabs:
        return

    for tab in doc.tabs:
        dt = tab.document_tab
        if not dt:
            continue
        if dt.body and dt.body.content:
            # 1. Strip inter-table separator paragraphs
            dt.body.content = _strip_inter_table_separators(dt.body.content)
            # 2. Normalise paragraph styles
            for se in dt.body.content:
                _normalize_structural_element_para_styles(se)
            # 3. Ensure a trailing empty paragraph exists.
            # Some raw API documents omit the synthetic trailing paragraph and
            # instead have the last content paragraph's '\n' serve as the
            # terminator.  The markdown serde (_ensure_trailing_paragraph)
            # always adds an explicit trailing paragraph, so the base needs one
            # too to avoid a spurious insertText "\n" at the end.
            _ensure_base_trailing_paragraph(dt.body.content)


def _strip_inter_table_separators(
    content: list[StructuralElement],
) -> list[StructuralElement]:
    """Remove empty paragraphs that sit between two tables in the body.

    The real Google Docs API always inserts a trailing paragraph after every
    table, so consecutive tables are separated by an empty '\\n' paragraph.
    The markdown serde doesn't produce these separator paragraphs.  To keep
    the base consistent with the desired document, drop any paragraph whose
    sole content is '\\n' when it is surrounded by tables.
    """
    out: list[StructuralElement] = []
    n = len(content)
    for i, se in enumerate(content):
        if se.paragraph:
            # Check if this is a bare '\n' separator between two tables
            para = se.paragraph
            elements = para.elements or []
            text = "".join(
                e.text_run.content for e in elements if e.text_run and e.text_run.content
            )
            if text == "\n":
                # Look for a table before and after this paragraph
                prev_is_table = any(out) and out[-1].table is not None
                next_is_table = (
                    i + 1 < n and content[i + 1].table is not None
                )
                if prev_is_table and next_is_table:
                    continue  # skip this inter-table separator
        out.append(se)
    return out


def _normalize_structural_element_para_styles(se: StructuralElement) -> None:
    """Recursively strip non-markdown paragraph style fields from a StructuralElement."""
    if se.paragraph:
        _normalize_paragraph(se.paragraph)
    elif se.table:
        for row in se.table.table_rows or []:
            for cell in row.table_cells or []:
                _normalize_table_cell_style(cell)
                for cell_se in cell.content or []:
                    _normalize_structural_element_para_styles(cell_se)


def _normalize_table_cell_style(cell: TableCell) -> None:
    """Normalize table cell backgroundColor by round-tripping through hex.

    The Google Docs API returns truncated float values for RGB colors
    (e.g. 0.81960785) while our hex_to_rgb computes full Python float
    precision (0.8196078431372549).  Round-tripping through hex normalizes
    both representations to the same float values so the reconciler does
    not generate spurious updateTableCellStyle backgroundColor requests.
    """
    style = cell.table_cell_style
    if not style or not style.background_color:
        return
    hex_val = optional_color_to_hex(style.background_color)
    if hex_val:
        style.background_color = hex_to_optional_color(hex_val)


def _normalize_paragraph(para: Paragraph) -> None:
    """Reduce paragraph style and text run styles in-place for markdown consistency.

    Two normalisations:

    1. **Paragraph style reduction** — The markdown serde only sets
       ``namedStyleType`` on paragraph styles.  All other fields are stripped.

    2. **Text run normalisation** — Strip non-markdown text run style fields
       (fontSize, foregroundColor, backgroundColor, etc.) that the markdown
       serde cannot express.  Also replace U+000B (vertical tab / line break)
       in run content with a plain space to match what mistletoe produces when
       re-parsing the serialized markdown.
    """
    ps = para.paragraph_style
    if ps:
        para.paragraph_style = ParagraphStyle(named_style_type=ps.named_style_type)

    new_elements: list[ParagraphElement] = []
    for elem in para.elements or []:
        tr = elem.text_run
        if not tr:
            new_elements.append(elem)
            continue
        # Replace vertical tab with a space so the base fingerprint matches
        # what mistletoe produces when parsing the serialized markdown.
        if tr.content and "\u000b" in tr.content:
            tr.content = tr.content.replace("\u000b", " ")
        content = tr.content or ""
        # If a run embeds the paragraph-terminal '\n' in the middle of other
        # text (e.g. "Recruit41 Playbook\n" as one bold run), split it into a
        # styled text part and an unstyled '\n' part.  The markdown serde
        # always produces a separate bare '\n' run, so splitting here keeps
        # the run count equal and avoids falling into positional comparison.
        if content.endswith("\n") and len(content) > 1:
            text_part = content[:-1]
            si = elem.start_index
            ei = elem.end_index
            text_end = (si + len(text_part)) if si is not None else None
            text_elem = ParagraphElement(
                text_run=TextRun(content=text_part, text_style=tr.text_style),
                start_index=si,
                end_index=text_end,
            )
            nl_elem = ParagraphElement(
                text_run=TextRun(content="\n", text_style=None),
                start_index=text_end,
                end_index=ei,
            )
            new_elements.append(text_elem)
            new_elements.append(nl_elem)
            # Normalise the text part's style in-place below
            tr = text_elem.text_run
            assert tr is not None
        else:
            new_elements.append(elem)
        # The trailing '\n' run always has no style in the markdown-serde
        # desired document.  Strip all styles on '\n'-only runs.
        if content == "\n":
            tr.text_style = None
            continue
        # Strip non-markdown text run style fields from the base so that
        # matched paragraphs don't generate spurious updateTextStyle requests.
        if tr.text_style:
            ts = tr.text_style
            tr.text_style = TextStyle(
                bold=ts.bold,
                italic=ts.italic,
                strikethrough=ts.strikethrough,
                underline=ts.underline,
                link=ts.link,
                weighted_font_family=ts.weighted_font_family,
            )
    para.elements = new_elements


def _ensure_base_trailing_paragraph(content: list[StructuralElement]) -> None:
    """Add a synthetic trailing empty paragraph to the base if one is absent.

    Some Google Docs API responses omit the required trailing empty paragraph,
    relying on the last content paragraph's terminal '\\n' instead.  The
    markdown serde (_ensure_trailing_paragraph) always adds an explicit empty
    trailing paragraph.  Without this, the LCS alignment sees one extra
    ADDED element in the desired, generating a spurious insertText "\\n".
    """
    if not content:
        return
    last = content[-1]
    if last.paragraph is None:
        return  # Ends with a table or section break — leave as-is
    elems = last.paragraph.elements or []
    if len(elems) == 1:
        tr = elems[0].text_run
        if tr and tr.content == "\n":
            return  # Already has a trailing empty paragraph

    # Last paragraph is non-empty — add a synthetic trailing paragraph.
    # Use the end_index of the last element as the start of the new paragraph.
    ei = last.end_index
    synthetic = StructuralElement(
        paragraph=Paragraph(
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            elements=[ParagraphElement(text_run=TextRun(content="\n"))],
        ),
        start_index=ei,
        end_index=(ei + 1) if ei is not None else None,
    )
    content.append(synthetic)


def _create_pristine_zip(folder: Path) -> Path:
    """Zip the entire serde output (excluding .pristine/ and .raw/) into pristine zip.

    Args:
        folder: The document folder to zip

    Returns:
        Path to the created zip file
    """
    pristine_dir = folder / PRISTINE_DIR
    pristine_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pristine_dir / PRISTINE_ZIP

    _skip_dirs = {PRISTINE_DIR, RAW_DIR}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_dir():
                continue
            # Skip anything inside .pristine/ or .raw/
            try:
                rel = path.relative_to(folder)
            except ValueError:
                continue
            if rel.parts[0] in _skip_dirs:
                continue
            zf.write(path, rel)

    return zip_path


def _extract_pristine_zip(folder: Path, dest: Path) -> None:
    """Extract the pristine zip into dest directory.

    Args:
        folder: The document folder containing .pristine/document.zip
        dest: Destination directory to extract into
    """
    zip_path = folder / PRISTINE_DIR / PRISTINE_ZIP
    if not zip_path.exists():
        raise FileNotFoundError(f"Pristine zip not found: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def _read_document_id(folder: Path) -> str:
    """Read the document ID from index.xml.

    Args:
        folder: The document folder containing index.xml

    Returns:
        The document ID string
    """
    index_path = folder / "index.xml"
    if not index_path.exists():
        # Fall back to folder name
        return folder.name
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))
    return index.id or folder.name
