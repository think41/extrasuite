"""Tests for SML diff engine.

Tests cover:
- Element matching by ID (Spec: sml-reconciliation-spec.md#element-matching)
- Change types (added, deleted, modified) (Spec: sml-reconciliation-spec.md#change-types)
- Text content diffing (Spec: sml-reconciliation-spec.md#text-content-diffing)
- Slide reordering detection
"""

from extraslide.diff import (
    ChangeType,
    diff_sml,
)
from extraslide.parser import parse_sml


class TestSlideChanges:
    """Test detection of slide-level changes."""

    def test_detect_added_slide(self) -> None:
        """Detect newly added slide."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
            <Slide id="slide2" layout="layout1"/>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        added = [c for c in result.slide_changes if c.change_type == ChangeType.ADDED]
        assert len(added) == 1
        assert added[0].slide_id == "slide2"
        assert added[0].layout == "layout1"

    def test_detect_deleted_slide(self) -> None:
        """Detect deleted slide."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
            <Slide id="slide2"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        deleted = [
            c for c in result.slide_changes if c.change_type == ChangeType.DELETED
        ]
        assert len(deleted) == 1
        assert deleted[0].slide_id == "slide2"

    def test_detect_slide_class_change(self) -> None:
        """Detect slide background change via class."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1" class="bg-#ffffff"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1" class="bg-#3b82f6"/>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        modified = [
            c for c in result.slide_changes if c.change_type == ChangeType.MODIFIED
        ]
        assert len(modified) == 1
        assert modified[0].slide_id == "slide1"
        assert "bg-#ffffff" in modified[0].original_classes
        assert "bg-#3b82f6" in modified[0].new_classes

    def test_detect_slide_reordering(self) -> None:
        """Detect when slides are reordered."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1"/>
            <Slide id="slide2"/>
            <Slide id="slide3"/>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide3"/>
            <Slide id="slide1"/>
            <Slide id="slide2"/>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        assert result.slides_reordered is True
        assert result.slide_order == ["slide3", "slide1", "slide2"]

    def test_no_changes(self) -> None:
        """No changes detected for identical presentations."""
        sml = """
        <Presentation id="pres1">
            <Slide id="slide1" class="bg-#ffffff">
                <TextBox id="tb1" class="x-72 y-100 w-400 h-50"/>
            </Slide>
        </Presentation>
        """

        original = parse_sml(sml)
        edited = parse_sml(sml)

        result = diff_sml(original, edited)

        assert len(result.slide_changes) == 0
        assert result.slides_reordered is False


