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
- bullet.textStyle (API-derived from text content, not stored in XML)
- inlineObjectElement.textStyle (not represented in XML format)
- textStyle on \\n-only textRuns (style on trailing newline is not meaningful)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.serde.xml import XmlSerde, from_document, to_document

_xml_serde = XmlSerde()

GOLDEN_DIR = Path(__file__).parent / "golden"

# Golden file document IDs
GOLDEN_DOCS = [
    "14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ",  # 3-tab doc with tables, HRs
    "1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc",  # 1-tab doc with lists, images
]


def _load_golden_doc(doc_id: str) -> Document:
    """Load a golden file and parse it as a Document."""
    path = GOLDEN_DIR / f"{doc_id}.json"
    raw = json.loads(path.read_text())
    return Document.model_validate(raw)


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


def _strip_non_roundtripped(obj: Any) -> Any:
    """Strip fields that the serde doesn't round-trip.

    - bullet.textStyle: API-derived from text content, not stored in XML
    - inlineObjectElement.textStyle: not represented in XML format
    - textStyle on \\n-only textRuns: style on trailing newline is not meaningful
    """
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            # Strip bullet.textStyle (API-computed from text styles)
            if k == "bullet" and isinstance(v, dict):
                v = {bk: bv for bk, bv in v.items() if bk != "textStyle"}
                if not v:
                    continue
            # Strip textStyle from inlineObjectElement
            if k == "inlineObjectElement" and isinstance(v, dict):
                v = {ek: ev for ek, ev in v.items() if ek != "textStyle"}
            # Strip textStyle from \n-only textRuns
            if k == "textRun" and isinstance(v, dict) and v.get("content") == "\n":
                v = {tk: tv for tk, tv in v.items() if tk != "textStyle"}
            result[k] = _strip_non_roundtripped(v)
        return result
    if isinstance(obj, list):
        return [_strip_non_roundtripped(item) for item in obj]
    return obj


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


def _build_list_indents(
    lists_raw: dict[str, Any],
) -> dict[tuple[str, int], tuple[str | None, str | None]]:
    """Build (list_id, level) → (indentFirst_xml, indentLeft_xml) from raw lists dict.

    Mirrors _build_list_level_indents in _to_xml.py.
    """
    result: dict[tuple[str, int], tuple[str | None, str | None]] = {}
    for list_id, doc_list in lists_raw.items():
        lp = doc_list.get("listProperties", {})
        nesting_levels = lp.get("nestingLevels", [])
        for idx, nl in enumerate(nesting_levels):
            ifl = nl.get("indentFirstLine") or {}
            ist = nl.get("indentStart") or {}
            mag_first = ifl.get("magnitude")
            mag_left = ist.get("magnitude")
            indent_first = f"{mag_first}pt" if mag_first is not None else None
            indent_left = f"{mag_left}pt" if mag_left is not None else None
            result[(list_id, idx)] = (indent_first, indent_left)
    return result


def _strip_para_style_dict(
    ps_dict: dict[str, Any],
    para_defs: dict[str, str],
) -> dict[str, Any]:
    """Strip named-style defaults from a paragraphStyle dict.

    Validates through ParagraphStyle, applies extract_para_style with defaults,
    then rebuilds via resolve_para_style — the same path serde uses.
    """
    from extradoc.api_types._generated import (
        ParagraphStyle,
        ParagraphStyleNamedStyleType,
    )
    from extradoc.serde._styles import extract_para_style, resolve_para_style

    nst_val = ps_dict.get("namedStyleType")
    heading_id = ps_dict.get("headingId")

    ps = ParagraphStyle.model_validate(ps_dict)
    clean_attrs = extract_para_style(ps, defaults=para_defs)

    nst = ParagraphStyleNamedStyleType(nst_val) if nst_val else None
    clean_ps = resolve_para_style(clean_attrs, named_style_type=nst)
    result = clean_ps.model_dump(by_alias=True, exclude_none=True)

    if heading_id:
        result["headingId"] = heading_id
    return result


