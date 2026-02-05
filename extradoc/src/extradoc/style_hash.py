"""Generate stable, content-based style IDs.

Style IDs are 5-character hashes derived from style properties.
Same properties always produce the same ID across runs.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

# Valid characters for XML NCName (ID attribute)
# First character: letters and underscore only
FIRST_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
# Subsequent characters: letters, digits, underscore, hyphen, period
REST_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-."


def style_id(properties: Mapping[str, Any]) -> str:
    """Generate a 5-character style ID from properties.

    Args:
        properties: Style properties dict, e.g., {"font": "Arial", "size": "11pt"}

    Returns:
        5-character string valid as XML ID, e.g., "kX9_m"

    The ID is:
    - Deterministic: same properties always produce same ID
    - Stable: order of properties doesn't matter (sorted internally)
    - Collision-resistant: ~946 million possible values
    - XML-valid: starts with letter/underscore, rest alphanumeric + _-.
    """
    if not properties:
        # Empty/base style gets a readable ID
        return "_base"

    # Canonical serialization: sorted keys, pipe-separated
    canonical = "|".join(f"{k}={v}" for k, v in sorted(properties.items()))

    # MD5 hash (not for crypto, just for distribution)
    h = hashlib.md5(canonical.encode("utf-8")).digest()

    # Convert to large integer
    num = int.from_bytes(h, "big")

    # Encode first character (from restricted set)
    first = FIRST_CHARS[num % len(FIRST_CHARS)]
    num //= len(FIRST_CHARS)

    # Encode remaining 4 characters
    rest = []
    for _ in range(4):
        rest.append(REST_CHARS[num % len(REST_CHARS)])
        num //= len(REST_CHARS)

    return first + "".join(rest)


def style_id_short(properties: Mapping[str, Any], length: int = 4) -> str:
    """Generate a shorter style ID (for less complex documents).

    Args:
        properties: Style properties dict
        length: Total ID length (2-6, default 4)

    Returns:
        ID string of specified length
    """
    if not properties:
        return "_" * length

    canonical = "|".join(f"{k}={v}" for k, v in sorted(properties.items()))
    h = hashlib.md5(canonical.encode("utf-8")).digest()
    num = int.from_bytes(h, "big")

    first = FIRST_CHARS[num % len(FIRST_CHARS)]
    num //= len(FIRST_CHARS)

    rest = []
    for _ in range(length - 1):
        rest.append(REST_CHARS[num % len(REST_CHARS)])
        num //= len(REST_CHARS)

    return first + "".join(rest)


# --- Demonstration ---

if __name__ == "__main__":
    # Example styles
    examples = [
        {},  # Base/empty
        {"bold": "1"},
        {"italic": "1"},
        {"bold": "1", "italic": "1"},
        {"font": "Arial", "size": "11pt"},
        {"font": "Arial", "size": "11pt", "color": "#000000"},
        {"font": "Courier", "size": "10pt", "bg": "#F5F5F5"},
        {"color": "#FF0000", "bold": "1"},
        {"alignment": "CENTER"},
    ]

    print("Style ID Generation Examples:")
    print("-" * 50)
    for props in examples:
        sid = style_id(props)
        print(f"{sid}  ←  {props or '(empty/base)'}")

    print("\n" + "-" * 50)
    print("Stability test (same input = same output):")
    for _ in range(3):
        sid = style_id({"font": "Arial", "bold": "1"})
        print(f"  {sid}")
