"""Normalize and compare Document dicts for verify()."""

from __future__ import annotations

import copy
from typing import Any

# Keys that are server-generated and should be ignored during comparison
_IGNORE_KEYS = frozenset(
    {
        "revisionId",
        "documentId",
        "suggestionsViewMode",
        "headingId",
        "listId",  # bullet list ID is server-generated (random kix.xxx string)
        "namedRangeId",  # named range ID is server-generated
        "nestingLevel",  # bullet nesting level — mock omits it; serde emits 0
        "documentStyle",
        "namedStyles",
        "suggestedDocumentStyleChanges",
        "suggestedNamedStylesChanges",
        "inlineObjects",
        "positionedObjects",
        "lists",
    }
)

# Paragraph style fields managed by the bullet list level.
# createParagraphBullets always sets these to match the level-0 defaults.
# The serde suppresses them (they duplicate the list-level definition), so
# they appear in actual but not in desired.  Strip them when comparing
# bullet paragraphs so they don't produce spurious diffs.
_BULLET_PARA_STYLE_STRIP = frozenset({"indentFirstLine", "indentStart"})

# Keys within textStyle/paragraphStyle that are commonly server-defaulted
_STYLE_IGNORE_KEYS = frozenset(
    {
        "suggestedTextStyleChanges",
        "suggestedParagraphStyleChanges",
        "suggestedBulletChanges",
        "suggestedDeletionIds",
        "suggestedInsertionIds",
        "suggestedPositionedObjectIds",
        "suggestedTableCellStyleChanges",
        "suggestedTableRowStyleChanges",
    }
)


def _strip_keys(obj: Any, keys_to_strip: frozenset[str]) -> Any:
    """Recursively strip specified keys from a dict/list structure."""
    if isinstance(obj, dict):
        return {
            k: _strip_keys(v, keys_to_strip)
            for k, v in obj.items()
            if k not in keys_to_strip
        }
    if isinstance(obj, list):
        return [_strip_keys(item, keys_to_strip) for item in obj]
    return obj


def _strip_implicit_link_styles(text_style: dict[str, Any]) -> dict[str, Any]:
    """Strip foregroundColor and underline from link text styles.

    The real API (and mock) automatically applies blue foreground color and
    underline decoration when a link is set on a text run.  The deserialized
    desired document only stores the explicit ``link`` object.  Strip the
    implicit visual decorations so verify() doesn't report spurious diffs.
    """
    if "link" not in text_style:
        return text_style
    return {k: v for k, v in text_style.items() if k not in ("foregroundColor", "underline")}


