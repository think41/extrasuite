"""Tests for the new slide processor and related modules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extraslide.bounds import BoundingBox
from extraslide.content_generator import generate_slide_content
from extraslide.id_manager import IDManager
from extraslide.render_tree import RenderNode, build_render_tree
from extraslide.slide_processor import process_presentation
from extraslide.style_extractor import extract_styles


class TestBoundingBox:
    """Tests for BoundingBox class."""

    def test_basic_properties(self):
        box = BoundingBox(x=10, y=20, w=100, h=50)
        assert box.x == 10
        assert box.y == 20
        assert box.w == 100
        assert box.h == 50
        assert box.x2 == 110
        assert box.y2 == 70
        assert box.area == 5000

    def test_contains_fully_inside(self):
        outer = BoundingBox(x=0, y=0, w=100, h=100)
        inner = BoundingBox(x=10, y=10, w=20, h=20)
        assert outer.contains(inner, threshold=0.7)

    def test_contains_partial_overlap(self):
        outer = BoundingBox(x=0, y=0, w=100, h=100)
        partial = BoundingBox(x=50, y=50, w=100, h=100)
        # Only 25% overlap (50x50 out of 100x100)
        assert not outer.contains(partial, threshold=0.7)

    def test_relative_to(self):
        parent = BoundingBox(x=100, y=200, w=300, h=400)
        child = BoundingBox(x=150, y=250, w=50, h=60)
        relative = child.relative_to(parent)
        assert relative.x == 50
        assert relative.y == 50
        assert relative.w == 50
        assert relative.h == 60

    def test_absolute_from(self):
        parent = BoundingBox(x=100, y=200, w=300, h=400)
        relative = BoundingBox(x=50, y=50, w=50, h=60)
        absolute = relative.absolute_from(parent)
        assert absolute.x == 150
        assert absolute.y == 250
        assert absolute.w == 50
        assert absolute.h == 60


class TestIDManager:
    """Tests for IDManager class."""

    def test_assign_element_id(self):
        manager = IDManager()
        clean_id = manager.assign_element_id("google_object_1")
        assert clean_id == "e1"
        assert manager.get_google_id("e1") == "google_object_1"
        assert manager.get_clean_id("google_object_1") == "e1"

    def test_assign_multiple_ids(self):
        manager = IDManager()
        assert manager.assign_element_id("obj1") == "e1"
        assert manager.assign_element_id("obj2") == "e2"
        assert manager.assign_group_id("grp1") == "g1"
        assert manager.assign_slide_id("slide1") == "s1"

    def test_from_dict(self):
        mapping = {"e1": "google1", "e2": "google2", "g1": "group1"}
        manager = IDManager.from_dict(mapping)
        assert manager.get_google_id("e1") == "google1"
        assert manager.get_clean_id("group1") == "g1"
        # Counter should be restored
        assert manager.assign_element_id("new_elem") == "e3"


class TestRenderTree:
    """Tests for render tree construction."""

    def test_simple_element(self):
        elements = [
            {
                "objectId": "obj1",
                "size": {
                    "width": {"magnitude": 914400},
                    "height": {"magnitude": 457200},
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": 0,
                    "translateY": 0,
                },
                "shape": {"shapeType": "RECTANGLE"},
            }
        ]
        id_manager = IDManager()
        id_manager.assign_element_id("obj1")

        roots = build_render_tree(elements, id_manager)
        assert len(roots) == 1
        assert roots[0].clean_id == "e1"
        assert roots[0].element_type == "RECTANGLE"

    def test_containment(self):
        # Larger element contains smaller one
        elements = [
            {
                "objectId": "outer",
                "size": {
                    "width": {"magnitude": 9144000},
                    "height": {"magnitude": 4572000},
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": 0,
                    "translateY": 0,
                },
                "shape": {"shapeType": "RECTANGLE"},
            },
            {
                "objectId": "inner",
                "size": {
                    "width": {"magnitude": 914400},
                    "height": {"magnitude": 457200},
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": 914400,
                    "translateY": 457200,
                },
                "shape": {"shapeType": "TEXT_BOX"},
            },
        ]
        id_manager = IDManager()
        id_manager.assign_element_id("outer")
        id_manager.assign_element_id("inner")

        roots = build_render_tree(elements, id_manager)
        assert len(roots) == 1
        assert roots[0].clean_id == "e1"  # outer
        assert len(roots[0].children) == 1
        assert roots[0].children[0].clean_id == "e2"  # inner


class TestStyleExtractor:
    """Tests for style extraction."""

    def test_extract_position(self):
        node = RenderNode(
            element={
                "objectId": "obj1",
                "shape": {"shapeType": "RECTANGLE"},
            },
            bounds=BoundingBox(x=100, y=200, w=300, h=150),
            clean_id="e1",
        )

        styles = extract_styles([node])
        assert "e1" in styles
        assert styles["e1"]["position"]["x"] == 100
        assert styles["e1"]["position"]["y"] == 200
        assert styles["e1"]["position"]["relative"] is False

    def test_extract_relative_position(self):
        parent = RenderNode(
            element={
                "objectId": "parent",
                "shape": {"shapeType": "RECTANGLE"},
            },
            bounds=BoundingBox(x=100, y=200, w=500, h=300),
            clean_id="e1",
        )
        child = RenderNode(
            element={
                "objectId": "child",
                "shape": {"shapeType": "TEXT_BOX"},
            },
            bounds=BoundingBox(x=150, y=250, w=100, h=50),
            clean_id="e2",
            parent=parent,
        )
        parent.children = [child]

        styles = extract_styles([parent])
        assert styles["e1"]["position"]["relative"] is False
        assert styles["e2"]["position"]["relative"] is True
        assert styles["e2"]["position"]["x"] == 50
        assert styles["e2"]["position"]["y"] == 50


class TestContentGenerator:
    """Tests for minimal SML content generation."""

    def test_generate_simple_element(self):
        node = RenderNode(
            element={
                "objectId": "obj1",
                "shape": {"shapeType": "RECTANGLE"},
            },
            bounds=BoundingBox(x=100, y=200, w=300, h=150),
            clean_id="e1",
        )

        content = generate_slide_content([node])
        assert 'id="e1"' in content
        assert 'x="100"' in content
        assert 'y="200"' in content
        assert "<Rect" in content

    def test_children_with_absolute_position(self):
        """All elements have absolute positions, including children."""
        parent = RenderNode(
            element={
                "objectId": "parent",
                "shape": {"shapeType": "RECTANGLE"},
            },
            bounds=BoundingBox(x=100, y=200, w=500, h=300),
            clean_id="e1",
        )
        child = RenderNode(
            element={
                "objectId": "child",
                "shape": {"shapeType": "TEXT_BOX"},
            },
            bounds=BoundingBox(x=150, y=250, w=100, h=50),
            clean_id="e2",
            parent=parent,
        )
        parent.children = [child]

        content = generate_slide_content([parent])
        # Parent should have position
        assert 'id="e1"' in content
        assert 'x="100"' in content
        # Child should also have absolute position
        lines = content.split("\n")
        child_line = next(line for line in lines if 'id="e2"' in line)
        assert 'x="150"' in child_line
        assert 'y="250"' in child_line


class TestSlideProcessor:
    """Integration tests for the slide processor."""

    @pytest.fixture
    def sample_presentation(self):
        """Create a minimal sample presentation for testing."""
        return {
            "title": "Test Presentation",
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide1",
                    "pageElements": [
                        {
                            "objectId": "elem1",
                            "size": {
                                "width": {"magnitude": 914400},
                                "height": {"magnitude": 457200},
                            },
                            "transform": {
                                "scaleX": 1,
                                "scaleY": 1,
                                "translateX": 0,
                                "translateY": 0,
                            },
                            "shape": {"shapeType": "RECTANGLE"},
                        },
                    ],
                },
            ],
        }

    def test_process_presentation(self, sample_presentation):
        result = process_presentation(sample_presentation)

        assert "id_mapping" in result
        assert "styles" in result
        assert "slides" in result
        assert "presentation_info" in result

        assert result["presentation_info"]["title"] == "Test Presentation"
        assert result["presentation_info"]["slideCount"] == 1
        assert len(result["slides"]) == 1


class TestWithGoldenFile:
    """Tests using actual presentation data if available."""

    @pytest.fixture
    def golden_presentation(self):
        """Load golden file if available."""
        golden_path = (
            Path(__file__).parent.parent
            / "output/1FDmkjjecAqRpNUQK8gAsFdCASXJ7zIR004FXppwdZbA/.raw/presentation.json"
        )
        if not golden_path.exists():
            pytest.skip("Golden file not available")
        return json.loads(golden_path.read_text())

    def test_process_real_presentation(self, golden_presentation):
        result = process_presentation(golden_presentation)

        # Should have reasonable number of IDs
        assert len(result["id_mapping"]) > 100

        # Should have slides
        assert len(result["slides"]) == 32

        # Each slide should have content
        for slide in result["slides"]:
            assert slide["content"]
            assert 'id="' in slide["content"]
