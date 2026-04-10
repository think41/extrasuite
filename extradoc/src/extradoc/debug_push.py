"""Debug artifacts for the push pipeline.

Dumps the full push-pipeline state (base doc, desired doc, diff ops,
batch requests) into ``<folder>/.debug/`` so an agent can inspect exactly
what the reconciler produced.  When a push fails with an API error, the
error message carries a ``requests[N]`` index — ``analyze_push_error``
reads back the dumped batch, extracts the failing request plus its
nearby context, and emits a focused narrative.

Usage:
    from extradoc.debug_push import dump_debug_artifacts, analyze_push_error
    debug_dir = dump_debug_artifacts("path/to/folder")
    # ... run the push ...
    # on failure:
    print(analyze_push_error("path/to/folder", api_error_message))
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Document,
    DocumentTab,
    Request,
    StructuralElement,
)
from extradoc.diffmerge import diff as diff_documents
from extradoc.mock.reindex import reindex_and_normalize_all_tabs
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde._models import IndexXml
from extradoc.serde.markdown import MarkdownSerde
from extradoc.serde.xml import XmlSerde

BODY_SEGMENT = ""  # Google's convention: empty segment_id == body


@dataclass
class SegmentSnapshot:
    """End-index of a single segment (body / header / footer / footnote)."""

    tab_id: str
    segment_id: str  # "" for body; otherwise header/footer/footnote id
    kind: str  # "body" | "header" | "footer" | "footnote"
    end_index: int


@dataclass
class RequestInfo:
    """Flattened view of a Request for debugging."""

    batch_index: int
    request_index: int  # within the batch
    op_type: str  # e.g. "insertText", "deleteContentRange"
    tab_id: str | None
    segment_id: str  # "" = body
    location_index: int | None  # None for end-of-segment / range-only ops
    range_start: int | None
    range_end: int | None
    delta: int  # +N for inserts, -N for deletes, 0 for styling
    preview: str  # short description
    raw: dict[str, Any]  # full serialized request for reference


# ──────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────


def dump_debug_artifacts(folder: str | Path) -> Path:
    """Run the offline half of the push pipeline and dump every artifact.

    Writes to ``<folder>/.debug/``:
      - ``base_document.json``     — base Document (post-serde, transport-accurate)
      - ``desired_document.json``  — desired Document (post merge+reindex)
      - ``diff_ops.txt``           — human-readable list of DiffOp
      - ``batch_requests.json``    — flat list of lowered requests, each tagged
                                     with ``batch_index`` and ``request_index``
      - ``segments.txt``           — base + desired per-segment end_index
      - ``base_segments_detail.txt`` — per-element index map of the base doc
      - ``desired_segments_detail.txt`` — per-element index map of the desired doc
      - ``report.txt``             — sections-1-4 narrative (same info, rendered)

    Returns the path to the ``.debug/`` directory.  Agents should read
    ``batch_requests.json`` when triaging a push failure — the flat index
    matches the ``requests[N]`` index in the API error message.
    """
    folder = Path(folder)
    debug_dir = folder / ".debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    # --- Load base and desired via serde ---
    # Markdown layout stores index.xml under .extrasuite/; XML layout keeps it at root.
    index_path = folder / ".extrasuite" / "index.xml"
    if not index_path.exists():
        index_path = folder / "index.xml"
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))
    serde: Any = (
        MarkdownSerde() if (index.format or "xml") == "markdown" else XmlSerde()
    )
    result = serde.deserialize(folder)

    base_doc = result.base.document
    desired_dict = result.desired.document.model_dump(by_alias=True, exclude_none=True)
    reindex_and_normalize_all_tabs(desired_dict)
    desired_doc = Document.model_validate(desired_dict)

    # --- Diff + lower ---
    ops = diff_documents(base_doc, desired_doc)
    batches = reconcile_batches(base_doc, desired_doc)

    base_segments = _collect_segments(base_doc)
    desired_segments = _collect_segments(desired_doc)
    flat_requests = _flatten_requests(batches)

    # --- Write JSON artifacts ---
    (debug_dir / "base_document.json").write_text(
        json.dumps(base_doc.model_dump(by_alias=True, exclude_none=True), indent=2),
        encoding="utf-8",
    )
    (debug_dir / "desired_document.json").write_text(
        json.dumps(desired_dict, indent=2),
        encoding="utf-8",
    )

    # batch_requests.json: list of {batch_index, request_index, op_type, request}
    flat_dump: list[dict[str, Any]] = []
    for b_i, batch in enumerate(batches):
        for r_i, req in enumerate(batch.requests or []):
            flat_dump.append(
                {
                    "batch_index": b_i,
                    "request_index": r_i,
                    "op_type": _request_op_type(req),
                    "request": req.model_dump(by_alias=True, exclude_none=True),
                }
            )
    (debug_dir / "batch_requests.json").write_text(
        json.dumps(flat_dump, indent=2),
        encoding="utf-8",
    )

    # diff_ops.txt
    diff_lines = [f"[{i:3}] {_describe_diff_op(op)}" for i, op in enumerate(ops)]
    (debug_dir / "diff_ops.txt").write_text(
        "\n".join(diff_lines) + "\n", encoding="utf-8"
    )

    # segments.txt
    seg_lines = ["# Base segments"]
    for s in base_segments:
        seg_lines.append(
            f"  tab={s.tab_id!r} segment={s.segment_id!r} kind={s.kind} "
            f"end_index={s.end_index}"
        )
    seg_lines.append("")
    seg_lines.append("# Desired segments (post merge+reindex)")
    for s in desired_segments:
        seg_lines.append(
            f"  tab={s.tab_id!r} segment={s.segment_id!r} kind={s.kind} "
            f"end_index={s.end_index}"
        )
    (debug_dir / "segments.txt").write_text(
        "\n".join(seg_lines) + "\n", encoding="utf-8"
    )

    # base_segments_detail.txt / desired_segments_detail.txt —
    # per-element index map, so you can answer "what is at index N?" without
    # navigating the nested JSON.
    (debug_dir / "base_segments_detail.txt").write_text(
        _render_segments_detail(base_doc), encoding="utf-8"
    )
    (debug_dir / "desired_segments_detail.txt").write_text(
        _render_segments_detail(desired_doc), encoding="utf-8"
    )

    # report.txt — sections 1-4 narrative (redundant with JSON but easier to skim)
    report = _render_report(
        folder=folder,
        document_id=index.id or folder.name,
        format=index.format or "xml",
        base_doc=base_doc,
        base_segments=base_segments,
        desired_segments=desired_segments,
        ops=ops,
        flat_requests=flat_requests,
    )
    (debug_dir / "report.txt").write_text(report, encoding="utf-8")

    return debug_dir


_REQUESTS_INDEX_RE = re.compile(r"requests\[(\d+)\]")


def analyze_push_error(
    folder: str | Path,
    error_message: str,
    *,
    batch_index: int = 0,
    context_window: int = 12,
) -> str:
    """Produce a focused narrative for a push-time API error.

    Parses ``requests[N]`` out of ``error_message`` and reads back the
    dumped batch from ``<folder>/.debug/batch_requests.json``.  Emits:
      - the raw error
      - the failing request's JSON body
      - the ``context_window`` requests that ran immediately before it
      - pointers to the ``.debug/`` artifacts for deeper investigation

    The Google Docs API aborts the batch on first failure, so requests
    after the failing one were NOT executed.
    """
    folder = Path(folder)
    debug_dir = folder / ".debug"
    batch_path = debug_dir / "batch_requests.json"

    lines: list[str] = []
    lines.append("═" * 78)
    lines.append("PUSH ERROR ANALYSIS")
    lines.append("═" * 78)
    lines.append("")
    lines.append("Error from Google Docs API:")
    for ln in error_message.strip().splitlines():
        lines.append(f"  {ln}")
    lines.append("")

    if not batch_path.exists():
        lines.append(
            f"  (no debug artifacts found at {debug_dir} — run push with "
            "--debug before the failure to enable analysis)"
        )
        return "\n".join(lines)

    m = _REQUESTS_INDEX_RE.search(error_message)
    if not m:
        lines.append(
            "  (could not find a 'requests[N]' reference in the error message; "
            "see the debug artifacts manually)"
        )
        lines.append(f"  debug artifacts: {debug_dir}/")
        return "\n".join(lines)

    failing_idx = int(m.group(1))

    flat = json.loads(batch_path.read_text(encoding="utf-8"))
    batch_reqs = [r for r in flat if r.get("batch_index") == batch_index]
    if not batch_reqs:
        lines.append(f"  (batch {batch_index} not found in {batch_path})")
        return "\n".join(lines)

    if failing_idx >= len(batch_reqs):
        lines.append(
            f"  (failing index {failing_idx} out of range: batch {batch_index} "
            f"has {len(batch_reqs)} requests)"
        )
        return "\n".join(lines)

    failing = batch_reqs[failing_idx]
    lines.append(
        f"Failing request: batch={batch_index} request_index={failing_idx} "
        f"op_type={failing['op_type']}"
    )
    lines.append("")
    lines.append("  Request JSON:")
    for ln in json.dumps(failing["request"], indent=2).splitlines():
        lines.append(f"    {ln}")
    lines.append("")

    start = max(0, failing_idx - context_window)
    lines.append(
        f"Preceding {failing_idx - start} requests in batch {batch_index} "
        f"(these ran successfully and may have shifted indices):"
    )
    for r in batch_reqs[start:failing_idx]:
        summary = _summarize_request_dict(r["request"])
        lines.append(f"  [{r['request_index']:4}] {r['op_type']:24} {summary}")
    lines.append("")
    lines.append(f"Full batch + base/desired documents: {debug_dir}/")
    lines.append("  - batch_requests.json  (flat list matching requests[N])")
    lines.append("  - base_document.json   (starting state)")
    lines.append("  - desired_document.json (target state)")
    lines.append("  - segments.txt          (per-segment end_index)")
    lines.append("  - diff_ops.txt          (structural ops before lowering)")
    lines.append("  - report.txt            (rendered summary)")
    lines.append("")
    lines.append("═" * 78)
    return "\n".join(lines)


def _summarize_request_dict(req: dict[str, Any]) -> str:
    """One-line summary of a serialized Request dict."""
    if "insertText" in req:
        it = req["insertText"]
        loc = it.get("location") or {}
        text = it.get("text", "")
        preview = text.replace("\n", "\\n")
        if len(preview) > 32:
            preview = preview[:32] + "…"
        return f"@idx={loc.get('index')}  {preview!r}"
    if "insertTable" in req:
        it = req["insertTable"]
        loc = it.get("location") or {}
        return f"@idx={loc.get('index')}  {it.get('rows')}x{it.get('columns')}"
    if "deleteContentRange" in req:
        rng = req["deleteContentRange"].get("range") or {}
        return f"range=[{rng.get('startIndex')}..{rng.get('endIndex')})"
    for key in (
        "updateTextStyle",
        "updateParagraphStyle",
        "createParagraphBullets",
        "createNamedRange",
    ):
        if key in req:
            rng = req[key].get("range") or {}
            return f"range=[{rng.get('startIndex')}..{rng.get('endIndex')})"
    return ""


def _request_op_type(req: Request) -> str:
    """Extract the op type from a Request (first non-None field)."""
    d = req.model_dump(by_alias=True, exclude_none=True)
    for key in d:
        return key
    return "unknown"


# ──────────────────────────────────────────────────────────────────────────
# Segment collection
# ──────────────────────────────────────────────────────────────────────────


def _collect_segments(doc: Document) -> list[SegmentSnapshot]:
    """Return per-segment end-index snapshots for every tab's body/header/footer/footnote."""
    snapshots: list[SegmentSnapshot] = []

    if doc.tabs:
        for tab in doc.tabs:
            tab_id = ""
            if tab.tab_properties and tab.tab_properties.tab_id:
                tab_id = tab.tab_properties.tab_id
            if tab.document_tab:
                snapshots.extend(_segments_from_doc_tab(tab_id, tab.document_tab))
    else:
        # Legacy single-tab
        body = doc.body
        if body and body.content:
            snapshots.append(
                SegmentSnapshot(
                    tab_id="",
                    segment_id=BODY_SEGMENT,
                    kind="body",
                    end_index=_end_of_content(body.content),
                )
            )
        # headers/footers/footnotes at document level
        for seg_id, header in (doc.headers or {}).items():
            snapshots.append(
                SegmentSnapshot(
                    tab_id="",
                    segment_id=seg_id,
                    kind="header",
                    end_index=_end_of_content(header.content or []),
                )
            )
        for seg_id, footer in (doc.footers or {}).items():
            snapshots.append(
                SegmentSnapshot(
                    tab_id="",
                    segment_id=seg_id,
                    kind="footer",
                    end_index=_end_of_content(footer.content or []),
                )
            )
        for seg_id, footnote in (doc.footnotes or {}).items():
            snapshots.append(
                SegmentSnapshot(
                    tab_id="",
                    segment_id=seg_id,
                    kind="footnote",
                    end_index=_end_of_content(footnote.content or []),
                )
            )

    return snapshots