def _normalize_text_styles(obj: Any) -> Any:
    """Remove empty textStyle dicts and normalize style representations."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            normalized = _normalize_text_styles(v)
            # Remove empty textStyle/paragraphStyle dicts
            if (
                k in ("textStyle", "paragraphStyle", "tableCellStyle")
                and normalized == {}
            ):
                continue
            if k == "textStyle" and isinstance(normalized, dict):
                normalized = _strip_implicit_link_styles(normalized)
                if not normalized:
                    continue
            result[k] = normalized
        return result
    if isinstance(obj, list):
        return [_normalize_text_styles(item) for item in obj]
    return obj


def _strip_table_metadata(obj: Any) -> Any:
    """Strip mock-generated table metadata for comparison.

    Tables created by the mock's insertTable have extra fields
    (tableCellStyle, tableRowStyle, tableStyle, paragraphStyle on cell
    paragraphs, startIndex/endIndex on rows/cells) that test-helper-built
    desired documents don't include. We strip these to focus comparison
    on text content and structure.
    """
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "tableRows":
                result[k] = _strip_table_rows(v)
            elif k == "tableStyle":
                continue
            else:
                result[k] = _strip_table_metadata(v)
        return result
    if isinstance(obj, list):
        return [_strip_table_metadata(item) for item in obj]
    return obj


def _strip_table_rows(rows: Any) -> Any:
    if not isinstance(rows, list):
        return rows
    result = []
    for row in rows:
        if isinstance(row, dict):
            new_row: dict[str, Any] = {}
            for k, v in row.items():
                if k in ("startIndex", "endIndex", "tableRowStyle"):
                    continue
                if k == "tableCells":
                    new_row[k] = _strip_table_cells(v)
                else:
                    new_row[k] = _strip_table_metadata(v)
            result.append(new_row)
        else:
            result.append(row)
    return result


def _strip_table_cells(cells: Any) -> Any:
    if not isinstance(cells, list):
        return cells
    result = []
    for cell in cells:
        if isinstance(cell, dict):
            new_cell: dict[str, Any] = {}
            for k, v in cell.items():
                if k in ("startIndex", "endIndex", "tableCellStyle"):
                    continue
                if k == "content":
                    new_cell[k] = _strip_cell_para_styles(v)
                else:
                    new_cell[k] = _strip_table_metadata(v)
            result.append(new_cell)
        else:
            result.append(cell)
    return result


# Fields in cell paragraph styles that are always structural defaults generated
# by the mock (via insertTable) but never included in test-builder docs.
# These can be safely stripped from both sides when comparing.
_CELL_PARA_STYLE_ALWAYS_STRIP = frozenset(
    {
        "direction",
        "spacingMode",
        "spaceAbove",
        "spaceBelow",
        "borderTop",
        "borderBottom",
        "borderLeft",
        "borderRight",
        "borderBetween",
        "indentFirstLine",
        "indentStart",
        "indentEnd",
        "keepLinesTogether",
        "keepWithNext",
        "avoidWidowAndOrphan",
        "shading",
        "pageBreakBefore",
    }
)

# Cell paragraph style fields with known default values. Strip when value equals
# the default so that both mock-generated defaults and absent fields compare equal.
# Non-default values (e.g. namedStyleType=HEADING_1, alignment=CENTER) are kept.
_CELL_PARA_STYLE_DEFAULT_VALUES: dict[str, Any] = {
    "namedStyleType": "NORMAL_TEXT",
    "alignment": "START",
    "lineSpacing": 100,
}


def _normalize_cell_para_style(para_style: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a table cell paragraph style for comparison.

    Strips structural default fields and fields equal to their default values.
    Returns None if nothing meaningful remains (caller should omit the key).
    """
    filtered = {
        k: v
        for k, v in para_style.items()
        if k not in _CELL_PARA_STYLE_ALWAYS_STRIP
        and _CELL_PARA_STYLE_DEFAULT_VALUES.get(k, object()) != v
    }
    return filtered if filtered else None


def _strip_cell_para_styles(content: Any) -> Any:
    """Normalize table cell content for comparison.

    Strips indices and removes structural-default paragraphStyle fields so that
    mock-generated default styles compare equal to test-builder docs that omit
    them. Meaningful non-default values (e.g. namedStyleType=HEADING_1,
    alignment=CENTER) are preserved so verify() catches real failures.
    """
    if not isinstance(content, list):
        return content
    result = []
    for elem in content:
        if isinstance(elem, dict):
            new_elem = {
                k: v for k, v in elem.items() if k not in ("startIndex", "endIndex")
            }
            if "paragraph" in new_elem:
                new_para = dict(new_elem["paragraph"])
                if "paragraphStyle" in new_para:
                    normalized = _normalize_cell_para_style(new_para["paragraphStyle"])
                    if normalized is None:
                        del new_para["paragraphStyle"]
                    else:
                        new_para["paragraphStyle"] = normalized
                if "elements" in new_para:
                    new_para["elements"] = [
                        {
                            k: v
                            for k, v in pe.items()
                            if k not in ("startIndex", "endIndex")
                        }
                        for pe in new_para["elements"]
                    ]
                new_elem["paragraph"] = new_para
            result.append(_strip_table_metadata(new_elem))
        else:
            result.append(_strip_table_metadata(elem))
    return result


def _strip_bullet_para_indent(obj: Any) -> Any:
    """Strip list-managed indent fields from bullet paragraph styles.

    The serde suppresses indentFirstLine/indentStart on bullet paragraphs
    because they duplicate the list level's own definition.  The mock's
    createParagraphBullets always adds them back.  Strip them from both
    sides so verify() doesn't report spurious diffs for bullet items.
    """
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "paragraph":
                para = dict(v) if isinstance(v, dict) else v
                if (
                    isinstance(para, dict)
                    and "bullet" in para
                    and "paragraphStyle" in para
                ):
                    ps = {
                        pk: pv
                        for pk, pv in para["paragraphStyle"].items()
                        if pk not in _BULLET_PARA_STYLE_STRIP
                    }
                    para = dict(para)
                    if ps:
                        para["paragraphStyle"] = ps
                    else:
                        del para["paragraphStyle"]
                result[k] = _strip_bullet_para_indent(para)
            else:
                result[k] = _strip_bullet_para_indent(v)
        return result
    if isinstance(obj, list):
        return [_strip_bullet_para_indent(item) for item in obj]
    return obj


