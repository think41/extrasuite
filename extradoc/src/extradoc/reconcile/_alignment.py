"""LCS-based alignment of StructuralElements between base and desired documents."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, NamedTuple

from extradoc.reconcile._extractors import content_fingerprint

if TYPE_CHECKING:
    from extradoc.api_types._generated import StructuralElement, Tab


class AlignmentOp(Enum):
    MATCHED = "MATCHED"
    DELETED = "DELETED"
    ADDED = "ADDED"


class AlignedElement(NamedTuple):
    """Result of aligning two lists of StructuralElements."""

    op: AlignmentOp
    base_idx: int | None  # index in base list (None for ADDED)
    desired_idx: int | None  # index in desired list (None for DELETED)
    base_element: StructuralElement | None
    desired_element: StructuralElement | None


class TabAlignment(NamedTuple):
    """Result of aligning tabs between base and desired."""

    matched: list[tuple[Tab, Tab]]  # (base_tab, desired_tab)
    deleted: list[Tab]  # tabs in base but not desired
    added: list[Tab]  # tabs in desired but not base


def align_tabs(base_tabs: list[Tab], desired_tabs: list[Tab]) -> TabAlignment:
    """Align tabs by tab_id."""
    base_by_id: dict[str, Tab] = {}
    for t in base_tabs:
        tid = t.tab_properties.tab_id if t.tab_properties else None
        if tid:
            base_by_id[tid] = t

    desired_by_id: dict[str, Tab] = {}
    for t in desired_tabs:
        tid = t.tab_properties.tab_id if t.tab_properties else None
        if tid:
            desired_by_id[tid] = t

    matched = []
    for tid, desired_tab in desired_by_id.items():
        if tid in base_by_id:
            matched.append((base_by_id[tid], desired_tab))

    deleted = [t for tid, t in base_by_id.items() if tid not in desired_by_id]
    added = [t for tid, t in desired_by_id.items() if tid not in base_by_id]

    return TabAlignment(matched=matched, deleted=deleted, added=added)


def _lcs_table(base_fps: list[str], desired_fps: list[str]) -> list[list[int]]:
    """Build LCS length table."""
    m, n = len(base_fps), len(desired_fps)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if base_fps[i - 1] == desired_fps[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp


class AlignedSequenceEntry(NamedTuple):
    """Result of aligning two fingerprint sequences."""

    op: AlignmentOp
    base_idx: int | None
    desired_idx: int | None


def align_sequences(
    base_fps: list[str], desired_fps: list[str]
) -> list[AlignedSequenceEntry]:
    """Align two fingerprint lists using LCS with positional fallback.

    Returns (op, base_idx, desired_idx) tuples in order.

    If LCS produces zero MATCHED entries, falls back to positional alignment:
    pair items by index (0<->0, 1<->1, ...), extras are ADDED or DELETED.
    This guarantees at least min(base_count, desired_count) MATCHED entries.
    """
    dp = _lcs_table(base_fps, desired_fps)

    # Backtrack
    result: list[AlignedSequenceEntry] = []
    i, j = len(base_fps), len(desired_fps)

    while i > 0 or j > 0:
        if i > 0 and j > 0 and base_fps[i - 1] == desired_fps[j - 1]:
            result.append(
                AlignedSequenceEntry(
                    op=AlignmentOp.MATCHED, base_idx=i - 1, desired_idx=j - 1
                )
            )
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            result.append(
                AlignedSequenceEntry(
                    op=AlignmentOp.ADDED, base_idx=None, desired_idx=j - 1
                )
            )
            j -= 1
        else:
            result.append(
                AlignedSequenceEntry(
                    op=AlignmentOp.DELETED, base_idx=i - 1, desired_idx=None
                )
            )
            i -= 1

    result.reverse()

    # Positional fallback: if no MATCHED entries, pair by index
    has_match = any(e.op == AlignmentOp.MATCHED for e in result)
    if not has_match and base_fps and desired_fps:
        result = []
        min_len = min(len(base_fps), len(desired_fps))
        for k in range(min_len):
            result.append(
                AlignedSequenceEntry(op=AlignmentOp.MATCHED, base_idx=k, desired_idx=k)
            )
        for k in range(min_len, len(base_fps)):
            result.append(
                AlignedSequenceEntry(
                    op=AlignmentOp.DELETED, base_idx=k, desired_idx=None
                )
            )
        for k in range(min_len, len(desired_fps)):
            result.append(
                AlignedSequenceEntry(op=AlignmentOp.ADDED, base_idx=None, desired_idx=k)
            )

    return result


def align_structural_elements(
    base_elements: list[StructuralElement],
    desired_elements: list[StructuralElement],
) -> list[AlignedElement]:
    """Align two lists of StructuralElements using LCS on fingerprints.

    Returns a list of AlignedElement indicating matched, deleted, or added elements.
    The order respects the desired document order for additions and base order for deletions.
    """
    base_fps = [content_fingerprint(e) for e in base_elements]
    desired_fps = [content_fingerprint(e) for e in desired_elements]

    dp = _lcs_table(base_fps, desired_fps)

    # Backtrack to find alignment
    result: list[AlignedElement] = []
    i, j = len(base_fps), len(desired_fps)

    while i > 0 or j > 0:
        if i > 0 and j > 0 and base_fps[i - 1] == desired_fps[j - 1]:
            result.append(
                AlignedElement(
                    op=AlignmentOp.MATCHED,
                    base_idx=i - 1,
                    desired_idx=j - 1,
                    base_element=base_elements[i - 1],
                    desired_element=desired_elements[j - 1],
                )
            )
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            result.append(
                AlignedElement(
                    op=AlignmentOp.ADDED,
                    base_idx=None,
                    desired_idx=j - 1,
                    base_element=None,
                    desired_element=desired_elements[j - 1],
                )
            )
            j -= 1
        else:
            result.append(
                AlignedElement(
                    op=AlignmentOp.DELETED,
                    base_idx=i - 1,
                    desired_idx=None,
                    base_element=base_elements[i - 1],
                    desired_element=None,
                )
            )
            i -= 1

    result.reverse()
    return result
