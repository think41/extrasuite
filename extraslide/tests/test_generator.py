"""Tests for the JSON to SML generator.

Tests cover:
- Presentation metadata generation
- Shape element generation
- Text content with P/T structure and ranges
- Line, image, table elements
- Groups

Spec reference: markup-syntax-design.md, sml-reconciliation-spec.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extraslide.generator import json_to_sml


class TestSMLGeneratorBasics:
    """Test basic SML generation."""

    def test_empty_presentation(self) -> None:
        """Generate SML for minimal presentation."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},  # 720pt
                "height": {"magnitude": 5143500, "unit": "EMU"},  # 405pt
            },
        }

        sml = json_to_sml(pres)

        assert '<Presentation id="test123"' in sml
        assert 'w="720pt"' in sml
        assert 'h="405pt"' in sml
        assert "</Presentation>" in sml

    def test_presentation_with_title(self) -> None:
        """Presentation title should be included."""
        pres = {
            "presentationId": "test123",
            "title": "My Presentation",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
        }

        sml = json_to_sml(pres)

        assert 'title="My Presentation"' in sml


class TestSlideGeneration:
    """Test slide element generation."""

    def test_simple_slide(self) -> None:
        """Generate SML for a slide with id."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [{"objectId": "slide_1", "pageElements": []}],
        }

        sml = json_to_sml(pres)

        assert '<Slide id="slide_1"' in sml
        assert "</Slide>" in sml

    def test_slide_with_layout(self) -> None:
        """Slide should reference its layout."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "slideProperties": {
                        "layoutObjectId": "layout_1",
                        "masterObjectId": "master_1",
                    },
                    "pageElements": [],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert 'layout="layout_1"' in sml
        assert 'master="master_1"' in sml

    def test_skipped_slide(self) -> None:
        """Skipped slide should have skipped attribute."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "slideProperties": {"isSkipped": True},
                    "pageElements": [],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert 'skipped="true"' in sml


class TestShapeGeneration:
    """Test shape element generation.

    Spec: Element name = Shape type
    """

    def test_textbox_shape(self) -> None:
        """TEXT_BOX should become <TextBox>."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "shape_1",
                            "size": {
                                "width": {"magnitude": 3000000, "unit": "EMU"},
                                "height": {"magnitude": 1000000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 914400,  # 72pt
                                "translateY": 1828800,  # 144pt
                                "unit": "EMU",
                            },
                            "shape": {"shapeType": "TEXT_BOX", "shapeProperties": {}},
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert '<TextBox id="shape_1"' in sml
        assert "x-72" in sml
        assert "y-144" in sml

    def test_rectangle_shape(self) -> None:
        """RECTANGLE should become <Rect>."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "rect_1",
                            "size": {
                                "width": {"magnitude": 2540000, "unit": "EMU"},  # 200pt
                                "height": {
                                    "magnitude": 1270000,
                                    "unit": "EMU",
                                },  # 100pt
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 0,
                                "translateY": 0,
                                "unit": "EMU",
                            },
                            "shape": {
                                "shapeType": "RECTANGLE",
                                "shapeProperties": {
                                    "shapeBackgroundFill": {
                                        "solidFill": {
                                            "color": {
                                                "rgbColor": {
                                                    "red": 0.26,
                                                    "green": 0.52,
                                                    "blue": 0.96,
                                                }
                                            },
                                            "alpha": 1.0,
                                        }
                                    }
                                },
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert '<Rect id="rect_1"' in sml
        assert "w-200" in sml
        assert "h-100" in sml
        assert "fill-#4285f5" in sml  # Google blue (hex from RGB)


class TestTextContentGeneration:
    """Test text content generation with P/T structure.

    Spec: All text must be in <P><T>...</T></P> structure.
    Range attributes are read-only for diffing.
    """

    def test_simple_text_content(self) -> None:
        """Generate text with explicit P and T elements."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "text_1",
                            "size": {
                                "width": {"magnitude": 5080000, "unit": "EMU"},
                                "height": {"magnitude": 635000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 914400,
                                "translateY": 914400,
                                "unit": "EMU",
                            },
                            "shape": {
                                "shapeType": "TEXT_BOX",
                                "text": {
                                    "textElements": [
                                        {
                                            "endIndex": 12,
                                            "paragraphMarker": {
                                                "style": {"alignment": "START"}
                                            },
                                        },
                                        {
                                            "endIndex": 11,
                                            "textRun": {
                                                "content": "Hello World",
                                                "style": {"fontFamily": "Roboto"},
                                            },
                                        },
                                        {
                                            "startIndex": 11,
                                            "endIndex": 12,
                                            "textRun": {"content": "\n", "style": {}},
                                        },
                                    ]
                                },
                                "shapeProperties": {},
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        # Must have explicit P and T structure
        assert "<P" in sml
        assert "<T" in sml
        assert "Hello World" in sml
        assert "</T>" in sml
        assert "</P>" in sml

        # Range attributes should be present
        assert 'range="' in sml

    def test_styled_text_runs(self) -> None:
        """Text runs with styling should have appropriate classes."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "text_1",
                            "size": {
                                "width": {"magnitude": 5080000, "unit": "EMU"},
                                "height": {"magnitude": 635000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 0,
                                "translateY": 0,
                                "unit": "EMU",
                            },
                            "shape": {
                                "shapeType": "TEXT_BOX",
                                "text": {
                                    "textElements": [
                                        {
                                            "endIndex": 12,
                                            "paragraphMarker": {"style": {}},
                                        },
                                        {
                                            "endIndex": 6,
                                            "textRun": {
                                                "content": "Hello ",
                                                "style": {},
                                            },
                                        },
                                        {
                                            "startIndex": 6,
                                            "endIndex": 11,
                                            "textRun": {
                                                "content": "World",
                                                "style": {"bold": True},
                                            },
                                        },
                                        {
                                            "startIndex": 11,
                                            "endIndex": 12,
                                            "textRun": {"content": "\n", "style": {}},
                                        },
                                    ]
                                },
                                "shapeProperties": {},
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        # Should have two T elements
        assert "<T" in sml
        assert "Hello " in sml
        assert "World" in sml
        # Bold should be a class
        assert "bold" in sml


class TestLineGeneration:
    """Test line element generation."""

    def test_straight_line(self) -> None:
        """Generate SML for a straight line."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "line_1",
                            "size": {
                                "width": {"magnitude": 2540000, "unit": "EMU"},
                                "height": {"magnitude": 1270000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 914400,
                                "translateY": 914400,
                                "unit": "EMU",
                            },
                            "line": {
                                "lineType": "STRAIGHT_LINE",
                                "lineProperties": {
                                    "lineFill": {
                                        "solidFill": {
                                            "color": {"rgbColor": {}},
                                            "alpha": 1.0,
                                        }
                                    },
                                    "weight": {"magnitude": 12700, "unit": "EMU"},
                                    "dashStyle": "SOLID",
                                    "startArrow": "NONE",
                                    "endArrow": "FILL_ARROW",
                                },
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert '<Line id="line_1"' in sml
        assert "line-straight" in sml
        assert "arrow-end-fill" in sml


class TestImageGeneration:
    """Test image element generation."""

    def test_image_with_url(self) -> None:
        """Generate SML for an image with short URL reference."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "img_1",
                            "size": {
                                "width": {"magnitude": 3810000, "unit": "EMU"},
                                "height": {"magnitude": 2540000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 0,
                                "translateY": 0,
                                "unit": "EMU",
                            },
                            "image": {
                                "contentUrl": "https://example.com/image.png",
                                "imageProperties": {},
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert '<Image id="img_1"' in sml
        # Image src uses short reference
        assert 'src="img:' in sml
        # Full URL is in Images section
        assert "<Images>" in sml
        assert 'url="https://example.com/image.png"' in sml


class TestTableGeneration:
    """Test table element generation.

    Spec: Tables use explicit row and column indices.
    """

    def test_simple_table(self) -> None:
        """Generate SML for a table."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "table_1",
                            "size": {
                                "width": {"magnitude": 7620000, "unit": "EMU"},
                                "height": {"magnitude": 2540000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 914400,
                                "translateY": 2540000,
                                "unit": "EMU",
                            },
                            "table": {
                                "rows": 2,
                                "columns": 3,
                                "tableRows": [
                                    {
                                        "rowHeight": {
                                            "magnitude": 635000,
                                            "unit": "EMU",
                                        },
                                        "tableCells": [
                                            {
                                                "text": {
                                                    "textElements": [
                                                        {
                                                            "endIndex": 8,
                                                            "paragraphMarker": {
                                                                "style": {}
                                                            },
                                                        },
                                                        {
                                                            "endIndex": 7,
                                                            "textRun": {
                                                                "content": "Cell A1",
                                                                "style": {},
                                                            },
                                                        },
                                                        {
                                                            "startIndex": 7,
                                                            "endIndex": 8,
                                                            "textRun": {
                                                                "content": "\n",
                                                                "style": {},
                                                            },
                                                        },
                                                    ]
                                                },
                                                "tableCellProperties": {},
                                            },
                                            {
                                                "text": {"textElements": []},
                                                "tableCellProperties": {},
                                            },
                                            {
                                                "text": {"textElements": []},
                                                "tableCellProperties": {},
                                            },
                                        ],
                                    },
                                    {
                                        "rowHeight": {
                                            "magnitude": 635000,
                                            "unit": "EMU",
                                        },
                                        "tableCells": [
                                            {
                                                "text": {"textElements": []},
                                                "tableCellProperties": {},
                                            },
                                            {
                                                "text": {"textElements": []},
                                                "tableCellProperties": {},
                                            },
                                            {
                                                "text": {"textElements": []},
                                                "tableCellProperties": {},
                                            },
                                        ],
                                    },
                                ],
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert '<Table id="table_1"' in sml
        assert 'rows="2"' in sml
        assert 'cols="3"' in sml
        assert "<Row" in sml
        assert "<Cell" in sml
        assert 'r="0"' in sml
        assert 'c="0"' in sml
        assert "Cell A1" in sml


class TestGroupGeneration:
    """Test group element generation."""

    def test_group_with_children(self) -> None:
        """Groups should contain their children."""
        pres = {
            "presentationId": "test123",
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 5143500, "unit": "EMU"},
            },
            "slides": [
                {
                    "objectId": "slide_1",
                    "pageElements": [
                        {
                            "objectId": "group_1",
                            "size": {
                                "width": {"magnitude": 2540000, "unit": "EMU"},
                                "height": {"magnitude": 1270000, "unit": "EMU"},
                            },
                            "transform": {
                                "scaleX": 1.0,
                                "scaleY": 1.0,
                                "translateX": 0,
                                "translateY": 0,
                                "unit": "EMU",
                            },
                            "elementGroup": {
                                "children": [
                                    {
                                        "objectId": "child_1",
                                        "size": {
                                            "width": {
                                                "magnitude": 1270000,
                                                "unit": "EMU",
                                            },
                                            "height": {
                                                "magnitude": 635000,
                                                "unit": "EMU",
                                            },
                                        },
                                        "transform": {
                                            "scaleX": 1.0,
                                            "scaleY": 1.0,
                                            "translateX": 0,
                                            "translateY": 0,
                                            "unit": "EMU",
                                        },
                                        "shape": {
                                            "shapeType": "RECTANGLE",
                                            "shapeProperties": {},
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                }
            ],
        }

        sml = json_to_sml(pres)

        assert '<Group id="group_1"' in sml
        assert '<Rect id="child_1"' in sml
        assert "</Group>" in sml


class TestRealPresentationFile:
    """Test against real presentation JSON if available."""

    @pytest.fixture
    def example_json_path(self) -> Path:
        """Path to example JSON file."""
        return Path(__file__).parent.parent / "examples" / "json"

    def test_can_parse_example_presentation(self, example_json_path: Path) -> None:
        """Should be able to parse real presentation JSON."""
        json_files = list(example_json_path.glob("*.json"))
        if not json_files:
            pytest.skip("No example JSON files found")

        for json_file in json_files:
            # Only try first 100KB to avoid memory issues in test
            content = json_file.read_text()[:100000]
            # Find a valid JSON subset
            try:
                # Try to parse what we have
                data = json.loads(content + "}")  # May need closing
            except json.JSONDecodeError:
                # Skip malformed subset
                continue

            # Should not raise
            sml = json_to_sml(data)
            assert "<Presentation" in sml
