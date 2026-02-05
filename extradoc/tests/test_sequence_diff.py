"""Tests for sequence_diff module."""

from extradoc.desugar import Paragraph, SpecialElement, Table, TableCell, TextRun
from extradoc.sequence_diff import (
    diff_text,
    element_signature,
    elements_match,
    sections_are_identical,
    sequence_diff,
)


class TestElementSignature:
    """Tests for element_signature function."""

    def test_paragraph_signature_includes_style(self) -> None:
        """Paragraph signature includes named style."""
        para = Paragraph(named_style="HEADING_1", runs=[TextRun(text="Hello")])
        sig = element_signature(para)
        assert "HEADING_1" in sig
        assert "Hello" in sig

    def test_paragraph_signature_includes_bullet(self) -> None:
        """Paragraph signature includes bullet type."""
        para = Paragraph(
            bullet_type="bullet", bullet_level=0, runs=[TextRun(text="Item")]
        )
        sig = element_signature(para)
        assert "bullet" in sig
        assert "Item" in sig

    def test_table_signature_includes_dimensions(self) -> None:
        """Table signature includes rows and columns."""
        table = Table(rows=3, cols=4, cells=[])
        sig = element_signature(table)
        assert "3x4" in sig

    def test_special_element_signature_includes_type(self) -> None:
        """Special element signature includes type."""
        elem = SpecialElement(element_type="pagebreak")
        sig = element_signature(elem)
        assert "pagebreak" in sig


class TestElementsMatch:
    """Tests for elements_match function."""

    def test_identical_paragraphs_match(self) -> None:
        """Identical paragraphs match."""
        p1 = Paragraph(named_style="NORMAL_TEXT", runs=[TextRun(text="Hello")])
        p2 = Paragraph(named_style="NORMAL_TEXT", runs=[TextRun(text="Hello")])
        assert elements_match(p1, p2)

    def test_different_text_paragraphs_dont_match(self) -> None:
        """Paragraphs with different text don't match."""
        p1 = Paragraph(named_style="NORMAL_TEXT", runs=[TextRun(text="Hello")])
        p2 = Paragraph(named_style="NORMAL_TEXT", runs=[TextRun(text="World")])
        assert not elements_match(p1, p2)

    def test_different_style_paragraphs_dont_match(self) -> None:
        """Paragraphs with different styles don't match."""
        p1 = Paragraph(named_style="NORMAL_TEXT", runs=[TextRun(text="Title")])
        p2 = Paragraph(named_style="HEADING_1", runs=[TextRun(text="Title")])
        assert not elements_match(p1, p2)

    def test_different_run_styles_dont_match(self) -> None:
        """Paragraphs with different run styles don't match."""
        p1 = Paragraph(runs=[TextRun(text="Hello", styles={})])
        p2 = Paragraph(runs=[TextRun(text="Hello", styles={"bold": "1"})])
        assert not elements_match(p1, p2)

    def test_identical_tables_match(self) -> None:
        """Identical tables match."""
        cell1 = TableCell(row=0, col=0, content=[Paragraph(runs=[TextRun(text="A")])])
        t1 = Table(rows=1, cols=1, cells=[cell1])

        cell2 = TableCell(row=0, col=0, content=[Paragraph(runs=[TextRun(text="A")])])
        t2 = Table(rows=1, cols=1, cells=[cell2])

        assert elements_match(t1, t2)

    def test_different_dimension_tables_dont_match(self) -> None:
        """Tables with different dimensions don't match."""
        t1 = Table(rows=2, cols=2, cells=[])
        t2 = Table(rows=3, cols=2, cells=[])
        assert not elements_match(t1, t2)

    def test_identical_specials_match(self) -> None:
        """Identical special elements match."""
        s1 = SpecialElement(element_type="pagebreak", attributes={})
        s2 = SpecialElement(element_type="pagebreak", attributes={})
        assert elements_match(s1, s2)

    def test_different_type_specials_dont_match(self) -> None:
        """Different type special elements don't match."""
        s1 = SpecialElement(element_type="pagebreak", attributes={})
        s2 = SpecialElement(element_type="hr", attributes={})
        assert not elements_match(s1, s2)

    def test_different_types_dont_match(self) -> None:
        """Different element types don't match."""
        para = Paragraph(runs=[TextRun(text="Hello")])
        table = Table(rows=1, cols=1, cells=[])
        assert not elements_match(para, table)


class TestSectionsAreIdentical:
    """Tests for sections_are_identical function."""

    def test_identical_sections_are_identical(self) -> None:
        """Identical sections are identical."""
        content1 = [
            Paragraph(runs=[TextRun(text="First")]),
            Paragraph(runs=[TextRun(text="Second")]),
        ]
        content2 = [
            Paragraph(runs=[TextRun(text="First")]),
            Paragraph(runs=[TextRun(text="Second")]),
        ]
        assert sections_are_identical(content1, content2)

    def test_different_length_sections_not_identical(self) -> None:
        """Different length sections are not identical."""
        content1 = [Paragraph(runs=[TextRun(text="First")])]
        content2 = [
            Paragraph(runs=[TextRun(text="First")]),
            Paragraph(runs=[TextRun(text="Second")]),
        ]
        assert not sections_are_identical(content1, content2)

    def test_different_content_sections_not_identical(self) -> None:
        """Different content sections are not identical."""
        content1 = [Paragraph(runs=[TextRun(text="Hello")])]
        content2 = [Paragraph(runs=[TextRun(text="World")])]
        assert not sections_are_identical(content1, content2)

    def test_empty_sections_are_identical(self) -> None:
        """Empty sections are identical."""
        assert sections_are_identical([], [])


