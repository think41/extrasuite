"""Regression guards for MarkdownSerde 3-way merge preservation.

These tests verify that the markdown serde's 3-way merge preserves
properties from the raw API base that markdown cannot represent (colors,
fonts, direction, padding, headingId, cell styles, etc.).

Originally written as xfail bug-catching tests. Now passing as regression
guards after the 3-way merge fix. Any test still marked xfail documents
a known limitation.

Test naming: test_bug_<category>_<what>

Categories:
- style_loss: text styles (font, color, underline) preserved on round-trip
- paragraph: paragraph-level properties (direction, lineSpacing)
- table: table cell styles, structure, row addition
- empty_para: colored empty paragraph handling
- heading: heading ID preservation
- list: indent properties preserved
- inline_code: surrounding styles preserved
- bullet: bullet textStyle preservation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.serde.markdown import MarkdownSerde

GOLDEN_DIR = Path(__file__).parent / "golden"
MD_GOLDEN_ID = "1vL8dY0Ok__9VaUIqhBCMeElS5QdaKZfbgr_YCja5kx0"

_serde = MarkdownSerde()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_golden(doc_id: str) -> Document:
    path = GOLDEN_DIR / f"{doc_id}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _make_bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


class RoundTrip:
    def __init__(self, doc_id: str, folder: Path) -> None:
        self.doc = _load_golden(doc_id)
        self.bundle = _make_bundle(self.doc)
        self.folder = folder
        _serde.serialize(self.bundle, self.folder)

    def _tab_path(self, tab: str) -> Path:
        new = self.folder / "tabs" / f"{tab}.md"
        if new.exists():
            return new
        legacy = self.folder / f"{tab}.md"
        if legacy.exists():
            return legacy
        return new if (self.folder / "tabs").is_dir() else legacy

    def read_md(self, tab: str = "Tab_1") -> str:
        return self._tab_path(tab).read_text(encoding="utf-8")

    def write_md(self, content: str, tab: str = "Tab_1") -> None:
        self._tab_path(tab).write_text(content, encoding="utf-8")

    def edit_md(self, *, find: str, replace: str, tab: str = "Tab_1") -> None:
        md = self.read_md(tab)
        assert find in md, f"'{find}' not found in {tab}.md"
        self.write_md(md.replace(find, replace), tab)

    def deserialize(self):
        return _serde.deserialize(self.folder)


def _custom_doc_roundtrip(
    doc_dict: dict,
    folder: Path,
    edit_find: str | None = None,
    edit_replace: str | None = None,
):
    """Create a custom document, serialize, optionally edit, and deserialize."""
    doc = Document.model_validate(doc_dict)
    bundle = _make_bundle(doc)
    _serde.serialize(bundle, folder)
    if edit_find and edit_replace:
        tab_path = folder / "tabs" / "Tab_1.md" if (folder / "tabs").is_dir() else folder / "Tab_1.md"
        md = tab_path.read_text()
        md = md.replace(edit_find, edit_replace)
        tab_path.write_text(md)
    return _serde.deserialize(folder)


def _tab_dt(doc: Document, tab_idx: int = 0):
    return doc.tabs[tab_idx].document_tab  # type: ignore[index]


def _body_content(doc: Document, tab_idx: int = 0):
    dt = _tab_dt(doc, tab_idx)
    return dt.body.content or []  # type: ignore[union-attr]


def body_texts(doc: Document, tab_idx: int = 0) -> list[str]:
    texts: list[str] = []
    for se in _body_content(doc, tab_idx):
        if se.paragraph:
            text = "".join(
                (pe.text_run.content or "").rstrip("\n")
                for pe in (se.paragraph.elements or [])
                if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
            )
            if text:
                texts.append(text)
    return texts


def body_runs(doc: Document, tab_idx: int = 0, para_text: str = "") -> list[dict]:
    for se in _body_content(doc, tab_idx):
        if not se.paragraph:
            continue
        full_text = "".join(
            (pe.text_run.content or "").rstrip("\n")
            for pe in (se.paragraph.elements or [])
            if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
        )
        if para_text not in full_text:
            continue
        runs: list[dict] = []
        for pe in se.paragraph.elements or []:
            if not pe.text_run:
                continue
            content = pe.text_run.content or ""
            if content == "\n":
                continue
            ts = pe.text_run.text_style
            runs.append(
                {
                    "text": content,
                    "bold": bool(ts and ts.bold),
                    "italic": bool(ts and ts.italic),
                    "underline": bool(ts and ts.underline),
                    "strikethrough": bool(ts and ts.strikethrough),
                    "link": (ts.link.url or "") if ts and ts.link else "",
                    "font": (
                        ts.weighted_font_family.font_family
                        if ts and ts.weighted_font_family
                        else ""
                    ),
                    "font_size": (
                        ts.font_size.magnitude if ts and ts.font_size else None
                    ),
                    "fg_color": ts.foreground_color is not None if ts else False,
                    "bg_color": ts.background_color is not None if ts else False,
                }
            )
        return runs
    pytest.fail(f"No paragraph containing '{para_text}' found")


def body_para_styles(doc: Document, tab_idx: int = 0) -> list[dict]:
    """Extract paragraph style properties for paragraphs with text content."""
    styles: list[dict] = []
    for se in _body_content(doc, tab_idx):
        if not se.paragraph:
            continue
        text = "".join(
            (pe.text_run.content or "").rstrip("\n")
            for pe in (se.paragraph.elements or [])
            if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
        )
        if not text:
            continue
        ps = se.paragraph.paragraph_style
        styles.append(
            {
                "text": text,
                "named_style": (
                    str(ps.named_style_type)
                    if ps and ps.named_style_type
                    else "NORMAL_TEXT"
                ),
                "alignment": str(ps.alignment) if ps and ps.alignment else None,
                "line_spacing": ps.line_spacing if ps else None,
                "direction": str(ps.direction) if ps and ps.direction else None,
                "space_above": (
                    ps.space_above.magnitude
                    if ps and ps.space_above and ps.space_above.magnitude
                    else None
                ),
                "space_below": (
                    ps.space_below.magnitude
                    if ps and ps.space_below and ps.space_below.magnitude
                    else None
                ),
                "indent_first": (
                    ps.indent_first_line.magnitude
                    if ps and ps.indent_first_line and ps.indent_first_line.magnitude
                    else None
                ),
                "indent_start": (
                    ps.indent_start.magnitude
                    if ps and ps.indent_start and ps.indent_start.magnitude
                    else None
                ),
                "heading_id": ps.heading_id if ps else None,
            }
        )
    return styles


def table_cell_para_styles(
    doc: Document, tab_idx: int = 0, table_idx: int = 0, row: int = 0, col: int = 0
) -> list[dict]:
    """Extract paragraph style dicts from a specific table cell."""
    table_count = 0
    for se in _body_content(doc, tab_idx):
        if not se.table:
            continue
        if table_count != table_idx:
            table_count += 1
            continue
        rows = se.table.table_rows or []
        cells = rows[row].table_cells or []
        result: list[dict] = []
        for cell_se in cells[col].content or []:
            if not cell_se.paragraph:
                continue
            ps = cell_se.paragraph.paragraph_style
            result.append(
                {
                    "named_style": (
                        str(ps.named_style_type) if ps and ps.named_style_type else None
                    ),
                    "line_spacing": ps.line_spacing if ps else None,
                    "direction": str(ps.direction) if ps and ps.direction else None,
                }
            )
        return result
    pytest.fail(f"Table index {table_idx} not found")


def table_cell_style(
    doc: Document, tab_idx: int = 0, table_idx: int = 0, row: int = 0, col: int = 0
) -> dict:
    """Extract tableCellStyle from a specific cell."""
    table_count = 0
    for se in _body_content(doc, tab_idx):
        if not se.table:
            continue
        if table_count != table_idx:
            table_count += 1
            continue
        rows = se.table.table_rows or []
        cells = rows[row].table_cells or []
        tcs = cells[col].table_cell_style
        if not tcs:
            return {}
        return tcs.model_dump(by_alias=True, exclude_none=True)
    pytest.fail(f"Table index {table_idx} not found")


# ===========================================================================
# BUG: Link text runs lose underline and foregroundColor after any edit
# ===========================================================================


class TestLinkStyleLoss:
    """Links in the golden doc have underline=True and foregroundColor (blue)
    as part of their textStyle. Markdown cannot represent these implicit link
    styles. On any body edit, the 3-way merge replaces body content from
    mine, which lacks these styles.
    """

    def test_bug_link_loses_foreground_color_after_unrelated_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing a distant paragraph should not strip link foregroundColor."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        # Edit a paragraph far from the links
        rt.edit_md(
            find="Final paragraph of the document.",
            replace="Final edited paragraph.",
        )
        result = rt.deserialize()
        runs = body_runs(result.desired.document, para_text="Example Website")
        link_runs = [r for r in runs if r["link"]]
        assert link_runs, "Link should still exist"
        assert link_runs[0]["fg_color"], (
            "Link lost foregroundColor after editing an unrelated paragraph"
        )

    def test_bug_link_loses_underline_after_unrelated_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing a distant paragraph should not strip link underline."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Final paragraph of the document.",
            replace="Final edited paragraph.",
        )
        result = rt.deserialize()
        runs = body_runs(result.desired.document, para_text="Example Website")
        link_runs = [r for r in runs if r["link"]]
        assert link_runs, "Link should still exist"
        assert link_runs[0]["underline"], (
            "Link lost underline after editing an unrelated paragraph"
        )

    def test_bug_all_links_lose_color_after_any_edit(self, tmp_path: Path) -> None:
        """All links lose foreground color after any body edit."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Final paragraph of the document.",
            replace="Final edited paragraph.",
        )
        result = rt.deserialize()
        # Check the second link paragraph (Google, GitHub)
        runs = body_runs(result.desired.document, para_text="Google")
        link_runs = [r for r in runs if r["link"]]
        assert len(link_runs) >= 2, "Should have Google and GitHub links"
        for lr in link_runs:
            assert lr["fg_color"], f"Link '{lr['text']}' lost foregroundColor"


