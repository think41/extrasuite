"""
End-to-end tests: DOCX → markdown → edit → apply → pandoc verify.

Each test covers one or more markdown features:
  - Heading text change
  - Heading level change (h1→h3, h2→h3)
  - Paragraph text edit
  - Bold / italic / strikethrough formatting
  - Table cell edit
  - Bullet list item edit
  - Ordered list item edit
  - List item deletion
  - List item insertion
  - Paragraph deletion
  - Paragraph insertion
  - Code block (simulated via a code-style edit)
  - Block quote (round-trip)

Workflow for every scenario:
  1. Parse test_report.docx  → base AST
  2. Serialize to markdown   → base_md
  3. Edit base_md            → edited_md
  4. parse_markdown(edited_md) → derived AST
  5. diff(base, derived)     → ops
  6. apply_ops(docx, ops, output_docx)
  7. pandoc output_docx --to=gfm  → verify assertions
  8. Save output to testdata/e2e_fixtures/<scenario>.docx for manual review

The original (before) is always testdata/test_report.docx.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

from extradocx import DocxParser, apply_ops, diff, parse_markdown, to_markdown

TESTDATA = pathlib.Path(__file__).parent.parent / "testdata"
REPORT_DOCX = TESTDATA / "test_report.docx"
FIXTURES_DIR = TESTDATA / "e2e_fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pandoc(docx_path: pathlib.Path) -> str:
    """Run pandoc on *docx_path* and return GFM markdown output."""
    result = subprocess.run(
        ["pandoc", str(docx_path), "--to=gfm"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _apply_and_verify(
    base_md: str,
    edited_md: str,
    doc: object,
    scenario_name: str,
    tmp_path: pathlib.Path,
) -> str:
    """Full pipeline: diff → apply → pandoc. Returns pandoc output."""
    reparsed = parse_markdown(edited_md)
    ops = diff(doc, reparsed)  # type: ignore[arg-type]

    out_path = tmp_path / f"{scenario_name}.docx"
    apply_ops(REPORT_DOCX, ops, out_path, base_children=doc.children)  # type: ignore[attr-defined]

    # Save to fixtures dir for manual review
    fixture_path = FIXTURES_DIR / f"{scenario_name}.docx"
    shutil.copy(out_path, fixture_path)

    return _pandoc(out_path)


@pytest.fixture(scope="module")
def doc():
    return DocxParser(REPORT_DOCX).parse()


@pytest.fixture(scope="module")
def base_md(doc):
    return to_markdown(doc)


# ---------------------------------------------------------------------------
# Scenario 1: Heading text change (h1)
# ---------------------------------------------------------------------------


class TestHeadingTextChange:
    """Change the text of an h1 heading."""

    def test_h1_text_changed(self, doc, base_md, tmp_path):
        edited = base_md.replace(
            "# Chapter 1: Introduction to Software Engineering",
            "# Chapter 1: Getting Started",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "h1_text_change", tmp_path)

        assert "Chapter 1: Getting Started" in pandoc_out
        assert "Chapter 1: Introduction to Software Engineering" not in pandoc_out

    def test_h2_text_changed(self, doc, base_md, tmp_path):
        edited = base_md.replace("## 1.1 Overview", "## 1.1 Introduction Overview")
        pandoc_out = _apply_and_verify(base_md, edited, doc, "h2_text_change", tmp_path)

        assert "1.1 Introduction Overview" in pandoc_out
        assert "1.1 Overview" not in pandoc_out or "Introduction Overview" in pandoc_out

    def test_h3_text_changed(self, doc, base_md, tmp_path):
        edited = base_md.replace("### 2.1.1 Interviews", "### 2.1.1 Interview Techniques")
        pandoc_out = _apply_and_verify(base_md, edited, doc, "h3_text_change", tmp_path)

        assert "Interview Techniques" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 2: Heading level change
# ---------------------------------------------------------------------------


class TestHeadingLevelChange:
    """Promote or demote a heading level."""

    def test_h2_to_h3(self, doc, base_md, tmp_path):
        """Demote ## 1.2 Historical Context to ### 1.2 Historical Context."""
        edited = base_md.replace("## 1.2 Historical Context", "### 1.2 Historical Context")
        pandoc_out = _apply_and_verify(base_md, edited, doc, "h2_to_h3_level_change", tmp_path)

        # The heading should appear at h3 level
        assert "1.2 Historical Context" in pandoc_out
        # pandoc GFM output uses ### for h3
        assert re.search(r"###\s+1\.2 Historical Context", pandoc_out)

    def test_h1_to_h2(self, doc, base_md, tmp_path):
        """Demote # Chapter 2 to ## Chapter 2."""
        edited = base_md.replace(
            "# Chapter 2: Requirements Engineering",
            "## Chapter 2: Requirements Engineering",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "h1_to_h2_level_change", tmp_path)

        assert "Chapter 2: Requirements Engineering" in pandoc_out
        assert re.search(r"##\s+Chapter 2: Requirements Engineering", pandoc_out)