class TestSequenceDiff:
    """Tests for sequence_diff function."""

    def test_identical_sequences_all_equal(self) -> None:
        """Identical sequences produce all equal changes."""
        p1 = Paragraph(runs=[TextRun(text="Hello")])
        p2 = Paragraph(runs=[TextRun(text="World")])

        pristine = [(p1, 1, 7), (p2, 7, 13)]
        current = [(p1, 1, 7), (p2, 7, 13)]

        # Create new paragraphs for current (same content)
        c1 = Paragraph(runs=[TextRun(text="Hello")])
        c2 = Paragraph(runs=[TextRun(text="World")])
        current = [(c1, 1, 7), (c2, 7, 13)]

        changes = sequence_diff(pristine, current)

        # All should be equal
        for change in changes:
            assert change.type == "equal"

    def test_insert_detected(self) -> None:
        """Inserted element is detected."""
        p1 = Paragraph(runs=[TextRun(text="First")])
        p2 = Paragraph(runs=[TextRun(text="Third")])

        pristine = [(p1, 1, 7), (p2, 7, 13)]

        c1 = Paragraph(runs=[TextRun(text="First")])
        c2 = Paragraph(runs=[TextRun(text="Second")])
        c3 = Paragraph(runs=[TextRun(text="Third")])
        current = [(c1, 1, 7), (c2, 7, 14), (c3, 14, 20)]

        changes = sequence_diff(pristine, current)

        # Should have an insert for "Second"
        insert_changes = [c for c in changes if c.type == "insert"]
        assert len(insert_changes) >= 1

    def test_delete_detected(self) -> None:
        """Deleted element is detected."""
        p1 = Paragraph(runs=[TextRun(text="First")])
        p2 = Paragraph(runs=[TextRun(text="Second")])
        p3 = Paragraph(runs=[TextRun(text="Third")])

        pristine = [(p1, 1, 7), (p2, 7, 14), (p3, 14, 20)]

        c1 = Paragraph(runs=[TextRun(text="First")])
        c3 = Paragraph(runs=[TextRun(text="Third")])
        current = [(c1, 1, 7), (c3, 7, 13)]

        changes = sequence_diff(pristine, current)

        # Should have a delete for "Second"
        delete_changes = [c for c in changes if c.type == "delete"]
        assert len(delete_changes) >= 1


class TestDiffText:
    """Tests for diff_text function."""

    def test_identical_text_no_changes(self) -> None:
        """Identical text produces only equal operations."""
        operations = diff_text("Hello World", "Hello World")

        # Should have one equal operation
        non_equal = [op for op in operations if op[0] != "equal"]
        assert len(non_equal) == 0

    def test_word_replacement(self) -> None:
        """Replacing a word produces delete+insert."""
        operations = diff_text("Hello World", "Hello Universe")

        # Should have delete and insert
        deletes = [op for op in operations if op[0] == "delete"]
        inserts = [op for op in operations if op[0] == "insert"]

        assert len(deletes) >= 1
        assert len(inserts) >= 1

        # Character-level diff may split "Universe" due to shared 'r' with "World"
        # Combined inserts should reconstruct the replacement
        insert_texts = [op[3] for op in inserts]
        combined = "".join(insert_texts)
        # Check that we're inserting the right characters
        assert "Unive" in combined or "Universe" in combined

    def test_append_text(self) -> None:
        """Appending text produces insert."""
        operations = diff_text("Hello", "Hello World")

        # Should have insert for " World"
        inserts = [op for op in operations if op[0] == "insert"]
        assert len(inserts) >= 1

        insert_texts = [op[3] for op in inserts]
        assert any("World" in t for t in insert_texts)

    def test_prepend_text(self) -> None:
        """Prepending text produces insert at beginning."""
        operations = diff_text("World", "Hello World")

        # Should have insert for "Hello "
        inserts = [op for op in operations if op[0] == "insert"]
        assert len(inserts) >= 1

        insert_texts = [op[3] for op in inserts]
        assert any("Hello" in t for t in insert_texts)

    def test_delete_text(self) -> None:
        """Deleting text produces delete operation."""
        operations = diff_text("Hello World", "Hello")

        # Should have delete for " World"
        deletes = [op for op in operations if op[0] == "delete"]
        assert len(deletes) >= 1

    def test_utf16_indexes(self) -> None:
        """Operations use correct UTF-16 indexes."""
        # Emoji is 2 UTF-16 code units
        operations = diff_text("Hi\U0001f600", "Hi\U0001f600!")

        # Total length of "Hi\U0001f600" is 2 + 2 = 4 UTF-16 units
        # Insert should be at index 4
        inserts = [op for op in operations if op[0] == "insert"]
        assert len(inserts) >= 1

        # Insert position should be 4
        insert_positions = [op[1] for op in inserts]
        assert 4 in insert_positions

    def test_empty_to_text(self) -> None:
        """Empty string to text produces insert."""
        operations = diff_text("", "Hello")

        inserts = [op for op in operations if op[0] == "insert"]
        assert len(inserts) >= 1

        insert_texts = [op[3] for op in inserts]
        assert "Hello" in insert_texts

    def test_text_to_empty(self) -> None:
        """Text to empty string produces delete."""
        operations = diff_text("Hello", "")

        deletes = [op for op in operations if op[0] == "delete"]
        assert len(deletes) >= 1