# ===========================================================================
# BUG: Paragraph-level styles lost after body edits
# ===========================================================================


class TestParagraphStyleLoss:
    """Paragraph styles (direction, lineSpacing) exist in the base document
    but markdown cannot represent them. After any edit, the 3-way merge
    replaces body content from the markdown parse, losing these.
    """

    def test_bug_edited_paragraph_loses_direction(self, tmp_path: Path) -> None:
        """Editing paragraph text should preserve paragraphStyle.direction."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        # Check base has direction set
        base_styles = body_para_styles(rt.bundle.document)
        plain_para = [s for s in base_styles if s["text"] == "Second plain paragraph."]
        assert plain_para
        base_direction = plain_para[0]["direction"]

        rt.edit_md(
            find="Second plain paragraph.",
            replace="Edited plain paragraph.",
        )
        result = rt.deserialize()
        desired_styles = body_para_styles(result.desired.document)
        edited_para = [
            s for s in desired_styles if s["text"] == "Edited plain paragraph."
        ]
        assert edited_para, "Desired should have the edited paragraph"
        assert edited_para[0]["direction"] == base_direction, (
            f"direction lost: base={base_direction}, desired={edited_para[0]['direction']}"
        )

    def test_bug_unedited_paragraph_loses_direction_after_other_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing paragraph A should not destroy paragraph B's direction."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_styles = body_para_styles(rt.bundle.document)
        target = [
            s for s in base_styles if s["text"] == "Content under the second heading."
        ]
        assert target
        base_direction = target[0]["direction"]

        rt.edit_md(
            find="Second plain paragraph.",
            replace="Modified paragraph.",
        )
        result = rt.deserialize()
        desired_styles = body_para_styles(result.desired.document)
        target_d = [
            s
            for s in desired_styles
            if s["text"] == "Content under the second heading."
        ]
        assert target_d, "Unedited paragraph should still exist"
        assert target_d[0]["direction"] == base_direction, (
            f"Unedited paragraph lost direction: base={base_direction}, "
            f"desired={target_d[0]['direction']}"
        )

    def test_bug_table_cell_paragraph_loses_line_spacing(self, tmp_path: Path) -> None:
        """Table cell paragraph lineSpacing should survive after edit."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_ps = table_cell_para_styles(rt.bundle.document, row=0, col=0)
        assert base_ps
        base_ls = base_ps[0]["line_spacing"]

        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()

        desired_ps = table_cell_para_styles(result.desired.document, row=0, col=0)
        assert desired_ps
        assert desired_ps[0]["line_spacing"] == base_ls, (
            f"lineSpacing lost: base={base_ls}, desired={desired_ps[0]['line_spacing']}"
        )

    def test_bug_table_cell_paragraph_loses_direction(self, tmp_path: Path) -> None:
        """Table cell paragraph direction should survive after edit."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_ps = table_cell_para_styles(rt.bundle.document, row=0, col=0)
        assert base_ps
        base_dir = base_ps[0]["direction"]

        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()

        desired_ps = table_cell_para_styles(result.desired.document, row=0, col=0)
        assert desired_ps
        assert desired_ps[0]["direction"] == base_dir, (
            f"direction lost: base={base_dir}, desired={desired_ps[0]['direction']}"
        )


# ===========================================================================
# BUG: Table cell style loss (padding, contentAlignment, backgroundColor)
# ===========================================================================


class TestTableCellStyleLoss:
    """Table cells in the golden doc have tableCellStyle properties (padding,
    contentAlignment, backgroundColor). GFM markdown cannot represent these.
    After any edit, the 3-way merge rebuilds the table from the markdown
    parse, which creates cells with empty TableCellStyle().
    """

    def test_bug_cell_padding_lost_after_non_table_edit(self, tmp_path: Path) -> None:
        """Editing a paragraph outside the table should preserve cell padding."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_cs = table_cell_style(rt.bundle.document, row=0, col=0)
        assert "paddingLeft" in base_cs, f"Base should have padding: {base_cs}"

        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()

        desired_cs = table_cell_style(result.desired.document, row=0, col=0)
        assert "paddingLeft" in desired_cs, (
            f"Cell padding lost. Base: {list(base_cs.keys())}, "
            f"desired: {list(desired_cs.keys())}"
        )

    def test_bug_cell_alignment_lost_after_non_table_edit(self, tmp_path: Path) -> None:
        """Table cell contentAlignment should survive after non-table edit."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_cs = table_cell_style(rt.bundle.document, row=0, col=0)
        assert "contentAlignment" in base_cs

        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()

        desired_cs = table_cell_style(result.desired.document, row=0, col=0)
        assert "contentAlignment" in desired_cs, (
            f"contentAlignment lost. Base: {list(base_cs.keys())}, "
            f"desired: {list(desired_cs.keys())}"
        )

    def test_bug_untouched_cell_loses_style_after_other_cell_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing cell [1,0] should not destroy cell [2,2] padding."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_cs = table_cell_style(rt.bundle.document, row=2, col=2)
        assert "paddingLeft" in base_cs

        rt.edit_md(find="| Alpha |", replace="| Omega |")
        result = rt.deserialize()

        desired_cs = table_cell_style(result.desired.document, row=2, col=2)
        assert "paddingLeft" in desired_cs, (
            f"Untouched cell lost padding. Base: {list(base_cs.keys())}, "
            f"desired: {list(desired_cs.keys())}"
        )


# ===========================================================================
# BUG: GFM table header always gets bold
# ===========================================================================


# ===========================================================================
# BUG: Inline code ignores surrounding formatting
# ===========================================================================


class TestInlineCodeStyleLoss:
    """_tokens_to_elements creates a hardcoded TextStyle for InlineCode
    (Courier New 10pt). It ignores the accumulated `style` parameter,
    so surrounding bold/italic formatting is lost.
    """

    def test_bug_bold_inline_code_loses_bold(self, tmp_path: Path) -> None:
        """**`code`** should produce a run with bold=True AND font=Courier New."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="This has **`bold code`** here.",
        )
        result = rt.deserialize()
        runs = body_runs(result.desired.document, para_text="bold code")
        code_runs = [r for r in runs if r["font"] == "Courier New"]
        assert code_runs, "Should have a Courier New run"
        assert code_runs[0]["bold"], (
            f"**`bold code`** should be bold AND monospace, got: {code_runs[0]}"
        )

    def test_bug_italic_inline_code_loses_italic(self, tmp_path: Path) -> None:
        """*`code`* should produce a run with italic=True AND font=Courier New."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Second plain paragraph.",
            replace="This has *`italic code`* here.",
        )
        result = rt.deserialize()
        runs = body_runs(result.desired.document, para_text="italic code")
        code_runs = [r for r in runs if r["font"] == "Courier New"]
        assert code_runs, "Should have a Courier New run"
        assert code_runs[0]["italic"], (
            f"*`italic code`* should be italic AND monospace, got: {code_runs[0]}"
        )


# ===========================================================================
# BUG: Heading ID lost when heading text is edited
# ===========================================================================


class TestHeadingIdLoss:
    """Heading IDs (paragraphStyle.headingId) are set by Google Docs and used
    for internal links. Markdown deserialization creates headings without
    headingId. After editing heading text, the merge replaces the heading
    from mine, losing the ID.
    """

    def test_bug_heading_id_lost_after_text_edit(self, tmp_path: Path) -> None:
        """Editing heading text should preserve the heading ID."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_styles = body_para_styles(rt.bundle.document)
        intro = [s for s in base_styles if s["text"] == "Introduction"]
        assert intro
        base_heading_id = intro[0]["heading_id"]
        assert base_heading_id, "Base heading should have an ID"

        rt.edit_md(find="# Introduction\n", replace="# Overview\n")
        result = rt.deserialize()

        desired_styles = body_para_styles(result.desired.document)
        overview = [s for s in desired_styles if s["text"] == "Overview"]
        assert overview, "Desired should have 'Overview' heading"
        assert overview[0]["heading_id"] == base_heading_id, (
            f"Heading ID lost: base={base_heading_id}, "
            f"desired={overview[0]['heading_id']}"
        )

    def test_bug_unedited_heading_loses_id_after_paragraph_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing a paragraph should not destroy heading IDs elsewhere."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_styles = body_para_styles(rt.bundle.document)
        intro = [s for s in base_styles if s["text"] == "Introduction"]
        assert intro
        base_heading_id = intro[0]["heading_id"]
        assert base_heading_id

        rt.edit_md(
            find="Final paragraph of the document.",
            replace="Final edited paragraph.",
        )
        result = rt.deserialize()

        desired_styles = body_para_styles(result.desired.document)
        intro_d = [s for s in desired_styles if s["text"] == "Introduction"]
        assert intro_d, "Heading should still exist"
        assert intro_d[0]["heading_id"] == base_heading_id, (
            f"Unedited heading lost ID: base={base_heading_id}, "
            f"desired={intro_d[0]['heading_id']}"
        )


