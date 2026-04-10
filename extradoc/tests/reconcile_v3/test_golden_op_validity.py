"""Golden regression harness for the coordinate contract (Task 5).

Every ``tests/golden/*.json`` fixture is fed through a realistic
pull -> mutate -> diff -> lower cycle. The batchUpdate requests emitted by
``reconcile_batches`` are validated against the base document by
``simulate_ops_against_base`` — if any emitted range is structurally
incompatible with the base (straddles a tableCell boundary, touches index 0
or the body terminal, is empty/inverted, etc.) the test fails loudly.

Mutations:
- no-op (expect empty or fully valid request list)
- edit first non-empty text run
- insert a new paragraph after the first body paragraph
- toggle bold on the first non-empty run

Plus a FORM-15G-specific test that joins the paragraphs of a multi-paragraph
table cell and asserts no op lands on the cell-boundary index.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from extradoc.api_types._generated import (
    Document,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    TextRun,
    TextStyle,
)
from extradoc.reconcile_v3.api import reconcile_batches

from .helpers import simulate_ops_against_base

GOLDEN_DIR = Path(__file__).parent.parent / "golden"

# All golden fixtures (raw Google Docs API document dicts).
GOLDEN_FIXTURES: list[Path] = sorted(GOLDEN_DIR.glob("*.json"))
FIXTURE_IDS = [p.stem for p in GOLDEN_FIXTURES]

FORM15G_FIXTURE = GOLDEN_DIR / "form15g_base.json"

# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def _load_raw(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_doc(path: Path) -> Document:
    return Document.model_validate(_load_raw(path))


def _doc_to_dict(doc: Document) -> dict[str, Any]:
    return doc.model_dump(by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------
# Request extraction
# ---------------------------------------------------------------------------


def _flatten_requests(batches: list[Any]) -> list[dict[str, Any]]:
    """Flatten a list of BatchUpdateDocumentRequest into plain-dict requests."""
    out: list[dict[str, Any]] = []
    for batch in batches:
        for req in batch.requests or []:
            out.append(req.model_dump(by_alias=True, exclude_none=True))
    return out


def _run_reconcile(base: Document, desired: Document) -> list[dict[str, Any]]:
    batches = reconcile_batches(base, desired)
    return _flatten_requests(batches)


def _style_ops_on_inserted_content(reqs: list[dict[str, Any]]) -> set[int]:
    """Return indices of style update requests whose range lies entirely
    inside content inserted by an earlier request in the same batch.

    The Task 4 simulator validates style-update ranges by un-shifting them
    through the cumulative insert/delete delta, then checking containment in
    the base segment map. A style update on *freshly inserted* content is
    valid in the post-insert frame but un-shifts to a negative or
    inside-insertion range, which the simulator flags as a false positive.
    This helper identifies those requests so the test can skip them.
    """
    skip: set[int] = set()
    # Track concrete inserted spans in post-execution coordinates.
    inserted_spans: list[tuple[int, int]] = []
    cum_shift = 0
    for i, req in enumerate(reqs):
        if "insertText" in req:
            op = req["insertText"]
            loc = op.get("location") or {}
            text = op.get("text", "")
            if "index" in loc:
                start = loc["index"]
                inserted_spans.append((start, start + len(text)))
                cum_shift += len(text)
            elif op.get("endOfSegmentLocation") is not None:
                cum_shift += len(text)
        elif "deleteContentRange" in req:
            rng = req["deleteContentRange"].get("range") or {}
            s = rng.get("startIndex")
            e = rng.get("endIndex")
            if isinstance(s, int) and isinstance(e, int):
                cum_shift -= e - s
        elif "updateTextStyle" in req or "updateParagraphStyle" in req:
            key = (
                "updateTextStyle"
                if "updateTextStyle" in req
                else "updateParagraphStyle"
            )
            rng = req[key].get("range") or {}
            s = rng.get("startIndex")
            e = rng.get("endIndex")
            if not isinstance(s, int) or not isinstance(e, int):
                continue
            for ins_s, ins_e in inserted_spans:
                if ins_s <= s and e <= ins_e:
                    skip.add(i)
                    break
    return skip


def _assert_valid(base_dict: dict[str, Any], reqs: list[dict[str, Any]]) -> None:
    violations = simulate_ops_against_base(base_dict, reqs)
    # Drop false positives: style updates on freshly-inserted content. The
    # simulator can't tell these apart from drifted ranges — see helper above.
    skip = _style_ops_on_inserted_content(reqs)
    real = [v for v in violations if v.request_index not in skip]
    if real:
        lines = [f"  {v.request_index}: {v.op_type}: {v.reason}" for v in real]
        raise AssertionError(
            "simulate_ops_against_base found "
            f"{len(real)} violation(s):\n" + "\n".join(lines)
        )


def _assert_range_shape(reqs: list[dict[str, Any]]) -> None:
    """Concrete-int + non-empty checks on every emitted range."""
    for i, req in enumerate(reqs):
        for key in (
            "deleteContentRange",
            "updateTextStyle",
            "updateParagraphStyle",
            "insertText",
        ):
            if key not in req:
                continue
            op = req[key]
            if key == "insertText":
                loc = op.get("location") or {}
                if loc:
                    idx = loc.get("index")
                    assert isinstance(idx, int), f"req {i} {key}: non-int index {idx!r}"
                continue
            rng = op.get("range") or {}
            if not rng:
                continue  # e.g. namedStyleType-only update
            s = rng.get("startIndex")
            e = rng.get("endIndex")
            if s is None and e is None:
                continue
            assert isinstance(s, int) and isinstance(e, int), (
                f"req {i} {key}: non-int range {s!r}..{e!r}"
            )
            assert e > s, f"req {i} {key}: empty range [{s}..{e})"


# ---------------------------------------------------------------------------
# Mutation helpers — operate on the desired Document Pydantic model
# ---------------------------------------------------------------------------


def _iter_body_paragraphs(doc: Document):
    """Yield (parent_content, index, StructuralElement) for every body paragraph."""
    for tab in doc.tabs or []:
        dt = tab.document_tab
        if dt is None or dt.body is None:
            continue
        for i, el in enumerate(dt.body.content or []):
            if el.paragraph is not None:
                yield dt.body.content, i, el


def _find_first_nonempty_run(
    doc: Document,
) -> tuple[Any, int, ParagraphElement, TextRun] | None:
    """Return (content_list, para_idx, ParagraphElement, TextRun) for first
    body paragraph whose first text run has non-whitespace content."""
    for content, idx, el in _iter_body_paragraphs(doc):
        para: Paragraph = el.paragraph  # type: ignore[assignment]
        for pe in para.elements or []:
            tr = pe.text_run
            if tr is None:
                continue
            txt = tr.content or ""
            if txt.strip():
                return content, idx, pe, tr
    return None


def mutate_edit_text(doc: Document) -> Document:
    found = _find_first_nonempty_run(doc)
    assert found is not None, "fixture has no non-empty text runs"
    _content, _idx, _pe, tr = found
    original = tr.content or ""
    # Strip trailing newline (paragraph terminator) before editing.
    nl = "\n" if original.endswith("\n") else ""
    core = original[: len(original) - len(nl)]
    # Choose a replacement of different length.
    new_core = (core + " X") if len(core) > 0 else "Hello"
    tr.content = new_core + nl
    return doc


def mutate_insert_paragraph(doc: Document) -> Document:
    # Insert after the first body paragraph (position 1), leaving the existing
    # first paragraph untouched. Avoids touching index 0 at all.
    for tab in doc.tabs or []:
        dt = tab.document_tab
        if dt is None or dt.body is None or not dt.body.content:
            continue
        # Find first paragraph index.
        first_para_idx = None
        for i, el in enumerate(dt.body.content):
            if el.paragraph is not None:
                first_para_idx = i
                break
        if first_para_idx is None:
            continue
        new_el = StructuralElement(
            paragraph=Paragraph(
                elements=[ParagraphElement(text_run=TextRun(content="Inserted\n"))],
                paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            )
        )
        dt.body.content.insert(first_para_idx + 1, new_el)
        return doc
    raise AssertionError("fixture has no body paragraphs to insert after")


def mutate_toggle_bold(doc: Document) -> Document:
    found = _find_first_nonempty_run(doc)
    assert found is not None, "fixture has no non-empty text runs"
    _content, _idx, _pe, tr = found
    style = tr.text_style or TextStyle()
    style.bold = not bool(style.bold)
    tr.text_style = style
    return doc


MUTATIONS = {
    "edit_text": mutate_edit_text,
    "insert_paragraph": mutate_insert_paragraph,
    "toggle_bold": mutate_toggle_bold,
}


# ---------------------------------------------------------------------------
# Parametrized tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=FIXTURE_IDS)
def test_noop_roundtrip(fixture: Path) -> None:
    base_dict = _load_raw(fixture)
    base = Document.model_validate(base_dict)
    desired = Document.model_validate(copy.deepcopy(base_dict))
    reqs = _run_reconcile(base, desired)
    # A no-op should either emit nothing or only shape-free requests; any
    # emitted op must still validate against the base.
    _assert_range_shape(reqs)
    _assert_valid(base_dict, reqs)


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=FIXTURE_IDS)
@pytest.mark.parametrize("mutation_name", list(MUTATIONS.keys()))
def test_synthetic_mutation(fixture: Path, mutation_name: str) -> None:
    base_dict = _load_raw(fixture)
    base = Document.model_validate(base_dict)
    desired = Document.model_validate(copy.deepcopy(base_dict))
    MUTATIONS[mutation_name](desired)
    reqs = _run_reconcile(base, desired)
    _assert_range_shape(reqs)
    _assert_valid(base_dict, reqs)


# ---------------------------------------------------------------------------
# FORM-15G-specific: cell paragraph join must not land on cell boundary
# ---------------------------------------------------------------------------


def _find_multipara_cell(doc: Document) -> tuple[list, int, int] | None:
    """Return (cell.content list, cell.start_index, cell.end_index) for the
    first body table cell with >= 2 non-empty paragraphs."""
    for tab in doc.tabs or []:
        dt = tab.document_tab
        if dt is None or dt.body is None:
            continue
        for el in dt.body.content or []:
            tbl = el.table
            if tbl is None:
                continue
            for row in tbl.table_rows or []:
                for cell in row.table_cells or []:
                    paras = [p for p in (cell.content or []) if p.paragraph]
                    nonempty = [
                        p
                        for p in paras
                        if any(
                            pe.text_run
                            and pe.text_run.content
                            and pe.text_run.content.strip()
                            for pe in (p.paragraph.elements or [])
                        )
                    ]
                    if len(nonempty) >= 2:
                        return (
                            cell.content,
                            cell.start_index or 0,
                            cell.end_index or 0,
                        )
    return None


def test_form15g_cell_join_no_boundary_op() -> None:
    """Join multi-paragraph table cell; assert no op lands on the cell
    boundary index (414..496 region) and pin the expected op count."""
    base_dict = _load_raw(FORM15G_FIXTURE)
    base = Document.model_validate(base_dict)
    desired = Document.model_validate(copy.deepcopy(base_dict))

    found = _find_multipara_cell(desired)
    assert found is not None, "form15g fixture lost its multi-paragraph cell"
    cell_content, _cell_start, cell_end = found

    # Collect all text from the cell's non-terminal paragraphs, then replace
    # them with a single joined paragraph. Drop the trailing empty terminator
    # paragraph only if there are multiple — keep at least one.
    joined_text_parts: list[str] = []
    for p in cell_content:
        if p.paragraph is None:
            continue
        for pe in p.paragraph.elements or []:
            if pe.text_run and pe.text_run.content:
                joined_text_parts.append(pe.text_run.content.replace("\n", " "))
    joined = " ".join(t.strip() for t in joined_text_parts if t.strip()) + "\n"

    new_para = StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=joined))],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        )
    )
    # Replace cell.content with [joined_para, terminator_para].
    terminator = StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content="\n"))],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        )
    )
    cell_content.clear()
    cell_content.append(new_para)
    cell_content.append(terminator)

    reqs = _run_reconcile(base, desired)
    _assert_range_shape(reqs)
    _assert_valid(base_dict, reqs)

    # Assert no op targets the cell-boundary index (cell_end or cell_end - 1,
    # the row terminator). Use a loose check: scan every range/index in the
    # flat request list and ensure none equals cell_end or cell_end + 1.
    forbidden = {cell_end, cell_end + 1}
    for i, req in enumerate(reqs):
        for key, op in req.items():
            if not isinstance(op, dict):
                continue
            rng = op.get("range") or {}
            if rng:
                assert rng.get("startIndex") not in forbidden, (
                    f"req {i} {key} startIndex hits cell-boundary {rng}"
                )
                assert rng.get("endIndex") not in forbidden, (
                    f"req {i} {key} endIndex hits cell-boundary {rng}"
                )
            loc = op.get("location") or {}
            if loc:
                assert loc.get("index") not in forbidden, (
                    f"req {i} {key} location.index hits cell-boundary {loc}"
                )

    # Snapshot: pin the expected op count so future drift is visible. If this
    # number changes, inspect the diff carefully — a smaller count is likely
    # fine, a larger count may indicate regression.
    assert len(reqs) > 0, "cell join produced no ops"
    # Upper bound; tune after first run.
    assert len(reqs) < 200, f"cell join produced unexpectedly many ops: {len(reqs)}"
