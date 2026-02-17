"""Golden file round-trip test for serde: Document → XML → Document.

Tests that serializing a real Google Docs API response to XML and
deserializing it back produces an equivalent Document.

Normalization philosophy (from serde/CLAUDE.md):
The XML→Document conversion does NOT need to perfectly reproduce the original
API Document. It needs to be **consistent**: when both base and desired Documents
go through the same XML→Document path, any systematic bias cancels out.

We normalize away:
- startIndex/endIndex (indices are recomputed separately)
- suggestionsViewMode (not part of document content)
- False booleans (absent and false are semantically equivalent)
- Zero-magnitude dimensions like {unit: PT} (absent and 0pt are equivalent)
- Empty/default borders with no actual styling data
- Empty shading ({backgroundColor: {}})
- Empty textStyle ({}) on non-textRun elements (horizontalRule, etc.)
- Float precision differences from hex↔RGB conversion
- Trailing \\n run merging (both sides do the same thing)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from extradoc.api_types._generated import Document
from extradoc.serde import deserialize, from_document, serialize, to_document

GOLDEN_DIR = Path(__file__).parent / "golden"
DOC_ID = "14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ"


def _load_golden_doc() -> Document:
    """Load a golden file and parse it as a Document."""
    path = GOLDEN_DIR / f"{DOC_ID}.json"
    raw = json.loads(path.read_text())
    return Document.model_validate(raw)


def _is_empty_value(v: Any) -> bool:
    """Check if a value is an empty default that should be stripped."""
    if v is False:
        return True
    return bool(isinstance(v, dict) and not v)


def _is_zero_dim(v: Any) -> bool:
    """Check if a value is a zero-magnitude dimension like {unit: PT}."""
    if not isinstance(v, dict):
        return False
    if set(v.keys()) == {"unit"}:
        return True
    return v.get("magnitude") is not None and v["magnitude"] == 0


def _is_default_border(v: Any) -> bool:
    """Check if a border is a default (empty color, no real width)."""
    if not isinstance(v, dict):
        return False
    keys = set(v.keys())
    # Default borders have color={}, dashStyle=SOLID, padding={unit:PT}, width={unit:PT}
    if keys <= {"color", "dashStyle", "padding", "width"}:
        color = v.get("color")
        width = v.get("width")
        if (color == {} or color is None) and _is_zero_dim(width):
            return True
    return False


def _is_empty_shading(v: Any) -> bool:
    """Check if shading is empty ({backgroundColor: {}})."""
    if isinstance(v, dict) and set(v.keys()) == {"backgroundColor"}:
        return v["backgroundColor"] == {} or v["backgroundColor"] is None
    return False


_BORDER_KEYS = frozenset(
    {"borderTop", "borderBottom", "borderLeft", "borderRight", "borderBetween"}
)
_DIM_KEYS = frozenset(
    {
        "indentStart",
        "indentEnd",
        "indentFirstLine",
        "spaceAbove",
        "spaceBelow",
        "paddingTop",
        "paddingBottom",
        "paddingLeft",
        "paddingRight",
        "marginTop",
        "marginBottom",
        "marginLeft",
        "marginRight",
        "marginHeader",
        "marginFooter",
        "minRowHeight",
        "width",
    }
)
_FALSE_BOOL_KEYS = frozenset(
    {
        "keepLinesTogether",
        "keepWithNext",
        "pageBreakBefore",
        "avoidWidowAndOrphan",
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "smallCaps",
        "preventOverflow",
        "tableHeader",
        "flipPageOrientation",
        "useFirstPageHeaderFooter",
    }
)


def _round_float(v: float, decimals: int = 4) -> float:
    """Round a float to reduce precision differences from hex↔RGB conversion."""
    return round(v, decimals)


def _normalize(obj: Any) -> Any:
    """Recursively normalize a document dict for comparison.

    Strips defaults, normalizes floats, removes indices.
    """
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            # Skip indices
            if k in ("startIndex", "endIndex"):
                continue
            # Skip false booleans
            if k in _FALSE_BOOL_KEYS and v is False:
                continue
            # Skip zero-magnitude dimensions
            if k in _DIM_KEYS and _is_zero_dim(v):
                continue
            # Skip default borders
            if k in _BORDER_KEYS and _is_default_border(v):
                continue
            # Skip empty shading
            if k == "shading" and _is_empty_shading(v):
                continue
            # Skip empty textStyle on non-textRun elements
            if k == "textStyle" and isinstance(v, dict) and not v:
                continue
            # Normalize the value
            normalized = _normalize(v)
            # Skip if normalization resulted in empty dict
            if isinstance(normalized, dict) and not normalized:
                continue
            result[k] = normalized
        return result
    if isinstance(obj, list):
        return [_normalize(item) for item in obj]
    if isinstance(obj, float):
        return _round_float(obj)
    return obj


def _merge_trailing_newline_runs(
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge a trailing \\n textRun into the preceding textRun.

    The Google Docs API returns separate runs for content and trailing \\n.
    The serde round-trip merges them. Normalize the original to match.
    """
    if len(elements) < 2:
        return elements

    last = elements[-1]
    if not isinstance(last, dict) or "textRun" not in last:
        return elements

    last_tr = last["textRun"]
    if last_tr.get("content") != "\n":
        return elements

    prev = elements[-2]
    if not isinstance(prev, dict) or "textRun" not in prev:
        return elements

    # Merge: append \n to the previous textRun's content
    merged = []
    for i, elem in enumerate(elements[:-1]):
        if i == len(elements) - 2:
            # Clone and append \n
            new_elem = json.loads(json.dumps(elem))
            new_elem["textRun"]["content"] += "\n"
            merged.append(new_elem)
        else:
            merged.append(elem)
    return merged


