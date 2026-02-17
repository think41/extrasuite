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
        "documentStyle",
        "namedStyles",
        "suggestedDocumentStyleChanges",
        "suggestedNamedStylesChanges",
        "inlineObjects",
        "positionedObjects",
        "lists",
    }
)

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


def _strip_cell_para_styles(content: Any) -> Any:
    """Strip indices and paragraphStyle from table cell content.

    Table cell content indices differ between Full Structure (mock-generated)
    and Minimal Structure (test-helper-built) tables. Strip them so
    comparison focuses on text content.
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
                new_para.pop("paragraphStyle", None)
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


def normalize_document(doc_dict: dict[str, Any]) -> dict[str, Any]:
    """Normalize a document dict for comparison.

    Strips server-generated fields and normalizes styles.
    """
    result: dict[str, Any] = copy.deepcopy(doc_dict)
    result = _strip_keys(result, _IGNORE_KEYS | _STYLE_IGNORE_KEYS)
    result = _normalize_text_styles(result)
    result = _strip_table_metadata(result)
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