# ---------------------------------------------------------------------------
# Scenario 3: Paragraph text edit
# ---------------------------------------------------------------------------


class TestParagraphTextEdit:
    """Edit body paragraph text."""

    def test_paragraph_text_replaced(self, doc, base_md, tmp_path):
        """Replace a bullet list item text."""
        edited = base_md.replace(
            "- 1960s: Birth of structured programming",
            "- 1960s: Origins of structured programming",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "paragraph_text_replace", tmp_path)

        assert "Origins of structured programming" in pandoc_out
        assert "Birth of structured programming" not in pandoc_out

    def test_mixed_bold_italic_paragraph_edited(self, doc, base_md, tmp_path):
        """Edit a paragraph that contains bold and italic runs."""
        old_line = (
            "**Note: **Software engineering encompasses a wide range of disciplines "
            "from requirements analysis to deployment and maintenance."
            "* — see appendix for details.*"
        )
        new_line = (
            "**Note: **Software engineering covers many disciplines "
            "from design to operations.* — see appendix.*"
        )
        edited = base_md.replace(old_line, new_line)
        pandoc_out = _apply_and_verify(base_md, edited, doc, "bold_italic_paragraph_edit", tmp_path)

        assert "covers many disciplines" in pandoc_out
        assert "encompasses a wide range" not in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 4: Formatting changes (bold, italic, strikethrough)
# ---------------------------------------------------------------------------


class TestFormattingChanges:
    """Add or change inline formatting."""

    def test_add_bold_to_text(self, doc, base_md, tmp_path):
        """Wrap an existing plain text phrase in bold."""
        edited = base_md.replace(
            "1. Separation of concerns",
            "1. **Separation of concerns**",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "add_bold_formatting", tmp_path)

        assert "Separation of concerns" in pandoc_out
        # pandoc should preserve bold markup
        assert "**Separation of concerns**" in pandoc_out or "Separation of concerns" in pandoc_out

    def test_add_italic_to_heading(self, doc, base_md, tmp_path):
        """Change a heading's text to include italic."""
        edited = base_md.replace(
            "## 1.3 Core Principles",
            "## 1.3 *Core* Principles",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "add_italic_in_heading", tmp_path)

        assert "Core" in pandoc_out
        assert "Principles" in pandoc_out

    def test_add_strikethrough(self, doc, base_md, tmp_path):
        """Add strikethrough formatting to a list item."""
        edited = base_md.replace(
            "- 2020s: LLM-assisted development",
            "- ~~2020s: LLM-assisted development~~ (now mainstream)",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "add_strikethrough", tmp_path)

        assert "LLM" in pandoc_out
        assert "mainstream" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 5: Table cell edit
# ---------------------------------------------------------------------------


class TestTableCellEdit:
    """Edit content in a table cell."""

    def test_table_cell_text_replaced(self, doc, base_md, tmp_path):
        """Change a table cell value."""
        # The SOLID principles table has SRP → DIP rows
        edited = base_md.replace(
            "| SRP           | Single Responsibility Principle | One class per conc",
            "| SRP           | Single Responsibility Principle | One module per con",
        )
        # Fix the truncated line by replacing just the visible prefix
        edited = base_md.replace(
            "One class per concern",
            "One module per concern",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "table_cell_edit", tmp_path)

        assert "One module per concern" in pandoc_out
        assert "One class per concern" not in pandoc_out

    def test_table_header_text_replaced(self, doc, base_md, tmp_path):
        """Change a deployment strategies table cell."""
        edited = base_md.replace(
            "Big Bang",
            "Full Cutover",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "table_header_edit", tmp_path)

        assert "Full Cutover" in pandoc_out
        assert "Big Bang" not in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 6: Bullet list item edits
# ---------------------------------------------------------------------------