def _segments_from_doc_tab(tab_id: str, dt: DocumentTab) -> list[SegmentSnapshot]:
    out: list[SegmentSnapshot] = []
    body = dt.body
    if body and body.content:
        out.append(
            SegmentSnapshot(
                tab_id=tab_id,
                segment_id=BODY_SEGMENT,
                kind="body",
                end_index=_end_of_content(body.content),
            )
        )
    for seg_id, header in (dt.headers or {}).items():
        out.append(
            SegmentSnapshot(
                tab_id=tab_id,
                segment_id=seg_id,
                kind="header",
                end_index=_end_of_content(header.content or []),
            )
        )
    for seg_id, footer in (dt.footers or {}).items():
        out.append(
            SegmentSnapshot(
                tab_id=tab_id,
                segment_id=seg_id,
                kind="footer",
                end_index=_end_of_content(footer.content or []),
            )
        )
    for seg_id, footnote in (dt.footnotes or {}).items():
        out.append(
            SegmentSnapshot(
                tab_id=tab_id,
                segment_id=seg_id,
                kind="footnote",
                end_index=_end_of_content(footnote.content or []),
            )
        )
    return out


def _end_of_content(content: list[StructuralElement]) -> int:
    last_end = 0
    for se in content:
        if se.end_index is not None and se.end_index > last_end:
            last_end = se.end_index
    return last_end


