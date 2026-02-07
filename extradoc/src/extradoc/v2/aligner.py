"""Block alignment for ExtraDoc v2.

Two-pass alignment algorithm:
1. Exact content match (hash-based, first-match-wins)
2. Structural key match (tag-based, positional within groups)

Interleaving ensures current-document order is preserved.
"""

from __future__ import annotations

from collections import defaultdict

from .types import AlignedPair, StructuralBlock, TableRowBlock


class BlockAligner:
    """Aligns blocks from pristine and current lists for comparison."""

    def align(
        self,
        pristine: list[StructuralBlock],
        current: list[StructuralBlock],
    ) -> list[AlignedPair]:
        """Align two lists of structural blocks.

        Returns a list of AlignedPair where:
        - (i, None) means pristine[i] was deleted
        - (None, j) means current[j] was added
        - (i, j) means pristine[i] matches current[j]

        Uses a two-pass approach:
        1. Exact content match
        2. Structural key match for remaining unmatched blocks

        Results are interleaved to respect current document order.
        """
        matched_pristine: set[int] = set()
        matched_current: set[int] = set()
        alignment: list[tuple[int | None, int | None]] = []

        # --- Pass 1: Exact content matches ---
        pristine_by_content: dict[str, list[int]] = {}
        for i, block in enumerate(pristine):
            content = block.content_hash()
            if content not in pristine_by_content:
                pristine_by_content[content] = []
            pristine_by_content[content].append(i)

        for j, block in enumerate(current):
            content = block.content_hash()
            candidates = pristine_by_content.get(content, [])
            for i in candidates:
                if i not in matched_pristine:
                    alignment.append((i, j))
                    matched_pristine.add(i)
                    matched_current.add(j)
                    break

        # --- Pass 2: Structural key match ---
        unmatched_p = [
            (i, pristine[i]) for i in range(len(pristine)) if i not in matched_pristine
        ]
        unmatched_c = [
            (j, current[j]) for j in range(len(current)) if j not in matched_current
        ]

        pristine_by_key: dict[str, list[int]] = {}
        for i, block in unmatched_p:
            key = block.structural_key()
            if key not in pristine_by_key:
                pristine_by_key[key] = []
            pristine_by_key[key].append(i)

        for j, block in unmatched_c:
            key = block.structural_key()
            candidates = pristine_by_key.get(key, [])
            if candidates:
                i = candidates.pop(0)
                alignment.append((i, j))
                matched_pristine.add(i)
                matched_current.add(j)

        # --- Interleave into current document order ---
        return self._interleave(
            alignment, pristine, current, matched_pristine, matched_current
        )

    def _interleave(
        self,
        alignment: list[tuple[int | None, int | None]],
        pristine: list[StructuralBlock],
        current: list[StructuralBlock],
        matched_pristine: set[int],
        matched_current: set[int],
    ) -> list[AlignedPair]:
        """Interleave matches, additions, and deletions in document order."""
        # Build lookup: current_idx -> pristine_idx for matched pairs
        c_to_p: dict[int, int] = {}
        for p_idx, c_idx in alignment:
            if p_idx is not None and c_idx is not None:
                c_to_p[c_idx] = p_idx

        # Unmatched additions and deletions
        added_c = {j for j in range(len(current)) if j not in matched_current}
        deleted_p = sorted(i for i in range(len(pristine)) if i not in matched_pristine)

        # Walk current document order, interleaving deletions
        result: list[AlignedPair] = []
        del_ptr = 0
        last_matched_p = -1

        for c_idx in range(len(current)):
            if c_idx in c_to_p:
                p_idx = c_to_p[c_idx]
                # Flush deletions whose pristine index falls between
                # the previous matched pristine index and this one
                while (
                    del_ptr < len(deleted_p)
                    and deleted_p[del_ptr] > last_matched_p
                    and deleted_p[del_ptr] < p_idx
                ):
                    result.append(AlignedPair(deleted_p[del_ptr], None))
                    del_ptr += 1
                result.append(AlignedPair(p_idx, c_idx))
                last_matched_p = max(last_matched_p, p_idx)
            elif c_idx in added_c:
                result.append(AlignedPair(None, c_idx))

        # Flush remaining deletions
        while del_ptr < len(deleted_p):
            result.append(AlignedPair(deleted_p[del_ptr], None))
            del_ptr += 1

        return result

    def align_table_rows(
        self,
        pristine_rows: list[TableRowBlock],
        current_rows: list[TableRowBlock],
    ) -> list[AlignedPair]:
        """Align table rows using ID-based matching.

        Matches rows by block_id with positional fallback for duplicate IDs.
        """
        p_id_to_indices: dict[str, list[int]] = defaultdict(list)
        for i, row in enumerate(pristine_rows):
            p_id_to_indices[row.row_id].append(i)

        p_id_consumed: dict[str, int] = defaultdict(int)
        matched_p: set[int] = set()
        alignment: list[AlignedPair] = []

        for c_i, c_row in enumerate(current_rows):
            bid = c_row.row_id
            slot = p_id_consumed[bid]
            p_slots = p_id_to_indices.get(bid, [])
            if slot < len(p_slots):
                p_i = p_slots[slot]
                alignment.append(AlignedPair(p_i, c_i))
                matched_p.add(p_i)
                p_id_consumed[bid] = slot + 1
            else:
                alignment.append(AlignedPair(None, c_i))

        # Pristine rows not matched are deleted
        for p_i in range(len(pristine_rows)):
            if p_i not in matched_p:
                alignment.append(AlignedPair(p_i, None))

        return alignment