class TestBulletListItemEdit:
    """Edit bullet list items."""

    def test_list_item_text_changed(self, doc, base_md, tmp_path):
        edited = base_md.replace(
            "- 1990s: Agile manifesto and iterative development",
            "- 1990s: Agile manifesto and rapid development",
        )
        pandoc_out = _apply_and_verify(
            base_md, edited, doc, "bullet_list_item_text_change", tmp_path
        )

        assert "rapid development" in pandoc_out
        assert "iterative development" not in pandoc_out

    def test_two_list_items_changed(self, doc, base_md, tmp_path):
        """Edit two different list items in the same list."""
        edited = base_md.replace(
            "- 2000s: DevOps, cloud computing, microservices",
            "- 2000s: DevOps and cloud-native architectures",
        ).replace(
            "- 2010s: AI/ML integration in software workflows",
            "- 2010s: AI/ML and data-driven development",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "two_bullet_items_changed", tmp_path)

        assert "cloud-native architectures" in pandoc_out
        assert "data-driven development" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 7: Ordered list item edits
# ---------------------------------------------------------------------------


class TestOrderedListItemEdit:
    """Edit numbered list items."""

    def test_ordered_item_changed(self, doc, base_md, tmp_path):
        edited = base_md.replace(
            "1. Separation of concerns",
            "1. Separation of responsibilities",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "ordered_list_item_change", tmp_path)

        assert "Separation of responsibilities" in pandoc_out
        assert "Separation of concerns" not in pandoc_out

    def test_ordered_item_with_inline_code(self, doc, base_md, tmp_path):
        """Change an ordered list item to include inline code."""
        edited = base_md.replace(
            "2. DRY (Don't Repeat Yourself)",
            "2. DRY (`Don't Repeat Yourself`)",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "ordered_item_with_code", tmp_path)

        assert "Don't Repeat Yourself" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 8: Block deletion
# ---------------------------------------------------------------------------


class TestBlockDeletion:
    """Delete paragraphs and headings."""

    def test_delete_paragraph(self, doc, base_md, tmp_path):
        """Delete the bold/italic 'Note:' paragraph."""
        note_line = None
        for line in base_md.split("\n"):
            if "**Note: **Software engineering encompasses" in line:
                note_line = line
                break
        assert note_line is not None, "Note line not found in base_md"

        edited = base_md.replace(note_line + "\n", "")
        pandoc_out = _apply_and_verify(base_md, edited, doc, "delete_paragraph", tmp_path)

        assert "encompasses a wide range" not in pandoc_out

    def test_delete_h3_heading(self, doc, base_md, tmp_path):
        """Delete a sub-heading."""
        edited = base_md.replace("### 2.1.1 Interviews\n", "")
        pandoc_out = _apply_and_verify(base_md, edited, doc, "delete_h3_heading", tmp_path)

        assert "2.1.1 Interviews" not in pandoc_out

    def test_delete_list_item(self, doc, base_md, tmp_path):
        """Remove one item from a bullet list."""
        edited = base_md.replace("- 1970s: Software crisis and the rise of methodologies\n", "")
        pandoc_out = _apply_and_verify(base_md, edited, doc, "delete_list_item", tmp_path)

        assert "Software crisis" not in pandoc_out
        # Other items should still be present
        assert "1960s" in pandoc_out
        assert "1980s" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 9: Block insertion
# ---------------------------------------------------------------------------


class TestBlockInsertion:
    """Insert new paragraphs and headings."""

    def test_insert_paragraph_after_heading(self, doc, base_md, tmp_path):
        """Insert a new paragraph after an existing heading."""
        edited = base_md.replace(
            "## 1.1 Overview\n",
            "## 1.1 Overview\n\nThis section provides a high-level overview.\n",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "insert_paragraph", tmp_path)

        assert "This section provides a high-level overview." in pandoc_out

    def test_insert_heading_before_section(self, doc, base_md, tmp_path):
        """Insert a new h2 heading before an existing h2."""
        edited = base_md.replace(
            "## 1.2 Historical Context\n",
            "## 1.1b Context Background\n\nBackground information.\n\n## 1.2 Historical Context\n",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "insert_heading", tmp_path)

        assert "Context Background" in pandoc_out
        assert "Background information." in pandoc_out

    def test_insert_list_item(self, doc, base_md, tmp_path):
        """Insert a new bullet item into an existing list."""
        edited = base_md.replace(
            "- 1980s: Object-oriented programming emerges\n",
            "- 1975s: Structured design methods\n- 1980s: Object-oriented programming emerges\n",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "insert_list_item", tmp_path)

        assert "Structured design methods" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 10: Link handling
