# Extrasheet Diff/Push Specification

Version: 1.0.0
Last Updated: 2026-01-28

## Overview

This document specifies how extrasheet compares edited files against the pristine copy and generates Google Sheets API `batchUpdate` requests to apply changes.

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Google Sheets batchUpdate Operations](#google-sheets-batchupdate-operations)
3. [File Change to Operation Mapping](#file-change-to-operation-mapping)
4. [Formula Invalidation Problem](#formula-invalidation-problem)
5. [Diff Algorithm](#diff-algorithm)
6. [Request Generation](#request-generation)
7. [Operation Ordering](#operation-ordering)
8. [Supported vs Unsupported Operations](#supported-vs-unsupported-operations)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DIFF/PUSH FLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  .pristine/spreadsheet.zip          Current Files                       │
│         │                                │                              │
│         ▼                                ▼                              │
│  ┌─────────────┐                 ┌─────────────┐                        │
│  │ Extract &   │                 │ Read from   │                        │
│  │ Parse       │                 │ Disk        │                        │
│  └──────┬──────┘                 └──────┬──────┘                        │
│         │                                │                              │
│         ▼                                ▼                              │
│  ┌─────────────────────────────────────────────┐                        │
│  │              DIFF ENGINE                     │                        │
│  │  - Compare spreadsheet.json (sheet changes) │                        │
│  │  - Compare data.tsv (cell values)           │                        │
│  │  - Compare formula.json (formulas)          │                        │
│  │  - Compare format.json (formatting)         │                        │
│  │  - Compare feature.json (charts, etc.)      │                        │
│  │  - Compare dimension.json (row/col sizes)   │                        │
│  └──────────────────┬──────────────────────────┘                        │
│                     │                                                   │
│                     ▼                                                   │
│  ┌─────────────────────────────────────────────┐                        │
│  │           REQUEST GENERATOR                  │                        │
│  │  - Convert changes to batchUpdate requests  │                        │
│  │  - Order requests correctly                 │                        │
│  │  - Validate no formula-breaking changes     │                        │
│  └──────────────────┬──────────────────────────┘                        │
│                     │                                                   │
│                     ▼                                                   │
│  ┌─────────────────────────────────────────────┐                        │
│  │          batchUpdate JSON                    │                        │
│  │  (diff outputs this, push sends to API)     │                        │
│  └─────────────────────────────────────────────┘                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Google Sheets batchUpdate Operations

The Google Sheets API provides 69 batchUpdate operations organized into categories:

### Cell Data (5 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `updateCells` | Updates cells in a range with new data | **Primary** - for values, formulas, formats |
| `repeatCell` | Applies same cell data to a range | Supported - for bulk formatting |
| `appendCells` | Adds cells after last row with data | Supported - for appending data |
| `mergeCells` | Merges cells in a range | Supported |
| `unmergeCells` | Unmerges cells in a range | Supported |

### Rows & Columns (10 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `appendDimension` | Adds rows/columns at the end | **Safe** - doesn't shift formulas |
| `insertDimension` | Inserts rows/columns at index | **Supported** - runs LAST after all content changes |
| `deleteDimension` | Deletes rows/columns | **Supported** - runs LAST after all content changes |
| `moveDimension` | Moves rows/columns | **Supported** - runs LAST after all content changes |
| `updateDimensionProperties` | Updates row/column size, hidden | Supported |
| `autoResizeDimensions` | Auto-resize based on content | Not supported |
| `addDimensionGroup` | Creates row/column group | Supported |
| `deleteDimensionGroup` | Deletes row/column group | Supported |
| `updateDimensionGroup` | Updates group collapsed state | Supported |
| `textToColumns` | Splits text column | Not supported |

### Sheet Management (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addSheet` | Creates new sheet | Supported |
| `deleteSheet` | Deletes sheet | Supported |
| `duplicateSheet` | Duplicates sheet | Not supported |

### Sheet Properties (2 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `updateSheetProperties` | Updates sheet title, hidden, frozen rows/cols | Supported |
| `updateSpreadsheetProperties` | Updates spreadsheet title, locale, timezone | Supported |

### Formatting (5 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `updateBorders` | Sets cell borders | Supported |
| `addConditionalFormatRule` | Adds conditional format | Supported |
| `deleteConditionalFormatRule` | Deletes conditional format | Supported |
| `updateConditionalFormatRule` | Updates conditional format | Supported |
| `updateEmbeddedObjectBorder` | Updates chart/image border | Not supported |

### Named Ranges (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addNamedRange` | Creates named range | Supported |
| `deleteNamedRange` | Deletes named range | Supported |
| `updateNamedRange` | Updates named range | Supported |

### Charts (2 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addChart` | Creates chart | Supported |
| `updateChartSpec` | Updates chart configuration | Supported |

### Filters (6 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `setBasicFilter` | Sets filter on sheet | Supported |
| `clearBasicFilter` | Clears filter | Supported |
| `addFilterView` | Creates filter view | Supported |
| `deleteFilterView` | Deletes filter view | Supported |
| `updateFilterView` | Updates filter view | Supported |
| `duplicateFilterView` | Duplicates filter view | Not supported |

### Data Validation (1 operation)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `setDataValidation` | Sets validation rule on range | Supported |

### Protection (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addProtectedRange` | Creates protected range | Supported |
| `deleteProtectedRange` | Deletes protected range | Supported |
| `updateProtectedRange` | Updates protected range | Supported |

### Copy & Paste (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `copyPaste` | Copies data between ranges | Not supported |
| `cutPaste` | Moves data between ranges | Not supported |
| `pasteData` | Pastes delimited data | Not supported |

### Other Operations
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `autoFill` | Auto-fills data/formula pattern | **Critical** - for formula range updates |
| `findReplace` | Find and replace text | Not supported |
| `sortRange` | Sorts data in range | Supported - runs LAST |
| `deleteDuplicates` | Removes duplicate rows | Not supported |
| `trimWhitespace` | Trims whitespace | Not supported |
| `randomizeRange` | Randomizes row order | Not supported |
| `deleteRange` | Deletes range, shifts cells | **Supported** - runs LAST |
| `insertRange` | Inserts range, shifts cells | **Supported** - runs LAST |

### Banded Ranges (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addBanding` | Creates alternating colors | Supported |
| `deleteBanding` | Deletes banding | Supported |
| `updateBanding` | Updates banding | Supported |

### Tables (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addTable` | Creates structured table | Supported |
| `deleteTable` | Deletes table | Supported |
| `updateTable` | Updates table | Supported |

### Slicers (2 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `addSlicer` | Creates slicer | Supported |
| `updateSlicerSpec` | Updates slicer | Supported |

### Embedded Objects (2 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `deleteEmbeddedObject` | Deletes chart/image | Supported |
| `updateEmbeddedObjectPosition` | Moves/resizes chart/image | Supported |

### Developer Metadata (3 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| `createDeveloperMetadata` | Creates app-specific metadata | Supported |
| `updateDeveloperMetadata` | Updates metadata | Supported |
| `deleteDeveloperMetadata` | Deletes metadata | Supported |

### Data Sources (5 operations)
| Operation | Description | Extrasheet Support |
|-----------|-------------|-------------------|
| All data source operations | BigQuery/Looker connections | Not supported |

---

## Two Workflows: Declarative and Imperative

Extrasheet provides two distinct workflows for modifying spreadsheets:

### Declarative Workflow (pull-diff-push)

The primary workflow for 90% of use cases. Edit files to declare the desired state, then push.

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  pull   │────▶│  edit   │────▶│  diff   │────▶│  push   │
│         │     │ files   │     │         │     │         │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
     │                               │               │
     ▼                               ▼               ▼
 Downloads          Agent edits   Compares      Applies
 to files           data.tsv,     pristine      changes
                    formula.json, vs current    to API
                    format.json
```

**Characteristics:**
- **Order-independent**: Changes are detected by comparing states, not tracked sequentially
- **Idempotent**: Running diff/push multiple times with same files produces same result
- **Safe**: Cannot accidentally invalidate formulas (dimensions are fixed)

**What you CAN do declaratively:**
- Modify cell values
- Add/modify/remove formulas
- Change formatting (cell formats, conditional formats, borders)
- Add/modify/remove features (charts, tables, filters, validation, etc.)
- Update properties (sheet title, frozen rows, hidden state, etc.)
- Add/modify/remove named ranges

**What you CANNOT do declaratively:**
- Insert rows/columns
- Delete rows/columns
- Move rows/columns
- Sort data

### Imperative Workflow (explicit commands)

For structural changes that alter the grid dimensions. These are explicit commands.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────┐
│ Imperative      │────▶│ Execute via     │────▶│ re-pull │
│ commands        │     │ API             │     │         │
└─────────────────┘     └─────────────────┘     └─────────┘
        │                       │                    │
        ▼                       ▼                    ▼
  insertDimension         Runs immediately      Local files
  deleteDimension         on Google Sheets      are now stale,
  moveDimension                                 need refresh
  sortRange
```

**Characteristics:**
- **Order-dependent**: Commands execute in the order specified
- **Immediate**: Applied directly to Google Sheets API
- **Invalidates local state**: After execution, local files are stale

**After imperative commands, you MUST:**
1. Re-pull the spreadsheet to get updated state
2. Then continue with declarative edits if needed

### Interleaving Workflows

The LLM can interleave declarative and imperative workflows as needed:

```
Example: Add a new "Status" column between columns B and C

1. [Imperative] Insert column at position C
   → extrasheet exec insertDimension --dimension=COLUMNS --index=2

2. [Re-pull] Get updated state
   → extrasheet pull <id>

3. [Declarative] Fill the new column with data and formulas
   → Edit data.tsv, formula.json
   → extrasheet push
```

Or batch multiple imperative operations:

```
Example: Restructure the sheet

1. [Imperative] Batch structural changes
   → extrasheet exec --batch commands.json
   (contains: insertDimension, moveDimension, deleteDimension)

2. [Re-pull] Get updated state
   → extrasheet pull <id>

3. [Declarative] Make content changes
   → Edit files, push
```

### Why Two Workflows?

**Declarative is preferred because:**
- Simpler mental model (desired state, not steps)
- Order doesn't matter
- Easy to review changes before applying
- Handles 90% of editing tasks

**Imperative is necessary because:**
- Structural changes shift cell references
- Google Sheets updates formulas automatically
- Our local files would have stale coordinates after structural changes
- Simpler to re-pull than to track coordinate transformations

---

## File Change to Operation Mapping

### spreadsheet.json Changes

| Change | API Operation |
|--------|---------------|
| `properties.title` changed | `updateSpreadsheetProperties` |
| `properties.locale` changed | `updateSpreadsheetProperties` |
| `properties.timeZone` changed | `updateSpreadsheetProperties` |
| Sheet added (new entry in `sheets[]`) | `addSheet` |
| Sheet removed | `deleteSheet` |
| `sheets[].title` changed | `updateSheetProperties` |
| `sheets[].hidden` changed | `updateSheetProperties` |
| `sheets[].gridProperties.frozenRowCount` changed | `updateSheetProperties` |
| `sheets[].gridProperties.frozenColumnCount` changed | `updateSheetProperties` |
| `sheets[].tabColorStyle` changed | `updateSheetProperties` |
| `sheets[].index` changed (reorder) | `updateSheetProperties` |

### data.tsv Changes

The data.tsv file contains cell VALUES (formulas show their computed results).

| Change | Detection | Result |
|--------|-----------|--------|
| Cell value changed | Cell-by-cell comparison | `updateCells` with `userEnteredValue` |
| Row count changed | Grid dimension mismatch | **Error**: Use imperative commands |
| Column count changed | Grid dimension mismatch | **Error**: Use imperative commands |

**Important:** When a cell has a formula (in formula.json), changing data.tsv for that cell is **ignored** - the formula takes precedence.

**Grid dimension validation:** The diff engine validates that grid dimensions match between pristine and current. If dimensions differ, it raises `GridDimensionChangedError`:

```python
def validate_grid_dimensions(pristine_tsv: str, current_tsv: str) -> None:
    pristine_grid = parse_tsv(pristine_tsv)
    current_grid = parse_tsv(current_tsv)

    pristine_rows = len(pristine_grid)
    current_rows = len(current_grid)
    pristine_cols = max(len(row) for row in pristine_grid) if pristine_grid else 0
    current_cols = max(len(row) for row in current_grid) if current_grid else 0

    if pristine_rows != current_rows or pristine_cols != current_cols:
        raise GridDimensionChangedError(
            f"Grid dimensions changed from {pristine_rows}x{pristine_cols} "
            f"to {current_rows}x{current_cols}. "
            "Use imperative commands (extrasheet exec) for structural changes."
        )
```

### formula.json Changes

| Change | Detection Method | API Operation |
|--------|-----------------|---------------|
| New single-cell formula | Key present in edited, not in pristine | `updateCells` with `userEnteredValue.formulaValue` |
| New range formula | Range key present in edited, not in pristine | `updateCells` (first cell) + `autoFill` |
| Formula removed | Key present in pristine, not in edited | `updateCells` with `userEnteredValue` (value from data.tsv) |
| Formula modified (single cell) | Same key, different value | `updateCells` with `userEnteredValue.formulaValue` |
| Formula modified (range) | Same range key, different formula | `updateCells` (first cell) + `autoFill` |
| Formula range expanded | e.g., "A1:A5" → "A1:A10" | `autoFill` to extend |
| Formula range contracted | e.g., "A1:A10" → "A1:A5" | `updateCells` to clear removed cells |

**AutoFill for Formula Ranges:**

When a formula is associated with a range (e.g., `"C2:C100": "=A2+B2"`), the most efficient approach is:

1. Update the FIRST cell with the formula using `updateCells`
2. Use `autoFill` to copy the formula across the entire range

This is far more efficient than sending individual `updateCells` for each cell, and it properly handles relative references.

```python
def generate_formula_range_requests(
    range_key: str,
    formula: str,
    sheet_id: int,
) -> list[dict]:
    """
    Generate requests for a formula range change.

    Example: "C2:C100": "=A2+B2"

    1. updateCells: Set C2 = "=A2+B2"
    2. autoFill: Fill from C2 to C2:C100
    """
    start_cell, end_cell = parse_range(range_key)
    start_row, start_col = a1_to_cell(start_cell)
    end_row, end_col = a1_to_cell(end_cell)

    requests = []

    # 1. Set the formula in the first cell
    requests.append({
        "updateCells": {
            "rows": [{
                "values": [{
                    "userEnteredValue": {"formulaValue": formula}
                }]
            }],
            "fields": "userEnteredValue",
            "start": {
                "sheetId": sheet_id,
                "rowIndex": start_row,
                "columnIndex": start_col,
            }
        }
    })

    # 2. AutoFill to the entire range
    requests.append({
        "autoFill": {
            "useAlternateSeries": False,
            "sourceAndDestination": {
                "source": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": start_row + 1,
                    "startColumnIndex": start_col,
                    "endColumnIndex": start_col + 1,
                },
                "destination": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row + 1,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col + 1,
                },
                "fillLength": end_row - start_row,
            }
        }
    })

    return requests
```

**Why AutoFill is Critical:**

1. **Efficiency**: One API call vs. hundreds of `updateCells`
2. **Correctness**: Google Sheets handles relative reference adjustment
3. **Consistency**: Matches how users would manually drag formulas

### format.json Changes

| Change | Detection Method | API Operation |
|--------|-----------------|---------------|
| `formatRules` entry added | New range in edited | `repeatCell` or `updateCells` |
| `formatRules` entry removed | Range in pristine, not in edited | `repeatCell` to clear format |
| `formatRules` entry modified | Same range, different format | `repeatCell` with new format |
| `conditionalFormats` added | New index | `addConditionalFormatRule` |
| `conditionalFormats` removed | Index in pristine, not in edited | `deleteConditionalFormatRule` |
| `conditionalFormats` modified | Same index, different rule | `updateConditionalFormatRule` |
| `merges` added | New merge range | `mergeCells` |
| `merges` removed | Merge in pristine, not in edited | `unmergeCells` |
| `notes` added/modified | New/changed note | `updateCells` with `note` field |
| `notes` removed | Note in pristine, not in edited | `updateCells` with empty `note` |

### feature.json Changes

| Change | Detection Method | API Operation |
|--------|-----------------|---------------|
| `basicFilter` added | Present in edited, not pristine | `setBasicFilter` |
| `basicFilter` removed | Present in pristine, not edited | `clearBasicFilter` |
| `basicFilter` modified | Different filter specs | `setBasicFilter` (replaces) |
| `dataValidation` added | New validation group | `setDataValidation` |
| `dataValidation` removed | Group in pristine, not edited | `setDataValidation` with no rule |
| `dataValidation` modified | Different rule for same cells | `setDataValidation` |
| `bandedRanges` added | New banded range | `addBanding` |
| `bandedRanges` removed | Banded range in pristine only | `deleteBanding` |
| `bandedRanges` modified | Different colors/range | `updateBanding` |
| `charts` added | New chart | `addChart` |
| `charts` removed | Chart in pristine only | `deleteEmbeddedObject` |
| `charts` modified | Different spec | `updateChartSpec` |
| `tables` added | New table | `addTable` |
| `tables` removed | Table in pristine only | `deleteTable` |
| `tables` modified | Different config | `updateTable` |
| `filterViews` added | New filter view | `addFilterView` |
| `filterViews` removed | Filter view in pristine only | `deleteFilterView` |
| `filterViews` modified | Different filter specs | `updateFilterView` |
| `slicers` added | New slicer | `addSlicer` |
| `slicers` removed | Slicer in pristine only | `deleteEmbeddedObject` |
| `slicers` modified | Different spec | `updateSlicerSpec` |

### dimension.json Changes

| Change | Detection Method | API Operation |
|--------|-----------------|---------------|
| Row/column size changed | Different `pixelSize` | `updateDimensionProperties` |
| Row/column hidden | `hidden: true` added | `updateDimensionProperties` |
| Row/column unhidden | `hidden: true` removed | `updateDimensionProperties` |
| Row/column group added | New group in groups array | `addDimensionGroup` |
| Row/column group removed | Group in pristine only | `deleteDimensionGroup` |
| Group collapsed/expanded | Different `collapsed` value | `updateDimensionGroup` |

### named_ranges.json Changes

| Change | Detection Method | API Operation |
|--------|-----------------|---------------|
| Named range added | New name in edited | `addNamedRange` |
| Named range removed | Name in pristine only | `deleteNamedRange` |
| Named range modified | Same name, different range | `updateNamedRange` |

### theme.json Changes

| Change | Detection Method | API Operation |
|--------|-----------------|---------------|
| `defaultFormat` changed | Different format values | `updateSpreadsheetProperties` |
| `spreadsheetTheme` changed | Different theme colors | `updateSpreadsheetProperties` |

---

## Diff Algorithm

### Phase 1: Load and Parse

```python
async def diff(folder: Path) -> DiffResult:
    """
    Compare current files against pristine copy.

    Returns DiffResult containing all detected changes.
    """
    # 1. Extract pristine files from zip
    pristine = extract_pristine(folder / ".pristine" / "spreadsheet.zip")

    # 2. Load current files
    current = load_current_files(folder)

    # 3. Parse spreadsheet.json for sheet metadata
    pristine_meta = json.loads(pristine["spreadsheet.json"])
    current_meta = json.loads(current["spreadsheet.json"])

    # 4. Build sheet mapping (folder name → sheetId)
    sheet_mapping = build_sheet_mapping(current_meta)

    # 5. Diff each component
    result = DiffResult()

    # Spreadsheet-level changes
    result.spreadsheet_changes = diff_spreadsheet_properties(
        pristine_meta, current_meta
    )

    # Sheet-level changes
    for sheet in current_meta["sheets"]:
        folder_name = sheet["folder"]
        sheet_id = sheet["sheetId"]

        result.sheet_changes.append(
            diff_sheet(
                pristine, current, folder_name, sheet_id
            )
        )

    # Detect structural changes (to be run LAST)
    result.structural_changes = detect_structural_changes(
        pristine_meta, current_meta, pristine, current
    )

    return result
```

### Phase 2: Cell-Level Diffing

For data.tsv and formula.json, we need to diff at the cell level:

```python
def diff_sheet_data(
    pristine_tsv: str,
    current_tsv: str,
    pristine_formulas: dict,
    current_formulas: dict,
) -> tuple[list[CellChange], list[StructuralChange]]:
    """
    Diff cell data between pristine and current.

    Returns:
        - cell_changes: List of individual cell changes
        - structural_changes: List of insert/delete/move operations
    """
    cell_changes = []
    structural_changes = []

    # Parse TSV files
    pristine_grid = parse_tsv(pristine_tsv)
    current_grid = parse_tsv(current_tsv)

    # Detect structural changes first
    structural = detect_structural_changes(pristine_grid, current_grid)
    if structural:
        structural_changes.extend(structural)
        # Adjust cell positions based on structural changes
        # for proper content diffing
        adjusted_grid = apply_reverse_structural(current_grid, structural)
    else:
        adjusted_grid = current_grid

    # Expand formula ranges - DON'T expand to individual cells
    # Instead, compare ranges directly for efficiency
    pristine_ranges = pristine_formulas  # Keep as ranges
    current_ranges = current_formulas

    # Get dimensions (of original pristine coordinates)
    max_row = len(pristine_grid)
    max_col = max(len(row) for row in pristine_grid) if pristine_grid else 0

    # Compare each cell using pristine coordinates
    for row in range(max_row):
        for col in range(max_col):
            cell_ref = f"{col_to_letter(col)}{row + 1}"

            pristine_value = get_cell(pristine_grid, row, col)
            current_value = get_cell(adjusted_grid, row, col)

            # Check if cell is part of a formula range
            pristine_formula = get_formula_for_cell(pristine_ranges, cell_ref)
            current_formula = get_formula_for_cell(current_ranges, cell_ref)

            # ... rest of cell comparison logic

    return cell_changes, structural_changes
```

### Phase 3: Detecting Structural Changes

```python
def detect_structural_changes(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
) -> list[StructuralChange]:
    """
    Detect row/column insertions, deletions, and moves.

    Uses heuristics:
    1. If current has more rows and content shifted down → middle insert
    2. If current has more columns and content shifted right → middle insert
    """
    pristine_rows = len(pristine_grid)
    current_rows = len(current_grid)

    if current_rows > pristine_rows:
        # Check if it's an append (new rows at end) or insert (content shifted)
        # Compare first N rows - if they match, it's an append
        for i in range(min(pristine_rows, 10)):  # Check first 10 rows
            if pristine_grid[i] != current_grid[i]:
                # Content shifted - this is a middle insertion
                return True

    # Similar check for columns
    # ...

    return False
```

---

## Request Generation

### Building UpdateCells Requests

The most common operation is `updateCells`. We batch changes into ranges for efficiency:

```python
def generate_update_cells_requests(
    changes: list[CellChange],
    sheet_id: int,
) -> list[dict]:
    """
    Generate updateCells requests from cell changes.

    Groups adjacent cells into ranges for efficiency.
    """
    requests = []

    # Group changes by row for row-based batching
    changes_by_row = group_by_row(changes)

    for row_idx, row_changes in changes_by_row.items():
        # Build RowData with CellData for each changed cell
        row_data = build_row_data(row_changes)

        # Find the range this row covers
        start_col = min(c.col for c in row_changes)
        end_col = max(c.col for c in row_changes) + 1

        requests.append({
            "updateCells": {
                "rows": [row_data],
                "fields": "userEnteredValue",
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_idx,
                    "endRowIndex": row_idx + 1,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                }
            }
        })

    return requests


def build_row_data(changes: list[CellChange]) -> dict:
    """Build RowData object for updateCells."""
    # Sort by column
    changes = sorted(changes, key=lambda c: c.col)

    cells = []
    for change in changes:
        cell_data = {}

        if change.change_type == "formula":
            cell_data["userEnteredValue"] = {
                "formulaValue": change.new_value
            }
        elif change.change_type == "value":
            # Determine value type
            cell_data["userEnteredValue"] = infer_value_type(change.new_value)

        cells.append(cell_data)

    return {"values": cells}


def infer_value_type(value: str) -> dict:
    """
    Infer the ExtendedValue type from a string value.

    Returns appropriate userEnteredValue structure.
    """
    if value == "":
        return {}  # Empty cell

    # Try to parse as number
    try:
        num = float(value.replace(",", ""))
        return {"numberValue": num}
    except ValueError:
        pass

    # Check for boolean
    if value.upper() == "TRUE":
        return {"boolValue": True}
    if value.upper() == "FALSE":
        return {"boolValue": False}

    # Default to string
    return {"stringValue": value}
```

### Format Request Generation

```python
def generate_format_requests(
    format_changes: list[FormatChange],
    sheet_id: int,
) -> list[dict]:
    """Generate formatting requests from format changes."""
    requests = []

    for change in format_changes:
        if change.change_type == "add" or change.change_type == "modify":
            # Use repeatCell for efficient range formatting
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        **a1_to_grid_range(change.range),
                    },
                    "cell": {
                        "userEnteredFormat": change.format
                    },
                    "fields": build_format_fields(change.format),
                }
            })
        elif change.change_type == "remove":
            # Clear formatting by setting to default
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        **a1_to_grid_range(change.range),
                    },
                    "cell": {
                        "userEnteredFormat": {}
                    },
                    "fields": "userEnteredFormat",
                }
            })

    return requests
```

---

## Declarative Diff: Order Independence

In the declarative workflow, the diff engine compares pristine vs current state and generates the minimal set of API requests. Order doesn't matter because we're comparing states, not tracking changes.

### How Diff Works

```python
def diff(folder: Path) -> DiffResult:
    """
    Compare current files against pristine copy.

    Returns changes grouped by type, not ordered.
    """
    pristine = extract_pristine(folder / ".pristine" / "spreadsheet.zip")
    current = load_current_files(folder)

    return DiffResult(
        cell_changes=diff_cells(pristine, current),
        formula_changes=diff_formulas(pristine, current),
        format_changes=diff_formats(pristine, current),
        feature_changes=diff_features(pristine, current),
        property_changes=diff_properties(pristine, current),
    )
```

### Request Generation

The request generator converts diff results to API requests. While the diff is unordered, requests are batched efficiently:

```python
def generate_requests(diff: DiffResult) -> list[dict]:
    """
    Generate batchUpdate requests from diff.

    Batches changes for efficiency, but conceptually unordered.
    """
    requests = []

    # Cell changes → updateCells (batched by row)
    requests.extend(generate_cell_requests(diff.cell_changes))

    # Formula ranges → updateCells + autoFill
    requests.extend(generate_formula_requests(diff.formula_changes))

    # Format changes → repeatCell, updateBorders, etc.
    requests.extend(generate_format_requests(diff.format_changes))

    # Feature changes → add/update/delete operations
    requests.extend(generate_feature_requests(diff.feature_changes))

    # Property changes → updateSheetProperties, etc.
    requests.extend(generate_property_requests(diff.property_changes))

    return requests
```

### No Structural Operations in Declarative Workflow

The declarative workflow **never generates** structural operations:
- No `insertDimension`
- No `deleteDimension`
- No `moveDimension`
- No `sortRange`

If the diff detects a grid dimension change (more/fewer rows or columns), it raises an error:

```python
class GridDimensionChangedError(DiffError):
    """
    Local files have different grid dimensions than pristine.

    This happens when rows/columns were added/removed from data.tsv.
    Use imperative commands for structural changes.
    """
    pass
```

## Imperative Workflow: batchUpdate Command

Structural changes use the native Google Sheets batchUpdate format directly.

### CLI Interface

```bash
# Execute batchUpdate requests from JSON file
extrasheet batchUpdate <url_or_folder> <requests.json>

# After batchUpdate, re-pull to get updated state
extrasheet pull <url>
```

### Request Format

Uses the exact same format as the Google Sheets API - no new syntax to learn:

```json
{
  "requests": [
    {
      "insertDimension": {
        "range": {
          "sheetId": 0,
          "dimension": "COLUMNS",
          "startIndex": 2,
          "endIndex": 3
        }
      }
    },
    {
      "moveDimension": {
        "source": {
          "sheetId": 0,
          "dimension": "ROWS",
          "startIndex": 10,
          "endIndex": 15
        },
        "destinationIndex": 2
      }
    }
  ]
}
```

This is the same schema documented in `discovery.json` and used throughout the LLM agent guide.

### Implementation

```python
async def batch_update_command(
    url_or_folder: str,
    requests_file: Path,
) -> BatchUpdateResult:
    """Execute batchUpdate requests directly."""

    # Load requests from JSON file
    with open(requests_file) as f:
        payload = json.load(f)

    requests = payload.get("requests", [])
    if not requests:
        return BatchUpdateResult(success=True, message="No requests to execute")

    # Resolve spreadsheet ID
    spreadsheet_id = resolve_spreadsheet_id(url_or_folder)

    # Execute via API
    response = await transport.batch_update(spreadsheet_id, requests)

    return BatchUpdateResult(
        success=True,
        message=f"Executed {len(requests)} requests. Run 'extrasheet pull' to refresh.",
        response=response,
    )
```

### When to Use batchUpdate

Use `batchUpdate` for any operation that changes grid dimensions or structure:

| Operation | Example |
|-----------|---------|
| Insert rows/columns | `insertDimension` |
| Delete rows/columns | `deleteDimension` |
| Move rows/columns | `moveDimension` |
| Append rows/columns | `appendDimension` |
| Sort data | `sortRange` |
| Any other structural change | As needed |

### Convention: Re-pull After batchUpdate

After running `batchUpdate`, always re-pull before making further declarative edits:

```bash
extrasheet batchUpdate <url> requests.json
extrasheet pull <url>  # Refresh local state
```

This is a convention, not enforced by tooling. The reason: after structural changes, cell coordinates shift, so the local files no longer match the remote state.

---

## Supported Operations by Workflow

### Declarative Workflow (pull-diff-push)

All content and formatting operations are supported declaratively:

| Category | Operations | Notes |
|----------|-----------|-------|
| Cell values | `updateCells` | Diff detects value changes in data.tsv |
| Formulas | `updateCells` + `autoFill` | Diff detects formula.json changes |
| Cell formatting | `repeatCell`, `updateBorders` | Diff detects format.json changes |
| Conditional formatting | `add/update/deleteConditionalFormatRule` | Full support |
| Merges | `mergeCells`, `unmergeCells` | Diff detects merge changes |
| Notes | `updateCells` with note field | Diff detects note changes |
| Data validation | `setDataValidation` | Diff detects validation changes |
| Basic filter | `setBasicFilter`, `clearBasicFilter` | Full support |
| Filter views | `add/update/deleteFilterView` | Full support |
| Banded ranges | `add/update/deleteBanding` | Full support |
| Named ranges | `add/update/deleteNamedRange` | Full support |
| Charts | `addChart`, `updateChartSpec`, `deleteEmbeddedObject` | Full support |
| Tables | `add/update/deleteTable` | Full support |
| Slicers | `addSlicer`, `updateSlicerSpec` | Full support |
| Protected ranges | `add/update/deleteProtectedRange` | Full support |
| Sheet properties | `updateSheetProperties` | Title, frozen, hidden, tab color |
| Spreadsheet properties | `updateSpreadsheetProperties` | Title, locale, timezone |
| Dimension properties | `updateDimensionProperties` | Row/column size, hidden |
| Dimension groups | `add/update/deleteDimensionGroup` | Grouping support |
| Developer metadata | `create/update/deleteDeveloperMetadata` | Full support |
| Add new sheet | `addSheet` | Add entry to spreadsheet.json |
| Delete sheet | `deleteSheet` | Remove entry from spreadsheet.json |

### Imperative Workflow (exec command)

Structural operations require explicit imperative commands:

| Category | Operations | Notes |
|----------|-----------|-------|
| Insert rows/columns | `insertDimension` | Explicit command, requires re-pull |
| Delete rows/columns | `deleteDimension` | Explicit command, requires re-pull |
| Move rows/columns | `moveDimension` | Explicit command, requires re-pull |
| Insert cells | `insertRange` | Explicit command, requires re-pull |
| Delete cells | `deleteRange` | Explicit command, requires re-pull |
| Append rows/columns | `appendDimension` | Explicit command, requires re-pull |
| Sort data | `sortRange` | Explicit command, requires re-pull |

### Not Supported

| Category | Reason |
|----------|--------|
| Copy/paste operations | Use declarative: edit destination cells directly |
| Find/replace | Agent can edit files directly |
| Auto-resize dimensions | Not needed for most use cases |
| Duplicate sheet | Agent can create new sheet and copy content |
| Duplicate filter view | Agent can create new filter view |
| Data sources | Requires external BigQuery/Looker connections |
| Delete duplicates | Agent can identify and remove in data.tsv |
| Trim whitespace | Agent can edit values directly |
| Randomize range | Agent can reorder in data.tsv if needed |
| Text to columns | Agent can parse and write values |

---

## Error Handling

### Validation Errors

```python
class DiffValidationError(Exception):
    """Base class for diff validation errors."""
    pass

class InconsistentStateError(DiffValidationError):
    """Pristine and current state are inconsistent."""
    pass

class UnsupportedChangeError(DiffValidationError):
    """Change type is not supported."""
    pass

class MissingPristineError(DiffValidationError):
    """Pristine copy not found - need to re-pull."""
    pass
```

### API Errors

When push fails, we should provide helpful context:

```python
async def push(folder: Path) -> PushResult:
    """Apply changes to Google Sheets."""
    try:
        diff_result = await diff(folder)
        requests = generate_requests(diff_result)

        if not requests:
            return PushResult(success=True, changes=0, message="No changes to apply")

        # Log structural operations for visibility
        structural_ops = [r for r in requests if is_structural(r)]
        if structural_ops:
            log.info(f"Structural operations will run last: {len(structural_ops)}")

        response = await transport.batch_update(spreadsheet_id, requests)
        return PushResult(
            success=True,
            changes=len(requests),
            message=f"Applied {len(requests)} changes",
        )

    except DiffValidationError as e:
        return PushResult(
            success=False,
            error="validation_error",
            message=str(e),
        )

    except APIError as e:
        # Parse API error for helpful message
        return PushResult(
            success=False,
            error="api_error",
            message=f"Google Sheets API error: {e.message}",
            details=e.details,
        )
```

---

## Testing Strategy

### Unit Tests

1. **Diff detection tests** - Verify correct change detection for each file type
2. **Request generation tests** - Verify correct batchUpdate JSON structure
3. **Structural operation detection** - Verify correct ordering of structural operations
4. **AutoFill generation** - Verify formula ranges generate updateCells + autoFill
5. **Edge cases** - Empty sheets, large sheets, special characters

### Integration Tests

1. **Golden file tests** - Use saved API responses to verify round-trip
2. **End-to-end tests** - Pull, modify, diff, verify requests

### Test Data

Create golden files with:
- Simple sheet with values only
- Sheet with formulas
- Sheet with formatting
- Sheet with all features
- Large sheet (performance testing)

---

## Implementation Plan

### Core Infrastructure

1. **DiffResult data structures**
   - `SpreadsheetChange` - spreadsheet-level property changes
   - `SheetChange` - sheet-level changes (add, delete, modify properties)
   - `CellChange` - individual cell changes (value, formula)
   - `FormulaRangeChange` - formula range changes (for autoFill)
   - `FormatChange` - formatting changes
   - `FeatureChange` - feature changes (charts, filters, etc.)

2. **Pristine extraction**
   - Extract `.pristine/spreadsheet.zip`
   - Parse all file types
   - Build comparison structures

3. **Grid dimension validation**
   - Verify row/column counts match between pristine and current
   - Raise `GridDimensionChangedError` if dimensions differ

### Declarative Workflow: Diff

4. **data.tsv diffing**
   - Validate grid dimensions match
   - Cell-by-cell comparison within fixed grid
   - Generate `CellChange` for each modified cell

5. **formula.json diffing**
   - Range-level comparison
   - Detect new/modified/deleted ranges
   - Track first cell + range for autoFill generation

6. **format.json diffing**
   - `formatRules` comparison
   - `conditionalFormats` comparison
   - `merges` comparison
   - `notes` and `textFormatRuns` comparison

7. **feature.json diffing**
   - Charts, tables, filters, slicers
   - Data validation groups
   - Banded ranges

8. **Other file diffing**
   - dimension.json (row/column sizes, hidden, groups)
   - spreadsheet.json (sheet properties, named ranges)
   - theme.json (default format, theme colors)

### Declarative Workflow: Request Generation

9. **Cell request generation**
   - `updateCells` for value/formula changes
   - `autoFill` for formula ranges
   - Batch by row for efficiency

10. **Format request generation**
    - `repeatCell` for range formatting
    - `updateBorders` for borders
    - `add/update/deleteConditionalFormatRule`
    - `mergeCells` / `unmergeCells`

11. **Feature request generation**
    - `addChart`, `updateChartSpec`, `deleteEmbeddedObject`
    - `addTable`, `updateTable`, `deleteTable`
    - `add/update/deleteFilterView`
    - `setBasicFilter`, `clearBasicFilter`
    - `setDataValidation`
    - `add/update/deleteBanding`
    - `addSlicer`, `updateSlicerSpec`
    - `add/update/deleteProtectedRange`

### Imperative Workflow: batchUpdate Command

12. **batchUpdate command**
    - Load requests from JSON file
    - Validate JSON structure
    - Execute via Google Sheets API
    - Return response

### CLI Commands

13. **Declarative commands**
    - `extrasheet diff <folder>` - output batchUpdate JSON
    - `extrasheet push <folder>` - apply declarative changes

14. **Imperative command**
    - `extrasheet batchUpdate <url> <requests.json>` - execute any batchUpdate requests

### Testing

15. **Golden file tests**
    - Create test spreadsheets with all features
    - Pull, modify, diff, verify requests
    - Test grid dimension validation errors

16. **batchUpdate tests**
    - Test request loading from JSON
    - Test API execution