def _split_trailing_newlines_in_para(elements: list[Any]) -> list[Any]:
    """Split text runs that end with '\\n' into (content, '\\n') pairs.

    The mock's updateTextStyle merges a trailing '\\n' into the styled middle
    run (style_ops.py: "merge trailing \\n into middle if no link").  This
    produces a single run like 'print("hello")\\n' with Courier New, while the
    desired document's deserialization always keeps the paragraph-ending '\\n'
    as a separate un-styled run.  Splitting before comparison lets
    _consolidate_text_runs_in_para then match the two representations.
    """
    result: list[Any] = []
    for elem in elements:
        if not isinstance(elem, dict) or "textRun" not in elem:
            result.append(elem)
            continue
        tr = elem["textRun"]
        content = tr.get("content") or ""
        style = tr.get("textStyle")
        if content.endswith("\n") and len(content) > 1 and style:
            # Split into "text" (with style) and "\n" (no style)
            text_part = content[:-1]
            text_tr: dict[str, Any] = {"content": text_part, "textStyle": style}
            result.append({"textRun": text_tr})
            result.append({"textRun": {"content": "\n"}})
        else:
            result.append(elem)
    return result


def _consolidate_text_runs_in_para(elements: list[Any]) -> list[Any]:
    """Merge adjacent text runs with identical textStyle.

    The Google Docs API and the mock may merge adjacent same-style runs that
    the deserialization code keeps separate (e.g. a trailing '\\n' run vs the
    preceding same-style run).  Consolidating both sides before comparison
    avoids spurious list-length mismatches.
    """
    result: list[Any] = []
    for elem in elements:
        if not isinstance(elem, dict) or "textRun" not in elem:
            result.append(elem)
            continue
        tr = elem["textRun"]
        content = tr.get("content") or ""
        style = tr.get("textStyle")  # None or a dict
        if result and isinstance(result[-1], dict) and "textRun" in result[-1]:
            prev_tr = result[-1]["textRun"]
            prev_style = prev_tr.get("textStyle")
            if prev_style == style:
                # Merge: concatenate content, keep (or omit) shared style
                merged_tr: dict[str, Any] = {"content": (prev_tr.get("content") or "") + content}
                if style is not None:
                    merged_tr["textStyle"] = style
                result[-1] = {"textRun": merged_tr}
                continue
        result.append(elem)
    return result


def _consolidate_text_runs(obj: Any) -> Any:
    """Recursively split trailing-newline runs then consolidate same-style runs."""
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "elements" and isinstance(v, list):
                processed = [_consolidate_text_runs(e) for e in v]
                processed = _split_trailing_newlines_in_para(processed)
                result[k] = _consolidate_text_runs_in_para(processed)
            else:
                result[k] = _consolidate_text_runs(v)
        return result
    if isinstance(obj, list):
        return [_consolidate_text_runs(item) for item in obj]
    return obj