# ===========================================================================
# BUG: Colored empty paragraph loses color after body edit
# ===========================================================================


class TestColoredEmptyParagraph:
    """Colored empty paragraphs are serialized as <!-- --> but deserialized
    as plain paragraphs with no styling. On any body edit, the merge
    replaces body content from mine, losing the color.
    """

    def test_bug_colored_empty_para_loses_color_after_edit(
        self, tmp_path: Path
    ) -> None:
        """Colored empty paragraph should survive a nearby edit."""
        doc_dict = _load_golden(MD_GOLDEN_ID).model_dump(
            by_alias=True, exclude_none=True
        )

        # Inject a colored empty paragraph
        tab = doc_dict["tabs"][0]["documentTab"]
        body_content = tab["body"]["content"]
        colored_para = {
            "paragraph": {
                "elements": [
                    {
                        "textRun": {
                            "content": "\n",
                            "textStyle": {
                                "foregroundColor": {
                                    "color": {
                                        "rgbColor": {"red": 1.0, "green": 0, "blue": 0}
                                    }
                                }
                            },
                        }
                    }
                ],
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            }
        }
        body_content.insert(2, colored_para)

        result = _custom_doc_roundtrip(
            doc_dict,
            tmp_path / "doc",
            edit_find="Second plain paragraph.",
            edit_replace="Modified paragraph.",
        )

        found_colored = False
        for se in _body_content(result.desired.document):
            if not se.paragraph:
                continue
            elems = se.paragraph.elements or []
            if len(elems) == 1:
                tr = elems[0].text_run
                if (
                    tr
                    and tr.content == "\n"
                    and tr.text_style
                    and tr.text_style.foreground_color is not None
                ):
                    found_colored = True
                    break

        assert found_colored, (
            "Colored empty paragraph lost its foregroundColor after a nearby edit"
        )


