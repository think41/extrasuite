"""Contract document scenario tests for reconcile_v3.

These tests use the real contract document golden file and verify that
common editing scenarios produce correct batchUpdate operations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde.markdown import MarkdownSerde

GOLDEN_DIR = Path(__file__).parent.parent / "golden"
CONTRACT_BASE_ID = "18WZe578kHC0DP4Q1c-hhs15VWUJlFYNMvSwtzk-Wgbo"

_serde = MarkdownSerde()


def _load_base() -> Document:
    path = GOLDEN_DIR / f"{CONTRACT_BASE_ID}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


def _flatten_requests(batches: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for batch in batches:
        for req in batch.requests or []:
            out.append(req.model_dump(by_alias=True, exclude_none=True))
    return out


def _serialize_and_edit(
    base_doc: Document,
    tmp_path: Path,
    edit_fn: Callable[[str], str],
) -> tuple[Document, Document]:
    """Serialize base_doc, apply edit_fn to the tab markdown, deserialize."""
    folder = tmp_path / "doc"
    _serde.serialize(_bundle(base_doc), folder)

    tab_files = list((folder / "tabs").glob("*.md"))
    assert len(tab_files) >= 1, f"expected at least one tab file, got {tab_files}"
    tab_md = tab_files[0]

    content = tab_md.read_text()
    edited = edit_fn(content)
    tab_md.write_text(edited)

    result = _serde.deserialize(folder)
    return result.base.document, result.desired.document


# ---------------------------------------------------------------------------
# Scenario A: Complete rewrite of the heavily-styled title paragraph
# ---------------------------------------------------------------------------


def test_scenario_a_title_rewrite_no_delete_insert_pair(tmp_path: Path) -> None:
    """Completely rewriting the title should produce surgical ops, not delete+insert.

    The title '**<u>SAMPLE SHARED SERVICES AGREEMENT</u>**' is the first
    non-image paragraph, with bold + underline styling.  When rewritten to
    something with 0 Jaccard similarity, the aligner should still match it
    in-place and emit updateTextStyle / insertText ops rather than a
    deleteContentRange + insertText spanning the whole paragraph.
    """
    base_doc = _load_base()

    def edit(content: str) -> str:
        return content.replace(
            "**<u>SAMPLE SHARED SERVICES AGREEMENT</u>**",
            "**<u>COMPLETELY DIFFERENT ORGANIZATION PARTNERSHIP CONTRACT</u>**",
        )

    base, desired = _serialize_and_edit(base_doc, tmp_path, edit)
    batches = reconcile_batches(base, desired)
    reqs = _flatten_requests(batches)

    # Collect deleteContentRange ops and their ranges
    deletes = [r for r in reqs if "deleteContentRange" in r]
    # Find the title's start index in base doc — it's the 2nd paragraph
    # (after inline image). We verify no delete spans more than the paragraph.
    # The title is at roughly startIndex=1 and has ~40 chars.
    # A suspicious delete is one that covers >50 chars in the first 200 indices.
    title_region_end = 200  # generous upper bound for title paragraph

    large_title_deletes = [
        r
        for r in deletes
        if (
            r["deleteContentRange"]["range"].get("startIndex", 9999) < title_region_end
            and (
                r["deleteContentRange"]["range"].get("endIndex", 0)
                - r["deleteContentRange"]["range"].get("startIndex", 0)
            )
            > 30
        )
    ]

    assert large_title_deletes == [], (
        f"Expected no large deleteContentRange over the title paragraph, "
        f"but found: {large_title_deletes}"
    )


# ---------------------------------------------------------------------------
# Scenario B: Table cell single-field edit produces no row ops
# ---------------------------------------------------------------------------


def test_scenario_b_table_cell_edit_no_row_ops(tmp_path: Path) -> None:
    """Editing a single table cell must not produce insertTableRow/deleteTableRow.

    The first table has '[Hourly Salary Amount' as its first cell.
    Changing that to '[Annual Salary Equivalent]' is a content-only change
    within one cell and must not trigger any row structural ops.
    """
    base_doc = _load_base()

    def edit(content: str) -> str:
        return content.replace(
            "| [Hourly Salary Amount | $ |",
            "| [Annual Salary Equivalent] | $ |",
        )

    base, desired = _serialize_and_edit(base_doc, tmp_path, edit)
    batches = reconcile_batches(base, desired)
    reqs = _flatten_requests(batches)

    row_ops = [r for r in reqs if "insertTableRow" in r or "deleteTableRow" in r]
    assert row_ops == [], (
        f"Expected no row ops for a single-cell content edit, but got: {row_ops}"
    )


# ---------------------------------------------------------------------------
# Scenario C: Duplicate placeholder — only first instance edited
# ---------------------------------------------------------------------------


def test_scenario_c_first_agency_filled_second_unchanged(tmp_path: Path) -> None:
    """Filling in the first '[AGENCY]' must not touch the second one.

    The document has '[AGENCY]' at two places (lines 285 and 307 in the
    serialized markdown).  Replacing only the first occurrence must produce
    exactly one insertText/deleteContentRange pair, not two.
    """
    base_doc = _load_base()

    def edit(content: str) -> str:
        # Replace only the first occurrence
        return content.replace("[AGENCY]", "Community Action Program", 1)

    base, desired = _serialize_and_edit(base_doc, tmp_path, edit)
    batches = reconcile_batches(base, desired)
    reqs = _flatten_requests(batches)

    # Find both [AGENCY] paragraph indices in the base doc
    base_dict = base.model_dump(by_alias=True, exclude_none=True)
    tab_dt = base_dict["tabs"][0]["documentTab"]
    body_content = tab_dt["body"]["content"]

    agency_starts: list[int] = []
    for se in body_content:
        if "paragraph" not in se:
            continue
        p = se["paragraph"]
        text = "".join(
            el.get("textRun", {}).get("content", "") for el in p.get("elements", [])
        )
        if text.strip() == "[AGENCY]":
            si = se.get("startIndex")
            if si is not None:
                agency_starts.append(si)

    assert len(agency_starts) == 2, (
        f"Expected exactly 2 [AGENCY] paragraphs in base doc, found at: {agency_starts}"
    )

    first_agency_start = agency_starts[0]
    second_agency_start = agency_starts[1]

    content_ops = [r for r in reqs if "insertText" in r or "deleteContentRange" in r]

    # No content op should target the second [AGENCY] paragraph
    ops_near_second = []
    for r in content_ops:
        if "insertText" in r:
            idx = r["insertText"].get("location", {}).get("index", -1)
        else:
            idx = r["deleteContentRange"]["range"].get("startIndex", -1)
        # Within 5 chars of second_agency_start is close enough
        if abs(idx - second_agency_start) <= 5:
            ops_near_second.append(r)

    assert ops_near_second == [], (
        f"Expected no ops near the second [AGENCY] paragraph (index={second_agency_start}), "
        f"but found: {ops_near_second}"
    )

    # At least one content op must target the first [AGENCY] paragraph
    ops_near_first = []
    for r in content_ops:
        if "insertText" in r:
            idx = r["insertText"].get("location", {}).get("index", -1)
        else:
            idx = r["deleteContentRange"]["range"].get("startIndex", -1)
        if abs(idx - first_agency_start) <= 30:  # generous — paragraph is short
            ops_near_first.append(r)

    assert ops_near_first, (
        f"Expected at least one content op near the first [AGENCY] paragraph "
        f"(index={first_agency_start}), but got none. All content ops: {content_ops}"
    )


# ---------------------------------------------------------------------------
# Scenario D: Paragraph immediately before table — complete rewrite
# ---------------------------------------------------------------------------


def test_scenario_d_para_before_table_rewrite_no_cross_boundary_delete(
    tmp_path: Path,
) -> None:
    """Rewriting the paragraph before the first table must not produce a delete
    that crosses the table boundary.

    '[Shared Staff]' is followed immediately by a table. A complete text
    rewrite of that paragraph must emit a delete confined to that paragraph's
    range, not one that extends into the table.
    """
    base_doc = _load_base()

    def edit(content: str) -> str:
        return content.replace(
            "**[Shared Staff]**[^kix.fn9]",
            "**[Personnel Cost Allocation Table]**[^kix.fn9]",
        )

    base, desired = _serialize_and_edit(base_doc, tmp_path, edit)
    batches = reconcile_batches(base, desired)
    reqs = _flatten_requests(batches)

    # Find where the first table starts in the base doc
    base_dict = base.model_dump(by_alias=True, exclude_none=True)
    tab_dt = base_dict["tabs"][0]["documentTab"]
    body = tab_dt["body"]["content"]

    table_starts: list[int] = []
    for se in body:
        if "table" in se and se.get("startIndex") is not None:
            table_starts.append(se["startIndex"])

    assert table_starts, "Could not find any tables in base document"
    first_table_start = min(table_starts)

    # No deleteContentRange should cross into or beyond the table
    bad_deletes = []
    for r in reqs:
        if "deleteContentRange" in r:
            rng = r["deleteContentRange"]["range"]
            s = rng.get("startIndex", 0)
            e = rng.get("endIndex", 0)
            if s < first_table_start <= e:
                bad_deletes.append(r)

    assert bad_deletes == [], (
        f"Found deleteContentRange ops that cross the first table boundary "
        f"(table starts at {first_table_start}): {bad_deletes}"
    )


# ---------------------------------------------------------------------------
# Scenario E: Paragraph with footnote reference — append text
# ---------------------------------------------------------------------------


def test_scenario_e_append_to_para_with_footnote_preserves_footnote(
    tmp_path: Path,
) -> None:
    """Appending text to a paragraph that contains a footnote reference must
    not produce a deleteFootnote op, and the paragraph must be matched
    in-place (no delete+reinsert of the whole paragraph).

    The paragraph starting with '[Shared Staff]' has footnote reference
    kix.fn9. We append ' (see schedule)' to it.
    """
    base_doc = _load_base()

    def edit(content: str) -> str:
        # Append text after the footnote reference marker
        return content.replace(
            "**[Shared Staff]**[^kix.fn9]",
            "**[Shared Staff]**[^kix.fn9] (see schedule)",
        )

    base, desired = _serialize_and_edit(base_doc, tmp_path, edit)
    batches = reconcile_batches(base, desired)
    reqs = _flatten_requests(batches)

    # No deleteFootnote ops
    delete_footnote_ops = [r for r in reqs if "deleteFootnote" in r]
    assert delete_footnote_ops == [], (
        f"Expected no deleteFootnote ops when appending to a para with footnote, "
        f"but got: {delete_footnote_ops}"
    )

    # The paragraph should be matched in-place: no large delete spanning
    # the whole paragraph. The paragraph "[Shared Staff]\n" is about 16 chars.
    # A delete of >15 chars in that region suggests a delete+reinsert pattern.
    # Find the paragraph's start index in base.
    base_dict = base.model_dump(by_alias=True, exclude_none=True)
    tab_dt = base_dict["tabs"][0]["documentTab"]
    body_content = tab_dt["body"]["content"]

    shared_staff_start: int | None = None
    for se in body_content:
        if "paragraph" not in se:
            continue
        p = se["paragraph"]
        text = "".join(
            el.get("textRun", {}).get("content", "") for el in p.get("elements", [])
        )
        if "[Shared Staff]" in text:
            shared_staff_start = se.get("startIndex")
            break

    assert shared_staff_start is not None, "Could not find '[Shared Staff]' paragraph"

    # No delete should start at or near shared_staff_start and span the whole para
    para_len = 20  # "[Shared Staff]\n" + footnote ref ≈ 16-20 chars
    full_para_deletes = [
        r
        for r in reqs
        if "deleteContentRange" in r
        and abs(
            r["deleteContentRange"]["range"].get("startIndex", -999)
            - shared_staff_start
        )
        <= 2
        and (
            r["deleteContentRange"]["range"].get("endIndex", 0)
            - r["deleteContentRange"]["range"].get("startIndex", 0)
        )
        >= para_len
    ]
    assert full_para_deletes == [], (
        f"Expected no full-paragraph delete for '[Shared Staff]' para, "
        f"but found: {full_para_deletes}"
    )
