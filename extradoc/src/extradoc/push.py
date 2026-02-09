"""Push orchestration for ExtraDoc v2.

Implements the 3-batch strategy:
1. Batch 1: createHeader / createFooter → capture real IDs
2. Batch 2: Main body + createFootnote → capture real footnote IDs
3. Batch 3: Footnote content requests (with rewritten segment IDs)
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from extradoc.desugar import desugar_document
from extradoc.request_generators.structural import (
    extract_placeholder_footnote_ids,
    separate_by_segment_ids,
)

from .engine import DiffEngine

if TYPE_CHECKING:
    from extradoc.transport import Transport

    from .types import ChangeNode

# File constants
DOCUMENT_XML = "document.xml"
STYLES_XML = "styles.xml"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "document.zip"


@dataclass
class PushResult:
    """Result of a push operation."""

    success: bool
    document_id: str
    changes_applied: int
    message: str = ""


class PushClient:
    """Handles the v2 push workflow."""

    def diff(self, folder: Path) -> tuple[str, list[dict[str, Any]], ChangeNode]:
        """Run the v2 diff on a folder.

        Returns (document_id, requests, change_tree).
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

        return document_id, requests, change_tree

    async def push(
        self,
        folder: Path,
        transport: Transport,
        force: bool = False,  # noqa: ARG002
    ) -> PushResult:
        """Push local changes to Google Docs using 3-batch strategy."""
        folder = Path(folder)
        document_id, requests, _change_tree = self.diff(folder)

        if not requests:
            return PushResult(
                success=True,
                document_id=document_id,
                changes_applied=0,
                message="No changes to apply",
            )

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
        current_styles = None
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
        new_tab_ids = _new_tab_ids(pristine_xml, current_xml)

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

        # --- Batch 1a: Tab creation → capture real tab IDs ---
        if tab_create_requests:
            tab_response = await transport.batch_update(
                document_id, tab_create_requests
            )
            t_idx = 0
            for rep in tab_response.get("replies", []):
                if "addDocumentTab" in rep and t_idx < len(new_tab_ids):
                    tab_props = rep["addDocumentTab"].get("tabProperties", {})
                    real_id = tab_props.get("tabId")
                    if real_id:
                        tab_id_map[new_tab_ids[t_idx]] = real_id
                    t_idx += 1

        # --- Batch 1b: Header/footer creation (with rewritten tab IDs) ---
        if hf_create_requests:
            if tab_id_map:
                hf_create_requests = [_rewrite(r) for r in hf_create_requests]
            hf_response = await transport.batch_update(document_id, hf_create_requests)
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

        # Build placeholder → tabId mapping from createFootnote requests
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
            main_response = await transport.batch_update(document_id, main_requests)

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
            await transport.batch_update(
                document_id, cleanup_requests + footnote_requests
            )

        return PushResult(
            success=True,
            document_id=document_id,
            changes_applied=len(requests),
            message=f"Applied {len(requests)} changes",
        )

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


def _new_tab_ids(pristine_xml: str, current_xml: str) -> list[str]:
    """Detect tab IDs present in current but not in pristine."""
    pristine_tabs = set(re.findall(r'<tab\s+id="([^"]+)"', pristine_xml))
    current_tabs = re.findall(r'<tab\s+id="([^"]+)"', current_xml)
    return [tid for tid in current_tabs if tid not in pristine_tabs]