# ===========================================================================
# BUG: List paragraph indent lost on round-trip
# ===========================================================================


class TestListIndentLoss:
    """List items in the base doc have paragraphStyle with indentFirstLine
    and indentStart. Markdown deserialization creates list paragraphs without
    these. After editing a list item, the indent properties are lost.
    """

    def test_bug_edited_list_item_loses_indent(self, tmp_path: Path) -> None:
        """Editing a list item should preserve indent properties."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_styles = body_para_styles(rt.bundle.document)
        bullet_items = [s for s in base_styles if s["text"] == "First bullet item"]
        assert bullet_items
        base_indent_first = bullet_items[0]["indent_first"]

        rt.edit_md(find="- First bullet item\n", replace="- Edited bullet item\n")
        result = rt.deserialize()

        desired_styles = body_para_styles(result.desired.document)
        edited = [s for s in desired_styles if s["text"] == "Edited bullet item"]
        assert edited, "Edited list item should exist"
        assert edited[0]["indent_first"] == base_indent_first, (
            f"indentFirst lost: base={base_indent_first}, desired={edited[0]['indent_first']}"
        )

    def test_bug_unedited_list_item_loses_indent_after_other_edit(
        self, tmp_path: Path
    ) -> None:
        """Editing a non-list paragraph should preserve list item indents."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_styles = body_para_styles(rt.bundle.document)
        bullet_items = [s for s in base_styles if s["text"] == "First bullet item"]
        assert bullet_items
        base_indent_first = bullet_items[0]["indent_first"]

        rt.edit_md(
            find="Final paragraph of the document.",
            replace="Final edited paragraph.",
        )
        result = rt.deserialize()

        desired_styles = body_para_styles(result.desired.document)
        bullet_d = [s for s in desired_styles if s["text"] == "First bullet item"]
        assert bullet_d, "List item should still exist"
        assert bullet_d[0]["indent_first"] == base_indent_first, (
            f"Unedited list item lost indent: base={base_indent_first}, "
            f"desired={bullet_d[0]['indent_first']}"
        )


