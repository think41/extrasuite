"""Tests for the Google Docs index calculator."""

import json
from pathlib import Path

import pytest

from extradoc.indexer import utf16_len, validate_document


class TestUtf16Len:
    """Tests for UTF-16 length calculation."""

    def test_ascii_string(self) -> None:
        """ASCII characters are 1 UTF-16 code unit each."""
        assert utf16_len("hello") == 5
        assert utf16_len("") == 0
        assert utf16_len(" ") == 1

    def test_newline(self) -> None:
        """Newline is 1 UTF-16 code unit."""
        assert utf16_len("\n") == 1
        assert utf16_len("hello\n") == 6

    def test_bmp_unicode(self) -> None:
        """Characters in BMP (U+0000 to U+FFFF) are 1 UTF-16 code unit."""
        # Smart quotes
        assert utf16_len("\u2019") == 1  # Right single quotation mark
        assert utf16_len("I\u2019m") == 3  # "I'm" with smart quote

        # Em dash
        assert utf16_len("\u2014") == 1

        # Private use area (used by Google Docs for special markers)
        assert utf16_len("\ue907") == 1

    def test_surrogate_pairs(self) -> None:
        """Characters outside BMP (> U+FFFF) need surrogate pairs (2 code units)."""
        # Emoji
        assert utf16_len("😀") == 2  # U+1F600
        assert utf16_len("hello 😀") == 8  # 6 + 2

        # Mathematical symbols (U+1D54F - mathematical double-struck X)
        assert utf16_len("\U0001d54f") == 2

        # Multiple emoji
        assert utf16_len("😀😀😀") == 6  # 3 emoji * 2 code units each

    def test_mixed_content(self) -> None:
        """Mixed ASCII, BMP, and surrogate pair characters."""
        # "Hi 😀!" = 2 + 1 + 2 + 1 = 6
        assert utf16_len("Hi 😀!") == 6

        # Japanese + emoji
        assert utf16_len("こんにちは") == 5  # All BMP
        assert utf16_len("こんにちは😀") == 7  # 5 + 2


class TestGoldenFiles:
    """Tests using golden files from real Google Docs."""

    @pytest.fixture
    def golden_dir(self) -> Path:
        """Path to golden test files."""
        return Path(__file__).parent / "golden"

    def test_validate_r41_ai_support_agent(self, golden_dir: Path) -> None:
        """Validate indexes in the R41 AI Support Agent document."""
        doc_path = golden_dir / "1tlHGpgjoibP0eVXRvCGSmkqrLATrXYTo7dUnmV7x01o.json"
        if not doc_path.exists():
            pytest.skip("Golden file not found")

        document = json.loads(doc_path.read_text())
        result = validate_document(document)

        assert result.is_valid, f"Index mismatches: {result.mismatches[:5]}"
        assert result.total_elements_checked > 0

    def test_validate_sri_document_edit_testing(self, golden_dir: Path) -> None:
        """Validate indexes in the Sri-Document-Edit-Testing document."""
        doc_path = golden_dir / "1arcBS-A_LqbvrstLAADAjCZj4kvTlqmQ0ztFNfyAEyc.json"
        if not doc_path.exists():
            pytest.skip("Golden file not found")

        document = json.loads(doc_path.read_text())
        result = validate_document(document)

        assert result.is_valid, f"Index mismatches: {result.mismatches[:5]}"
        assert result.total_elements_checked > 0
        # This document has tables, headers, footers
        assert result.total_elements_checked > 1500


