"""
Spreadsheet to file representation transformer.

Converts Google Sheets API responses into the extrasheet file format.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from extrasheet.format_compression import compress_cell_formats
from extrasheet.formula_compression import compress_formulas
from extrasheet.utils import (
    cell_to_a1,
    escape_tsv_value,
    get_effective_value_string,
    grid_range_to_a1,
    is_default_cell_format,
    is_default_dimension,
    sanitize_filename,
)

if TYPE_CHECKING:
    from extrasheet.api_types import (
        GridData,
        NamedRange,
        Sheet,
        Spreadsheet,
    )


class SpreadsheetTransformer:
    """Transforms a Google Sheets API Spreadsheet response into file representations."""

    def __init__(
        self,
        spreadsheet: Spreadsheet,
        *,
        truncation_info: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the transformer with a spreadsheet response.

        Args:
            spreadsheet: Full Spreadsheet object from Google Sheets API
            truncation_info: Optional dict mapping sheetId -> truncation details.
                           Used when rows were limited during fetch.
        """
        self.spreadsheet = spreadsheet
        self.truncation_info = truncation_info or {}
        self._sheet_folders: dict[int, str] = {}  # sheetId -> folder name

    def transform(self) -> dict[str, Any]:
        """Transform the spreadsheet into file representations.

        Returns:
            Dictionary with file paths as keys and content as values.
            Content is either a string (for TSV) or a dict (for JSON).
        """
        result: dict[str, Any] = {}

        # Get spreadsheet ID for root folder
        spreadsheet_id = self.spreadsheet.get("spreadsheetId", "unknown")

        # Compute sheet folder names (handle duplicates)
        self._compute_sheet_folders()

        # Extract sheet previews (needed for spreadsheet.json)
        sheet_previews = self._extract_all_sheet_previews()

        # Transform spreadsheet-level files
        result[f"{spreadsheet_id}/spreadsheet.json"] = (
            self._transform_spreadsheet_metadata(sheet_previews)
        )

        # Theme file (defaultFormat and spreadsheetTheme)
        theme = self._extract_theme()
        if theme:
            result[f"{spreadsheet_id}/theme.json"] = theme

        # Named ranges (if any)
        named_ranges = self.spreadsheet.get("namedRanges", [])
        if named_ranges:
            result[f"{spreadsheet_id}/named_ranges.json"] = (
                self._transform_named_ranges(named_ranges)
            )

        # Developer metadata (if any)
        dev_metadata = self.spreadsheet.get("developerMetadata", [])
        if dev_metadata:
            result[f"{spreadsheet_id}/developer_metadata.json"] = {
                "developerMetadata": dev_metadata
            }

        # Data sources (if any)
        data_sources = self.spreadsheet.get("dataSources", [])
        schedules = self.spreadsheet.get("dataSourceSchedules", [])
        if data_sources or schedules:
            result[f"{spreadsheet_id}/data_sources.json"] = {
                "dataSources": data_sources,
                "refreshSchedules": schedules,
            }

        # Transform each sheet
        for sheet in self.spreadsheet.get("sheets", []):
            sheet_id = sheet.get("properties", {}).get("sheetId", 0)
            folder = self._sheet_folders.get(sheet_id, f"sheet_{sheet_id}")

            sheet_files = self._transform_sheet(sheet)
            for filename, content in sheet_files.items():
                result[f"{spreadsheet_id}/{folder}/{filename}"] = content

        return result

    def _compute_sheet_folders(self) -> None:
        """Compute unique folder names for each sheet."""
        sheets = self.spreadsheet.get("sheets", [])
        used_names: dict[str, int] = {}

        for sheet in sheets:
            props = sheet.get("properties", {})
            sheet_id = props.get("sheetId", 0)
            title = props.get("title", f"Sheet{sheet_id}")

            # Sanitize the title
            folder_name = sanitize_filename(title)

            # Handle duplicates
            if folder_name in used_names:
                used_names[folder_name] += 1
                folder_name = f"{folder_name}_{sheet_id}"
            else:
                used_names[folder_name] = 1

            self._sheet_folders[sheet_id] = folder_name

    def _transform_spreadsheet_metadata(
        self, sheet_previews: dict[int, dict[str, Any]]
    ) -> dict[str, Any]:
        """Transform spreadsheet-level metadata.

        Args:
            sheet_previews: Dict mapping sheetId to preview data (firstRows, lastRows)
        """
        props = self.spreadsheet.get("properties", {})

        # Slim properties - only keep essential fields
        # Theme-related fields (defaultFormat, spreadsheetTheme) go to theme.json
        slim_props: dict[str, Any] = {}
        for key in ("title", "locale", "autoRecalc", "timeZone"):
            if key in props:
                slim_props[key] = props[key]

        # Build sheets array with essential metadata
        sheets_meta = []
        for sheet in self.spreadsheet.get("sheets", []):
            sheet_props = sheet.get("properties", {})
            sheet_id = sheet_props.get("sheetId", 0)

            sheet_entry: dict[str, Any] = {
                "sheetId": sheet_id,
                "title": sheet_props.get("title", ""),
                "index": sheet_props.get("index", 0),
                "sheetType": sheet_props.get("sheetType", "GRID"),
                "folder": self._sheet_folders.get(sheet_id, f"sheet_{sheet_id}"),
            }

            # Add grid properties if present
            grid_props = sheet_props.get("gridProperties")
            if grid_props:
                sheet_entry["gridProperties"] = grid_props

            # Add optional properties
            if sheet_props.get("hidden"):
                sheet_entry["hidden"] = True
            if sheet_props.get("rightToLeft"):
                sheet_entry["rightToLeft"] = True
            if sheet_props.get("tabColorStyle"):
                sheet_entry["tabColorStyle"] = sheet_props["tabColorStyle"]
            elif sheet_props.get("tabColor"):
                sheet_entry["tabColor"] = sheet_props["tabColor"]

            # Add truncation info if this sheet was truncated
            if sheet_id in self.truncation_info:
                sheet_entry["truncation"] = self.truncation_info[sheet_id]

            # Add preview if available
            if sheet_id in sheet_previews:
                sheet_entry["preview"] = sheet_previews[sheet_id]

            sheets_meta.append(sheet_entry)

        result = {
            "spreadsheetId": self.spreadsheet.get("spreadsheetId", ""),
            "spreadsheetUrl": self.spreadsheet.get("spreadsheetUrl", ""),
            "properties": slim_props,
            "sheets": sheets_meta,
        }

        # Add top-level truncation warning if any sheets were truncated
        if self.truncation_info:
            result["_truncationWarning"] = (
                "Some sheets have partial data. Check each sheet's 'truncation' field for details."
            )

        return result

    def _transform_named_ranges(self, named_ranges: list[NamedRange]) -> dict[str, Any]:
        """Transform named ranges."""
        return {"namedRanges": named_ranges}

    def _extract_theme(self) -> dict[str, Any]:
        """Extract theme information (defaultFormat, spreadsheetTheme) from properties.

        Returns:
            Dict with defaultFormat and/or spreadsheetTheme, or empty dict if neither exists.
        """
        props = self.spreadsheet.get("properties", {})
        theme: dict[str, Any] = {}

        if "defaultFormat" in props:
            theme["defaultFormat"] = props["defaultFormat"]
        if "spreadsheetTheme" in props:
            theme["spreadsheetTheme"] = props["spreadsheetTheme"]

        return theme

    def _extract_all_sheet_previews(self) -> dict[int, dict[str, Any]]:
        """Extract preview rows (first 5, last 3) for all sheets.

        Returns:
            Dict mapping sheetId to preview dict with firstRows and lastRows.
        """
        previews: dict[int, dict[str, Any]] = {}

        for sheet in self.spreadsheet.get("sheets", []):
            sheet_props = sheet.get("properties", {})
            sheet_id = sheet_props.get("sheetId", 0)
            sheet_type = sheet_props.get("sheetType", "GRID")

            # Only GRID sheets have preview data
            if sheet_type != "GRID":
                continue

            grid_data_list = sheet.get("data", [])
            if not grid_data_list:
                # Empty sheet - include empty preview
                previews[sheet_id] = {"firstRows": [], "lastRows": []}
                continue

            preview = self._extract_sheet_preview(grid_data_list)
            previews[sheet_id] = preview

        return previews

    def _extract_sheet_preview(self, grid_data_list: list[GridData]) -> dict[str, Any]:
        """Extract preview rows for a single sheet.

        Args:
            grid_data_list: List of GridData objects

        Returns:
            Dict with firstRows (up to 5) and lastRows (up to 3)
        """
        # Build the same sparse grid as in _transform_grid_to_tsv
        cells: dict[tuple[int, int], str] = {}
        max_row = -1
        max_col = -1

        for grid_data in grid_data_list:
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                actual_row = start_row + row_idx
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    actual_col = start_col + col_idx
                    value = get_effective_value_string(cell_data)
                    if value:
                        cells[(actual_row, actual_col)] = value
                        max_row = max(max_row, actual_row)
                        max_col = max(max_col, actual_col)

        if max_row < 0:
            # No data
            return {"firstRows": [], "lastRows": []}

        total_rows = max_row + 1

        def get_row_values(row: int) -> list[str]:
            """Get all values for a row as a list."""
            return [cells.get((row, col), "") for col in range(max_col + 1)]

        # First 5 rows
        first_count = min(5, total_rows)
        first_rows = [get_row_values(r) for r in range(first_count)]

        # Last 3 rows (non-overlapping with first rows)
        last_rows: list[list[str]] = []
        if total_rows > 5:
            # Only include last rows if they don't overlap with first rows
            last_start = max(5, total_rows - 3)
            for r in range(last_start, total_rows):
                last_rows.append(get_row_values(r))

        return {"firstRows": first_rows, "lastRows": last_rows}

    def _transform_sheet(self, sheet: Sheet) -> dict[str, Any]:
        """Transform a single sheet into file representations.

        Args:
            sheet: Sheet object from API

        Returns:
            Dictionary of filename -> content for this sheet
        """
        result: dict[str, Any] = {}
        props = sheet.get("properties", {})
        sheet_type = props.get("sheetType", "GRID")

        # Only GRID sheets have grid data
        if sheet_type == "GRID":
            grid_data_list = sheet.get("data", [])
            if grid_data_list:
                # Data TSV
                data_tsv = self._transform_grid_to_tsv(grid_data_list, props)
                if data_tsv:
                    result["data.tsv"] = data_tsv

                # Formulas
                formulas = self._extract_formulas(grid_data_list)
                if formulas:
                    result["formula.json"] = formulas

                # Formatting
                formatting = self._extract_formatting(sheet, grid_data_list)
                if self._has_formatting_content(formatting):
                    result["format.json"] = formatting

                # Dimensions
                dimensions = self._extract_dimensions(grid_data_list, sheet)
                if self._has_dimension_content(dimensions):
                    result["dimension.json"] = dimensions

        # Features (charts, pivots, etc.) - applies to all sheet types
        features = self._extract_features(sheet)
        if self._has_feature_content(features):
            result["feature.json"] = features

        # Protection
        protected_ranges = sheet.get("protectedRanges", [])
        if protected_ranges:
            result["protection.json"] = {"protectedRanges": protected_ranges}

        return result

    def _transform_grid_to_tsv(
        self, grid_data_list: list[GridData], props: dict[str, Any]
    ) -> str:
        """Transform grid data to TSV format.

        Args:
            grid_data_list: List of GridData objects
            props: Sheet properties

        Returns:
            TSV string
        """
        grid_props = props.get("gridProperties", {})
        row_count = grid_props.get("rowCount", 0)
        col_count = grid_props.get("columnCount", 0)

        if row_count == 0 or col_count == 0:
            return ""

        # Build a sparse grid from all GridData objects
        # Key: (row, col), Value: formatted string
        cells: dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0

        for grid_data in grid_data_list:
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                actual_row = start_row + row_idx
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    actual_col = start_col + col_idx

                    value = get_effective_value_string(cell_data)
                    if value:  # Only store non-empty values
                        cells[(actual_row, actual_col)] = value
                        max_row = max(max_row, actual_row)
                        max_col = max(max_col, actual_col)

        if not cells:
            return ""

        # Generate TSV
        lines: list[str] = []

        # Data rows
        for row in range(max_row + 1):
            row_values: list[str] = []
            for col in range(max_col + 1):
                value = cells.get((row, col), "")
                row_values.append(escape_tsv_value(value))
            lines.append("\t".join(row_values))

        return "\n".join(lines)

    def _extract_formulas(self, grid_data_list: list[GridData]) -> dict[str, Any]:
        """Extract formulas from grid data.

        Returns:
            Dictionary with formulas, arrayFormulas, and dataSourceFormulas
        """
        formulas: dict[str, str] = {}
        array_formulas: dict[str, Any] = {}
        data_source_formulas: list[dict[str, Any]] = []

        for grid_data in grid_data_list:
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    actual_row = start_row + row_idx
                    actual_col = start_col + col_idx
                    cell_a1 = cell_to_a1(actual_row, actual_col)

                    # Check for formula in userEnteredValue
                    user_value = cell_data.get("userEnteredValue", {})
                    formula = user_value.get("formulaValue")
                    if formula:
                        formulas[cell_a1] = formula

                    # Check for data source formula
                    ds_formula = cell_data.get("dataSourceFormula")
                    if ds_formula:
                        data_source_formulas.append(
                            {
                                "cell": cell_a1,
                                "formula": ds_formula.get("dataSourceId", ""),
                                "dataExecutionStatus": ds_formula.get(
                                    "dataExecutionStatus"
                                ),
                            }
                        )

        # Compress regular formulas into ranges (unified format)
        result: dict[str, Any] = dict(compress_formulas(formulas)) if formulas else {}

        if array_formulas:
            result["arrayFormulas"] = array_formulas
        if data_source_formulas:
            result["dataSourceFormulas"] = data_source_formulas

        return result

    def _extract_formatting(
        self, sheet: Sheet, grid_data_list: list[GridData]
    ) -> dict[str, Any]:
        """Extract formatting information from sheet and grid data.

        Uses range compression to reduce verbose per-cell formats into
        cascading rules with optimized format representation.
        """
        result: dict[str, Any] = {}

        # Default format from spreadsheet
        spreadsheet_props = self.spreadsheet.get("properties", {})
        default_format = spreadsheet_props.get("defaultFormat")

        # Cell formats (sparse) - collect raw formats first
        cell_formats: dict[str, Any] = {}
        text_format_runs: dict[str, Any] = {}
        notes: dict[str, str] = {}

        for grid_data in grid_data_list:
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    actual_row = start_row + row_idx
                    actual_col = start_col + col_idx
                    cell_a1 = cell_to_a1(actual_row, actual_col)

                    # User-entered format
                    user_format = cell_data.get("userEnteredFormat")
                    if user_format and not is_default_cell_format(
                        user_format, default_format
                    ):
                        cell_formats[cell_a1] = user_format

                    # Text format runs (rich text)
                    runs = cell_data.get("textFormatRuns")
                    if runs:
                        text_format_runs[cell_a1] = runs

                    # Cell notes
                    note = cell_data.get("note")
                    if note:
                        notes[cell_a1] = note

        # Compress cell formats into cascading rules
        if cell_formats:
            compressed = compress_cell_formats(cell_formats)
            if compressed.get("formatRules"):
                result["formatRules"] = compressed["formatRules"]

        # Conditional formats
        cond_formats = sheet.get("conditionalFormats", [])
        if cond_formats:
            # Add rule index for fly-blind editing
            indexed_formats = []
            for idx, rule in enumerate(cond_formats):
                rule_copy = dict(rule)
                rule_copy["ruleIndex"] = idx
                # Convert ranges to A1 notation
                if "ranges" in rule_copy:
                    rule_copy["ranges"] = [
                        grid_range_to_a1(r) for r in rule_copy["ranges"]
                    ]
                indexed_formats.append(rule_copy)
            result["conditionalFormats"] = indexed_formats

        # Merged cells
        merges = sheet.get("merges", [])
        if merges:
            merge_ranges = []
            for merge in merges:
                merge_ranges.append(
                    {
                        "range": grid_range_to_a1(merge),
                        "startRow": merge.get("startRowIndex"),
                        "endRow": merge.get("endRowIndex"),
                        "startColumn": merge.get("startColumnIndex"),
                        "endColumn": merge.get("endColumnIndex"),
                    }
                )
            result["merges"] = merge_ranges

        if text_format_runs:
            result["textFormatRuns"] = text_format_runs

        if notes:
            result["notes"] = notes

        return result

    def _extract_features(self, sheet: Sheet) -> dict[str, Any]:
        """Extract features (charts, pivots, filters, etc.) from sheet."""
        result: dict[str, Any] = {}

        # Charts
        charts = sheet.get("charts", [])
        if charts:
            result["charts"] = charts

        # Basic filter
        basic_filter = sheet.get("basicFilter")
        if basic_filter:
            result["basicFilter"] = basic_filter

        # Filter views
        filter_views = sheet.get("filterViews", [])
        if filter_views:
            result["filterViews"] = filter_views

        # Slicers
        slicers = sheet.get("slicers", [])
        if slicers:
            result["slicers"] = slicers

        # Banded ranges
        banded_ranges = sheet.get("bandedRanges", [])
        if banded_ranges:
            result["bandedRanges"] = banded_ranges

        # Tables
        tables = sheet.get("tables", [])
        if tables:
            result["tables"] = tables

        # Pivot tables - extracted from cells
        pivot_tables = self._extract_pivot_tables(sheet)
        if pivot_tables:
            result["pivotTables"] = pivot_tables

        # Data source tables - extracted from cells
        ds_tables = self._extract_data_source_tables(sheet)
        if ds_tables:
            result["dataSourceTables"] = ds_tables

        # Data validation - extracted from cells
        data_validation = self._extract_data_validation(sheet)
        if data_validation:
            result["dataValidation"] = data_validation

        return result

    def _extract_pivot_tables(self, sheet: Sheet) -> list[dict[str, Any]]:
        """Extract pivot tables from cell data."""
        pivot_tables: list[dict[str, Any]] = []

        for grid_data in sheet.get("data", []):
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    pivot = cell_data.get("pivotTable")
                    if pivot:
                        actual_row = start_row + row_idx
                        actual_col = start_col + col_idx
                        pivot_entry = dict(pivot)
                        pivot_entry["anchorCell"] = cell_to_a1(actual_row, actual_col)
                        pivot_tables.append(pivot_entry)

        return pivot_tables

    def _extract_data_source_tables(self, sheet: Sheet) -> list[dict[str, Any]]:
        """Extract data source tables from cell data."""
        ds_tables: list[dict[str, Any]] = []

        for grid_data in sheet.get("data", []):
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    ds_table = cell_data.get("dataSourceTable")
                    if ds_table:
                        actual_row = start_row + row_idx
                        actual_col = start_col + col_idx
                        table_entry = dict(ds_table)
                        table_entry["anchorCell"] = cell_to_a1(actual_row, actual_col)
                        ds_tables.append(table_entry)

        return ds_tables

    def _extract_data_validation(self, sheet: Sheet) -> list[dict[str, Any]]:
        """Extract data validation rules from cell data."""
        validation_rules: dict[str, dict[str, Any]] = {}  # rule -> cells

        for grid_data in sheet.get("data", []):
            start_row = grid_data.get("startRow", 0)
            start_col = grid_data.get("startColumn", 0)

            for row_idx, row_data in enumerate(grid_data.get("rowData", [])):
                for col_idx, cell_data in enumerate(row_data.get("values", [])):
                    validation = cell_data.get("dataValidation")
                    if validation:
                        actual_row = start_row + row_idx
                        actual_col = start_col + col_idx
                        cell_a1 = cell_to_a1(actual_row, actual_col)

                        # Use JSON string as key for grouping identical rules
                        rule_key = json.dumps(validation, sort_keys=True)

                        if rule_key not in validation_rules:
                            validation_rules[rule_key] = {
                                "cells": [],
                                "rule": validation,
                            }
                        validation_rules[rule_key]["cells"].append(cell_a1)

        # Convert to list format
        result: list[dict[str, Any]] = []
        for entry in validation_rules.values():
            cells = entry["cells"]
            # Try to compress to range if cells are contiguous
            # For now, just list the cells
            result.append(
                {
                    "range": ", ".join(cells)
                    if len(cells) <= 5
                    else f"{cells[0]}... ({len(cells)} cells)",
                    "cells": cells,
                    "rule": entry["rule"],
                }
            )

        return result

    def _extract_dimensions(
        self, grid_data_list: list[GridData], sheet: Sheet
    ) -> dict[str, Any]:
        """Extract dimension metadata (row/column sizes, groups)."""
        result: dict[str, Any] = {}

        # Row metadata (sparse - only non-default)
        row_metadata: list[dict[str, Any]] = []
        col_metadata: list[dict[str, Any]] = []

        for grid_data in grid_data_list:
            # Row metadata
            for idx, dim in enumerate(grid_data.get("rowMetadata", [])):
                if not is_default_dimension(dim, is_row=True):
                    actual_idx = grid_data.get("startRow", 0) + idx
                    row_entry: dict[str, Any] = {"index": actual_idx}
                    if dim.get("pixelSize"):
                        row_entry["pixelSize"] = dim["pixelSize"]
                    if dim.get("hidden"):
                        row_entry["hidden"] = True
                    if dim.get("developerMetadata"):
                        row_entry["developerMetadata"] = dim["developerMetadata"]
                    row_metadata.append(row_entry)

            # Column metadata
            for idx, dim in enumerate(grid_data.get("columnMetadata", [])):
                if not is_default_dimension(dim, is_row=False):
                    actual_idx = grid_data.get("startColumn", 0) + idx
                    col_entry: dict[str, Any] = {"index": actual_idx}
                    if dim.get("pixelSize"):
                        col_entry["pixelSize"] = dim["pixelSize"]
                    if dim.get("hidden"):
                        col_entry["hidden"] = True
                    if dim.get("developerMetadata"):
                        col_entry["developerMetadata"] = dim["developerMetadata"]
                    col_metadata.append(col_entry)

        if row_metadata:
            result["rowMetadata"] = row_metadata
        if col_metadata:
            result["columnMetadata"] = col_metadata

        # Row groups
        row_groups = sheet.get("rowGroups", [])
        if row_groups:
            result["rowGroups"] = row_groups

        # Column groups
        col_groups = sheet.get("columnGroups", [])
        if col_groups:
            result["columnGroups"] = col_groups

        # Developer metadata at sheet level (dimension-related)
        dev_metadata = sheet.get("developerMetadata", [])
        dim_metadata = [
            m for m in dev_metadata if m.get("location", {}).get("dimensionRange")
        ]
        if dim_metadata:
            result["developerMetadata"] = dim_metadata

        return result

    def _has_formatting_content(self, formatting: dict[str, Any]) -> bool:
        """Check if formatting dict has any meaningful content."""
        meaningful_keys = {
            "formatRules",
            "conditionalFormats",
            "merges",
            "textFormatRuns",
            "notes",
        }
        return bool(set(formatting.keys()) & meaningful_keys)

    def _has_feature_content(self, features: dict[str, Any]) -> bool:
        """Check if features dict has any meaningful content."""
        return bool(features)

    def _has_dimension_content(self, dimensions: dict[str, Any]) -> bool:
        """Check if dimensions dict has any meaningful content."""
        return bool(dimensions)