# ===========================================================================
# BUG: Table column properties lost
# ===========================================================================


class TestTableColumnProperties:
    """Table tableStyle (including tableColumnProperties) from the base
    is lost when the merge rebuilds the table from the markdown parse.
    """

    def test_bug_table_style_lost_after_edit(self, tmp_path: Path) -> None:
        """Table tableStyle should survive after a nearby edit."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")

        base_table = None
        for se in _body_content(rt.bundle.document):
            if se.table:
                base_table = se.table
                break
        assert base_table

        base_ts = base_table.table_style
        has_col_props = base_ts and base_ts.table_column_properties
        if not has_col_props:
            pytest.skip("Golden doc table has no tableColumnProperties")

        rt.edit_md(find="Second plain paragraph.", replace="Modified paragraph.")
        result = rt.deserialize()

        desired_table = None
        for se in _body_content(result.desired.document):
            if se.table:
                desired_table = se.table
                break
        assert desired_table

        desired_ts = desired_table.table_style
        assert desired_ts and desired_ts.table_column_properties, (
            "Table column properties lost after nearby edit"
        )


# ===========================================================================
# BUG: Multi-paragraph table cells collapse to single paragraph
# ===========================================================================


class TestMultiParagraphTableCell:
    """Google Docs cells can have multiple paragraphs. GFM joins them
    with spaces, losing paragraph structure on round-trip.
    """

    def test_bug_multi_paragraph_cell_collapses(self, tmp_path: Path) -> None:
        """Multi-paragraph cells should preserve paragraph count."""
        doc_dict = _load_golden(MD_GOLDEN_ID).model_dump(
            by_alias=True, exclude_none=True
        )

        # Add a second paragraph to cell [1,0]
        tab = doc_dict["tabs"][0]["documentTab"]
        for se in tab["body"]["content"]:
            if "table" not in se:
                continue
            cell = se["table"]["tableRows"][1]["tableCells"][0]
            extra_para = {
                "paragraph": {
                    "elements": [{"textRun": {"content": "Extra line\n"}}],
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                }
            }
            cell["content"].insert(0, extra_para)
            break

        result = _custom_doc_roundtrip(
            doc_dict,
            tmp_path / "doc",
            edit_find="Second plain paragraph.",
            edit_replace="Modified paragraph.",
        )

        for se_d in _body_content(result.desired.document):
            if not se_d.table:
                continue
            cell = se_d.table.table_rows[1].table_cells[0]
            para_count = sum(1 for cse in (cell.content or []) if cse.paragraph)
            assert para_count >= 2, (
                f"Multi-paragraph cell collapsed to {para_count} paragraph(s)"
            )
            break
        else:
            pytest.fail("Table not found in desired")


# ===========================================================================
# BUG: Trailing \n run structure changes after any edit
# ===========================================================================


class TestTrailingNewlineStructure:
    """In the base document, the trailing \\n is part of the last text run
    (e.g. ' in it.\\n'). After a body edit, the deserialized paragraphs
    have \\n as a separate run. This changes the run count and structure.
    """

    def test_bug_trailing_newline_becomes_separate_run(self, tmp_path: Path) -> None:
        """After edit, unedited paragraphs should preserve \\n in last run."""
        rt = RoundTrip(MD_GOLDEN_ID, tmp_path / "doc")
        rt.edit_md(
            find="Final paragraph of the document.",
            replace="Final edited paragraph.",
        )
        result = rt.deserialize()

        # Check the "bold text" paragraph — it shouldn't change at all
        for se in _body_content(result.base.document):
            if not se.paragraph:
                continue
            elems = se.paragraph.elements or []
            text = "".join(
                (e.text_run.content or "").rstrip("\n")
                for e in elems
                if e.text_run and e.text_run.content != "\n"
            )
            if "bold text" not in text:
                continue
            base_last = elems[-1].text_run.content if elems[-1].text_run else ""
            break
        else:
            pytest.fail("Base paragraph not found")

        for se in _body_content(result.desired.document):
            if not se.paragraph:
                continue
            elems = se.paragraph.elements or []
            text = "".join(
                (e.text_run.content or "").rstrip("\n")
                for e in elems
                if e.text_run and e.text_run.content != "\n"
            )
            if "bold text" not in text:
                continue
            desired_last = elems[-1].text_run.content if elems[-1].text_run else ""
            break
        else:
            pytest.fail("Desired paragraph not found")

        assert base_last == desired_last, (
            f"Trailing run changed: base last run={base_last!r}, "
            f"desired last run={desired_last!r}"
        )


# ===========================================================================
# BUG: Full table structure not preserved after non-table edit
# ===========================================================================


# ===========================================================================
# BUG: Document with bold+strikethrough in source loses styles after edit
# (only when styles are in the original document, not user-typed markdown)
# ===========================================================================


class TestOriginalDocStylePreservation:
    """When the original document has styled text (e.g. foreground color on
    regular text, non-standard font), these styles survive serialize but
    are lost on deserialize because the markdown parse doesn't capture them.
    """

    def test_bug_colored_text_loses_color_after_edit(self, tmp_path: Path) -> None:
        """Text with foreground color should survive after unrelated edit."""
        doc_dict = _load_golden(MD_GOLDEN_ID).model_dump(
            by_alias=True, exclude_none=True
        )

        # Add a paragraph with colored (red) text
        tab = doc_dict["tabs"][0]["documentTab"]
        body_content = tab["body"]["content"]
        colored_para = {
            "paragraph": {
                "elements": [
                    {
                        "textRun": {
                            "content": "This text is red.\n",
                            "textStyle": {
                                "foregroundColor": {
                                    "color": {
                                        "rgbColor": {"red": 1.0, "green": 0, "blue": 0}
                                    }
                                }
                            },
                        }
                    }
                ],
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            }
        }
        body_content.insert(3, colored_para)

        result = _custom_doc_roundtrip(
            doc_dict,
            tmp_path / "doc",
            edit_find="Second plain paragraph.",
            edit_replace="Modified paragraph.",
        )

        runs = body_runs(result.desired.document, para_text="This text is red")
        assert runs, "Red text paragraph should exist"
        assert runs[0]["fg_color"], "Red text lost its foregroundColor"

    def test_bug_highlighted_text_loses_background_after_edit(
        self, tmp_path: Path
    ) -> None:
        """Text with background color should survive after unrelated edit."""
        doc_dict = _load_golden(MD_GOLDEN_ID).model_dump(
            by_alias=True, exclude_none=True
        )

        # Add a paragraph with background-highlighted text
        tab = doc_dict["tabs"][0]["documentTab"]
        body_content = tab["body"]["content"]
        highlighted_para = {
            "paragraph": {
                "elements": [
                    {
                        "textRun": {
                            "content": "Highlighted text.\n",
                            "textStyle": {
                                "backgroundColor": {
                                    "color": {
                                        "rgbColor": {
                                            "red": 1.0,
                                            "green": 1.0,
                                            "blue": 0,
                                        }
                                    }
                                }
                            },
                        }
                    }
                ],
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            }
        }
        body_content.insert(3, highlighted_para)

        result = _custom_doc_roundtrip(
            doc_dict,
            tmp_path / "doc",
            edit_find="Second plain paragraph.",
            edit_replace="Modified paragraph.",
        )

        runs = body_runs(result.desired.document, para_text="Highlighted text")
        assert runs, "Highlighted paragraph should exist"
        assert runs[0]["bg_color"], "Highlighted text lost its backgroundColor"

    def test_bug_custom_font_text_loses_font_after_edit(self, tmp_path: Path) -> None:
        """Text with custom font should survive after unrelated edit."""
        doc_dict = _load_golden(MD_GOLDEN_ID).model_dump(
            by_alias=True, exclude_none=True
        )

        # Add a paragraph with Georgia font
        tab = doc_dict["tabs"][0]["documentTab"]
        body_content = tab["body"]["content"]
        font_para = {
            "paragraph": {
                "elements": [
                    {
                        "textRun": {
                            "content": "Georgia font text.\n",
                            "textStyle": {
                                "weightedFontFamily": {"fontFamily": "Georgia"}
                            },
                        }
                    }
                ],
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            }
        }
        body_content.insert(3, font_para)

        result = _custom_doc_roundtrip(
            doc_dict,
            tmp_path / "doc",
            edit_find="Second plain paragraph.",
            edit_replace="Modified paragraph.",
        )

        runs = body_runs(result.desired.document, para_text="Georgia font text")
        assert runs, "Georgia font paragraph should exist"
        assert runs[0]["font"] == "Georgia", (
            f"Font lost: expected 'Georgia', got '{runs[0]['font']}'"
        )

    def test_bug_font_size_lost_after_edit(self, tmp_path: Path) -> None:
        """Text with explicit font size should survive after unrelated edit."""
        doc_dict = _load_golden(MD_GOLDEN_ID).model_dump(
            by_alias=True, exclude_none=True
        )

        # Add a paragraph with 14pt font
        tab = doc_dict["tabs"][0]["documentTab"]
        body_content = tab["body"]["content"]
        size_para = {
            "paragraph": {
                "elements": [
                    {
                        "textRun": {
                            "content": "Large font text.\n",
                            "textStyle": {"fontSize": {"magnitude": 14, "unit": "PT"}},
                        }
                    }
                ],
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            }
        }
        body_content.insert(3, size_para)

        result = _custom_doc_roundtrip(
            doc_dict,
            tmp_path / "doc",
            edit_find="Second plain paragraph.",
            edit_replace="Modified paragraph.",
        )

        runs = body_runs(result.desired.document, para_text="Large font text")
        assert runs, "Large font paragraph should exist"
        assert runs[0]["font_size"] == 14, (
            f"Font size lost: expected 14, got {runs[0]['font_size']}"
        )


# ===========================================================================
# BUG: Spurious synthetic list defs injected into desired after word edit
# ===========================================================================

OASIS_CIQ_GOLDEN_ID = "19GeM80fb9c0uHEget4jaR8WotgXwNpTwTaOHzynH-PI"


class TestListIdsPreserved:
    """3-way merge must not inject synthetic list IDs into the desired document.

    List IDs can't be represented in markdown, so they should pass through
    from base untouched.  The injection block in _three_way_merge() was
    unconditionally copying all of mine's synthetic list defs (e.g.
    ``kix.md_list_bullet_1``) into desired even for UNCHANGED lists.  The
    reconciler then generated spurious createNamedRangeRequests/list requests
    for each of those 23 phantom defs.
    """

    def test_list_ids_preserved_through_word_edit(self, tmp_path: Path) -> None:
        """A single word edit in a non-list paragraph must not add synthetic list IDs."""
        from extradoc.reconcile_v3.api import reconcile_batches

        rt = RoundTrip(OASIS_CIQ_GOLDEN_ID, tmp_path / "doc")

        # Edit a plain (non-list) subtitle paragraph
        rt.edit_md(find="Public Review Draft 02", replace="Public Review Draft 03")

        result = rt.deserialize()

        # Collect list IDs from base and desired
        def _list_ids(doc: Document) -> set[str]:
            ids: set[str] = set()
            for tab in doc.tabs or []:
                dt = tab.document_tab
                if dt and dt.lists:
                    ids.update(dt.lists.keys())
            return ids

        base_ids = _list_ids(result.base.document)
        desired_ids = _list_ids(result.desired.document)

        # No new synthetic list IDs should appear in desired
        new_ids = desired_ids - base_ids
        assert not new_ids, (
            f"Spurious synthetic list IDs injected into desired: {sorted(new_ids)}"
        )

        # All base list IDs must survive into desired (not be lost either)
        missing_ids = base_ids - desired_ids
        assert not missing_ids, (
            f"Base list IDs missing from desired: {sorted(missing_ids)}"
        )

        # The requests should not include any createParagraphBullets or similar
        # list-construction requests caused by the spurious synthetic defs.
        batches = reconcile_batches(result.base.document, result.desired.document)
        list_requests = [
            req
            for batch in batches
            for req in (batch.requests or [])
            if req.model_dump(by_alias=True, exclude_none=True).keys()
            & {"createParagraphBullets", "updateListProperties"}
        ]
        assert not list_requests, (
            f"Unexpected list-related requests generated: {list_requests}. "
            "Likely caused by spurious synthetic list defs in desired."
        )
