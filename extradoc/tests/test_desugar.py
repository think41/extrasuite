"""Tests for desugar module and index counting model."""

from extradoc.desugar import Paragraph, SpecialElement, TextRun


class TestIndexCountingModel:
    """Tests for the UTF-16 index counting model."""

    def test_empty_paragraph_length(self) -> None:
        """Empty paragraph = 1 (just newline)."""
        para = Paragraph(runs=[])
        assert para.utf16_length() == 1

    def test_paragraph_with_text(self) -> None:
        """Paragraph with text = utf16_len(text) + 1."""
        para = Paragraph(runs=[TextRun(text="Hello")])
        assert para.utf16_length() == 6  # 5 + 1

    def test_paragraph_with_emoji(self) -> None:
        """Emoji uses surrogate pairs (2 UTF-16 code units)."""
        para = Paragraph(runs=[TextRun(text="Hi\U0001f600")])  # grinning face emoji
        # H(1) + i(1) + emoji(2) + newline(1) = 5
        assert para.utf16_length() == 5

    def test_paragraph_with_special_element(self) -> None:
        """Special element = 1, plus newline = 2."""
        para = Paragraph(
            runs=[TextRun(text="\x00pagebreak\x00", styles={"_special": "pagebreak"})]
        )
        assert para.utf16_length() == 2

    def test_paragraph_with_text_and_special(self) -> None:
        """Text + special + text + newline."""
        para = Paragraph(
            runs=[
                TextRun(text="A"),
                TextRun(text="\x00hr\x00", styles={"_special": "hr"}),
                TextRun(text="B"),
            ]
        )
        # A(1) + hr(1) + B(1) + newline(1) = 4
        assert para.utf16_length() == 4

    def test_special_element_standalone(self) -> None:
        """SpecialElement.utf16_length() = 1."""
        for elem_type in ["hr", "pagebreak", "columnbreak", "image", "person"]:
            elem = SpecialElement(element_type=elem_type)
            assert elem.utf16_length() == 1

    def test_paragraph_text_content(self) -> None:
        """Paragraph.text_content() returns concatenated run text."""
        para = Paragraph(
            runs=[
                TextRun(text="Hello "),
                TextRun(text="World"),
            ]
        )
        assert para.text_content() == "Hello World"

    def test_text_run_utf16_length_ascii(self) -> None:
        """ASCII text has length equal to character count."""
        run = TextRun(text="hello")
        assert run.utf16_length() == 5

    def test_text_run_utf16_length_unicode(self) -> None:
        """Unicode characters outside BMP take 2 UTF-16 code units."""
        # Emoji outside BMP
        run = TextRun(text="\U0001f600")  # grinning face
        assert run.utf16_length() == 2

    def test_text_run_special_marker(self) -> None:
        """Special markers have length 1 regardless of text content."""
        run = TextRun(text="\x00pagebreak\x00", styles={"_special": "pagebreak"})
        assert run.utf16_length() == 1