# ──────────────────────────────────────────────────────────────────────────
# Request flattening
# ──────────────────────────────────────────────────────────────────────────

# Map of request field name → human-readable op type
_REQUEST_FIELDS: dict[str, str] = {
    "insertText": "insertText",
    "deleteContentRange": "deleteContentRange",
    "insertTable": "insertTable",
    "insertTableRow": "insertTableRow",
    "insertTableColumn": "insertTableColumn",
    "deleteTableRow": "deleteTableRow",
    "deleteTableColumn": "deleteTableColumn",
    "insertSectionBreak": "insertSectionBreak",
    "insertPageBreak": "insertPageBreak",
    "insertInlineImage": "insertInlineImage",
    "createParagraphBullets": "createParagraphBullets",
    "deleteParagraphBullets": "deleteParagraphBullets",
    "updateTextStyle": "updateTextStyle",
    "updateParagraphStyle": "updateParagraphStyle",
    "updateDocumentStyle": "updateDocumentStyle",
    "updateTableCellStyle": "updateTableCellStyle",
    "updateTableRowStyle": "updateTableRowStyle",
    "updateTableColumnProperties": "updateTableColumnProperties",
    "createNamedRange": "createNamedRange",
    "deleteNamedRange": "deleteNamedRange",
    "createHeader": "createHeader",
    "createFooter": "createFooter",
    "createFootnote": "createFootnote",
    "deleteHeader": "deleteHeader",
    "deleteFooter": "deleteFooter",
    "addDocumentTab": "addDocumentTab",
    "deleteTab": "deleteTab",
    "mergeTableCells": "mergeTableCells",
    "unmergeTableCells": "unmergeTableCells",
    "replaceAllText": "replaceAllText",
}