def _strip_text_style_dict(
    ts_dict: dict[str, Any],
    text_defs: dict[str, str],
) -> dict[str, Any]:
    """Strip named-style defaults from a textStyle dict."""
    from extradoc.api_types._generated import TextStyle
    from extradoc.serde._styles import extract_text_style, resolve_text_style

    ts = TextStyle.model_validate(ts_dict)
    clean_attrs = extract_text_style(ts, defaults=text_defs)
    clean_ts = resolve_text_style(clean_attrs)
    return clean_ts.model_dump(by_alias=True, exclude_none=True)


def _strip_ns_from_content(
    content: list[Any],
    ns_defaults: Any,
    list_indents: dict[tuple[str, int], tuple[str | None, str | None]],
) -> list[Any]:
    """Recursively strip named-style defaults from content elements."""
    result = []
    for item in content:
        if not isinstance(item, dict):
            result.append(item)
            continue

        if "paragraph" in item:
            item = dict(item)
            para = dict(item["paragraph"])
            ps_dict = para.get("paragraphStyle") or {}
            nst = (
                ps_dict.get("namedStyleType", "NORMAL_TEXT")
                if ps_dict
                else "NORMAL_TEXT"
            )

            para_defs = dict(ns_defaults.para_defaults(nst))
            text_defs = ns_defaults.text_defaults(nst)

            # For list items, augment para_defs with listlevel indents
            bullet = para.get("bullet") or {}
            if bullet:
                list_id = bullet.get("listId")
                level = bullet.get("nestingLevel", 0)
                if list_id is not None:
                    ll_first, ll_left = list_indents.get((list_id, level), (None, None))
                    if ll_first is not None:
                        para_defs["indentFirst"] = ll_first
                    if ll_left is not None:
                        para_defs["indentLeft"] = ll_left

            if ps_dict:
                para["paragraphStyle"] = _strip_para_style_dict(ps_dict, para_defs)

            # Strip text defaults from textRun elements
            elements = para.get("elements") or []
            new_elements = []
            for elem in elements:
                elem = dict(elem)
                if "textRun" in elem:
                    tr = dict(elem["textRun"])
                    ts_dict = tr.get("textStyle") or {}
                    if ts_dict and text_defs:
                        cleaned = _strip_text_style_dict(ts_dict, text_defs)
                        tr["textStyle"] = cleaned
                        elem["textRun"] = tr
                new_elements.append(elem)
            para["elements"] = new_elements
            item["paragraph"] = para

        elif "table" in item:
            item = dict(item)
            table = dict(item["table"])

            # Recurse into table cells
            rows = table.get("tableRows") or []
            new_rows = []
            for row in rows:
                row = dict(row)
                cells = row.get("tableCells") or []
                new_cells = []
                for cell in cells:
                    cell = dict(cell)
                    cell["content"] = _strip_ns_from_content(
                        cell.get("content") or [], ns_defaults, list_indents
                    )
                    new_cells.append(cell)
                row["tableCells"] = new_cells
                new_rows.append(row)
            table["tableRows"] = new_rows

            # Strip widthType=FIXED_WIDTH from column properties
            table_style = table.get("tableStyle") or {}
            col_props = table_style.get("tableColumnProperties") or []
            if col_props:
                new_cols = []
                for col in col_props:
                    col = dict(col)
                    if col.get("widthType") == "FIXED_WIDTH":
                        del col["widthType"]
                    new_cols.append(col)
                table["tableStyle"] = dict(table_style)
                table["tableStyle"]["tableColumnProperties"] = new_cols

            item["table"] = table

        result.append(item)
    return result


