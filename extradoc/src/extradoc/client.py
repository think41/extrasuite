"""DocsClient - main interface for extradoc pull/diff/push operations.

Consolidates all operations into a single client class following
the same pattern as SheetsClient, SlidesClient, and FormsClient.
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from extradoc.comments_converter import (
    CommentOperations,
    compute_comment_ref_positions,
    convert_comments_to_xml,
    diff_comments,
    extract_comment_ref_ids,
)
from extradoc.desugar import desugar_document
from extradoc.engine import DiffEngine
from extradoc.request_generators.structural import (
    extract_placeholder_footnote_ids,
    separate_by_segment_ids,
)
from extradoc.xml_converter import convert_document_to_xml

if TYPE_CHECKING:
    from extradoc.transport import Transport

logger = logging.getLogger(__name__)

# File and directory name constants
DOCUMENT_XML = "document.xml"
STYLES_XML = "styles.xml"
COMMENTS_XML = "comments.xml"
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
    comments_created: int = 0
    replies_created: int = 0
    comments_resolved: int = 0


def _new_tab_ids(pristine_xml: str, current_xml: str) -> list[str]:
    """Detect tab IDs present in current but not in pristine."""
    pristine_tabs = set(re.findall(r'<tab\s+id="([^"]+)"', pristine_xml))
    current_tabs = re.findall(r'<tab\s+id="([^"]+)"', current_xml)
    return [tid for tid in current_tabs if tid not in pristine_tabs]


class DocsClient:
    """Main client for Google Docs pull/diff/push operations.

    Wraps a Transport instance to provide the full workflow.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def pull(
        self,
        document_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
    ) -> list[Path]:
        """Pull a document from Google Docs to local files.

        Args:
            document_id: The document identifier
            output_path: Parent directory for the output folder
            save_raw: Whether to save raw API responses to .raw/ folder

        Returns:
            List of file paths written
        """
        output_path = Path(output_path)
        document_data = await self._transport.get_document(document_id)

        document_dir = output_path / document_id
        document_dir.mkdir(parents=True, exist_ok=True)

        written_files: list[Path] = []

        # Fetch comments first so we can inject <comment-ref> tags into document.xml
        comments = await self._transport.list_comments(document_id)

        document_xml, styles_xml = convert_document_to_xml(
            document_data.raw, comments=comments or None
        )

        xml_path = document_dir / DOCUMENT_XML
        xml_path.write_text(document_xml, encoding="utf-8")
        written_files.append(xml_path)

        styles_path = document_dir / STYLES_XML
        styles_path.write_text(styles_xml, encoding="utf-8")
        written_files.append(styles_path)

        # Write simplified comments.xml (no position info)
        if comments:
            comments_xml = convert_comments_to_xml(comments, document_id)
            comments_path = document_dir / COMMENTS_XML
            comments_path.write_text(comments_xml, encoding="utf-8")
            written_files.append(comments_path)

        if save_raw:
            raw_dir = document_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / "document.json"
            raw_path.write_text(
                json.dumps(document_data.raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_path)
            if comments:
                comments_raw_path = raw_dir / "comments.json"
                comments_raw_path.write_text(
                    json.dumps({"comments": comments}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                written_files.append(comments_raw_path)

        pristine_path = self._create_pristine_copy(document_dir, written_files)
        written_files.append(pristine_path)

        return written_files

    def diff(
        self, folder: str | Path
    ) -> tuple[str, list[dict[str, Any]], Any, CommentOperations]:
        """Compare current files against pristine and generate batchUpdate requests.

        This is local-only and does not make any API calls.

        Args:
            folder: Path to document folder (containing document.xml)

        Returns:
            Tuple of (document_id, requests, change_tree, comment_ops)
        """
        folder = Path(folder)

        # Read current files
        current_xml = (folder / DOCUMENT_XML).read_text(encoding="utf-8")
        current_styles: str | None = None
        styles_path = folder / STYLES_XML
        if styles_path.exists():
            current_styles = styles_path.read_text(encoding="utf-8")

        # Read pristine from zip
        pristine_xml, pristine_styles, document_id = self._read_pristine(folder)

        # Run engine
        engine = DiffEngine()
        requests, change_tree = engine.diff(
            pristine_xml, current_xml, pristine_styles, current_styles
        )

        # Diff comments
        comment_ops = CommentOperations()
        comments_path = folder / COMMENTS_XML
        if comments_path.exists():
            current_comments_xml = comments_path.read_text(encoding="utf-8")
            pristine_comments_xml = self._read_pristine_comments(folder)

            # Detect new comment-refs in document.xml
            current_ref_ids = extract_comment_ref_ids(current_xml)
            pristine_ref_ids = extract_comment_ref_ids(pristine_xml)
            new_ref_ids = current_ref_ids - pristine_ref_ids

            # Compute positions for new comment-refs
            new_positions = None
            if new_ref_ids:
                all_positions = compute_comment_ref_positions(current_xml)
                new_positions = [
                    p for p in all_positions if p.comment_ref_id in new_ref_ids
                ]

            comment_ops = diff_comments(
                pristine_comments_xml, current_comments_xml, new_positions
            )

        return document_id, requests, change_tree, comment_ops

    async def push(self, folder: str | Path, *, force: bool = False) -> PushResult:
        """Push local changes to Google Docs using 3-batch strategy.

        Args:
            folder: Path to document folder (containing document.xml)
            force: Force push despite warnings

        Returns:
            PushResult with success status and details
        """
        _ = force  # reserved for future use
        folder = Path(folder)
        document_id, requests, _change_tree, comment_ops = self.diff(folder)

        if not requests and not comment_ops.has_operations:
            return PushResult(
                success=True,
                document_id=document_id,
                changes_applied=0,
                message="No changes to apply",
            )

        # --- Comment operations (BEFORE document changes) ---
        # Comments use Drive API v3 (separate from Docs batchUpdate).
        # Anchor positions are computed against the current live document
        # (which matches pristine), so we must create comments before any
        # document changes shift positions.
        comments_created = 0
        replies_created = 0
        comments_resolved = 0

        if comment_ops.has_operations:
            # New top-level comments are not supported. The Google Drive
            # API cannot anchor comments to specific text in Google Docs —
            # every strategy we tried results in "Original content deleted".
            # See extradoc/docs/comment-anchoring-limitation.md for the
            # full investigation and Google Issue Tracker references.
            if comment_ops.new_comments:
                logger.warning(
                    "Skipping %d new comment(s): creating top-level comments "
                    "is not supported by the Google Drive API",
                    len(comment_ops.new_comments),
                )

            for new_reply in comment_ops.new_replies:
                await self._transport.create_reply(
                    document_id, new_reply.comment_id, new_reply.content
                )
                replies_created += 1

            for resolve in comment_ops.resolves:
                await self._transport.create_reply(
                    document_id,
                    resolve.comment_id,
                    "",
                    action="resolve",
                )
                comments_resolved += 1

        # --- Classify requests ---
        tab_create_requests: list[dict[str, Any]] = []
        hf_create_requests: list[dict[str, Any]] = []
        other_requests: list[dict[str, Any]] = []
        for req in requests:
            if "addDocumentTab" in req:
                tab_create_requests.append(req)
            elif "createHeader" in req or "createFooter" in req:
                hf_create_requests.append(req)
            else:
                other_requests.append(req)

        # Identify new sections for ID mapping
        current_xml = (folder / DOCUMENT_XML).read_text(encoding="utf-8")
        current_styles: str | None = None
        if (folder / STYLES_XML).exists():
            current_styles = (folder / STYLES_XML).read_text(encoding="utf-8")
        pristine_xml, pristine_styles, _ = self._read_pristine(folder)

        current_doc = desugar_document(current_xml, current_styles)
        pristine_doc = desugar_document(pristine_xml, pristine_styles)

        def _new_section_ids(section_type: str) -> list[str]:
            pristine_ids = {
                s.section_id
                for s in pristine_doc.sections
                if s.section_type == section_type
            }
            return [
                s.section_id
                for s in current_doc.sections
                if s.section_type == section_type and s.section_id not in pristine_ids
            ]

        new_headers = _new_section_ids("header")
        new_footers = _new_section_ids("footer")
        # Detect new tab IDs
        new_tabs = _new_tab_ids(pristine_xml, current_xml)

        header_id_map: dict[str, str] = {}
        footer_id_map: dict[str, str] = {}
        footnote_id_map: dict[str, str] = {}
        tab_id_map: dict[str, str] = {}

        # Rewrite segment IDs and tab IDs
        def _rewrite(obj: Any, *, footnote_map: dict[str, str] | None = None) -> Any:
            if isinstance(obj, dict):
                rewritten: dict[str, Any] = {}
                for k, v in obj.items():
                    if k == "segmentId":
                        if v in header_id_map:
                            rewritten[k] = header_id_map[v]
                            continue
                        if v in footer_id_map:
                            rewritten[k] = footer_id_map[v]
                            continue
                        if footnote_map and v in footnote_map:
                            rewritten[k] = footnote_map[v]
                            continue
                    if k == "tabId" and isinstance(v, str) and v in tab_id_map:
                        rewritten[k] = tab_id_map[v]
                        continue
                    rewritten[k] = _rewrite(v, footnote_map=footnote_map)
                return rewritten
            if isinstance(obj, list):
                return [_rewrite(x, footnote_map=footnote_map) for x in obj]
            return obj

        # --- Batch 1a: Tab creation -> capture real tab IDs ---
        if tab_create_requests:
            tab_response = await self._transport.batch_update(
                document_id, tab_create_requests
            )
            t_idx = 0
            for rep in tab_response.get("replies", []):
                if "addDocumentTab" in rep and t_idx < len(new_tabs):
                    tab_props = rep["addDocumentTab"].get("tabProperties", {})
                    real_id = tab_props.get("tabId")
                    if real_id:
                        tab_id_map[new_tabs[t_idx]] = real_id
                    t_idx += 1

        # --- Batch 1b: Header/footer creation (with rewritten tab IDs) ---
        if hf_create_requests:
            if tab_id_map:
                hf_create_requests = [_rewrite(r) for r in hf_create_requests]
            hf_response = await self._transport.batch_update(
                document_id, hf_create_requests
            )
            h_idx = f_idx = 0
            for rep in hf_response.get("replies", []):
                if "createHeader" in rep and h_idx < len(new_headers):
                    real_id = rep["createHeader"].get("headerId")
                    if real_id:
                        header_id_map[new_headers[h_idx]] = real_id
                    h_idx += 1
                if "createFooter" in rep and f_idx < len(new_footers):
                    real_id = rep["createFooter"].get("footerId")
                    if real_id:
                        footer_id_map[new_footers[f_idx]] = real_id
                    f_idx += 1

        if header_id_map or footer_id_map or tab_id_map:
            other_requests = [_rewrite(r) for r in other_requests]

        # --- Batch 2: Main content + createFootnote ---
        # Extract placeholder IDs first, then use them to separate
        # footnote content requests into batch 3
        other_requests, footnote_placeholders = extract_placeholder_footnote_ids(
            other_requests
        )
        footnote_placeholder_ids = set(footnote_placeholders)
        main_requests, footnote_requests = separate_by_segment_ids(
            other_requests, footnote_placeholder_ids
        )

        # Build placeholder -> tabId mapping from createFootnote requests
        footnote_tab_ids: dict[str, str] = {}
        ph_iter = iter(footnote_placeholders)
        for req in main_requests:
            if "createFootnote" in req:
                tab_id_val = req["createFootnote"].get("location", {}).get("tabId", "")
                ph = next(ph_iter, None)
                if ph:
                    footnote_tab_ids[ph] = tab_id_val

        main_response: dict[str, Any] = {}
        if main_requests:
            main_response = await self._transport.batch_update(
                document_id, main_requests
            )

        # Map footnote placeholder IDs to real IDs
        replies = main_response.get("replies", [])
        fn_idx = 0
        for rep in replies:
            if "createFootnote" in rep:
                real_id = rep["createFootnote"].get("footnoteId")
                placeholder = ""
                if fn_idx < len(footnote_placeholders):
                    placeholder = footnote_placeholders[fn_idx]
                if placeholder and real_id:
                    footnote_id_map[placeholder] = real_id
                fn_idx += 1

        # --- Batch 3: Footnote content ---
        if header_id_map or footer_id_map or footnote_id_map:
            footnote_requests = [
                _rewrite(r, footnote_map=footnote_id_map) for r in footnote_requests
            ]

        if footnote_requests:
            cleanup_requests: list[dict[str, Any]] = []
            for ph_id in footnote_placeholders:
                real_id = footnote_id_map.get(ph_id, ph_id)
                tab_id_val = footnote_tab_ids.get(ph_id, "")
                cleanup_range: dict[str, Any] = {
                    "segmentId": real_id,
                    "startIndex": 0,
                    "endIndex": 1,
                }
                if tab_id_val:
                    cleanup_range["tabId"] = tab_id_val
                cleanup_requests.append(
                    {"deleteContentRange": {"range": cleanup_range}}
                )
            await self._transport.batch_update(
                document_id, cleanup_requests + footnote_requests
            )

        # Build result message
        parts: list[str] = []
        if requests:
            parts.append(f"{len(requests)} document changes")
        if comments_created:
            parts.append(f"{comments_created} comments created")
        if replies_created:
            parts.append(f"{replies_created} replies added")
        if comments_resolved:
            parts.append(f"{comments_resolved} comments resolved")

        message = "Applied " + ", ".join(parts) if parts else "No changes to apply"

        return PushResult(
            success=True,
            document_id=document_id,
            changes_applied=len(requests),
            message=message,
            comments_created=comments_created,
            replies_created=replies_created,
            comments_resolved=comments_resolved,
        )

    def _create_pristine_copy(
        self,
        document_dir: Path,
        written_files: list[Path],
    ) -> Path:
        """Create a pristine copy of the pulled files for diff/push workflow."""
        pristine_dir = document_dir / PRISTINE_DIR
        pristine_dir.mkdir(parents=True, exist_ok=True)

        zip_path = pristine_dir / PRISTINE_ZIP

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in written_files:
                if any(d in file_path.parts for d in [RAW_DIR, PRISTINE_DIR]):
                    continue
                arcname = file_path.relative_to(document_dir)
                zf.write(file_path, arcname)

        return zip_path

    def _read_pristine_comments(self, folder: Path) -> str | None:
        """Read pristine comments.xml from zip, if it exists."""
        zip_path = folder / PRISTINE_DIR / PRISTINE_ZIP
        if not zip_path.exists():
            return None
        with zipfile.ZipFile(zip_path, "r") as zf:
            if COMMENTS_XML in zf.namelist():
                return zf.read(COMMENTS_XML).decode("utf-8")
        return None

    def _read_pristine(self, folder: Path) -> tuple[str, str | None, str]:
        """Read pristine XML files from zip."""
        zip_path = folder / PRISTINE_DIR / PRISTINE_ZIP
        if not zip_path.exists():
            raise FileNotFoundError(f"Pristine zip not found: {zip_path}")

        pristine_xml = ""
        pristine_styles: str | None = None

        with zipfile.ZipFile(zip_path, "r") as zf:
            if DOCUMENT_XML in zf.namelist():
                pristine_xml = zf.read(DOCUMENT_XML).decode("utf-8")
            else:
                raise FileNotFoundError(f"{DOCUMENT_XML} not found in pristine zip")

            if STYLES_XML in zf.namelist():
                pristine_styles = zf.read(STYLES_XML).decode("utf-8")

        # Extract document ID
        document_id = folder.name
        match = re.search(r'<doc\s+id="([^"]+)"', pristine_xml)
        if match:
            document_id = match.group(1)

        return pristine_xml, pristine_styles, document_id
