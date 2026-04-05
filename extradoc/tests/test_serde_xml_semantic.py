"""Semantic XML -> Document tests.

These tests intentionally stop at ``serde.deserialize()``. Their job is to
prove that a desired XML folder parses into the semantic ``Document`` shape we
expect before the reconciler/lowerer gets involved.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from extradoc.serde.xml import XmlSerde

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document, StructuralElement

_xml_serde = XmlSerde()


def _write_xml_folder(
    root: Path,
    *,
    document_xml: str,
    styles_xml: str | None = None,
    index_xml: str | None = None,
    folder: str = "Tab_1",
) -> Path:
    """Create a minimal XML folder consumable by ``serde.deserialize()``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / folder).mkdir(parents=True, exist_ok=True)

    if index_xml is None:
        index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="doc.xml.semantic" title="XML Semantic Test">
  <tab id="t.0" title="Tab 1" folder="Tab_1" />
</doc>
"""

    (root / "index.xml").write_text(index_xml, encoding="utf-8")
    (root / folder / "document.xml").write_text(document_xml, encoding="utf-8")
    if styles_xml is not None:
        (root / folder / "styles.xml").write_text(styles_xml, encoding="utf-8")
    return root


def _paragraph_text(element: StructuralElement) -> str:
    assert element.paragraph is not None
    parts: list[str] = []
    for para_element in element.paragraph.elements or []:
        if para_element.text_run is not None:
            parts.append(para_element.text_run.content or "")
        elif para_element.footnote_reference is not None:
            parts.append(f"<fn:{para_element.footnote_reference.footnote_id}>")
        elif para_element.page_break is not None:
            parts.append("<pagebreak>")
        elif para_element.horizontal_rule is not None:
            parts.append("<hr>")
    return "".join(parts).rstrip("\n")


def _table_signature(element: StructuralElement) -> list[list[list[Any]]]:
    assert element.table is not None
    rows: list[list[list[Any]]] = []
    for row in element.table.table_rows or []:
        row_sig: list[list[Any]] = []
        for cell in row.table_cells or []:
            cell_sig: list[Any] = []
            for child in cell.content or []:
                cell_sig.append(_block_signature(child))
            row_sig.append(cell_sig)
        rows.append(row_sig)
    return rows


def _block_signature(element: StructuralElement) -> Any:
    if element.section_break is not None:
        style = element.section_break.section_style
        return (
            "sectionbreak",
            style.default_header_id if style else None,
            style.default_footer_id if style else None,
        )
    if element.table is not None:
        return ("table", _table_signature(element))
    if element.table_of_contents is not None:
        return ("toc",)
    assert element.paragraph is not None
    para = element.paragraph
    style = para.paragraph_style
    bullet = para.bullet
    return (
        "paragraph",
        style.named_style_type if style else None,
        _paragraph_text(element),
        bullet.nesting_level if bullet else None,
        bool(bullet),
    )


def _document_signature(document: Document) -> list[tuple[str | None, Any]]:
    signature: list[tuple[str | None, Any]] = []
    for tab in document.tabs or []:
        tab_title = tab.tab_properties.title if tab.tab_properties else None
        doc_tab = tab.document_tab
        assert doc_tab is not None

        body_sig = [_block_signature(block) for block in (doc_tab.body.content or [])]
        header_sig = {
            header_id: [_block_signature(block) for block in (header.content or [])]
            for header_id, header in (doc_tab.headers or {}).items()
        }
        footer_sig = {
            footer_id: [_block_signature(block) for block in (footer.content or [])]
            for footer_id, footer in (doc_tab.footers or {}).items()
        }
        footnote_sig = {
            footnote_id: [_block_signature(block) for block in (footnote.content or [])]
            for footnote_id, footnote in (doc_tab.footnotes or {}).items()
        }
        signature.append(
            (
                tab_title,
                {
                    "body": body_sig,
                    "headers": header_sig,
                    "footers": footer_sig,
                    "footnotes": footnote_sig,
                },
            )
        )
    return signature


def test_deserialize_xml_parses_expected_body_structure(tmp_path: Path) -> None:
    folder = _write_xml_folder(
        tmp_path / "xml-body",
        document_xml="""<?xml version="1.0" encoding="UTF-8"?>
