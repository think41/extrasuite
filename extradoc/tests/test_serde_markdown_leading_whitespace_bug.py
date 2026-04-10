"""Regression tests for leading-whitespace loss on markdown deserialization.

mistletoe's block parser strips leading indentation from paragraph content
before emitting inline tokens, so a paragraph that starts with spaces — e.g.
``"   *italic text*"`` or an HTML ``<td>`` with `` INTEREST`` — loses that
whitespace on the pull → edit → push → re-pull round trip. These tests guard
against that regression.
"""

from __future__ import annotations

from extradoc.serde.markdown._from_markdown import markdown_to_document


def _first_para_text(doc: object) -> str:
    # Walk the first tab's body and collect the text of the first paragraph.
    tab = doc.tabs[0]  # type: ignore[attr-defined]
    body = tab.document_tab.body
    for se in body.content or []:
        para = getattr(se, "paragraph", None)
        if para is None:
            continue
        # Skip empty paras and the leading section break
        text = "".join(
            (el.text_run.content or "") if getattr(el, "text_run", None) else ""
            for el in (para.elements or [])
        )
        if text.strip() == "" and not text.startswith(" "):
            continue
        return text
    return ""


def test_leading_whitespace_before_italic_run_is_preserved() -> None:
    """``'   *italic*\\n'`` should deserialize with 3 leading spaces intact."""
    doc = markdown_to_document({"Tab1": "   *italic text*\n"})
    text = _first_para_text(doc)
    assert text.startswith("   "), (
        f"Expected 3 leading spaces before italic run, got {text!r}"
    )
    assert "italic text" in text


def test_leading_whitespace_plain_paragraph_is_preserved() -> None:
    """Plain indented paragraphs must keep leading spaces."""
    doc = markdown_to_document({"Tab1": "   plain leading text\n"})
    text = _first_para_text(doc)
    assert text.startswith("   "), (
        f"Expected 3 leading spaces on plain paragraph, got {text!r}"
    )


def test_leading_whitespace_html_table_cell_is_preserved() -> None:
    """HTML ``<td>`` with leading space must not be stripped."""
    src = (
        "<table><tr>"
        "<td colspan=\"2\"> INTEREST</td>"
        "<td>other</td>"
        "</tr></table>\n"
    )
    doc = markdown_to_document({"Tab1": src})
    tab = doc.tabs[0]
    body = tab.document_tab.body
    table_se = next(se for se in (body.content or []) if getattr(se, "table", None))
    first_cell = table_se.table.table_rows[0].table_cells[0]
    cell_para = first_cell.content[0].paragraph
    cell_text = "".join(
        (el.text_run.content or "") if getattr(el, "text_run", None) else ""
        for el in (cell_para.elements or [])
    )
    assert cell_text.startswith(" "), (
        f"Expected leading space in HTML td content, got {cell_text!r}"
    )
    assert "INTEREST" in cell_text


def test_leading_whitespace_round_trip_via_serde() -> None:
    """Round-trip: deserialize → serialize → deserialize preserves leading ws."""
    from extradoc.serde.markdown._to_markdown import document_to_markdown

    src = "   *italic text* trailing\n"
    doc1 = markdown_to_document({"Tab1": src})
    md_out = document_to_markdown(doc1)
    # document_to_markdown returns dict[folder → dict[filename → content]]
    # find the body file
    tab_files = next(iter(md_out.values()))
    body_md = next(
        (v for k, v in tab_files.items() if k.endswith(".md") and "index" not in k),
        "",
    )
    doc2 = markdown_to_document({"Tab1": body_md})
    text = _first_para_text(doc2)
    assert text.startswith("   "), (
        f"Round-trip lost leading whitespace: {text!r} (body_md={body_md!r})"
    )
