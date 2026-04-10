"""Regression test for table-cell paragraph-merge corruption.

Bug (discovered on FORM-15G, doc 1FkRTeU852Mxg0OJh684MXutDxW7ubTkiA6_EXyRce54):

A table cell in the base doc contains TWO Google-Docs paragraphs that the
markdown serde joins into ONE GFM-table cell line:

    P0: "Previous year (P.Y.)3             2020-21\n"
    P1: "(for which declaration is being made)\n"
    P2: "\n"   (cell terminator)

The serde's ``ancestor`` (base serialised to markdown + parsed back) therefore
only has ONE content paragraph for this cell — the joined form. When the user
edits ``2020-21`` -> ``2024-25`` in the joined markdown line and the pipeline
computes ``desired = apply_ops(base, diff(ancestor, mine))``, the
3-way-merge in ``diffmerge/apply_ops.py::_merge_table_cell`` used to hit its
"desired has fewer paragraphs than raw base — preserve trailing raw paragraphs"
branch and leave ``raw[1]`` ("(for which declaration is being made)\n") in
place, duplicating the phrase that is already present in the updated
``raw[0]`` (the joined text).

The resulting ``desired`` document had a phantom middle paragraph that
``reconcile_v3`` then turned into overlapping delete/insert ops, corrupting
the pushed document.

This test pins the invariant at the serde layer: after a one-word edit in a
joined cell line, the desired document must not contain the phantom
paragraph.
"""

from __future__ import annotations

import json
from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.serde.markdown import MarkdownSerde

GOLDEN = Path(__file__).parent.parent / "golden"
BASE_FIXTURE = GOLDEN / "form15g_base.json"

P1_TEXT = "Previous year (P.Y.)3             2020-21"
P2_TEXT = "(for which declaration is being made)"


def _cell_paragraph_texts(doc: Document, needle: str) -> list[str]:
    """Return the text of every paragraph in the table cell containing ``needle``."""
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
                    full = ""
                    paras: list[str] = []
                    for p in cell.content or []:
                        pt = ""
                        if p.paragraph is not None:
                            for pe in p.paragraph.elements or []:
                                if pe.text_run is not None:
                                    pt += pe.text_run.content or ""
                        paras.append(pt)
                        full += pt
                    if needle in full:
                        return paras
    raise AssertionError(f"no cell containing {needle!r}")


def test_form15g_py_cell_edit_does_not_duplicate_phrase(tmp_path: Path) -> None:
    """End-to-end: pull form15g, edit 2020-21 -> 2024-25, assert desired is clean.

    The fix lives in ``diffmerge/apply_ops.py::_merge_table_cell``. Without the
    fix, the desired cell contains three paragraphs where the second duplicates
    text already present in the first.
    """
    base_dict = json.loads(BASE_FIXTURE.read_text())
    base_doc = Document.model_validate(base_dict)

    # Sanity-check the base document shape: the cell really has the two
    # separate paragraphs we need to join.
    base_paras = _cell_paragraph_texts(base_doc, "Previous year")
    assert any(P1_TEXT in p for p in base_paras), base_paras
    assert any(P2_TEXT in p and P1_TEXT not in p for p in base_paras), base_paras

    bundle = DocumentWithComments(
        document=base_doc, comments=FileComments(file_id="form15g")
    )

    folder = tmp_path / "form15g"
    folder.mkdir()
    serde = MarkdownSerde()
    serde.serialize(bundle, folder)

    # Find the markdown file containing the joined cell line and perform the
    # 2020-21 -> 2024-25 edit.
    edited = False
    for md_path in folder.rglob("*.md"):
        if ".pristine" in md_path.parts:
            continue
        text = md_path.read_text(encoding="utf-8")
        if "2020-21" in text and P2_TEXT in text:
            md_path.write_text(text.replace("2020-21", "2024-25"), encoding="utf-8")
            edited = True
            break
    assert edited, "could not locate the cell line in the serialised markdown"

    result = serde.deserialize(folder)
    desired_paras = _cell_paragraph_texts(result.desired.document, "Previous year")

    # The edit must be present.
    joined = next((p for p in desired_paras if "2024-25" in p), None)
    assert joined is not None, desired_paras
    assert P1_TEXT.replace("2020-21", "2024-25") in joined
    assert P2_TEXT in joined

    # No desired paragraph may still contain the old P2 text as its sole
    # content — that would be the phantom duplicate.
    phantom = [
        p
        for p in desired_paras
        if P2_TEXT in p and "2024-25" not in p and "Previous year" not in p
    ]
    assert not phantom, (
        "desired cell contains a phantom paragraph duplicating the joined "
        f"tail text: {phantom!r} (full paragraphs: {desired_paras!r})"
    )
