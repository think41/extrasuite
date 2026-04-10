"""Shared helpers for reconcile_v3 tests.

Provides lightweight factory functions to build synthetic Google Docs API
document structures using typed Pydantic models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from extradoc.api_types._generated import (
    Body,
    Dimension,
    Document,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    NamedStyle,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
)

# ---------------------------------------------------------------------------
# Paragraph helpers
# ---------------------------------------------------------------------------


def make_para_el(text: str, named_style: str = "NORMAL_TEXT") -> StructuralElement:
    """Return a content element containing a single paragraph."""
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        )
    )


def make_terminal_para() -> StructuralElement:
    """Return the terminal paragraph element (trailing newline)."""
    return make_para_el("\n")


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def make_table_el(rows: list[list[str]]) -> StructuralElement:
    """Return a content element containing a table."""
    table_rows = []
    for row_texts in rows:
        cells = [
            TableCell(
                content=[make_para_el(t), make_terminal_para()],
            )
            for t in row_texts
        ]
        table_rows.append(TableRow(table_cells=cells))
    return StructuralElement(
        table=Table(
            table_rows=table_rows,
            columns=len(rows[0]) if rows else 0,
            rows=len(rows),
        )
    )


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


def make_doc_tab(
    body_content: list[StructuralElement] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    lists: dict[str, object] | None = None,
    named_styles: list[NamedStyle] | None = None,
    document_style: dict[str, object] | None = None,
    inline_objects: dict[str, object] | None = None,
) -> DocumentTab:
    """Build a DocumentTab with sensible defaults."""
    if body_content is None:
        body_content = [make_terminal_para()]
    return DocumentTab(
        body=Body(content=body_content),
        headers=headers or {},
        footers=footers or {},
        footnotes=footnotes or {},
        lists=lists or {},
        named_styles=NamedStyles(styles=named_styles or []),
        document_style=document_style or {},
        inline_objects=inline_objects or {},
    )


def make_tab(
    tab_id: str,
    title: str = "Tab",
    index: int = 0,
    **kwargs: object,
) -> Tab:
    """Build a Tab with the given ID and DocumentTab content."""
    return Tab(
        tab_properties=TabProperties(tab_id=tab_id, title=title, index=index),
        document_tab=make_doc_tab(**kwargs),  # type: ignore[arg-type]
    )


def make_document(
    document_id: str = "doc1",
    tabs: list[Tab] | None = None,
) -> Document:
    """Build a minimal multi-tab Document."""
    if tabs is None:
        tabs = [make_tab("t1")]
    return Document(document_id=document_id, tabs=tabs)


def make_legacy_document(
    document_id: str = "doc1",
    body_content: list[StructuralElement] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    lists: dict[str, object] | None = None,
    named_styles: list[NamedStyle] | None = None,
    document_style: dict[str, object] | None = None,
) -> Document:
    """Build a legacy single-tab Document (body/headers at top level)."""
    if body_content is None:
        body_content = [make_terminal_para()]
    return Document(
        document_id=document_id,
        body=Body(content=body_content),
        headers=headers or {},
        footers=footers or {},
        footnotes=footnotes or {},
        lists=lists or {},
        named_styles=NamedStyles(styles=named_styles or []),
        document_style=document_style or {},
    )


# ---------------------------------------------------------------------------
# Named style helpers
# ---------------------------------------------------------------------------


def make_named_style(
    style_type: str,
    bold: bool = False,
    font_size: int | None = None,
) -> NamedStyle:
    """Build a NamedStyle with minimal properties."""
    text_style_kwargs: dict[str, object] = {}
    if bold:
        text_style_kwargs["bold"] = True
    if font_size is not None:
        text_style_kwargs["font_size"] = Dimension(magnitude=font_size, unit="PT")
    return NamedStyle(
        named_style_type=style_type,
        text_style=TextStyle(**text_style_kwargs),
        paragraph_style=ParagraphStyle(named_style_type=style_type),
    )


# ---------------------------------------------------------------------------
# Header / footer helpers
# ---------------------------------------------------------------------------


def make_header(header_id: str, text: str = "Header text") -> Header:
    """Build a Header."""
    return Header(
        header_id=header_id,
        content=[make_para_el(text), make_terminal_para()],
    )


def make_footer(footer_id: str, text: str = "Footer text") -> Footer:
    """Build a Footer."""
    return Footer(
        footer_id=footer_id,
        content=[make_para_el(text), make_terminal_para()],
    )


def make_footnote(footnote_id: str, text: str = "Footnote text") -> Footnote:
    """Build a Footnote."""
    return Footnote(
        footnote_id=footnote_id,
        content=[make_para_el(text), make_terminal_para()],
    )


# ---------------------------------------------------------------------------
# Indexed helpers (for lowering tests with start/end indices)
# ---------------------------------------------------------------------------


def make_indexed_para(
    text: str,
    start: int,
    named_style: str = "NORMAL_TEXT",
) -> StructuralElement:
    """Return a paragraph content element with Google Docs API index fields."""
    from extradoc.indexer import utf16_len

    end = start + utf16_len(text)
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        ),
    )


def make_indexed_terminal(start: int) -> StructuralElement:
    """Return a terminal paragraph element (bare '\\n') with index fields."""
    return make_indexed_para("\n", start)


def make_indexed_doc(
    tab_id: str = "t1",
    body_content: list[StructuralElement] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    document_style: dict[str, object] | None = None,
    named_styles: list[NamedStyle] | None = None,
) -> Document:
    """Build a minimal indexed Document for lowering tests."""
    if body_content is None:
        body_content = [make_indexed_terminal(1)]
    return make_document(
        tabs=[
            make_tab(
                tab_id,
                body_content=body_content,
                headers=headers,
                footers=footers,
                footnotes=footnotes,
                document_style=document_style,
                named_styles=named_styles,
            )
        ]
    )


# ---------------------------------------------------------------------------
# batchUpdate op simulator (validity oracle for tests)
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    """A detected problem with a batchUpdate request."""

    request_index: int
    op_type: str
    reason: str


@dataclass
class _Segment:
    """A structural text span of the base doc.

    ``start`` is the first index of the span, ``end`` is the exclusive end
    (one past the last character). ``kind`` is one of ``"paragraph"``,
    ``"table_start"``, ``"table_end"``, ``"cell"``.
    """

    start: int
    end: int
    kind: str
    path: str
    table_start_index: int | None = None


def _walk_content(
    content: list[dict[str, Any]],
    segs: list[_Segment],
    path: str,
) -> None:
    for i, se in enumerate(content):
        if "paragraph" in se:
            s = se.get("startIndex", 0)
            e = se.get("endIndex", s)
            segs.append(_Segment(s, e, "paragraph", f"{path}/p{i}"))
        elif "table" in se:
            tbl = se["table"]
            tbl_start = se.get("startIndex", 0)
            tbl_end = se.get("endIndex", tbl_start)
            segs.append(
                _Segment(
                    tbl_start,
                    tbl_end,
                    "table_start",
                    f"{path}/t{i}",
                    table_start_index=tbl_start,
                )
            )
            for ri, row in enumerate(tbl.get("tableRows", [])):
                for ci, cell in enumerate(row.get("tableCells", [])):
                    cs = cell.get("startIndex", 0)
                    ce = cell.get("endIndex", cs)
                    cell_path = f"{path}/t{i}/r{ri}/c{ci}"
                    segs.append(_Segment(cs, ce, "cell", cell_path))
                    _walk_content(cell.get("content", []), segs, cell_path)
        elif "sectionBreak" in se:
            s = se.get("startIndex", 0)
            e = se.get("endIndex", s + 1)
            segs.append(_Segment(s, e, "section_break", f"{path}/sb{i}"))
        elif "tableOfContents" in se:
            s = se.get("startIndex", 0)
            e = se.get("endIndex", s)
            segs.append(_Segment(s, e, "toc", f"{path}/toc{i}"))


@dataclass
class _SegmentMap:
    """A complete scan of a document segment (body / header / footer / footnote).

    ``segments`` is the flat list of structural spans (paragraphs, cells,
    section breaks). ``cell_boundaries`` contains the exclusive end index
    of every tableCell, which is where boundary-straddling deletes are
    illegal. ``terminal_end`` is the end of the last structural element
    (the body terminal `\\n`). ``table_starts`` is the set of indices
    that refer to a real table startIndex.
    """

    segments: list[_Segment]
    cell_boundaries: set[int]
    cell_spans: list[tuple[int, int]]
    table_starts: set[int]
    min_start: int
    terminal_end: int


def _build_segment_map(content: list[dict[str, Any]]) -> _SegmentMap:
    segs: list[_Segment] = []
    _walk_content(content, segs, "")
    cell_boundaries: set[int] = set()
    cell_spans: list[tuple[int, int]] = []
    table_starts: set[int] = set()
    for seg in segs:
        if seg.kind == "cell":
            cell_boundaries.add(seg.start)
            cell_boundaries.add(seg.end)
            cell_spans.append((seg.start, seg.end))
        if seg.kind == "table_start" and seg.table_start_index is not None:
            table_starts.add(seg.table_start_index)
    min_start = min((s.start for s in segs), default=0)
    terminal_end = max((s.end for s in segs), default=0)
    return _SegmentMap(
        segments=segs,
        cell_boundaries=cell_boundaries,
        cell_spans=cell_spans,
        table_starts=table_starts,
        min_start=min_start,
        terminal_end=terminal_end,
    )


def _iter_tab_segments(doc: dict[str, Any]) -> list[_SegmentMap]:
    """Collect one _SegmentMap per structural segment (body/headers/footers/footnotes).

    Supports both multi-tab (``doc["tabs"]``) and legacy (``doc["body"]``)
    document shapes.
    """
    maps: list[_SegmentMap] = []

    def _collect(dt: dict[str, Any]) -> None:
        body = dt.get("body") or {}
        if body:
            maps.append(_build_segment_map(body.get("content", [])))
        for hdr in (dt.get("headers") or {}).values():
            maps.append(_build_segment_map(hdr.get("content", [])))
        for ftr in (dt.get("footers") or {}).values():
            maps.append(_build_segment_map(ftr.get("content", [])))
        for fn in (dt.get("footnotes") or {}).values():
            maps.append(_build_segment_map(fn.get("content", [])))

    tabs = doc.get("tabs")
    if tabs:
        for tab in tabs:
            dt = tab.get("documentTab") or {}
            _collect(dt)
    else:
        _collect(doc)
    return maps


def _find_body_map(maps: list[_SegmentMap]) -> _SegmentMap | None:
    """The body is the first map (by collection order)."""
    return maps[0] if maps else None


def _straddles_cell_boundary(
    start: int,
    end: int,
    cell_spans: list[tuple[int, int]],
    cell_boundaries: set[int],
) -> int | None:
    """Return the offending cell boundary index if ``[start, end)`` crosses one, else None.

    Any cell start/end index strictly between ``start`` and ``end`` (exclusive
    on both sides) is a boundary-straddling delete and will be rejected by
    the API.
    """
    for b in cell_boundaries:
        if start < b < end:
            return b
    # Also reject ranges where one endpoint is inside a cell and the other
    # lies outside it entirely.
    for cs, ce in cell_spans:
        if cs < start < ce and end > ce:
            return ce
        if cs < end < ce and start < cs:
            return cs
    return None


def _within_any_element(start: int, end: int, segments: list[_Segment]) -> bool:
    """True iff ``[start, end)`` lies entirely within one structural element."""
    for seg in segments:
        if seg.kind in ("cell", "table_start"):
            # cells/tables are containers; their text content is in child paras
            continue
        if seg.start <= start and end <= seg.end:
            return True
    return False


def simulate_ops_against_base(
    base_doc_dict: dict[str, Any],
    batch_requests: list[dict[str, Any]],
) -> list[Violation]:
    """Walk each request and assert ranges/indices are valid against ``base_doc_dict``.

    Returns an empty list on success, else a list of :class:`Violation`
    describing the offending requests.

    Coordinate handling: the simulator tracks a cumulative byte delta from
    prior ``insertText`` / ``deleteContentRange`` requests in the batch and
    subtracts it from later ops' indices before validating against the
    (pre-shift) base segment map. This is an approximation — it assumes
    inserts/deletes happen in the body segment and does not model the
    structural effects of ``insertTable``/``deleteTableRow``/etc. For the
    FORM-15G class of bug (a single raw delete that straddles a cell
    boundary) this is sufficient.
    """
    maps = _iter_tab_segments(base_doc_dict)
    body = _find_body_map(maps)
    if body is None:
        return []

    violations: list[Violation] = []
    cum_shift = 0

    for idx, req in enumerate(batch_requests):
        if "deleteContentRange" in req:
            op = req["deleteContentRange"]
            rng = op.get("range", {})
            raw_s = rng.get("startIndex")
            raw_e = rng.get("endIndex")
            if raw_s is None or raw_e is None:
                violations.append(
                    Violation(idx, "deleteContentRange", "missing range indices")
                )
                continue
            # Un-shift back to base coordinates for validation.
            s = raw_s - cum_shift
            e = raw_e - cum_shift
            if e <= s:
                violations.append(
                    Violation(
                        idx,
                        "deleteContentRange",
                        f"empty or inverted range [{s}..{e})",
                    )
                )
                continue
            if s <= 0:
                violations.append(
                    Violation(
                        idx,
                        "deleteContentRange",
                        f"range touches index 0 (start={s})",
                    )
                )
                continue
            if e >= body.terminal_end:
                violations.append(
                    Violation(
                        idx,
                        "deleteContentRange",
                        f"range touches body terminal newline (end={e}, "
                        f"terminal={body.terminal_end})",
                    )
                )
                continue
            boundary = _straddles_cell_boundary(
                s, e, body.cell_spans, body.cell_boundaries
            )
            if boundary is not None:
                violations.append(
                    Violation(
                        idx,
                        "deleteContentRange",
                        f"range [{s}..{e}) straddles tableCell boundary "
                        f"at index {boundary}",
                    )
                )
                continue
            if not _within_any_element(s, e, body.segments):
                violations.append(
                    Violation(
                        idx,
                        "deleteContentRange",
                        f"range [{s}..{e}) does not lie within a single "
                        f"structural element",
                    )
                )
                continue
            cum_shift -= e - s

        elif "insertText" in req:
            op = req["insertText"]
            text = op.get("text", "")
            loc = op.get("location") or {}
            eos = op.get("endOfSegmentLocation")
            if eos is not None:
                cum_shift += len(text)
                continue
            raw_i = loc.get("index")
            if raw_i is None:
                violations.append(
                    Violation(idx, "insertText", "missing location.index")
                )
                continue
            i = raw_i - cum_shift
            if i < body.min_start or i >= body.terminal_end:
                violations.append(
                    Violation(
                        idx,
                        "insertText",
                        f"index {i} outside body [{body.min_start}.."
                        f"{body.terminal_end})",
                    )
                )
                continue
            cum_shift += len(text)

        elif "updateTextStyle" in req or "updateParagraphStyle" in req:
            key = (
                "updateTextStyle"
                if "updateTextStyle" in req
                else "updateParagraphStyle"
            )
            op = req[key]
            rng = op.get("range", {})
            raw_s = rng.get("startIndex")
            raw_e = rng.get("endIndex")
            if raw_s is None or raw_e is None:
                # Some style updates target namedStyleType only — skip.
                continue
            s = raw_s - cum_shift
            e = raw_e - cum_shift
            boundary = _straddles_cell_boundary(
                s, e, body.cell_spans, body.cell_boundaries
            )
            if boundary is not None:
                violations.append(
                    Violation(
                        idx,
                        key,
                        f"range [{s}..{e}) straddles tableCell boundary "
                        f"at index {boundary}",
                    )
                )
                continue
            # Endpoints must be within the body's overall span.
            if s < body.min_start or e > body.terminal_end:
                violations.append(
                    Violation(
                        idx,
                        key,
                        f"range [{s}..{e}) outside body [{body.min_start}.."
                        f"{body.terminal_end})",
                    )
                )
                continue

        elif (
            "insertTableRow" in req
            or "insertTableColumn" in req
            or "deleteTableRow" in req
            or "deleteTableColumn" in req
        ):
            key = next(iter(req.keys()))
            op = req[key]
            cell_loc = op.get("tableCellLocation") or {}
            tsl = cell_loc.get("tableStartLocation") or {}
            raw_i = tsl.get("index")
            if raw_i is None:
                violations.append(
                    Violation(idx, key, "missing tableStartLocation.index")
                )
                continue
            i = raw_i - cum_shift
            if i not in body.table_starts:
                violations.append(
                    Violation(
                        idx,
                        key,
                        f"tableStartLocation.index={i} does not refer to a "
                        f"base table start; known: {sorted(body.table_starts)}",
                    )
                )
                continue
        # Unrecognized request types: skip silently (forward-compat).

    return violations
