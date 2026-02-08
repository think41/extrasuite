"""Tests for the Google Docs index utilities."""

from extradoc.indexer import utf16_len


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
