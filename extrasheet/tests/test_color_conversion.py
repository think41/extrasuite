"""Tests for color conversion functions in format_compression."""

import pytest

from extrasheet.format_compression import (
    hex_to_rgb,
    normalize_colors_to_hex,
    normalize_colors_to_rgb,
    normalize_condition_values,
    rgb_to_hex,
)


class TestRgbToHex:
    def test_simple_red(self):
        assert rgb_to_hex({"red": 1.0, "green": 0, "blue": 0}) == "#FF0000"

    def test_simple_green(self):
        assert rgb_to_hex({"red": 0, "green": 1.0, "blue": 0}) == "#00FF00"

    def test_simple_blue(self):
        assert rgb_to_hex({"red": 0, "green": 0, "blue": 1.0}) == "#0000FF"

    def test_white(self):
        assert rgb_to_hex({"red": 1.0, "green": 1.0, "blue": 1.0}) == "#FFFFFF"

    def test_black(self):
        assert rgb_to_hex({"red": 0, "green": 0, "blue": 0}) == "#000000"

    def test_partial_values(self):
        # Only red specified, others default to 0
        assert rgb_to_hex({"red": 0.5}) == "#7F0000"

    def test_mixed_color(self):
        assert rgb_to_hex({"red": 0.8, "green": 1.0, "blue": 0.8}) == "#CCFFCC"


class TestHexToRgb:
    def test_red_with_hash(self):
        result = hex_to_rgb("#FF0000")
        assert result["red"] == pytest.approx(1.0)
        assert result["green"] == pytest.approx(0.0)
        assert result["blue"] == pytest.approx(0.0)

    def test_red_without_hash(self):
        result = hex_to_rgb("FF0000")
        assert result["red"] == pytest.approx(1.0)

    def test_green(self):
        result = hex_to_rgb("#00FF00")
        assert result["green"] == pytest.approx(1.0)

    def test_blue(self):
        result = hex_to_rgb("#0000FF")
        assert result["blue"] == pytest.approx(1.0)

    def test_white(self):
        result = hex_to_rgb("#FFFFFF")
        assert result["red"] == pytest.approx(1.0)
        assert result["green"] == pytest.approx(1.0)
        assert result["blue"] == pytest.approx(1.0)