def _flatten_requests(
    batches: list[BatchUpdateDocumentRequest],
) -> list[RequestInfo]:
    out: list[RequestInfo] = []
    for b_idx, batch in enumerate(batches):
        for r_idx, req in enumerate(batch.requests or []):
            raw = req.model_dump(by_alias=True, exclude_none=True, mode="python")
            op_type, body = _identify_op(raw)
            info = _analyze_op(b_idx, r_idx, op_type, body, raw)
            out.append(info)
    return out


def _identify_op(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for key in _REQUEST_FIELDS:
        if key in raw:
            val = raw[key]
            if isinstance(val, dict):
                return (key, val)
    # fallback: first key we see
    for k, v in raw.items():
        if isinstance(v, dict):
            return (k, v)
    return ("unknown", {})


def _analyze_op(
    batch_index: int,
    request_index: int,
    op_type: str,
    body: dict[str, Any],
    raw: dict[str, Any],
) -> RequestInfo:
    tab_id: str | None = None
    segment_id: str = BODY_SEGMENT
    location_index: int | None = None
    range_start: int | None = None
    range_end: int | None = None
    delta = 0
    preview = ""

    # --- location extraction ---
    loc = body.get("location") or body.get("endOfSegmentLocation")
    if isinstance(loc, dict):
        tab_id = loc.get("tabId")
        segment_id = loc.get("segmentId", "") or ""
        location_index = loc.get("index")

    range_obj = body.get("range") or body.get("textRange")
    if isinstance(range_obj, dict):
        tab_id = tab_id or range_obj.get("tabId")
        segment_id = range_obj.get("segmentId", segment_id) or segment_id
        range_start = range_obj.get("startIndex")
        range_end = range_obj.get("endIndex")

    # tableCellLocation (for insertTableRow, etc.) points at the table's start
    cell_loc = body.get("tableCellLocation")
    if isinstance(cell_loc, dict):
        tsl = cell_loc.get("tableStartLocation")
        if isinstance(tsl, dict):
            tab_id = tab_id or tsl.get("tabId")
            segment_id = tsl.get("segmentId", segment_id) or segment_id
            location_index = tsl.get("index")

    # --- delta + preview per op type ---
    if op_type == "insertText":
        text = body.get("text", "")
        delta = len(text)
        preview = _shorten(text)
    elif op_type == "deleteContentRange":
        if range_start is not None and range_end is not None:
            delta = -(range_end - range_start)
        preview = f"[{range_start}..{range_end})"
    elif op_type == "insertTable":
        rows = body.get("rows", 0)
        cols = body.get("columns", 0)
        # insertTable inserts: 1 (pre-\n at index) + 1 (table opener) +
        # rows * (1 (row opener) + cols * 2 (cell opener + terminal \n))
        # + 1 (trailing \n after last row).
        delta = 2 + rows * (1 + cols * 2) + 1
        preview = f"{rows}x{cols}"
    elif op_type in ("insertPageBreak", "insertSectionBreak", "insertInlineImage"):
        delta = 1
        preview = op_type
    elif op_type == "insertTableRow":
        preview = f"below={body.get('insertBelow', False)}"
    elif op_type == "insertTableColumn":
        preview = f"right={body.get('insertRight', False)}"
    elif op_type in ("deleteTableRow", "deleteTableColumn"):
        preview = op_type
    elif op_type == "createParagraphBullets":
        preview = str(body.get("bulletPreset", ""))
    elif op_type == "updateTextStyle":
        fields = body.get("fields", "")
        preview = f"fields={fields}"
    elif op_type == "updateParagraphStyle":
        style = body.get("paragraphStyle") or {}
        preview = f"fields={body.get('fields', '')} style={list(style.keys())}"
    elif op_type == "createNamedRange":
        preview = f"name={body.get('name', '')}"
    elif op_type == "deleteNamedRange":
        preview = f"name={body.get('name', body.get('namedRangeId', ''))}"
    elif op_type == "createHeader" or op_type == "createFooter":
        preview = str(body.get("type", ""))
    elif op_type == "createFootnote":
        preview = "footnote"
    else:
        preview = op_type

    return RequestInfo(
        batch_index=batch_index,
        request_index=request_index,
        op_type=op_type,
        tab_id=tab_id,
        segment_id=segment_id,
        location_index=location_index,
        range_start=range_start,
        range_end=range_end,
        delta=delta,
        preview=preview,
        raw=raw,
    )


# ──────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────


def _shorten(s: str, limit: int = 48) -> str:
    clean = s.replace("\n", "\\n").replace("\t", "\\t")
    if len(clean) > limit:
        return clean[:limit] + "…"
    return clean


def _hr(title: str = "", width: int = 78) -> str:
    if not title:
        return "─" * width
    prefix = f"─── {title} "
    return prefix + "─" * max(0, width - len(prefix))


def _render_report(
    *,
    folder: Path,
    document_id: str,
    format: str,
    base_doc: Document,
    base_segments: list[SegmentSnapshot],
    desired_segments: list[SegmentSnapshot],
    ops: list[Any],
    flat_requests: list[RequestInfo],
) -> str:
    lines: list[str] = []

    lines.append("═" * 78)
    lines.append(f"DEBUG PUSH REPORT  —  {folder}")
    lines.append(f"  document_id = {document_id}")
    lines.append(f"  format      = {format}")
    lines.append("═" * 78)
    lines.append("")

    # 1. Base doc segments
    lines.append(_hr("1. BASE DOCUMENT SEGMENTS"))
    for seg in base_segments:
        label = (
            f"tab={seg.tab_id!r} segment={seg.segment_id!r} ({seg.kind})"
            if seg.tab_id
            else f"segment={seg.segment_id!r} ({seg.kind})"
        )
        lines.append(f"  {label:55}  end_index={seg.end_index}")
    if base_doc.tabs:
        for tab in base_doc.tabs:
            tid = (
                tab.tab_properties.tab_id
                if tab.tab_properties and tab.tab_properties.tab_id
                else ""
            )
            if tab.document_tab and tab.document_tab.body:
                lines.append("")
                lines.append(f"  body content of tab={tid!r}:")
                lines.extend(_render_body_elements(tab.document_tab.body.content or []))
    lines.append("")

    # 2. Desired segments
    lines.append(_hr("2. DESIRED DOCUMENT SEGMENTS (after merge+reindex)"))
    for seg in desired_segments:
        label = (
            f"tab={seg.tab_id!r} segment={seg.segment_id!r} ({seg.kind})"
            if seg.tab_id
            else f"segment={seg.segment_id!r} ({seg.kind})"
        )
        lines.append(f"  {label:55}  end_index={seg.end_index}")
    lines.append("")

    # 3. Diff ops
    lines.append(_hr(f"3. DIFF OPS  ({len(ops)} ops)"))
    for i, op in enumerate(ops):
        lines.append(f"  [{i:3}] {_describe_diff_op(op)}")
    lines.append("")

    # 4. Batch requests
    total_reqs = sum(1 for _ in flat_requests)
    n_batches = max((r.batch_index for r in flat_requests), default=-1) + 1
    lines.append(
        _hr(f"4. BATCH REQUESTS  ({n_batches} batches, {total_reqs} requests)")
    )
    current_batch = -1
    for req in flat_requests:
        if req.batch_index != current_batch:
            current_batch = req.batch_index
            batch_req_count = sum(
                1 for r in flat_requests if r.batch_index == current_batch
            )
            lines.append("")
            lines.append(f"  Batch {current_batch}  ({batch_req_count} requests)")
        lines.append("  " + _format_request(req))
    lines.append("")

    lines.append("═" * 78)
    return "\n".join(lines)


def _render_segments_detail(doc: Document) -> str:
    """Render every structural element in every segment with its index range.

    Format (one element per line):
      [  12432..  12433) P[NORMAL_TEXT] '\\n'

    Answers "what is at index N?" at a glance.
    """
    lines: list[str] = []

    def _dump_segment(header: str, content: list[StructuralElement] | None) -> None:
        lines.append(header)
        if not content:
            lines.append("  (empty)")
            lines.append("")
            return
        for se in content:
            lines.append("  " + _format_element(se))
        lines.append("")

    if doc.tabs:
        for tab in doc.tabs:
            tab_id = ""
            if tab.tab_properties and tab.tab_properties.tab_id:
                tab_id = tab.tab_properties.tab_id
            dt = tab.document_tab
            if dt is None:
                continue
            if dt.body:
                _dump_segment(f"# tab={tab_id!r} body", dt.body.content)
            for seg_id, header in (dt.headers or {}).items():
                _dump_segment(f"# tab={tab_id!r} header={seg_id!r}", header.content)
            for seg_id, footer in (dt.footers or {}).items():
                _dump_segment(f"# tab={tab_id!r} footer={seg_id!r}", footer.content)
            for seg_id, footnote in (dt.footnotes or {}).items():
                _dump_segment(f"# tab={tab_id!r} footnote={seg_id!r}", footnote.content)
    else:
        if doc.body:
            _dump_segment("# body", doc.body.content)
        for seg_id, header in (doc.headers or {}).items():
            _dump_segment(f"# header={seg_id!r}", header.content)
        for seg_id, footer in (doc.footers or {}).items():
            _dump_segment(f"# footer={seg_id!r}", footer.content)
        for seg_id, footnote in (doc.footnotes or {}).items():
            _dump_segment(f"# footnote={seg_id!r}", footnote.content)

    return "\n".join(lines) + ("\n" if lines else "")


def _format_element(se: StructuralElement) -> str:
    start = se.start_index if se.start_index is not None else 0
    end = se.end_index if se.end_index is not None else 0
    if se.section_break is not None:
        return f"[{start:6}..{end:6}) SB"
    if se.paragraph is not None:
        nst = (
            se.paragraph.paragraph_style.named_style_type
            if se.paragraph.paragraph_style
            else None
        )
        text = _paragraph_text(se.paragraph)
        return f"[{start:6}..{end:6}) P[{nst}] {_shorten(text, 60)!r}"
    if se.table is not None:
        nrows = len(se.table.table_rows or [])
        ncols = (
            len(se.table.table_rows[0].table_cells or []) if se.table.table_rows else 0
        )
        return f"[{start:6}..{end:6}) TABLE {nrows}x{ncols}"
    if se.table_of_contents is not None:
        return f"[{start:6}..{end:6}) TOC"
    return f"[{start:6}..{end:6}) <unknown>"


def _render_body_elements(elements: list[StructuralElement]) -> list[str]:
    out: list[str] = []
    for se in elements:
        start = se.start_index if se.start_index is not None else 0
        end = se.end_index if se.end_index is not None else 0
        if se.section_break:
            out.append(f"    [{start:4}..{end:4}) SB")
        elif se.paragraph:
            nst = (
                se.paragraph.paragraph_style.named_style_type
                if se.paragraph.paragraph_style
                else None
            )
            text = _paragraph_text(se.paragraph)
            out.append(f"    [{start:4}..{end:4}) P({nst}, {_shorten(text, 40)!r})")
        elif se.table:
            nrows = len(se.table.table_rows or [])
            ncols = (
                len(se.table.table_rows[0].table_cells or [])
                if se.table.table_rows
                else 0
            )
            out.append(f"    [{start:4}..{end:4}) Table({nrows}x{ncols})")
        else:
            out.append(f"    [{start:4}..{end:4}) <unknown>")
    return out


def _paragraph_text(para: Any) -> str:
    parts: list[str] = []
    for el in para.elements or []:
        if el.text_run and el.text_run.content:
            parts.append(el.text_run.content)
    return "".join(parts)


def _format_request(req: RequestInfo) -> str:
    seg = req.segment_id or "body"
    tab = req.tab_id or "-"
    if req.location_index is not None:
        loc_s = f"@idx={req.location_index:>4}"
    elif req.range_start is not None and req.range_end is not None:
        loc_s = f"[{req.range_start}..{req.range_end})"
    else:
        loc_s = "end-of-seg"
    return (
        f"  [{req.request_index:3}] {req.op_type:24} "
        f"seg={seg:6} tab={tab:<4} {loc_s:15} "
        f"Δ={req.delta:+4}  {req.preview}"
    )


def _describe_diff_op(op: Any) -> str:
    cls = type(op).__name__
    # Extract a few identifying fields
    tab_id = getattr(op, "tab_id", None)
    pieces = [f"tab={tab_id!r}"] if tab_id is not None else []
    for fname in (
        "segment_id",
        "base_range",
        "desired_range",
        "header_id",
        "footer_id",
    ):
        if hasattr(op, fname):
            val = getattr(op, fname)
            if val is not None:
                pieces.append(f"{fname}={val!r}")
    # Length of any content lists
    for fname in ("desired_content", "base_content", "ops", "cell_ops", "row_ops"):
        if hasattr(op, fname):
            val = getattr(op, fname)
            if isinstance(val, list):
                pieces.append(f"{fname}=[{len(val)}]")
    return f"{cls}  " + " ".join(pieces)


def _append_json(
    lines: list[str], value: Any, indent: str, max_lines: int = 40
) -> None:
    s = json.dumps(value, indent=2, ensure_ascii=False)
    for i, ln in enumerate(s.split("\n")):
        if i >= max_lines:
            lines.append(indent + "…")
            break
        lines.append(indent + ln)
