"""Tests for the content diff module."""

from __future__ import annotations

from extraslide.content_diff import ChangeType, diff_slide_content
from extraslide.content_parser import parse_slide_content


class TestContentParser:
    """Tests for content parsing."""

    def test_parse_simple_element(self):
        content = '<Rect id="e1" x="100" y="200" w="300" h="150" />'
        elements = parse_slide_content(content)
        assert len(elements) == 1
        assert elements[0].clean_id == "e1"
        assert elements[0].x == 100
        assert elements[0].y == 200

    def test_parse_element_with_text(self):
        content = """
        <TextBox id="e1" x="100" y="200" w="300" h="150">
            <P>Hello World</P>
        </TextBox>
        """
        elements = parse_slide_content(content)
        assert len(elements) == 1
        assert elements[0].paragraphs == ["Hello World"]

    def test_parse_nested_elements(self):
        content = """
        <Group id="g1" x="0" y="0" w="500" h="400">
            <Rect id="e1" />
            <TextBox id="e2">
                <P>Text</P>
            </TextBox>
        </Group>
        """
        elements = parse_slide_content(content)
        assert len(elements) == 1
        assert elements[0].clean_id == "g1"
        assert len(elements[0].children) == 2
        assert elements[0].children[0].clean_id == "e1"
        assert elements[0].children[1].clean_id == "e2"


class TestContentDiff:
    """Tests for content diffing."""

    def test_detect_text_change(self):
        pristine = """
        <TextBox id="e1" x="100" y="200" w="300" h="150">
            <P>Original text</P>
        </TextBox>
        """
        edited = """
        <TextBox id="e1" x="100" y="200" w="300" h="150">
            <P>Changed text</P>
        </TextBox>
        """
        changes = diff_slide_content(pristine, edited, {}, "01")

        text_changes = [c for c in changes if c.change_type == ChangeType.TEXT_UPDATE]
        assert len(text_changes) == 1
        assert text_changes[0].target_id == "e1"
        assert text_changes[0].new_text == ["Changed text"]

    def test_detect_position_change(self):
        pristine = '<Rect id="e1" x="100" y="200" w="300" h="150" />'
        edited = '<Rect id="e1" x="150" y="250" w="300" h="150" />'

        changes = diff_slide_content(pristine, edited, {}, "01")

        move_changes = [c for c in changes if c.change_type == ChangeType.MOVE]
        assert len(move_changes) == 1
        assert move_changes[0].target_id == "e1"
        assert move_changes[0].new_position["x"] == 150
        assert move_changes[0].new_position["y"] == 250

    def test_detect_deletion(self):
        pristine = """
        <Rect id="e1" x="100" y="200" w="300" h="150" />
        <Rect id="e2" x="200" y="300" w="100" h="100" />
        """
        edited = '<Rect id="e1" x="100" y="200" w="300" h="150" />'

        changes = diff_slide_content(pristine, edited, {}, "01")

        delete_changes = [c for c in changes if c.change_type == ChangeType.DELETE]
        assert len(delete_changes) == 1
        assert delete_changes[0].target_id == "e2"

    def test_detect_copy(self):
        """Test that duplicate IDs are detected as copies."""
        pristine = '<Rect id="e1" x="100" y="200" w="300" h="150" />'
        # Edited has the same element twice (LLM copied it)
        edited = """
        <Rect id="e1" x="100" y="200" w="300" h="150" />
        <Rect id="e1" x="400" y="200" w="300" h="150" />
        """

        changes = diff_slide_content(pristine, edited, {}, "01")

        copy_changes = [c for c in changes if c.change_type == ChangeType.COPY]
        assert len(copy_changes) == 1
        assert copy_changes[0].source_id == "e1"
        assert copy_changes[0].new_position["x"] == 400

    def test_detect_new_element(self):
        pristine = '<Rect id="e1" x="100" y="200" w="300" h="150" />'
        edited = """
        <Rect id="e1" x="100" y="200" w="300" h="150" />
        <Rect id="e99" x="400" y="200" w="100" h="100" />
        """

        changes = diff_slide_content(pristine, edited, {}, "01")

        create_changes = [c for c in changes if c.change_type == ChangeType.CREATE]
        assert len(create_changes) == 1
        assert create_changes[0].target_id == "e99"


class TestCopyDetection:
    """Tests specifically for copy detection feature."""

    def test_multiple_copies(self):
        """Test that multiple copies of the same element are detected."""
        pristine = '<Rect id="e1" x="100" y="100" w="100" h="100" />'
        edited = """
        <Rect id="e1" x="100" y="100" w="100" h="100" />
        <Rect id="e1" x="200" y="100" w="100" h="100" />
        <Rect id="e1" x="300" y="100" w="100" h="100" />
        """

        changes = diff_slide_content(pristine, edited, {}, "01")

        copy_changes = [c for c in changes if c.change_type == ChangeType.COPY]
        assert len(copy_changes) == 2

    def test_copy_with_text_change(self):
        """Test that a copied element can have different text."""
        pristine = """
        <TextBox id="e1" x="100" y="100" w="200" h="50">
            <P>Original</P>
        </TextBox>
        """
        # Copy with different text
        edited = """
        <TextBox id="e1" x="100" y="100" w="200" h="50">
            <P>Original</P>
        </TextBox>
        <TextBox id="e1" x="100" y="200" w="200" h="50">
            <P>Copy with new text</P>
        </TextBox>
        """

        changes = diff_slide_content(pristine, edited, {}, "01")

        copy_changes = [c for c in changes if c.change_type == ChangeType.COPY]
        assert len(copy_changes) == 1
        assert copy_changes[0].new_text == ["Copy with new text"]