def _normalize_elements(obj: Any) -> Any:
    """Walk the structure and merge trailing \\n runs in paragraph elements."""
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "elements" and isinstance(v, list):
                v = _merge_trailing_newline_runs(v)
            result[k] = _normalize_elements(v)
        return result
    if isinstance(obj, list):
        return [_normalize_elements(item) for item in obj]
    return obj


def _normalize_doc(doc: Document) -> dict[str, Any]:
    """Convert Document to a normalized dict for comparison."""
    d = doc.model_dump(by_alias=True, exclude_none=True)
    d.pop("suggestionsViewMode", None)
    d = _normalize(d)
    d = _normalize_elements(d)
    return d


def _collect_diffs(
    original: Any,
    roundtrip: Any,
    path: str = "",
    diffs: list[str] | None = None,
) -> list[str]:
    """Recursively compare two structures and collect human-readable diffs."""
    if diffs is None:
        diffs = []

    if type(original) is not type(roundtrip):
        diffs.append(
            f"{path}: type mismatch: {type(original).__name__} vs {type(roundtrip).__name__}"
        )
        return diffs

    if isinstance(original, dict):
        all_keys = set(original) | set(roundtrip)
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else key
            if key not in roundtrip:
                val = original[key]
                val_str = repr(val)
                if len(val_str) > 120:
                    val_str = val_str[:120] + "..."
                diffs.append(f"{child_path}: missing in roundtrip (original={val_str})")
            elif key not in original:
                val = roundtrip[key]
                val_str = repr(val)
                if len(val_str) > 120:
                    val_str = val_str[:120] + "..."
                diffs.append(f"{child_path}: extra in roundtrip (value={val_str})")
            else:
                _collect_diffs(original[key], roundtrip[key], child_path, diffs)
    elif isinstance(original, list):
        if len(original) != len(roundtrip):
            diffs.append(
                f"{path}: list length mismatch: {len(original)} vs {len(roundtrip)}"
            )
            for i in range(min(len(original), len(roundtrip))):
                _collect_diffs(original[i], roundtrip[i], f"{path}[{i}]", diffs)
        else:
            for i in range(len(original)):
                _collect_diffs(original[i], roundtrip[i], f"{path}[{i}]", diffs)
    else:
        if isinstance(original, float) and isinstance(roundtrip, float):
            if not math.isclose(original, roundtrip, rel_tol=1e-3):
                diffs.append(f"{path}: value mismatch: {original!r} vs {roundtrip!r}")
        elif original != roundtrip:
            diffs.append(f"{path}: value mismatch: {original!r} vs {roundtrip!r}")

    return diffs


class TestGoldenRoundTrip:
    """Test round-trip fidelity using a real Google Docs API response."""

    def test_document_to_xml_to_document(self, tmp_path: Path) -> None:
        """Document → XML folder → Document produces equivalent Document."""
        original_doc = _load_golden_doc()

        # Step 1: Document → XML folder (serialize to disk)
        output_dir = tmp_path / "doc"
        serialize(original_doc, output_dir)

        # Step 2: XML folder → Document (deserialize from disk)
        roundtrip_doc = deserialize(output_dir)

        # Step 3: Compare
        original_norm = _normalize_doc(original_doc)
        roundtrip_norm = _normalize_doc(roundtrip_doc)

        diffs = _collect_diffs(original_norm, roundtrip_norm)

        if diffs:
            print(f"\n{'=' * 60}")
            print(f"Found {len(diffs)} differences:")
            print(f"{'=' * 60}")
            for i, diff in enumerate(diffs[:50], 1):
                print(f"  {i}. {diff}")
            if len(diffs) > 50:
                print(f"  ... and {len(diffs) - 50} more")
            print(f"{'=' * 60}\n")

        assert diffs == [], f"Round-trip produced {len(diffs)} differences"

    def test_in_memory_roundtrip(self) -> None:
        """Document → XML models → Document (no file I/O)."""
        original_doc = _load_golden_doc()

        # Step 1: Document → XML models
        _index, tabs = from_document(original_doc)

        # Step 2: XML models → Document
        roundtrip_doc = to_document(
            tabs,
            document_id=original_doc.document_id or "",
            title=original_doc.title or "",
        )

        # Step 3: Compare (revisionId is preserved via index.xml in file
        # round-trip but not in in-memory round-trip, so strip it here)
        original_norm = _normalize_doc(original_doc)
        original_norm.pop("revisionId", None)
        roundtrip_norm = _normalize_doc(roundtrip_doc)
        roundtrip_norm.pop("revisionId", None)

        diffs = _collect_diffs(original_norm, roundtrip_norm)

        if diffs:
            print(f"\n{'=' * 60}")
            print(f"Found {len(diffs)} differences:")
            print(f"{'=' * 60}")
            for i, diff in enumerate(diffs[:50], 1):
                print(f"  {i}. {diff}")
            if len(diffs) > 50:
                print(f"  ... and {len(diffs) - 50} more")
            print(f"{'=' * 60}\n")

        assert diffs == [], f"Round-trip produced {len(diffs)} differences"