class TestNormalizeColorsToHex:
    def test_simple_dict(self):
        input_data = {"red": 1.0, "green": 0, "blue": 0}
        result = normalize_colors_to_hex(input_data)
        assert result == "#FF0000"

    def test_nested_dict(self):
        input_data = {
            "format": {"backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8}}
        }
        result = normalize_colors_to_hex(input_data)
        assert result == {"format": {"backgroundColor": "#CCFFCC"}}

    def test_list_of_dicts(self):
        input_data = [
            {"color": {"red": 1, "green": 0, "blue": 0}},
            {"color": {"red": 0, "green": 1, "blue": 0}},
        ]
        result = normalize_colors_to_hex(input_data)
        assert result == [
            {"color": "#FF0000"},
            {"color": "#00FF00"},
        ]

    def test_preserves_non_color_dicts(self):
        input_data = {"name": "test", "value": 42}
        result = normalize_colors_to_hex(input_data)
        assert result == {"name": "test", "value": 42}

    def test_conditional_format_structure(self):
        input_data = {
            "booleanRule": {
                "condition": {"type": "NUMBER_GREATER"},
                "format": {"backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8}},
            }
        }
        result = normalize_colors_to_hex(input_data)
        assert result["booleanRule"]["format"]["backgroundColor"] == "#CCFFCC"


class TestNormalizeColorsToRgb:
    def test_simple_hex(self):
        input_data = "#FF0000"
        result = normalize_colors_to_rgb(input_data)
        assert result["red"] == pytest.approx(1.0)
        assert result["green"] == pytest.approx(0.0)
        assert result["blue"] == pytest.approx(0.0)

    def test_nested_dict(self):
        input_data = {"format": {"backgroundColor": "#CCFFCC"}}
        result = normalize_colors_to_rgb(input_data)
        assert "red" in result["format"]["backgroundColor"]
        assert result["format"]["backgroundColor"]["green"] == pytest.approx(1.0)

    def test_list_of_dicts(self):
        input_data = [
            {"color": "#FF0000"},
            {"color": "#00FF00"},
        ]
        result = normalize_colors_to_rgb(input_data)
        assert result[0]["color"]["red"] == pytest.approx(1.0)
        assert result[1]["color"]["green"] == pytest.approx(1.0)

    def test_preserves_non_hex_strings(self):
        input_data = {"name": "test", "type": "NUMBER"}
        result = normalize_colors_to_rgb(input_data)
        assert result == {"name": "test", "type": "NUMBER"}

    def test_invalid_hex_preserved(self):
        # Invalid hex strings should be preserved as-is
        input_data = {"color": "#GGG"}
        result = normalize_colors_to_rgb(input_data)
        assert result == {"color": "#GGG"}


class TestRoundtrip:
    def test_hex_to_rgb_to_hex(self):
        original = "#AABBCC"
        rgb = hex_to_rgb(original)
        result = rgb_to_hex(rgb)
        assert result == original

    def test_normalize_roundtrip(self):
        original = {
            "format": {
                "backgroundColor": "#CCFFCC",
                "textFormat": {"foregroundColor": "#FF0000"},
            }
        }
        # Convert to RGB then back to hex
        as_rgb = normalize_colors_to_rgb(original)
        back_to_hex = normalize_colors_to_hex(as_rgb)
        assert back_to_hex == original


class TestNormalizeConditionValues:
    """Tests for normalizing condition values in booleanRule conditions."""

    def test_plain_string_to_user_entered_value(self):
        """Plain string should be wrapped in userEnteredValue."""
        input_data = {
            "condition": {
                "type": "NUMBER_GREATER",
                "values": ["1000"],
            }
        }
        result = normalize_condition_values(input_data)
        assert result["condition"]["values"] == [{"userEnteredValue": "1000"}]

    def test_user_entered_value_passthrough(self):
        """Already-formatted userEnteredValue should pass through unchanged."""
        input_data = {
            "condition": {
                "type": "TEXT_CONTAINS",
                "values": [{"userEnteredValue": "test"}],
            }
        }
        result = normalize_condition_values(input_data)
        assert result["condition"]["values"] == [{"userEnteredValue": "test"}]

    def test_relative_date_passthrough(self):
        """relativeDate format should pass through unchanged."""
        input_data = {
            "condition": {
                "type": "DATE_BEFORE",
                "values": [{"relativeDate": "TODAY"}],
            }
        }
        result = normalize_condition_values(input_data)
        assert result["condition"]["values"] == [{"relativeDate": "TODAY"}]

    def test_multiple_values_mixed(self):
        """Multiple values with mixed formats should all be normalized."""
        input_data = {
            "condition": {
                "type": "NUMBER_BETWEEN",
                "values": ["100", {"userEnteredValue": "200"}],
            }
        }
        result = normalize_condition_values(input_data)
        assert result["condition"]["values"] == [
            {"userEnteredValue": "100"},
            {"userEnteredValue": "200"},
        ]

    def test_nested_boolean_rule(self):
        """Full booleanRule structure should be normalized."""
        input_data = {
            "booleanRule": {
                "condition": {
                    "type": "NUMBER_GREATER",
                    "values": ["50"],
                },
                "format": {"backgroundColor": "#00FF00"},
            }
        }
        result = normalize_condition_values(input_data)
        assert result["booleanRule"]["condition"]["values"] == [
            {"userEnteredValue": "50"}
        ]
        # Other fields preserved
        assert result["booleanRule"]["format"]["backgroundColor"] == "#00FF00"

    def test_list_of_rules(self):
        """List of conditional format rules should all be normalized."""
        input_data = [
            {"condition": {"type": "TEXT_EQ", "values": ["Yes"]}},
            {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "No"}]}},
        ]
        result = normalize_condition_values(input_data)
        assert result[0]["condition"]["values"] == [{"userEnteredValue": "Yes"}]
        assert result[1]["condition"]["values"] == [{"userEnteredValue": "No"}]

    def test_numeric_value_converted_to_string(self):
        """Numeric values should be converted to string in userEnteredValue."""
        input_data = {"condition": {"values": [42]}}
        result = normalize_condition_values(input_data)
        assert result["condition"]["values"] == [{"userEnteredValue": "42"}]

    def test_preserves_non_values_fields(self):
        """Fields other than 'values' should be preserved unchanged."""
        input_data = {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": ["=A1>B1"],
            },
            "format": {"bold": True},
        }
        result = normalize_condition_values(input_data)
        assert result["condition"]["type"] == "CUSTOM_FORMULA"
        assert result["format"]["bold"] is True

    def test_empty_values_list(self):
        """Empty values list should remain empty."""
        input_data = {"condition": {"type": "BLANK", "values": []}}
        result = normalize_condition_values(input_data)
        assert result["condition"]["values"] == []

    def test_no_values_key(self):
        """Conditions without values should pass through."""
        input_data = {"condition": {"type": "NOT_BLANK"}}
        result = normalize_condition_values(input_data)
        assert result == {"condition": {"type": "NOT_BLANK"}}
