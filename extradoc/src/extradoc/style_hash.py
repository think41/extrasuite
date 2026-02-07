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