def _strip_ns_defaults_from_doc(d: dict[str, Any]) -> dict[str, Any]:
    """Strip named-style defaults from a document dict (after model_dump).

    Mirrors what serde does: suppresses para/text style fields that match
    the named-style default for that paragraph's named style type, augments
    para defaults with listlevel indents for list items, and strips
    widthType=FIXED_WIDTH from column properties.

    Both sides of the comparison go through this step so any systematic
    bias cancels out.
    """
    from extradoc.api_types._generated import NamedStyles
    from extradoc.serde._styles import NamedStyleDefaults

    d = dict(d)
    new_tabs = []
    for tab in d.get("tabs") or []:
        tab = dict(tab)
        doc_tab = dict(tab.get("documentTab") or {})

        # Build named-style defaults for this tab
        named_styles_raw = doc_tab.get("namedStyles")
        ns_obj = (
            NamedStyles.model_validate(named_styles_raw) if named_styles_raw else None
        )
        ns_defaults = NamedStyleDefaults(ns_obj)

        # Build listlevel indents for this tab
        list_indents = _build_list_indents(doc_tab.get("lists") or {})

        # Strip from body, headers, footers, footnotes
        for section_key in ("body",):
            section = doc_tab.get(section_key)
            if section:
                section = dict(section)
                section["content"] = _strip_ns_from_content(
                    section.get("content") or [], ns_defaults, list_indents
                )
                doc_tab[section_key] = section

        for container_key in ("headers", "footers", "footnotes"):
            container = doc_tab.get(container_key) or {}
            if container:
                new_container = {}
                for k, v in container.items():
                    v = dict(v)
                    v["content"] = _strip_ns_from_content(
                        v.get("content") or [], ns_defaults, list_indents
                    )
                    new_container[k] = v
                doc_tab[container_key] = new_container

        tab["documentTab"] = doc_tab
        new_tabs.append(tab)
    d["tabs"] = new_tabs
    return d


def _normalize_doc(doc: Document) -> dict[str, Any]:
    """Convert Document to a normalized dict for comparison."""
    d = doc.model_dump(by_alias=True, exclude_none=True)
    d.pop("suggestionsViewMode", None)
    d = _strip_ns_defaults_from_doc(d)
    d = _normalize(d)
    d = _normalize_elements(d)
    d = _strip_non_roundtripped(d)
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
    """Test round-trip fidelity using real Google Docs API responses."""

    @pytest.mark.parametrize("doc_id", GOLDEN_DOCS)
    def test_document_to_xml_to_document(self, tmp_path: Path, doc_id: str) -> None:
        """Document → XML folder → Document produces equivalent Document."""
        original_doc = _load_golden_doc(doc_id)

        # Step 1: Document → XML folder (serialize to disk)
        output_dir = tmp_path / "doc"
        bundle = DocumentWithComments(
            document=original_doc, comments=FileComments(file_id="")
        )
        _xml_serde.serialize(bundle, output_dir)

        # Step 2: XML folder → Document (deserialize from disk)
        roundtrip_bundle = _xml_serde._parse(output_dir)
        roundtrip_doc = roundtrip_bundle.document

        # Step 3: Compare
        original_norm = _normalize_doc(original_doc)
        roundtrip_norm = _normalize_doc(roundtrip_doc)

        diffs = _collect_diffs(original_norm, roundtrip_norm)

        if diffs:
            print(f"\n{'=' * 60}")
            print(f"Found {len(diffs)} differences for {doc_id}:")
            print(f"{'=' * 60}")
            for i, diff in enumerate(diffs[:50], 1):
                print(f"  {i}. {diff}")
            if len(diffs) > 50:
                print(f"  ... and {len(diffs) - 50} more")
            print(f"{'=' * 60}\n")

        assert diffs == [], f"Round-trip produced {len(diffs)} differences"

    @pytest.mark.parametrize("doc_id", GOLDEN_DOCS)
    def test_in_memory_roundtrip(self, doc_id: str) -> None:
        """Document → XML models → Document (no file I/O)."""
        original_doc = _load_golden_doc(doc_id)

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
            print(f"Found {len(diffs)} differences for {doc_id}:")
            print(f"{'=' * 60}")
            for i, diff in enumerate(diffs[:50], 1):
                print(f"  {i}. {diff}")
            if len(diffs) > 50:
                print(f"  ... and {len(diffs) - 50} more")
            print(f"{'=' * 60}\n")

        assert diffs == [], f"Round-trip produced {len(diffs)} differences"