def _strip_para_element_indices(obj: Any) -> Any:
    """Strip startIndex/endIndex from paragraph elements.

    These are recomputed by the mock/API and can differ from the desired
    document's un-indexed representation, causing spurious diff noise.
    Only strip from elements *within* paragraphs (not from structural
    elements themselves, which need their indices for table annotation lookup).
    """
    if isinstance(obj, dict):
        if "paragraph" in obj and isinstance(obj["paragraph"], dict):
            para = dict(obj["paragraph"])
            if "elements" in para and isinstance(para["elements"], list):
                para["elements"] = [
                    {k: v for k, v in e.items() if k not in ("startIndex", "endIndex")}
                    if isinstance(e, dict)
                    else e
                    for e in para["elements"]
                ]
            obj = dict(obj)
            obj["paragraph"] = para
        return {k: _strip_para_element_indices(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_para_element_indices(item) for item in obj]
    return obj


def _is_empty_para_dict(elem: Any) -> bool:
    """Return True if elem is a bare empty paragraph (just '\\n' with no bullet or style)."""
    if not isinstance(elem, dict) or "paragraph" not in elem:
        return False
    p = elem["paragraph"]
    if not isinstance(p, dict):
        return False
    if "bullet" in p:
        return False
    elements = p.get("elements") or []
    if len(elements) != 1:
        return False
    pe = elements[0]
    if not isinstance(pe, dict):
        return False
    tr = pe.get("textRun")
    if not isinstance(tr, dict):
        return False
    # Content must be only whitespace / newline
    if (tr.get("content") or "").strip():
        return False
    ts = tr.get("textStyle") or {}
    return not ts


def _strip_post_table_empty_paras(content: list[Any]) -> list[Any]:
    """Strip bare empty paragraphs that immediately follow a table.

    insertTable displaces the left_anchor's trailing '\\n' to become a
    post-table separator paragraph.  The desired document (from markdown) does
    not model this separator.  Stripping from both sides avoids spurious
    list-length mismatches in verify().
    """
    result: list[Any] = []
    for elem in content:
        if result and isinstance(result[-1], dict) and "table" in result[-1]:
            if _is_empty_para_dict(elem):
                continue  # skip post-table displaced separator
        result.append(elem)
    return result


def _apply_post_table_strip(obj: Any) -> Any:
    """Recursively apply _strip_post_table_empty_paras to body content lists."""
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "content" and isinstance(v, list):
                result[k] = _strip_post_table_empty_paras(
                    [_apply_post_table_strip(e) for e in v]
                )
            else:
                result[k] = _apply_post_table_strip(v)
        return result
    if isinstance(obj, list):
        return [_apply_post_table_strip(item) for item in obj]
    return obj


def _strip_named_range_tab_ids(obj: Any) -> Any:
    """Strip tabId from named range Range objects (server adds it; desired omits it)."""
    if isinstance(obj, dict):
        # Named range range entries: strip tabId
        if "startIndex" in obj and "endIndex" in obj and "tabId" in obj:
            return {k: v for k, v in obj.items() if k != "tabId"}
        return {k: _strip_named_range_tab_ids(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_named_range_tab_ids(item) for item in obj]
    return obj


def normalize_document(doc_dict: dict[str, Any]) -> dict[str, Any]:
    """Normalize a document dict for comparison.

    Strips server-generated fields and normalizes styles.
    """
    result: dict[str, Any] = copy.deepcopy(doc_dict)
    result = _strip_keys(result, _IGNORE_KEYS | _STYLE_IGNORE_KEYS)
    result = _normalize_text_styles(result)
    result = _strip_table_metadata(result)
    result = _strip_bullet_para_indent(result)
    result = _strip_para_element_indices(result)
    result = _consolidate_text_runs(result)
    result = _apply_post_table_strip(result)
    result = _strip_named_range_tab_ids(result)
    return result


def _collect_diffs(
    path: str, actual: Any, expected: Any, diffs: list[str], max_diffs: int = 20
) -> None:
    """Recursively collect differences between two structures."""
    if len(diffs) >= max_diffs:
        return

    if type(actual) is not type(expected):
        diffs.append(
            f"{path}: type mismatch: {type(actual).__name__} vs {type(expected).__name__}"
        )
        return

    if isinstance(actual, dict):
        all_keys = set(actual.keys()) | set(expected.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}"
            if key not in actual:
                diffs.append(f"{child_path}: missing in actual")
            elif key not in expected:
                diffs.append(f"{child_path}: extra in actual")
            else:
                _collect_diffs(child_path, actual[key], expected[key], diffs, max_diffs)
    elif isinstance(actual, list):
        if len(actual) != len(expected):
            diffs.append(
                f"{path}: list length mismatch: {len(actual)} vs {len(expected)}"
            )
        for i in range(min(len(actual), len(expected))):
            _collect_diffs(f"{path}[{i}]", actual[i], expected[i], diffs, max_diffs)
    elif actual != expected:
        diffs.append(f"{path}: {actual!r} != {expected!r}")


def documents_match(
    actual: dict[str, Any], desired: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Compare two normalized document dicts.

    Returns (match, list_of_differences).
    """
    norm_actual = normalize_document(actual)
    norm_desired = normalize_document(desired)

    diffs: list[str] = []
    _collect_diffs("doc", norm_actual, norm_desired, diffs)
    return len(diffs) == 0, diffs