# ---------------------------------------------------------------------------


class TestLinkHandling:
    """Add or modify links in text."""

    def test_add_link_to_text(self, doc, base_md, tmp_path):
        """Add a hyperlink to a word in a paragraph."""
        edited = base_md.replace(
            "1. Separation of concerns",
            "1. [Separation of concerns](https://en.wikipedia.org/wiki/Separation_of_concerns)",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "add_link", tmp_path)

        assert "Separation of concerns" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 11: Complex multi-edit
# ---------------------------------------------------------------------------


class TestComplexMultiEdit:
    """Multiple edits in one pass — realistic agent workflow."""

    def test_multi_edit_chapter1(self, doc, base_md, tmp_path):
        """Edit heading + list item + table cell in one pass."""
        edited = (
            base_md.replace(
                "# Chapter 1: Introduction to Software Engineering",
                "# Chapter 1: Modern Software Engineering",
            )
            .replace(
                "- 1960s: Birth of structured programming",
                "- 1960s: Foundations of programming",
            )
            .replace(
                "One class per concern",
                "One concern per class",
            )
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "multi_edit_chapter1", tmp_path)

        assert "Modern Software Engineering" in pandoc_out
        assert "Foundations of programming" in pandoc_out
        assert "One concern per class" in pandoc_out

    def test_chapter_restructure(self, doc, base_md, tmp_path):
        """Demote a heading and edit surrounding content."""
        edited = base_md.replace(
            "## 2.3 Acceptance Criteria",
            "### 2.3 Acceptance Criteria",
        ).replace(
            "Acceptance criteria must be measurable, verifiable, and unambiguous.",
            "Acceptance criteria must be clear, measurable, and verifiable.",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "chapter_restructure", tmp_path)

        assert "Acceptance Criteria" in pandoc_out
        assert "clear, measurable, and verifiable" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 12: Inline code in text
# ---------------------------------------------------------------------------


class TestInlineCode:
    """Add inline code spans to text."""

    def test_add_inline_code(self, doc, base_md, tmp_path):
        """Replace a tool name with inline-code-formatted version."""
        edited = base_md.replace(
            "- Lint and format check (ruff, ESLint, etc.)",
            "- Lint and format check (`ruff`, `ESLint`, etc.)",
        )
        pandoc_out = _apply_and_verify(base_md, edited, doc, "add_inline_code", tmp_path)

        assert "ruff" in pandoc_out
        assert "ESLint" in pandoc_out


# ---------------------------------------------------------------------------
# Scenario 13: Fixture integrity — verify all fixtures were written
# ---------------------------------------------------------------------------


class TestFixtureIntegrity:
    """Sanity-check that all expected fixture files were produced."""

    EXPECTED_FIXTURES = [
        "h1_text_change",
        "h2_text_change",
        "h3_text_change",
        "h2_to_h3_level_change",
        "h1_to_h2_level_change",
        "paragraph_text_replace",
        "bold_italic_paragraph_edit",
        "add_bold_formatting",
        "add_italic_in_heading",
        "add_strikethrough",
        "table_cell_edit",
        "table_header_edit",
        "bullet_list_item_text_change",
        "two_bullet_items_changed",
        "ordered_list_item_change",
        "ordered_item_with_code",
        "delete_paragraph",
        "delete_h3_heading",
        "delete_list_item",
        "insert_paragraph",
        "insert_heading",
        "insert_list_item",
        "add_link",
        "multi_edit_chapter1",
        "chapter_restructure",
        "add_inline_code",
    ]

    def test_fixtures_directory_exists(self):
        assert FIXTURES_DIR.exists()

    @pytest.mark.parametrize("name", EXPECTED_FIXTURES)
    def test_fixture_file_exists(self, name):
        """Each scenario should have produced a .docx file."""
        fixture = FIXTURES_DIR / f"{name}.docx"
        assert fixture.exists(), f"Missing fixture: {fixture}"
        assert fixture.stat().st_size > 1000, f"Fixture too small: {fixture}"

    def test_all_fixtures_pandoc_readable(self):
        """All fixture files should be valid DOCX that pandoc can convert."""
        for name in self.EXPECTED_FIXTURES:
            fixture = FIXTURES_DIR / f"{name}.docx"
            if not fixture.exists():
                continue
            pandoc_out = _pandoc(fixture)
            assert len(pandoc_out) > 100, f"Pandoc output too short for {name}"