<tab id="t.0" title="Tab 1" index="0">
  <body>
    <sectionbreak defaultHeaderId="h.release" defaultFooterId="f.release" />
    <h1>Release Plan</h1>
    <p>Intro paragraph with a <a href="https://example.com">link</a>.</p>
    <li type="bullet">Top level bullet</li>
    <li type="bullet" level="1">Nested bullet</li>
    <p>Before page break.</p>
    <pagebreak />
    <h2>After Break</h2>
    <table>
      <tr>
        <td><p>Cell A1</p></td>
        <td><p>Cell A2</p></td>
      </tr>
    </table>
  </body>
</tab>
""",
    )

    document = _xml_serde._parse(folder).document
    tab = document.tabs[0]
    doc_tab = tab.document_tab
    assert doc_tab is not None
    body = doc_tab.body.content or []

    assert body[0].section_break is not None
    assert body[0].section_break.section_style is not None
    assert body[0].section_break.section_style.default_header_id == "h.release"
    assert body[0].section_break.section_style.default_footer_id == "f.release"

    assert body[1].paragraph is not None
    assert body[1].paragraph.paragraph_style.named_style_type == "HEADING_1"
    assert _paragraph_text(body[1]) == "Release Plan"

    assert _paragraph_text(body[2]) == "Intro paragraph with a link."

    assert body[3].paragraph is not None and body[4].paragraph is not None
    assert body[3].paragraph.bullet is not None
    assert body[4].paragraph.bullet is not None
    assert body[3].paragraph.bullet.list_id == body[4].paragraph.bullet.list_id
    assert body[3].paragraph.bullet.nesting_level is None
    assert body[4].paragraph.bullet.nesting_level == 1

    assert _paragraph_text(body[5]) == "Before page break."
    assert body[6].paragraph is not None
    assert _paragraph_text(body[6]) == "<pagebreak>"
    assert body[7].paragraph.paragraph_style.named_style_type == "HEADING_2"
    assert _paragraph_text(body[7]) == "After Break"

    assert body[8].table is not None
    table_rows = body[8].table.table_rows or []
    assert len(table_rows) == 1
    cell_1 = table_rows[0].table_cells[0]
    cell_2 = table_rows[0].table_cells[1]
    assert _paragraph_text(cell_1.content[0]) == "Cell A1"
    assert _paragraph_text(cell_2.content[0]) == "Cell A2"


def test_deserialize_xml_parses_segments_and_footnote_refs(tmp_path: Path) -> None:
    folder = _write_xml_folder(
        tmp_path / "xml-segments",
        document_xml="""<?xml version="1.0" encoding="UTF-8"?>
<tab id="t.0" title="Tab 1" index="0">
  <body>
    <sectionbreak defaultHeaderId="h.one" defaultFooterId="f.one" />
    <p>Body text before footnote<footnoteref id="fn.one" />.</p>
  </body>
  <header id="h.one">
    <p>Header content</p>
  </header>
  <footer id="f.one">
    <p>Footer content</p>
  </footer>
  <footnote id="fn.one">
    <p>Footnote content</p>
  </footnote>
</tab>
""",
    )

    document = _xml_serde._parse(folder).document
    doc_tab = document.tabs[0].document_tab
    assert doc_tab is not None

    body = doc_tab.body.content or []
    assert _paragraph_text(body[1]) == "Body text before footnote<fn:fn.one>."

    assert doc_tab.headers is not None and "h.one" in doc_tab.headers
    assert doc_tab.footers is not None and "f.one" in doc_tab.footers
    assert doc_tab.footnotes is not None and "fn.one" in doc_tab.footnotes
    assert _paragraph_text(doc_tab.headers["h.one"].content[0]) == "Header content"
    assert _paragraph_text(doc_tab.footers["f.one"].content[0]) == "Footer content"
    assert _paragraph_text(doc_tab.footnotes["fn.one"].content[0]) == (
        "Footnote content"
    )


def test_deserialize_xml_roundtrip_semantics_are_stable_for_live_fixture(
    tmp_path: Path,
) -> None:
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "xml_cycle2_live_probe"
        / "desired"
    )
    working = tmp_path / "xml-live-fixture"
    shutil.copytree(fixture, working)

    initial_bundle = _xml_serde._parse(working)
    roundtrip = tmp_path / "xml-live-fixture-roundtrip"
    _xml_serde.serialize(initial_bundle, roundtrip)
    reparsed_bundle = _xml_serde.deserialize(roundtrip).desired

    assert _document_signature(reparsed_bundle.document) == _document_signature(
        initial_bundle.document
    )
