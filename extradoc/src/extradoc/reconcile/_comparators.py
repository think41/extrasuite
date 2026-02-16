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


def normalize_document(doc_dict: dict[str, Any]) -> dict[str, Any]:
    """Normalize a document dict for comparison.

    Strips server-generated fields and normalizes styles.
    """
    result: dict[str, Any] = copy.deepcopy(doc_dict)
    result = _strip_keys(result, _IGNORE_KEYS | _STYLE_IGNORE_KEYS)
    result = _normalize_text_styles(result)
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
