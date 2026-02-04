"""
Spreadsheet to file representation transformer.

Converts Google Sheets API responses into the extrasheet file format.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from extrasheet.format_compression import compress_cell_formats, normalize_colors_to_hex
from extrasheet.formula_compression import compress_formulas
from extrasheet.utils import (
    cell_to_a1,
    column_index_to_letter,
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
                sheet_entry["tabColorStyle"] = normalize_colors_to_hex(
                    sheet_props["tabColorStyle"]
                )
            elif sheet_props.get("tabColor"):
                sheet_entry["tabColor"] = normalize_colors_to_hex(
                    sheet_props["tabColor"]
                )

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
        """Transform named ranges to use A1 notation."""
        converted: list[dict[str, Any]] = []

        for nr in named_ranges:
            nr_copy: dict[str, Any] = dict(nr)
            if "range" in nr_copy:
                # Convert GridRange to A1 notation
                range_data: dict[str, Any] = nr_copy["range"]
                nr_copy["range"] = grid_range_to_a1(range_data)
                # Keep sheetId separately for reference
                if "sheetId" in range_data:
                    nr_copy["sheetId"] = range_data["sheetId"]
            converted.append(nr_copy)

        return {"namedRanges": converted}

    def _extract_theme(self) -> dict[str, Any]:
        """Extract theme information (defaultFormat, spreadsheetTheme) from properties.

        Colors are normalized to hex format for consistency.

        Returns:
            Dict with defaultFormat and/or spreadsheetTheme, or empty dict if neither exists.
        """
        props = self.spreadsheet.get("properties", {})
        theme: dict[str, Any] = {}

        if "defaultFormat" in props:
            theme["defaultFormat"] = normalize_colors_to_hex(props["defaultFormat"])
        if "spreadsheetTheme" in props:
            theme["spreadsheetTheme"] = normalize_colors_to_hex(
                props["spreadsheetTheme"]
            )

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
        # Output as separate files instead of single feature.json
        feature_files = self._extract_feature_files(sheet)
        result.update(feature_files)

        # Protection
        protected_ranges = sheet.get("protectedRanges", [])
        if protected_ranges:
            result["protection.json"] = {"protectedRanges": protected_ranges}

        return result

    def _transform_grid_to_tsv(self, grid_data_list: list[GridData], props: Any) -> str:
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

                    # Text format runs (rich text) - normalize colors to hex
                    runs = cell_data.get("textFormatRuns")
                    if runs:
                        text_format_runs[cell_a1] = normalize_colors_to_hex(runs)

                    # Cell notes
                    note = cell_data.get("note")
                    if note:
                        notes[cell_a1] = note

        # Compress cell formats into cascading rules
        if cell_formats:
            compressed = compress_cell_formats(cell_formats)
            if compressed.get("formatRules"):
                result["formatRules"] = compressed["formatRules"]

        # Conditional formats - normalize colors to hex
        cond_formats = sheet.get("conditionalFormats", [])
        if cond_formats:
            # Add rule index for fly-blind editing
            indexed_formats = []
            for idx, rule in enumerate(cond_formats):
                rule_copy: dict[str, Any] = dict(rule)
                rule_copy["ruleIndex"] = idx
                # Convert ranges to A1 notation
                if "ranges" in rule_copy:
                    ranges_list: list[Any] = rule_copy["ranges"]
                    rule_copy["ranges"] = [grid_range_to_a1(r) for r in ranges_list]
                # Normalize colors to hex
                rule_copy = normalize_colors_to_hex(rule_copy)
                indexed_formats.append(rule_copy)
            result["conditionalFormats"] = indexed_formats

        # Merged cells - use A1 notation only
        merges = sheet.get("merges", [])
        if merges:
            merge_ranges = []
            for merge in merges:
                merge_ranges.append({"range": grid_range_to_a1(merge)})
            result["merges"] = merge_ranges

        if text_format_runs:
            result["textFormatRuns"] = text_format_runs

        if notes:
            result["notes"] = notes

        return result

    def _extract_feature_files(self, sheet: Sheet) -> dict[str, Any]:
        """Extract features into separate files.

        Instead of a single feature.json, outputs separate files:
        - charts.json: Charts
        - pivot-tables.json: Pivot tables
        - tables.json: Tables
        - filters.json: Basic filter + filter views
        - banded-ranges.json: Banded ranges
        - data-validation.json: Data validation rules
        - slicers.json: Slicers (rare)
        - data-source-tables.json: Data source tables (rare)

        Only creates files if content exists.
        """
        result: dict[str, Any] = {}

        # Charts - convert to A1 notation
        charts = sheet.get("charts", [])
        if charts:
            result["charts.json"] = {"charts": self._convert_charts_to_a1(charts)}

        # Pivot tables - extracted from cells (already uses A1 for anchorCell)
        pivot_tables = self._extract_pivot_tables(sheet)
        if pivot_tables:
            result["pivot-tables.json"] = {"pivotTables": pivot_tables}

        # Tables - convert to A1 notation
        tables = sheet.get("tables", [])
        if tables:
            result["tables.json"] = {"tables": self._convert_tables_to_a1(tables)}

        # Filters (basicFilter + filterViews) - convert to A1 notation
        basic_filter = sheet.get("basicFilter")
        filter_views = sheet.get("filterViews", [])
        if basic_filter or filter_views:
            filters_data: dict[str, Any] = {}
            if basic_filter:
                filters_data["basicFilter"] = self._convert_filter_to_a1(basic_filter)
            if filter_views:
                filters_data["filterViews"] = [
                    self._convert_filter_view_to_a1(fv) for fv in filter_views
                ]
            result["filters.json"] = filters_data

        # Banded ranges - normalize colors to hex and convert to A1 notation
        banded_ranges = sheet.get("bandedRanges", [])
        if banded_ranges:
            result["banded-ranges.json"] = {
                "bandedRanges": self._convert_banded_ranges_to_a1(banded_ranges)
            }

        # Data validation - extracted from cells
        data_validation = self._extract_data_validation(sheet)
        if data_validation:
            result["data-validation.json"] = {"dataValidation": data_validation}

        # Slicers (rare) - convert to A1 notation
        slicers = sheet.get("slicers", [])
        if slicers:
            result["slicers.json"] = {"slicers": self._convert_slicers_to_a1(slicers)}

        # Data source tables - extracted from cells (rare)
        ds_tables = self._extract_data_source_tables(sheet)
        if ds_tables:
            result["data-source-tables.json"] = {"dataSourceTables": ds_tables}

        return result

    def _extract_features(self, sheet: Sheet) -> dict[str, Any]:
        """Extract features (charts, pivots, filters, etc.) from sheet.

        DEPRECATED: This method is kept for backward compatibility.
        Use _extract_feature_files() for the new split format.
        """
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

        # Banded ranges - normalize colors to hex
        banded_ranges = sheet.get("bandedRanges", [])
        if banded_ranges:
            result["bandedRanges"] = normalize_colors_to_hex(banded_ranges)

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
        """Extract dimension metadata (row/column sizes, groups).

        Uses A1-style notation:
        - Rows use 1-based numbers (row 1, 2, 3...)
        - Columns use letters (A, B, C...)
        """

        result: dict[str, Any] = {}

        # Row metadata (sparse - only non-default)
        row_metadata: list[dict[str, Any]] = []
        col_metadata: list[dict[str, Any]] = []

        for grid_data in grid_data_list:
            # Row metadata - use 1-based row numbers
            for idx, dim in enumerate(grid_data.get("rowMetadata", [])):
                if not is_default_dimension(dim, is_row=True):
                    actual_idx = grid_data.get("startRow", 0) + idx
                    # Use 1-based row number
                    row_entry: dict[str, Any] = {"row": actual_idx + 1}
                    if dim.get("pixelSize"):
                        row_entry["pixelSize"] = dim["pixelSize"]
                    if dim.get("hidden"):
                        row_entry["hidden"] = True
                    if dim.get("developerMetadata"):
                        row_entry["developerMetadata"] = dim["developerMetadata"]
                    row_metadata.append(row_entry)

            # Column metadata - use column letters
            for idx, dim in enumerate(grid_data.get("columnMetadata", [])):
                if not is_default_dimension(dim, is_row=False):
                    actual_idx = grid_data.get("startColumn", 0) + idx
                    # Use column letter (A, B, C, ...)
                    col_entry: dict[str, Any] = {
                        "column": column_index_to_letter(actual_idx)
                    }
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

        # Row groups - convert to 1-based rows
        row_groups = sheet.get("rowGroups", [])
        if row_groups:
            result["rowGroups"] = self._convert_row_groups_to_a1(row_groups)

        # Column groups - convert to column letters
        col_groups = sheet.get("columnGroups", [])
        if col_groups:
            result["columnGroups"] = self._convert_col_groups_to_a1(col_groups)

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

    def _convert_charts_to_a1(self, charts: list[Any]) -> list[dict[str, Any]]:
        """Convert chart positions and source ranges from 0-based to A1 notation."""

        converted: list[dict[str, Any]] = []

        for chart in charts:
            chart_copy = dict(chart)

            # Convert anchor cell position
            if "position" in chart_copy:
                position = dict(chart_copy["position"])
                if "overlayPosition" in position:
                    overlay = dict(position["overlayPosition"])
                    if "anchorCell" in overlay:
                        anchor = overlay["anchorCell"]
                        row_idx = anchor.get("rowIndex", 0)
                        col_idx = anchor.get("columnIndex", 0)
                        # Replace with A1 notation
                        overlay["anchorCell"] = cell_to_a1(row_idx, col_idx)
                    position["overlayPosition"] = overlay
                chart_copy["position"] = position

            # Convert source ranges in spec.basicChart.domains and series
            if "spec" in chart_copy:
                spec = dict(chart_copy["spec"])
                if "basicChart" in spec:
                    basic_chart = dict(spec["basicChart"])
                    # Convert domains
                    if "domains" in basic_chart:
                        basic_chart["domains"] = [
                            self._convert_chart_domain_to_a1(d)
                            for d in basic_chart["domains"]
                        ]
                    # Convert series
                    if "series" in basic_chart:
                        basic_chart["series"] = [
                            self._convert_chart_series_to_a1(s)
                            for s in basic_chart["series"]
                        ]
                    spec["basicChart"] = basic_chart
                chart_copy["spec"] = spec

            converted.append(chart_copy)

        return converted

    def _convert_chart_domain_to_a1(self, domain: dict[str, Any]) -> dict[str, Any]:
        """Convert a chart domain's source ranges to A1 notation."""
        result = dict(domain)

        if "domain" in result:
            domain_inner = dict(result["domain"])
            if "sourceRange" in domain_inner:
                source_range = dict(domain_inner["sourceRange"])
                if "sources" in source_range:
                    source_range["sources"] = [
                        self._convert_grid_range_in_source(s)
                        for s in source_range["sources"]
                    ]
                domain_inner["sourceRange"] = source_range
            result["domain"] = domain_inner

        return result

    def _convert_chart_series_to_a1(self, series: dict[str, Any]) -> dict[str, Any]:
        """Convert a chart series' source ranges to A1 notation."""
        result = dict(series)

        if "series" in result:
            series_inner = dict(result["series"])
            if "sourceRange" in series_inner:
                source_range = dict(series_inner["sourceRange"])
                if "sources" in source_range:
                    source_range["sources"] = [
                        self._convert_grid_range_in_source(s)
                        for s in source_range["sources"]
                    ]
                series_inner["sourceRange"] = source_range
            result["series"] = series_inner

        return result

    def _convert_grid_range_in_source(self, source: dict[str, Any]) -> dict[str, Any]:
        """Convert a grid range source to A1 notation, keeping sheetId."""
        result: dict[str, Any] = {}

        # Keep sheetId for cross-sheet references
        if "sheetId" in source:
            result["sheetId"] = source["sheetId"]

        # Convert to A1 notation range
        result["range"] = grid_range_to_a1(source)

        return result

    def _convert_tables_to_a1(self, tables: list[Any]) -> list[dict[str, Any]]:
        """Convert table ranges and column indices to A1 notation."""

        converted: list[dict[str, Any]] = []

        for table in tables:
            table_copy = dict(table)

            # Convert range to A1 notation
            if "range" in table_copy:
                range_data = table_copy["range"]
                table_copy["range"] = grid_range_to_a1(range_data)

            # Convert columnProperties indices to column letters
            if "columnProperties" in table_copy:
                new_col_props = []
                for col_prop in table_copy["columnProperties"]:
                    col_copy = dict(col_prop)
                    if "columnIndex" in col_copy:
                        col_idx = col_copy["columnIndex"]
                        col_copy["column"] = column_index_to_letter(col_idx)
                        del col_copy["columnIndex"]
                    elif not col_copy.get("column"):
                        # First column (index 0) doesn't have columnIndex
                        col_copy["column"] = "A"
                    new_col_props.append(col_copy)
                table_copy["columnProperties"] = new_col_props

            converted.append(table_copy)

        return converted

    def _convert_filter_to_a1(self, basic_filter: Any) -> dict[str, Any]:
        """Convert basic filter range to A1 notation."""
        result = dict(basic_filter)

        if "range" in result:
            result["range"] = grid_range_to_a1(result["range"])

        return result

    def _convert_filter_view_to_a1(self, filter_view: Any) -> dict[str, Any]:
        """Convert filter view range to A1 notation."""
        result = dict(filter_view)

        if "range" in result:
            result["range"] = grid_range_to_a1(result["range"])

        return result

    def _convert_banded_ranges_to_a1(
        self, banded_ranges: list[Any]
    ) -> list[dict[str, Any]]:
        """Convert banded range ranges to A1 notation and normalize colors."""
        converted: list[dict[str, Any]] = []

        for banded in banded_ranges:
            banded_copy = normalize_colors_to_hex(dict(banded))

            # Convert range to A1 notation
            if "range" in banded_copy:
                banded_copy["range"] = grid_range_to_a1(banded_copy["range"])

            converted.append(banded_copy)

        return converted

    def _convert_slicers_to_a1(self, slicers: list[Any]) -> list[dict[str, Any]]:
        """Convert slicer positions and data ranges to A1 notation."""
        converted: list[dict[str, Any]] = []

        for slicer in slicers:
            slicer_copy = dict(slicer)

            # Convert position anchor cell
            if "position" in slicer_copy:
                position = dict(slicer_copy["position"])
                if "overlayPosition" in position:
                    overlay = dict(position["overlayPosition"])
                    if "anchorCell" in overlay:
                        anchor = overlay["anchorCell"]
                        row_idx = anchor.get("rowIndex", 0)
                        col_idx = anchor.get("columnIndex", 0)
                        overlay["anchorCell"] = cell_to_a1(row_idx, col_idx)
                    position["overlayPosition"] = overlay
                slicer_copy["position"] = position

            # Convert spec data range and column
            if "spec" in slicer_copy:
                spec = dict(slicer_copy["spec"])
                # Convert dataRange GridRange to A1
                if "dataRange" in spec and isinstance(spec["dataRange"], dict):
                    spec["dataRange"] = grid_range_to_a1(spec["dataRange"])
                # Convert columnIndex to column letter
                if "columnIndex" in spec:
                    spec["column"] = column_index_to_letter(spec["columnIndex"])
                    del spec["columnIndex"]
                slicer_copy["spec"] = spec

            converted.append(slicer_copy)

        return converted

    def _convert_row_groups_to_a1(self, row_groups: list[Any]) -> list[dict[str, Any]]:
        """Convert row group ranges to 1-based row numbers."""
        converted: list[dict[str, Any]] = []

        for group in row_groups:
            group_copy = dict(group)
            if "range" in group_copy:
                range_data = group_copy["range"]
                # Convert to 1-based row range like "2:10"
                start = range_data.get("startIndex", 0) + 1
                end = range_data.get("endIndex", start)
                group_copy["range"] = f"{start}:{end}"
            converted.append(group_copy)

        return converted

    def _convert_col_groups_to_a1(self, col_groups: list[Any]) -> list[dict[str, Any]]:
        """Convert column group ranges to column letters."""

        converted: list[dict[str, Any]] = []

        for group in col_groups:
            group_copy = dict(group)
            if "range" in group_copy:
                range_data = group_copy["range"]
                # Convert to column letter range like "B:D"
                start = column_index_to_letter(range_data.get("startIndex", 0))
                end_idx = range_data.get("endIndex", 1) - 1  # exclusive to inclusive
                end = column_index_to_letter(end_idx if end_idx >= 0 else 0)
                group_copy["range"] = f"{start}:{end}"
            converted.append(group_copy)

        return converted
