"""SML Diff Engine.

Compares two SML documents (original and edited) and produces a list of changes.

Spec reference: sml-reconciliation-spec.md#diff-detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from extraslide.parser import (
    ParsedAutoText,
    ParsedElement,
    ParsedParagraph,
    ParsedPresentation,
    ParsedSlide,
    ParsedTableCell,
    ParsedTableRow,
    ParsedTextRun,
)


class ChangeType(Enum):
    """Types of changes detected during diff.

    Spec: sml-reconciliation-spec.md#change-types
    """

    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    MOVED = "moved"
    UNCHANGED = "unchanged"


@dataclass
class TextChange:
    """Change to text content within an element.

    Spec: sml-reconciliation-spec.md#text-operations
    """

    change_type: ChangeType
    # For existing text runs, the original range
    range_start: int | None = None
    range_end: int | None = None
    # The content
    original_content: str | None = None
    new_content: str | None = None
    # Style classes
    original_classes: list[str] = field(default_factory=list)
    new_classes: list[str] = field(default_factory=list)
    # href
    original_href: str | None = None
    new_href: str | None = None
    # For insertions, position relative to preceding runs
    insert_after_index: int | None = None


@dataclass
class ParagraphChange:
    """Change to a paragraph.

    Spec: sml-reconciliation-spec.md#text-operations
    """

    change_type: ChangeType
    range_start: int | None = None
    range_end: int | None = None
    original_classes: list[str] = field(default_factory=list)
    new_classes: list[str] = field(default_factory=list)
    # Text run changes within this paragraph
    text_changes: list[TextChange] = field(default_factory=list)


@dataclass
class ElementChange:
    """Change to a page element.

    Spec: sml-reconciliation-spec.md#change-types
    """

    change_type: ChangeType
    element_id: str
    element_tag: str
    # For modified elements
    original_classes: list[str] = field(default_factory=list)
    new_classes: list[str] = field(default_factory=list)
    # Attribute changes
    original_attrs: dict[str, str] = field(default_factory=dict)
    new_attrs: dict[str, str] = field(default_factory=dict)
    # Text content changes
    paragraph_changes: list[ParagraphChange] = field(default_factory=list)
    # For new elements, the full element
    new_element: ParsedElement | None = None
    # For duplication
    duplicate_of: str | None = None
    # Position info for moved elements
    original_index: int | None = None
    new_index: int | None = None


@dataclass
class SlideChange:
    """Change to a slide.

    Spec: sml-reconciliation-spec.md#slide-operations
    """

    change_type: ChangeType
    slide_id: str
    # For modified slides
    original_classes: list[str] = field(default_factory=list)
    new_classes: list[str] = field(default_factory=list)
    # Element changes within this slide
    element_changes: list[ElementChange] = field(default_factory=list)
    # For new slides
    layout: str | None = None
    # Position info
    original_index: int | None = None
    new_index: int | None = None


@dataclass
class DiffResult:
    """Result of diffing two SML documents.

    Contains all detected changes organized for request generation.
    """

    # Presentation-level changes
    presentation_classes_changed: bool = False
    original_presentation_classes: list[str] = field(default_factory=list)
    new_presentation_classes: list[str] = field(default_factory=list)

    # Slide changes
    slide_changes: list[SlideChange] = field(default_factory=list)

    # Slide ordering changes (separate for clarity)
    slides_reordered: bool = False
    slide_order: list[str] = field(default_factory=list)  # New order of slide IDs


# ============================================================================
# Diff Engine
# ============================================================================


class SMLDiffEngine:
    """Engine for comparing two SML documents."""

    def diff(
        self, original: ParsedPresentation, edited: ParsedPresentation
    ) -> DiffResult:
        """Compare original and edited presentations.

        Args:
            original: The original parsed SML (from API).
            edited: The edited parsed SML (by user).

        Returns:
            DiffResult containing all detected changes.

        Spec: sml-reconciliation-spec.md#diff-detection
        """
        result = DiffResult()

        # Compare presentation-level classes
        if original.slides and edited.slides:
            # Presentation classes are on the Presentation element, but for now
            # we don't have a place for them. This could be added later.
            pass

        # Diff slides
        result.slide_changes = self._diff_slides(original.slides, edited.slides)

        # Check for slide reordering
        original_ids = [s.id for s in original.slides]
        edited_ids = [s.id for s in edited.slides]

        # Filter to slides that exist in both
        common_ids_original = [sid for sid in original_ids if sid in edited_ids]
        common_ids_edited = [sid for sid in edited_ids if sid in original_ids]

        if common_ids_original != common_ids_edited:
            result.slides_reordered = True
            result.slide_order = edited_ids

        return result

    def _diff_slides(
        self, original_slides: list[ParsedSlide], edited_slides: list[ParsedSlide]
    ) -> list[SlideChange]:
        """Diff slides between original and edited.

        Spec: sml-reconciliation-spec.md#element-matching
        """
        changes: list[SlideChange] = []

        # Build lookup by ID
        original_by_id = {s.id: (i, s) for i, s in enumerate(original_slides)}
        edited_by_id = {s.id: (i, s) for i, s in enumerate(edited_slides)}

        # Find deleted slides
        for slide_id, (idx, _slide) in original_by_id.items():
            if slide_id not in edited_by_id:
                changes.append(
                    SlideChange(
                        change_type=ChangeType.DELETED,
                        slide_id=slide_id,
                        original_index=idx,
                    )
                )

        # Find added and modified slides
        for slide_id, (idx, edited_slide) in edited_by_id.items():
            if slide_id not in original_by_id:
                # New slide
                changes.append(
                    SlideChange(
                        change_type=ChangeType.ADDED,
                        slide_id=slide_id,
                        new_index=idx,
                        new_classes=edited_slide.classes,
                        layout=edited_slide.layout,
                        element_changes=self._elements_to_add(edited_slide.elements),
                    )
                )
            else:
                # Potentially modified slide
                orig_idx, orig_slide = original_by_id[slide_id]
                slide_change = self._diff_slide(orig_slide, edited_slide, orig_idx, idx)
                if slide_change:
                    changes.append(slide_change)

        return changes

    def _diff_slide(
        self,
        original: ParsedSlide,
        edited: ParsedSlide,
        original_idx: int,
        edited_idx: int,
    ) -> SlideChange | None:
        """Diff a single slide.

        Returns None if unchanged.
        """
        element_changes = self._diff_elements(original.elements, edited.elements)
        classes_changed = set(original.classes) != set(edited.classes)

        if not element_changes and not classes_changed:
            return None

        return SlideChange(
            change_type=ChangeType.MODIFIED,
            slide_id=original.id,
            original_classes=original.classes,
            new_classes=edited.classes,
            element_changes=element_changes,
            original_index=original_idx,
            new_index=edited_idx,
        )

    def _diff_elements(
        self,
        original_elements: list[ParsedElement],
        edited_elements: list[ParsedElement],
    ) -> list[ElementChange]:
        """Diff page elements within a slide.

        Spec: sml-reconciliation-spec.md#element-matching
        """
        changes: list[ElementChange] = []

        # Build lookup by ID
        original_by_id = {e.id: (i, e) for i, e in enumerate(original_elements)}
        edited_by_id = {e.id: (i, e) for i, e in enumerate(edited_elements)}

        # Find deleted elements
        for elem_id, (idx, elem) in original_by_id.items():
            if elem_id not in edited_by_id:
                changes.append(
                    ElementChange(
                        change_type=ChangeType.DELETED,
                        element_id=elem_id,
                        element_tag=elem.tag,
                        original_index=idx,
                    )
                )

        # Find added and modified elements
        for elem_id, (idx, edited_elem) in edited_by_id.items():
            # Check for duplicate-of attribute
            duplicate_of = edited_elem.attrs.get("duplicate-of")

            if elem_id not in original_by_id:
                # New element
                changes.append(
                    ElementChange(
                        change_type=ChangeType.ADDED,
                        element_id=elem_id,
                        element_tag=edited_elem.tag,
                        new_classes=edited_elem.classes,
                        new_attrs=edited_elem.attrs,
                        new_element=edited_elem,
                        duplicate_of=duplicate_of,
                        new_index=idx,
                    )
                )
            else:
                # Potentially modified element
                orig_idx, orig_elem = original_by_id[elem_id]
                elem_change = self._diff_element(orig_elem, edited_elem, orig_idx, idx)
                if elem_change:
                    changes.append(elem_change)

        return changes

    def _elements_to_add(self, elements: list[ParsedElement]) -> list[ElementChange]:
        """Convert elements to add changes (for new slides)."""
        return [
            ElementChange(
                change_type=ChangeType.ADDED,
                element_id=elem.id,
                element_tag=elem.tag,
                new_classes=elem.classes,
                new_attrs=elem.attrs,
                new_element=elem,
                duplicate_of=elem.attrs.get("duplicate-of"),
                new_index=idx,
            )
            for idx, elem in enumerate(elements)
        ]

    def _diff_element(
        self,
        original: ParsedElement,
        edited: ParsedElement,
        original_idx: int,
        edited_idx: int,
    ) -> ElementChange | None:
        """Diff a single element.

        Returns None if unchanged.

        Spec: sml-reconciliation-spec.md#attribute-diffing
        """
        # Check tag change (not allowed - would need delete + create)
        if original.tag != edited.tag:
            # This is a significant change - treat as delete + add
            return ElementChange(
                change_type=ChangeType.MODIFIED,
                element_id=original.id,
                element_tag=original.tag,
                original_classes=original.classes,
                new_classes=edited.classes,
                original_attrs=original.attrs,
                new_attrs=edited.attrs,
                original_index=original_idx,
                new_index=edited_idx,
            )

        # Check classes
        classes_changed = set(original.classes) != set(edited.classes)

        # Check attributes (excluding class which is handled separately)
        attrs_changed = self._attrs_differ(original.attrs, edited.attrs)

        # Check text content
        paragraph_changes = self._diff_paragraphs(
            original.paragraphs, edited.paragraphs, original.id
        )

        # Check table content
        if original.table_rows or edited.table_rows:
            table_changes = self._diff_table_rows(
                original.table_rows, edited.table_rows
            )
            # Table changes would be handled separately
            if table_changes:
                classes_changed = True  # Mark as changed

        # Check group children
        if original.children or edited.children:
            child_changes = self._diff_elements(original.children, edited.children)
            if child_changes:
                # Mark element as modified if children changed
                return ElementChange(
                    change_type=ChangeType.MODIFIED,
                    element_id=original.id,
                    element_tag=original.tag,
                    original_classes=original.classes,
                    new_classes=edited.classes,
                    original_attrs=original.attrs,
                    new_attrs=edited.attrs,
                    paragraph_changes=paragraph_changes,
                    original_index=original_idx,
                    new_index=edited_idx,
                )

        if not classes_changed and not attrs_changed and not paragraph_changes:
            return None

        return ElementChange(
            change_type=ChangeType.MODIFIED,
            element_id=original.id,
            element_tag=original.tag,
            original_classes=original.classes,
            new_classes=edited.classes,
            original_attrs=original.attrs,
            new_attrs=edited.attrs,
            paragraph_changes=paragraph_changes,
            original_index=original_idx,
            new_index=edited_idx,
        )

    def _attrs_differ(self, original: dict[str, str], edited: dict[str, str]) -> bool:
        """Check if attributes differ (excluding some internal ones)."""
        # Keys to ignore in comparison
        ignore_keys = {"duplicate-of"}

        orig_filtered = {k: v for k, v in original.items() if k not in ignore_keys}
        edit_filtered = {k: v for k, v in edited.items() if k not in ignore_keys}

        return orig_filtered != edit_filtered

    def _diff_paragraphs(
        self,
        original: list[ParsedParagraph],
        edited: list[ParsedParagraph],
        _element_id: str,
    ) -> list[ParagraphChange]:
        """Diff paragraphs within an element.

        Spec: sml-reconciliation-spec.md#text-content-diffing
        """
        changes: list[ParagraphChange] = []

        # Match paragraphs by position (order matters per spec)
        max_len = max(len(original), len(edited))

        for i in range(max_len):
            orig_para = original[i] if i < len(original) else None
            edit_para = edited[i] if i < len(edited) else None

            if orig_para is None and edit_para is not None:
                # New paragraph
                changes.append(
                    ParagraphChange(
                        change_type=ChangeType.ADDED,
                        new_classes=edit_para.classes,
                        text_changes=self._runs_to_text_changes(
                            edit_para.runs, ChangeType.ADDED
                        ),
                    )
                )
            elif orig_para is not None and edit_para is None:
                # Deleted paragraph
                changes.append(
                    ParagraphChange(
                        change_type=ChangeType.DELETED,
                        range_start=orig_para.range_start,
                        range_end=orig_para.range_end,
                        original_classes=orig_para.classes,
                    )
                )
            elif orig_para is not None and edit_para is not None:
                # Potentially modified paragraph
                para_change = self._diff_paragraph(orig_para, edit_para)
                if para_change:
                    changes.append(para_change)

        return changes

    def _diff_paragraph(
        self, original: ParsedParagraph, edited: ParsedParagraph
    ) -> ParagraphChange | None:
        """Diff a single paragraph.

        Returns None if unchanged.
        """
        classes_changed = set(original.classes) != set(edited.classes)
        text_changes = self._diff_text_runs(original.runs, edited.runs)

        if not classes_changed and not text_changes:
            return None

        return ParagraphChange(
            change_type=ChangeType.MODIFIED,
            range_start=original.range_start,
            range_end=original.range_end,
            original_classes=original.classes,
            new_classes=edited.classes,
            text_changes=text_changes,
        )

    def _diff_text_runs(
        self,
        original: list[ParsedTextRun | ParsedAutoText],
        edited: list[ParsedTextRun | ParsedAutoText],
    ) -> list[TextChange]:
        """Diff text runs within a paragraph.

        Spec: sml-reconciliation-spec.md#text-content-diffing
        """
        changes: list[TextChange] = []

        # Match text runs by position (order matters per spec)
        max_len = max(len(original), len(edited))

        for i in range(max_len):
            orig_run = original[i] if i < len(original) else None
            edit_run = edited[i] if i < len(edited) else None

            if orig_run is None and edit_run is not None:
                # New text run
                if isinstance(edit_run, ParsedTextRun):
                    changes.append(
                        TextChange(
                            change_type=ChangeType.ADDED,
                            new_content=edit_run.content,
                            new_classes=edit_run.classes,
                            new_href=edit_run.href,
                            insert_after_index=i - 1 if i > 0 else None,
                        )
                    )
            elif orig_run is not None and edit_run is None:
                # Deleted text run
                if isinstance(orig_run, ParsedTextRun):
                    changes.append(
                        TextChange(
                            change_type=ChangeType.DELETED,
                            range_start=orig_run.range_start,
                            range_end=orig_run.range_end,
                            original_content=orig_run.content,
                            original_classes=orig_run.classes,
                        )
                    )
            elif orig_run is not None and edit_run is not None:
                # Potentially modified run
                run_change = self._diff_text_run(orig_run, edit_run)
                if run_change:
                    changes.append(run_change)

        return changes

    def _diff_text_run(
        self,
        original: ParsedTextRun | ParsedAutoText,
        edited: ParsedTextRun | ParsedAutoText,
    ) -> TextChange | None:
        """Diff a single text run.

        Returns None if unchanged.
        """
        # Handle AutoText
        if isinstance(original, ParsedAutoText) and isinstance(edited, ParsedAutoText):
            if original.type != edited.type:
                return TextChange(
                    change_type=ChangeType.MODIFIED,
                    range_start=original.range_start,
                    range_end=original.range_end,
                )
            return None

        # If types differ (one is ParsedTextRun, other is ParsedAutoText), it's a change
        if isinstance(original, ParsedTextRun) and not isinstance(
            edited, ParsedTextRun
        ):
            return TextChange(
                change_type=ChangeType.MODIFIED,
                range_start=original.range_start,
                range_end=original.range_end,
                original_content=original.content,
                original_classes=original.classes,
            )
        if not isinstance(original, ParsedTextRun) and isinstance(
            edited, ParsedTextRun
        ):
            return TextChange(change_type=ChangeType.MODIFIED)

        # Both are the same type - if both are AutoText, we handled that above
        # So both must be ParsedTextRun at this point
        if not isinstance(original, ParsedTextRun) or not isinstance(
            edited, ParsedTextRun
        ):
            return None  # Both are AutoText, already handled

        orig = original
        edit = edited

        content_changed = orig.content != edit.content
        classes_changed = set(orig.classes) != set(edit.classes)
        href_changed = orig.href != edit.href

        if not content_changed and not classes_changed and not href_changed:
            return None

        return TextChange(
            change_type=ChangeType.MODIFIED,
            range_start=orig.range_start,
            range_end=orig.range_end,
            original_content=orig.content,
            new_content=edit.content,
            original_classes=orig.classes,
            new_classes=edit.classes,
            original_href=orig.href,
            new_href=edit.href,
        )

    def _runs_to_text_changes(
        self,
        runs: list[ParsedTextRun | ParsedAutoText],
        change_type: ChangeType,
    ) -> list[TextChange]:
        """Convert runs to text changes (for new paragraphs)."""
        changes: list[TextChange] = []
        for i, run in enumerate(runs):
            if isinstance(run, ParsedTextRun):
                changes.append(
                    TextChange(
                        change_type=change_type,
                        new_content=run.content,
                        new_classes=run.classes,
                        new_href=run.href,
                        insert_after_index=i - 1 if i > 0 else None,
                    )
                )
        return changes

    def _diff_table_rows(
        self, original: list[ParsedTableRow], edited: list[ParsedTableRow]
    ) -> list[Any]:
        """Diff table rows.

        Returns list of row changes (simplified for now).
        """
        # Simple implementation - compare row counts and cell contents
        changes: list[Any] = []

        orig_by_idx = {r.row_index: r for r in original}
        edit_by_idx = {r.row_index: r for r in edited}

        # Deleted rows
        for idx in orig_by_idx:
            if idx not in edit_by_idx:
                changes.append({"type": "delete_row", "index": idx})

        # Added rows
        for idx in edit_by_idx:
            if idx not in orig_by_idx:
                changes.append({"type": "add_row", "index": idx})

        # Modified rows (compare cells)
        for idx in orig_by_idx:
            if idx in edit_by_idx:
                cell_changes = self._diff_table_cells(
                    orig_by_idx[idx].cells, edit_by_idx[idx].cells
                )
                if cell_changes:
                    changes.append(
                        {"type": "modify_row", "index": idx, "cells": cell_changes}
                    )

        return changes

    def _diff_table_cells(
        self, original: list[ParsedTableCell], edited: list[ParsedTableCell]
    ) -> list[Any]:
        """Diff table cells."""
        changes: list[Any] = []

        # Build lookup by (row, col)
        orig_by_pos = {(c.row, c.col): c for c in original}
        edit_by_pos = {(c.row, c.col): c for c in edited}

        for pos, edit_cell in edit_by_pos.items():
            orig_cell = orig_by_pos.get(pos)
            if orig_cell is None:
                changes.append({"type": "add_cell", "pos": pos})
            else:
                # Check for changes
                if set(orig_cell.classes) != set(edit_cell.classes):
                    changes.append(
                        {"type": "modify_cell", "pos": pos, "classes_changed": True}
                    )
                if (
                    orig_cell.colspan != edit_cell.colspan
                    or orig_cell.rowspan != edit_cell.rowspan
                ):
                    changes.append(
                        {"type": "modify_cell", "pos": pos, "span_changed": True}
                    )

        return changes


# ============================================================================
# Public API
# ============================================================================


def diff_sml(original: ParsedPresentation, edited: ParsedPresentation) -> DiffResult:
    """Compare two parsed SML presentations.

    Args:
        original: The original parsed SML (from API).
        edited: The edited parsed SML (by user).

    Returns:
        DiffResult containing all detected changes.
    """
    engine = SMLDiffEngine()
    return engine.diff(original, edited)
