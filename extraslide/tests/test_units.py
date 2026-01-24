"""Tests for unit conversion utilities.

Tests cover:
- EMU to PT conversion and vice versa (Spec: 1 pt = 12700 EMU)
- RGB to hex color conversion
- Hex to RGB color conversion
"""

import pytest

from extraslide.units import emu_to_pt, format_pt, hex_to_rgb, pt_to_emu, rgb_to_hex


class TestEmuPtConversion:
    """Test EMU <-> PT conversion.

    Spec reference: sml-reconciliation-spec.md#unit-conversion
    """

    def test_emu_to_pt_basic(self) -> None:
        """1 pt = 12700 EMU"""
        assert emu_to_pt(12700) == 1.0
        assert emu_to_pt(127000) == 10.0
        assert emu_to_pt(0) == 0.0

    def test_emu_to_pt_fractional(self) -> None:
        """Fractional conversions should work."""
        assert emu_to_pt(6350) == 0.5
        assert emu_to_pt(25400) == 2.0

    def test_pt_to_emu_basic(self) -> None:
        """Reverse conversion."""
        assert pt_to_emu(1.0) == 12700
        assert pt_to_emu(10.0) == 127000
        assert pt_to_emu(0) == 0

    def test_pt_to_emu_rounding(self) -> None:
        """PT to EMU should round to integer."""
        assert isinstance(pt_to_emu(1.5), int)
        assert pt_to_emu(1.5) == 19050

    def test_roundtrip(self) -> None:
        """EMU -> PT -> EMU should roundtrip (with rounding tolerance)."""
        original = 9144000  # Common slide width
        converted = pt_to_emu(emu_to_pt(original))
        assert converted == original


class TestColorConversion:
    """Test RGB <-> Hex color conversion.

    Spec reference: markup-syntax-design.md#solid-colors-rgb-hex
    """

    def test_rgb_to_hex_basic(self) -> None:
        """Basic RGB to hex."""
        assert rgb_to_hex(1.0, 0.0, 0.0) == "#ff0000"
        assert rgb_to_hex(0.0, 1.0, 0.0) == "#00ff00"
        assert rgb_to_hex(0.0, 0.0, 1.0) == "#0000ff"
        assert rgb_to_hex(0.0, 0.0, 0.0) == "#000000"
        assert rgb_to_hex(1.0, 1.0, 1.0) == "#ffffff"

    def test_rgb_to_hex_google_blue(self) -> None:
        """Google Blue (#4285f4) conversion."""
        # Approximate values from Google Slides API
        hex_val = rgb_to_hex(0.26, 0.52, 0.96)
        assert hex_val == "#4285f5"  # Close to #4285f4

    def test_rgb_to_hex_defaults_to_black(self) -> None:
        """Default (no args) should give black."""
        assert rgb_to_hex() == "#000000"

    def test_hex_to_rgb_basic(self) -> None:
        """Basic hex to RGB."""
        assert hex_to_rgb("#ff0000") == (1.0, 0.0, 0.0)
        assert hex_to_rgb("#00ff00") == (0.0, 1.0, 0.0)
        assert hex_to_rgb("#0000ff") == (0.0, 0.0, 1.0)

    def test_hex_to_rgb_without_hash(self) -> None:
        """Hex without # prefix should work."""
        assert hex_to_rgb("ff0000") == (1.0, 0.0, 0.0)

    def test_hex_to_rgb_roundtrip(self) -> None:
        """RGB -> hex -> RGB should roundtrip."""
        r, g, b = 0.5, 0.25, 0.75
        hex_val = rgb_to_hex(r, g, b)
        r2, g2, b2 = hex_to_rgb(hex_val)
        # Allow small tolerance due to 8-bit precision
        assert abs(r - r2) < 0.01
        assert abs(g - g2) < 0.01
        assert abs(b - b2) < 0.01

    def test_hex_to_rgb_invalid(self) -> None:
        """Invalid hex should raise ValueError."""
        with pytest.raises(ValueError):
            hex_to_rgb("invalid")
        with pytest.raises(ValueError):
            hex_to_rgb("#fff")  # Too short
        with pytest.raises(ValueError):
            hex_to_rgb("#fffffff")  # Too long


class TestFormatPt:
    """Test point value formatting."""

    def test_format_pt_integer(self) -> None:
        """Integer values should not have decimal."""
        assert format_pt(100.0) == "100"
        assert format_pt(72.0) == "72"

    def test_format_pt_decimal(self) -> None:
        """Decimal values should be preserved."""
        assert format_pt(100.5) == "100.5"
        assert format_pt(72.25) == "72.25"

    def test_format_pt_rounding(self) -> None:
        """Values should be rounded to specified precision."""
        assert format_pt(100.123456, precision=2) == "100.12"
        assert format_pt(100.999, precision=2) == "101"

    def test_format_pt_near_integer(self) -> None:
        """Values very close to integers should become integers."""
        assert format_pt(100.0001) == "100"
