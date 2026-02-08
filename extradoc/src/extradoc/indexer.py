"""Index tracking for Google Docs.

Google Docs uses UTF-16 code unit based indexing. This module provides
utilities to calculate and verify indexes for document elements.
"""

from __future__ import annotations


def utf16_len(text: str) -> int:
    """Calculate the length of a string in UTF-16 code units.

    Python strings are UTF-32 internally, but Google Docs uses UTF-16.
    Characters outside the BMP (code points > 0xFFFF) use surrogate pairs
    in UTF-16, consuming 2 code units.

    Args:
        text: The string to measure

    Returns:
        Length in UTF-16 code units
    """
    length = 0
    for char in text:
        code_point = ord(char)
        if code_point > 0xFFFF:
            # Surrogate pair needed
            length += 2
        else:
            length += 1
    return length