class TestIndexCalculator:
    """Unit tests for IndexCalculator with synthetic documents."""

    def test_simple_paragraph(self) -> None:
        """Test a document with a single paragraph."""
        document = {
            "documentId": "test",
            "body": {
                "content": [
                    {"endIndex": 1, "sectionBreak": {"sectionStyle": {}}},
                    {
                        "startIndex": 1,
                        "endIndex": 7,
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 7,
                                    "textRun": {"content": "hello\n"},
                                }
                            ]
                        },
                    },
                ]
            },
        }
        result = validate_document(document)
        assert result.is_valid

    def test_multiple_text_runs(self) -> None:
        """Test paragraph with multiple styled text runs."""
        document = {
            "documentId": "test",
            "body": {
                "content": [
                    {"endIndex": 1, "sectionBreak": {"sectionStyle": {}}},
                    {
                        "startIndex": 1,
                        "endIndex": 12,
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 6,
                                    "textRun": {"content": "hello"},
                                },
                                {
                                    "startIndex": 6,
                                    "endIndex": 12,
                                    "textRun": {"content": " world"},
                                },
                                {
                                    "startIndex": 12,
                                    "endIndex": 13,
                                    "textRun": {"content": "\n"},
                                },
                            ]
                        },
                    },
                ]
            },
        }
        # Fix: endIndex should be 13
        document["body"]["content"][1]["endIndex"] = 13
        result = validate_document(document)
        assert result.is_valid

    def test_horizontal_rule(self) -> None:
        """Test paragraph with horizontal rule (consumes 1 index)."""
        document = {
            "documentId": "test",
            "body": {
                "content": [
                    {"endIndex": 1, "sectionBreak": {"sectionStyle": {}}},
                    {
                        "startIndex": 1,
                        "endIndex": 3,
                        "paragraph": {
                            "elements": [
                                {"startIndex": 1, "endIndex": 2, "horizontalRule": {}},
                                {
                                    "startIndex": 2,
                                    "endIndex": 3,
                                    "textRun": {"content": "\n"},
                                },
                            ]
                        },
                    },
                ]
            },
        }
        result = validate_document(document)
        assert result.is_valid

    def test_simple_table(self) -> None:
        """Test a simple 1x1 table."""
        # Table structure:
        # - Table start: index 1 (marker)
        # - Row start: index 2 (marker)
        # - Cell start: index 3 (marker)
        # - Paragraph: indexes 4-6 ("A\n")
        # - Cell end: index 6
        # - Row end: index 6
        # - Table end: index 7 (end marker)
        document = {
            "documentId": "test",
            "body": {
                "content": [
                    {"endIndex": 1, "sectionBreak": {"sectionStyle": {}}},
                    {
                        "startIndex": 1,
                        "endIndex": 7,
                        "table": {
                            "rows": 1,
                            "columns": 1,
                            "tableRows": [
                                {
                                    "startIndex": 2,
                                    "endIndex": 6,
                                    "tableCells": [
                                        {
                                            "startIndex": 3,
                                            "endIndex": 6,
                                            "content": [
                                                {
                                                    "startIndex": 4,
                                                    "endIndex": 6,
                                                    "paragraph": {
                                                        "elements": [
                                                            {
                                                                "startIndex": 4,
                                                                "endIndex": 6,
                                                                "textRun": {
                                                                    "content": "A\n"
                                                                },
                                                            }
                                                        ]
                                                    },
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        },
                    },
                ]
            },
        }
        result = validate_document(document)
        assert result.is_valid

    def test_detects_mismatch(self) -> None:
        """Test that mismatches are detected correctly."""
        document = {
            "documentId": "test",
            "body": {
                "content": [
                    {"endIndex": 1, "sectionBreak": {"sectionStyle": {}}},
                    {
                        "startIndex": 1,
                        "endIndex": 8,  # Wrong! Should be 7
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 7,
                                    "textRun": {"content": "hello\n"},
                                }
                            ]
                        },
                    },
                ]
            },
        }
        result = validate_document(document)
        assert not result.is_valid
        assert len(result.mismatches) == 1
        assert result.mismatches[0].expected == 7
        assert result.mismatches[0].actual == 8

    def test_header_indexes_start_at_zero(self) -> None:
        """Test that header content indexes start at 0."""
        document = {
            "documentId": "test",
            "body": {"content": [{"endIndex": 1, "sectionBreak": {}}]},
            "headers": {
                "header1": {
                    "headerId": "header1",
                    "content": [
                        {
                            "startIndex": 0,
                            "endIndex": 7,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": 0,
                                        "endIndex": 7,
                                        "textRun": {"content": "Header\n"},
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        }
        result = validate_document(document)
        assert result.is_valid

    def test_footer_indexes_start_at_zero(self) -> None:
        """Test that footer content indexes start at 0."""
        document = {
            "documentId": "test",
            "body": {"content": [{"endIndex": 1, "sectionBreak": {}}]},
            "footers": {
                "footer1": {
                    "footerId": "footer1",
                    "content": [
                        {
                            "startIndex": 0,
                            "endIndex": 7,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": 0,
                                        "endIndex": 7,
                                        "textRun": {"content": "Footer\n"},
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        }
        result = validate_document(document)
        assert result.is_valid