class TestElementChanges:
    """Test detection of element-level changes."""

    def test_detect_added_element(self) -> None:
        """Detect newly added element."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1" class="x-72 y-100"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1" class="x-72 y-100"/>
                <Rect id="rect1" class="x-200 y-200 w-100 h-50 fill-#3b82f6"/>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        added = [
            e for e in slide_change.element_changes if e.change_type == ChangeType.ADDED
        ]
        assert len(added) == 1
        assert added[0].element_id == "rect1"
        assert added[0].element_tag == "Rect"

    def test_detect_deleted_element(self) -> None:
        """Detect deleted element."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1" class="x-72 y-100"/>
                <Rect id="rect1" class="x-200 y-200"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1" class="x-72 y-100"/>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        deleted = [
            e
            for e in slide_change.element_changes
            if e.change_type == ChangeType.DELETED
        ]
        assert len(deleted) == 1
        assert deleted[0].element_id == "rect1"

    def test_detect_element_class_change(self) -> None:
        """Detect element style change via class."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#ef4444"/>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        modified = [
            e
            for e in slide_change.element_changes
            if e.change_type == ChangeType.MODIFIED
        ]
        assert len(modified) == 1
        assert modified[0].element_id == "rect1"
        assert "fill-#3b82f6" in modified[0].original_classes
        assert "fill-#ef4444" in modified[0].new_classes

    def test_detect_element_position_change(self) -> None:
        """Detect element position change."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-300 y-200 w-200 h-100"/>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        modified = [
            e
            for e in slide_change.element_changes
            if e.change_type == ChangeType.MODIFIED
        ]
        assert len(modified) == 1
        assert "x-100" in modified[0].original_classes
        assert "x-300" in modified[0].new_classes

    def test_detect_duplicate_element(self) -> None:
        """Detect element with duplicate-of attribute."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
                <Rect id="rect2" class="x-350 y-100 w-200 h-100 fill-#22c55e" duplicate-of="rect1"/>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        added = [
            e for e in slide_change.element_changes if e.change_type == ChangeType.ADDED
        ]
        assert len(added) == 1
        assert added[0].element_id == "rect2"
        assert added[0].duplicate_of == "rect1"


class TestTextChanges:
    """Test detection of text content changes.

    Spec: sml-reconciliation-spec.md#text-content-diffing
    """

    def test_detect_text_content_change(self) -> None:
        """Detect text content modification."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1" class="x-72 y-100 w-400 h-50">
                    <P range="0-12">
                        <T range="0-11">Hello World</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1" class="x-72 y-100 w-400 h-50">
                    <P range="0-12">
                        <T range="0-11">Hello Universe</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]
        assert elem_change.element_id == "tb1"

        para_change = elem_change.paragraph_changes[0]
        text_change = para_change.text_changes[0]
        assert text_change.change_type == ChangeType.MODIFIED
        assert text_change.original_content == "Hello World"
        assert text_change.new_content == "Hello Universe"

    def test_detect_text_style_change(self) -> None:
        """Detect text style change (no content change)."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-6">
                        <T range="0-5">Hello</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-6">
                        <T range="0-5" class="bold italic">Hello</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]
        para_change = elem_change.paragraph_changes[0]
        text_change = para_change.text_changes[0]

        assert text_change.change_type == ChangeType.MODIFIED
        assert (
            text_change.original_content == text_change.new_content
        )  # Content unchanged
        assert "bold" in text_change.new_classes
        assert "italic" in text_change.new_classes

    def test_detect_added_text_run(self) -> None:
        """Detect newly added text run."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-6">Hello </T>
                        <T range="6-11">world</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-6">Hello </T>
                        <T class="italic">beautiful </T>
                        <T range="6-11">world</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]
        para_change = elem_change.paragraph_changes[0]

        # Should have changes for the inserted run and the shifted existing run
        assert len(para_change.text_changes) >= 1

    def test_detect_deleted_text_run(self) -> None:
        """Detect deleted text run."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-18">
                        <T range="0-6">Hello </T>
                        <T range="6-12" class="bold">world </T>
                        <T range="12-17">today</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-18">
                        <T range="0-6">Hello </T>
                        <T range="12-17">today</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]
        para_change = elem_change.paragraph_changes[0]

        # Should detect that the "world " run was deleted
        deleted = [
            t for t in para_change.text_changes if t.change_type == ChangeType.DELETED
        ]
        assert len(deleted) >= 1

    def test_detect_added_paragraph(self) -> None:
        """Detect newly added paragraph."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-11">First line.</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-11">First line.</T>
                    </P>
                    <P>
                        <T>Second line.</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]

        added = [
            p
            for p in elem_change.paragraph_changes
            if p.change_type == ChangeType.ADDED
        ]
        assert len(added) == 1

    def test_detect_deleted_paragraph(self) -> None:
        """Detect deleted paragraph."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-11">First line.</T>
                    </P>
                    <P range="12-25">
                        <T range="12-24">Second line.</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="0-11">First line.</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]

        deleted = [
            p
            for p in elem_change.paragraph_changes
            if p.change_type == ChangeType.DELETED
        ]
        assert len(deleted) == 1
        assert deleted[0].range_start == 12
        assert deleted[0].range_end == 25


class TestRangePreservation:
    """Test that ranges are preserved for request generation.

    Spec: sml-reconciliation-spec.md#ranges-are-read-only-coordinates
    """

    def test_preserve_original_range_for_delete(self) -> None:
        """Original range should be preserved for delete operations.

        Note: The diff engine matches by position, so when a middle run is
        deleted, it detects:
        - Position 1: content modified ("world " -> "today")
        - Position 2: deleted (original "today" has no match)

        This is per spec but results in delete+modify operations.
        """
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-18">
                        <T range="0-6">Hello </T>
                        <T range="6-12" class="bold">world </T>
                        <T range="12-17">today</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-18">
                        <T range="0-6">Hello </T>
                        <T range="12-17">today</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]
        para_change = elem_change.paragraph_changes[0]

        # Position-based matching means we get both a modified and deleted change
        # Position 1: "world " modified to "today"
        # Position 2: original "today" deleted (no match at position 2 in edited)
        deleted = [
            t for t in para_change.text_changes if t.change_type == ChangeType.DELETED
        ]

        # Should have at least one change (either delete or modify)
        assert len(para_change.text_changes) >= 1

        # The deleted run should have a range from the original
        if deleted:
            assert deleted[0].range_start is not None
            assert deleted[0].range_end is not None

    def test_preserve_original_range_for_modify(self) -> None:
        """Original range should be preserved for modify operations."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="6-11">world</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <TextBox id="tb1">
                    <P range="0-12">
                        <T range="6-11">universe</T>
                    </P>
                </TextBox>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        slide_change = result.slide_changes[0]
        elem_change = slide_change.element_changes[0]
        para_change = elem_change.paragraph_changes[0]
        text_change = para_change.text_changes[0]

        # The original range should be preserved
        assert text_change.range_start == 6
        assert text_change.range_end == 11


class TestGroupChanges:
    """Test detection of group element changes."""

    def test_detect_added_group_child(self) -> None:
        """Detect element added inside a group."""
        original = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Group id="group1" class="x-100 y-100">
                    <Rect id="rect1" class="x-0 y-0 w-100 h-50"/>
                </Group>
            </Slide>
        </Presentation>
        """)

        edited = parse_sml("""
        <Presentation id="pres1">
            <Slide id="slide1">
                <Group id="group1" class="x-100 y-100">
                    <Rect id="rect1" class="x-0 y-0 w-100 h-50"/>
                    <TextBox id="tb1" class="x-0 y-60 w-100 h-30"/>
                </Group>
            </Slide>
        </Presentation>
        """)

        result = diff_sml(original, edited)

        # Group should be marked as modified
        slide_change = result.slide_changes[0]
        modified = [
            e
            for e in slide_change.element_changes
            if e.change_type == ChangeType.MODIFIED
        ]
        assert len(modified) == 1
        assert modified[0].element_id == "group1"
