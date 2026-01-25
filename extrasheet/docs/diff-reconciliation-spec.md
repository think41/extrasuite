# ExtraSheet Diff and Reconciliation Specification

This document specifies how changes between two versions of an ExtraSheet directory are detected, compared, and transformed into Google Sheets API batchUpdate requests.

---

## Table of Contents

1. [Overview](#overview)
2. [Diff Pipeline](#diff-pipeline)
3. [Data Layer Diff](#data-layer-diff)
4. [Formula Layer Diff](#formula-layer-diff)
5. [Format Layer Diff](#format-layer-diff)
6. [Feature Layer Diff](#feature-layer-diff)
7. [Manifest Diff](#manifest-diff)
8. [Change Representation](#change-representation)
9. [Conflict Detection](#conflict-detection)
10. [Request Generation](#request-generation)
11. [Request Ordering](#request-ordering)
12. [Optimization Strategies](#optimization-strategies)
13. [Error Handling](#error-handling)

---

## Overview

### The Reconciliation Problem

Given:
- **Original**: The ExtraSheet state pulled from Google Sheets
- **Edited**: The ExtraSheet state after local modifications

Produce:
- **Changes**: A minimal set of differences
- **Requests**: Google Sheets API batchUpdate requests to apply changes

### Design Goals

1. **Minimal changes**: Only update what actually changed
2. **Efficient batching**: Combine multiple cell updates into single API calls
3. **Correct ordering**: Satisfy dependencies between operations
4. **Conflict detection**: Identify when changes may conflict
5. **Reversibility**: Enable undo by generating inverse operations

---

## Diff Pipeline

```
┌─────────────┐    ┌─────────────┐
│  Original   │    │   Edited    │
│ ExtraSheet  │    │ ExtraSheet  │
└──────┬──────┘    └──────┬──────┘
       │                   │
       └────────┬──────────┘
                │
       ┌────────▼────────┐
       │   File Differ   │
       │  (per file type)│
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │  Change Set     │
       │  (by category)  │
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │ Request Builder │
       │  (ordered list) │
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │   Optimizer     │
       │  (batch/merge)  │
       └────────┬────────┘
                │
                ▼
        batchUpdate API
```

---

## Data Layer Diff

### Input Files
- `sheets/{name}/data.tsv` (original)
- `sheets/{name}/data.tsv` (edited)

### Algorithm

```python
def diff_data(original_tsv: str, edited_tsv: str) -> list[CellChange]:
    """Diff two TSV files cell by cell."""
    original = parse_tsv(original_tsv)
    edited = parse_tsv(edited_tsv)
    changes = []

    # Get all cell coordinates
    all_cells = set(original.keys()) | set(edited.keys())

    for (row, col) in all_cells:
        orig_val = original.get((row, col))
        edit_val = edited.get((row, col))

        if orig_val is None and edit_val is not None:
            changes.append(CellChange(
                type=ChangeType.ADDED,
                sheet=sheet_name,
                row=row,
                col=col,
                new_value=edit_val
            ))
        elif orig_val is not None and edit_val is None:
            changes.append(CellChange(
                type=ChangeType.DELETED,
                sheet=sheet_name,
                row=row,
                col=col,
                old_value=orig_val
            ))
        elif orig_val != edit_val:
            changes.append(CellChange(
                type=ChangeType.MODIFIED,
                sheet=sheet_name,
                row=row,
                col=col,
                old_value=orig_val,
                new_value=edit_val
            ))

    return changes
```

### TSV Parsing

```python
def parse_tsv(content: str) -> dict[tuple[int, int], str]:
    """Parse TSV into cell dictionary."""
    cells = {}
    for row_idx, line in enumerate(content.split('\n')):
        if line:  # Skip empty lines
            values = line.split('\t')
            for col_idx, value in enumerate(values):
                if value:  # Only store non-empty cells
                    cells[(row_idx, col_idx)] = unescape(value)
    return cells

def unescape(value: str) -> str:
    """Unescape TSV special characters."""
    return value.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
```

### Dimension Changes

Detect when grid size changes:

```python
def detect_dimension_changes(original, edited):
    orig_rows = max(r for r, c in original.keys()) + 1 if original else 0
    orig_cols = max(c for r, c in original.keys()) + 1 if original else 0
    edit_rows = max(r for r, c in edited.keys()) + 1 if edited else 0
    edit_cols = max(c for r, c in edited.keys()) + 1 if edited else 0

    changes = []
    if edit_rows > orig_rows:
        changes.append(DimensionChange(type='add_rows', count=edit_rows - orig_rows))
    if edit_cols > orig_cols:
        changes.append(DimensionChange(type='add_columns', count=edit_cols - orig_cols))
    return changes
```

---

## Formula Layer Diff

### Input Files
- `sheets/{name}/formulas.json` (original)
- `sheets/{name}/formulas.json` (edited)

### Algorithm

```python
def diff_formulas(original_json: dict, edited_json: dict) -> list[FormulaChange]:
    """Diff formula dictionaries."""
    changes = []
    all_addresses = set(original_json.keys()) | set(edited_json.keys())

    for addr in all_addresses:
        orig = original_json.get(addr)
        edit = edited_json.get(addr)

        if orig is None and edit is not None:
            changes.append(FormulaChange(
                type=ChangeType.ADDED,
                address=addr,
                formula=edit
            ))
        elif orig is not None and edit is None:
            changes.append(FormulaChange(
                type=ChangeType.DELETED,
                address=addr,
                old_formula=orig
            ))
        elif orig != edit:
            changes.append(FormulaChange(
                type=ChangeType.MODIFIED,
                address=addr,
                old_formula=orig,
                new_formula=edit
            ))

    return changes
```

### Formula Normalization

Before comparison, normalize formulas:

```python
def normalize_formula(formula: str) -> str:
    """Normalize formula for comparison."""
    # Remove leading =
    if formula.startswith('='):
        formula = formula[1:]
    # Uppercase function names
    # (but preserve string literals)
    return formula  # Actual implementation more complex
```

---

## Format Layer Diff

### Input Files
- `sheets/{name}/format.json` (original)
- `sheets/{name}/format.json` (edited)

### Algorithm

Format diff is more complex due to range-based rules.

```python
def diff_format(original: dict, edited: dict) -> list[FormatChange]:
    changes = []

    # Diff dimensions
    changes.extend(diff_dimensions(
        original.get('dimensions', {}),
        edited.get('dimensions', {})
    ))

    # Diff merges
    changes.extend(diff_merges(
        original.get('merges', []),
        edited.get('merges', [])
    ))

    # Diff format rules
    changes.extend(diff_format_rules(
        original.get('rules', []),
        edited.get('rules', [])
    ))

    return changes
```

### Dimension Diff

```python
def diff_dimensions(original: dict, edited: dict) -> list[DimensionChange]:
    changes = []

    # Row heights
    orig_heights = original.get('rowHeights', {})
    edit_heights = edited.get('rowHeights', {})
    for row in set(orig_heights.keys()) | set(edit_heights.keys()):
        if orig_heights.get(row) != edit_heights.get(row):
            changes.append(RowHeightChange(
                row=int(row),
                height=edit_heights.get(row)  # None means default
            ))

    # Column widths
    orig_widths = original.get('columnWidths', {})
    edit_widths = edited.get('columnWidths', {})
    for col in set(orig_widths.keys()) | set(edit_widths.keys()):
        if orig_widths.get(col) != edit_widths.get(col):
            changes.append(ColumnWidthChange(
                column=col,
                width=edit_widths.get(col)
            ))

    return changes
```

### Merge Diff

```python
def diff_merges(original: list, edited: list) -> list[MergeChange]:
    original_set = set(original)
    edited_set = set(edited)

    changes = []

    # New merges
    for merge in edited_set - original_set:
        changes.append(MergeChange(type=ChangeType.ADDED, range=merge))

    # Removed merges
    for merge in original_set - edited_set:
        changes.append(MergeChange(type=ChangeType.DELETED, range=merge))

    return changes
```

### Format Rule Diff

Format rules are compared by content, not position:

```python
def diff_format_rules(original: list, edited: list) -> list[FormatRuleChange]:
    """Compare format rules, detecting additions, deletions, and modifications."""
    changes = []

    # Create fingerprints for matching
    orig_by_range = {rule['range']: rule for rule in original}
    edit_by_range = {rule['range']: rule for rule in edited}

    for range_key in set(orig_by_range.keys()) | set(edit_by_range.keys()):
        orig_rule = orig_by_range.get(range_key)
        edit_rule = edit_by_range.get(range_key)

        if orig_rule is None:
            changes.append(FormatRuleChange(
                type=ChangeType.ADDED,
                range=range_key,
                format=edit_rule['format']
            ))
        elif edit_rule is None:
            changes.append(FormatRuleChange(
                type=ChangeType.DELETED,
                range=range_key
            ))
        elif orig_rule['format'] != edit_rule['format']:
            changes.append(FormatRuleChange(
                type=ChangeType.MODIFIED,
                range=range_key,
                old_format=orig_rule['format'],
                new_format=edit_rule['format']
            ))

    return changes
```

---

## Feature Layer Diff

### Input Files
- `sheets/{name}/features.json` (original)
- `sheets/{name}/features.json` (edited)

### Algorithm

Features are matched by their unique IDs:

```python
def diff_features(original: dict, edited: dict) -> list[FeatureChange]:
    changes = []

    # Diff each feature type
    changes.extend(diff_charts(
        original.get('charts', []),
        edited.get('charts', [])
    ))
    changes.extend(diff_conditional_formats(
        original.get('conditionalFormats', []),
        edited.get('conditionalFormats', [])
    ))
    changes.extend(diff_data_validations(
        original.get('dataValidations', []),
        edited.get('dataValidations', [])
    ))
    # ... other feature types

    return changes
```

### Chart Diff

```python
def diff_charts(original: list, edited: list) -> list[ChartChange]:
    orig_by_id = {c['chartId']: c for c in original}
    edit_by_id = {c['chartId']: c for c in edited}

    changes = []

    for chart_id in set(orig_by_id.keys()) | set(edit_by_id.keys()):
        orig = orig_by_id.get(chart_id)
        edit = edit_by_id.get(chart_id)

        if orig is None:
            changes.append(ChartChange(
                type=ChangeType.ADDED,
                chart=edit
            ))
        elif edit is None:
            changes.append(ChartChange(
                type=ChangeType.DELETED,
                chartId=chart_id
            ))
        elif orig != edit:
            # Detailed diff for modifications
            changes.append(ChartChange(
                type=ChangeType.MODIFIED,
                chartId=chart_id,
                old_chart=orig,
                new_chart=edit,
                changed_fields=get_changed_fields(orig, edit)
            ))

    return changes
```

---

## Manifest Diff

### Input Files
- `manifest.json` (original)
- `manifest.json` (edited)

### Algorithm

```python
def diff_manifest(original: dict, edited: dict) -> list[ManifestChange]:
    changes = []

    # Spreadsheet properties
    for prop in ['title', 'locale', 'timeZone', 'autoRecalc']:
        if original.get(prop) != edited.get(prop):
            changes.append(SpreadsheetPropertyChange(
                property=prop,
                old_value=original.get(prop),
                new_value=edited.get(prop)
            ))

    # Sheet changes
    changes.extend(diff_sheets(
        original.get('sheets', []),
        edited.get('sheets', [])
    ))

    return changes

def diff_sheets(original: list, edited: list) -> list[SheetChange]:
    orig_by_id = {s['sheetId']: s for s in original}
    edit_by_id = {s['sheetId']: s for s in edited}

    changes = []

    for sheet_id in set(orig_by_id.keys()) | set(edit_by_id.keys()):
        orig = orig_by_id.get(sheet_id)
        edit = edit_by_id.get(sheet_id)

        if orig is None:
            changes.append(SheetChange(type=ChangeType.ADDED, sheet=edit))
        elif edit is None:
            changes.append(SheetChange(type=ChangeType.DELETED, sheetId=sheet_id))
        else:
            # Check for property changes
            for prop in ['title', 'index', 'hidden', 'tabColor']:
                if orig.get(prop) != edit.get(prop):
                    changes.append(SheetPropertyChange(
                        sheetId=sheet_id,
                        property=prop,
                        old_value=orig.get(prop),
                        new_value=edit.get(prop)
                    ))

    return changes
```

---

## Change Representation

### Change Types

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any, Optional

class ChangeType(Enum):
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"

@dataclass
class CellChange:
    type: ChangeType
    sheet: str
    row: int
    col: int
    old_value: Optional[str] = None
    new_value: Optional[str] = None

@dataclass
class FormulaChange:
    type: ChangeType
    sheet: str
    address: str
    old_formula: Optional[str] = None
    new_formula: Optional[str] = None

@dataclass
class FormatRuleChange:
    type: ChangeType
    sheet: str
    range: str
    old_format: Optional[dict] = None
    new_format: Optional[dict] = None

@dataclass
class ChartChange:
    type: ChangeType
    sheet: str
    chartId: Optional[int] = None
    old_chart: Optional[dict] = None
    new_chart: Optional[dict] = None

@dataclass
class SheetChange:
    type: ChangeType
    sheetId: Optional[int] = None
    sheet: Optional[dict] = None
```

### Change Set

```python
@dataclass
class ChangeSet:
    """Complete set of changes between two ExtraSheet versions."""

    # Structural changes
    sheet_changes: list[SheetChange]

    # Per-sheet changes (keyed by sheet name)
    cell_changes: dict[str, list[CellChange]]
    formula_changes: dict[str, list[FormulaChange]]
    format_changes: dict[str, list[FormatRuleChange]]
    merge_changes: dict[str, list[MergeChange]]
    dimension_changes: dict[str, list[DimensionChange]]

    # Feature changes
    chart_changes: dict[str, list[ChartChange]]
    conditional_format_changes: dict[str, list[ConditionalFormatChange]]
    validation_changes: dict[str, list[ValidationChange]]
    filter_changes: dict[str, list[FilterChange]]

    # Spreadsheet-level changes
    spreadsheet_property_changes: list[SpreadsheetPropertyChange]
    named_range_changes: list[NamedRangeChange]
```

---

## Conflict Detection

### Conflict Types

| Conflict | Description | Resolution |
|----------|-------------|------------|
| **Cell conflict** | Same cell modified differently | User choice or last-write-wins |
| **Formula vs Value** | Cell changed to value in one, formula in other | User choice |
| **Merge overlap** | Conflicting merge regions | Reject later operation |
| **Chart position** | Charts overlap | Allow (Sheets handles) |
| **Sheet deleted** | Sheet deleted but also modified | Prioritize deletion |

### Detection Algorithm

```python
def detect_conflicts(change_set_a: ChangeSet, change_set_b: ChangeSet) -> list[Conflict]:
    """Detect conflicts between two change sets."""
    conflicts = []

    # Cell conflicts
    for sheet in set(change_set_a.cell_changes.keys()) & set(change_set_b.cell_changes.keys()):
        a_cells = {(c.row, c.col): c for c in change_set_a.cell_changes[sheet]}
        b_cells = {(c.row, c.col): c for c in change_set_b.cell_changes[sheet]}

        for coord in set(a_cells.keys()) & set(b_cells.keys()):
            a_change = a_cells[coord]
            b_change = b_cells[coord]

            if a_change.new_value != b_change.new_value:
                conflicts.append(CellConflict(
                    sheet=sheet,
                    row=coord[0],
                    col=coord[1],
                    value_a=a_change.new_value,
                    value_b=b_change.new_value
                ))

    return conflicts
```

---

## Request Generation

### Cell Updates

```python
def generate_cell_update_request(
    sheet_id: int,
    changes: list[CellChange]
) -> dict:
    """Generate UpdateCellsRequest for multiple cell changes."""

    # Group changes into contiguous regions for efficiency
    regions = group_into_regions(changes)

    requests = []
    for region in regions:
        rows = []
        for row_idx in range(region.start_row, region.end_row):
            row_data = []
            for col_idx in range(region.start_col, region.end_col):
                change = region.get_cell(row_idx, col_idx)
                if change:
                    row_data.append({
                        "userEnteredValue": value_to_api(change.new_value)
                    })
                else:
                    row_data.append({})  # Keep existing
            rows.append({"values": row_data})

        requests.append({
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": region.start_row,
                    "endRowIndex": region.end_row,
                    "startColumnIndex": region.start_col,
                    "endColumnIndex": region.end_col
                },
                "rows": rows,
                "fields": "userEnteredValue"
            }
        })

    return requests

def value_to_api(value: str) -> dict:
    """Convert value to API format."""
    if value.startswith('='):
        return {"formulaValue": value}
    try:
        return {"numberValue": float(value)}
    except ValueError:
        if value.upper() in ('TRUE', 'FALSE'):
            return {"boolValue": value.upper() == 'TRUE'}
        return {"stringValue": value}
```

### Formula Updates

```python
def generate_formula_request(
    sheet_id: int,
    changes: list[FormulaChange]
) -> list[dict]:
    """Generate requests for formula changes."""
    requests = []

    for change in changes:
        row, col = a1_to_indices(change.address)

        if change.type == ChangeType.DELETED:
            # Clear formula, keep value (from data.tsv)
            # Value update handled separately
            pass
        else:
            requests.append({
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row,
                        "endRowIndex": row + 1,
                        "startColumnIndex": col,
                        "endColumnIndex": col + 1
                    },
                    "rows": [{
                        "values": [{
                            "userEnteredValue": {
                                "formulaValue": change.new_formula
                            }
                        }]
                    }],
                    "fields": "userEnteredValue"
                }
            })

    return requests
```

### Format Updates

```python
def generate_format_request(
    sheet_id: int,
    change: FormatRuleChange
) -> dict:
    """Generate format update request."""
    range_obj = a1_range_to_grid(sheet_id, change.range)

    return {
        "repeatCell": {
            "range": range_obj,
            "cell": {
                "userEnteredFormat": format_to_api(change.new_format)
            },
            "fields": fields_for_format(change.new_format)
        }
    }

def format_to_api(fmt: dict) -> dict:
    """Convert format dict to API format."""
    api_format = {}

    if 'bold' in fmt:
        api_format.setdefault('textFormat', {})['bold'] = fmt['bold']
    if 'italic' in fmt:
        api_format.setdefault('textFormat', {})['italic'] = fmt['italic']
    if 'fontSize' in fmt:
        api_format.setdefault('textFormat', {})['fontSize'] = fmt['fontSize']
    if 'textColor' in fmt:
        api_format.setdefault('textFormat', {})['foregroundColor'] = hex_to_color(fmt['textColor'])
    if 'backgroundColor' in fmt:
        api_format['backgroundColor'] = hex_to_color(fmt['backgroundColor'])
    if 'horizontalAlign' in fmt:
        api_format['horizontalAlignment'] = fmt['horizontalAlign']
    if 'numberFormat' in fmt:
        api_format['numberFormat'] = fmt['numberFormat']
    # ... other properties

    return api_format
```

### Chart Updates

```python
def generate_chart_request(change: ChartChange) -> dict:
    """Generate chart request."""
    if change.type == ChangeType.ADDED:
        return {
            "addChart": {
                "chart": chart_to_api(change.new_chart)
            }
        }
    elif change.type == ChangeType.DELETED:
        return {
            "deleteEmbeddedObject": {
                "objectId": change.chartId
            }
        }
    else:  # MODIFIED
        return {
            "updateChartSpec": {
                "chartId": change.chartId,
                "spec": chart_spec_to_api(change.new_chart['spec'])
            }
        }
```

---

## Request Ordering

### Dependency Graph

Requests must be ordered to satisfy dependencies:

```
1. STRUCTURAL CREATES
   ├── AddSheetRequest
   ├── InsertDimensionRequest
   └── AddNamedRangeRequest

2. CONTENT UPDATES
   ├── UpdateCellsRequest (values + formulas)
   └── PasteDataRequest

3. FORMAT UPDATES
   ├── RepeatCellRequest
   ├── UpdateBordersRequest
   ├── MergeCellsRequest
   └── UpdateDimensionPropertiesRequest

4. FEATURE CREATES
   ├── AddChartRequest
   ├── AddConditionalFormatRuleRequest
   ├── SetDataValidationRequest
   └── AddProtectedRangeRequest

5. FEATURE UPDATES
   ├── UpdateChartSpecRequest
   ├── UpdateConditionalFormatRuleRequest
   └── UpdateProtectedRangeRequest

6. DELETIONS (reverse order)
   ├── DeleteEmbeddedObjectRequest (charts)
   ├── DeleteConditionalFormatRuleRequest
   ├── UnmergeCellsRequest
   ├── DeleteDimensionRequest
   └── DeleteSheetRequest
```

### Ordering Algorithm

```python
def order_requests(requests: list[dict]) -> list[dict]:
    """Order requests by dependency phase."""
    phases = {
        'structural_creates': [],
        'content_updates': [],
        'format_updates': [],
        'feature_creates': [],
        'feature_updates': [],
        'deletions': []
    }

    for req in requests:
        phase = classify_request(req)
        phases[phase].append(req)

    # Build ordered list
    ordered = []
    ordered.extend(phases['structural_creates'])
    ordered.extend(phases['content_updates'])
    ordered.extend(phases['format_updates'])
    ordered.extend(phases['feature_creates'])
    ordered.extend(phases['feature_updates'])
    ordered.extend(reversed(phases['deletions']))  # Reverse order

    return ordered

def classify_request(req: dict) -> str:
    """Classify request into ordering phase."""
    req_type = list(req.keys())[0]

    if req_type in ['addSheet', 'insertDimension', 'addNamedRange']:
        return 'structural_creates'
    elif req_type in ['updateCells', 'pasteData', 'appendCells']:
        return 'content_updates'
    elif req_type in ['repeatCell', 'updateBorders', 'mergeCells',
                      'updateDimensionProperties', 'updateSheetProperties']:
        return 'format_updates'
    elif req_type in ['addChart', 'addConditionalFormatRule',
                      'setDataValidation', 'addProtectedRange']:
        return 'feature_creates'
    elif req_type in ['updateChartSpec', 'updateConditionalFormatRule',
                      'updateProtectedRange']:
        return 'feature_updates'
    else:  # Deletions
        return 'deletions'
```

---

## Optimization Strategies

### 1. Region Batching

Combine adjacent cell updates into rectangular regions:

```python
def group_into_regions(changes: list[CellChange]) -> list[Region]:
    """Group cell changes into rectangular regions."""
    # Sort by row, then column
    changes.sort(key=lambda c: (c.row, c.col))

    regions = []
    current_region = None

    for change in changes:
        if current_region and current_region.can_extend(change):
            current_region.add(change)
        else:
            if current_region:
                regions.append(current_region)
            current_region = Region(change)

    if current_region:
        regions.append(current_region)

    return regions
```

### 2. Format Deduplication

Combine identical format rules:

```python
def dedupe_format_requests(requests: list[dict]) -> list[dict]:
    """Combine format requests with identical formats."""
    by_format = defaultdict(list)

    for req in requests:
        if 'repeatCell' in req:
            format_key = json.dumps(req['repeatCell']['cell'], sort_keys=True)
            by_format[format_key].append(req['repeatCell']['range'])

    deduped = []
    for format_key, ranges in by_format.items():
        cell = json.loads(format_key)
        # Could combine ranges if adjacent
        for range_obj in ranges:
            deduped.append({
                "repeatCell": {
                    "range": range_obj,
                    "cell": cell,
                    "fields": infer_fields(cell)
                }
            })

    return deduped
```

### 3. Skip No-Op Changes

Filter out changes that don't actually change anything:

```python
def filter_noop_changes(changes: list[CellChange]) -> list[CellChange]:
    """Remove changes where old == new."""
    return [c for c in changes if c.old_value != c.new_value]
```

### 4. Request Merging

Combine multiple requests of the same type:

```python
def merge_update_cells_requests(requests: list[dict]) -> list[dict]:
    """Merge UpdateCellsRequest for same sheet."""
    by_sheet = defaultdict(list)

    for req in requests:
        if 'updateCells' in req:
            sheet_id = req['updateCells']['range']['sheetId']
            by_sheet[sheet_id].append(req)

    # Merge requests for each sheet
    merged = []
    for sheet_id, sheet_requests in by_sheet.items():
        # Implementation depends on adjacency
        merged.extend(merge_adjacent_updates(sheet_requests))

    return merged
```

---

## Error Handling

### Validation Errors

Catch errors before API call:

```python
def validate_changes(change_set: ChangeSet) -> list[ValidationError]:
    """Validate changes before generating requests."""
    errors = []

    # Check for invalid cell references
    for sheet, changes in change_set.cell_changes.items():
        for change in changes:
            if change.row < 0 or change.col < 0:
                errors.append(ValidationError(
                    f"Invalid cell position: ({change.row}, {change.col})"
                ))

    # Check for invalid formulas
    for sheet, changes in change_set.formula_changes.items():
        for change in changes:
            if change.new_formula and not change.new_formula.startswith('='):
                errors.append(ValidationError(
                    f"Formula must start with '=': {change.new_formula}"
                ))

    return errors
```

### API Errors

Handle API errors gracefully:

```python
def apply_changes_with_retry(
    service,
    spreadsheet_id: str,
    requests: list[dict],
    max_retries: int = 3
) -> dict:
    """Apply changes with retry logic."""
    for attempt in range(max_retries):
        try:
            return service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests}
            ).execute()
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:  # Retryable
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise

    raise Exception(f"Failed after {max_retries} retries")
```

### Partial Failure Recovery

If batchUpdate partially fails:

```python
def handle_partial_failure(
    error: HttpError,
    requests: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Split requests into succeeded and failed."""
    # Parse error response for failure index
    # Return (completed, failed) for retry
    pass
```

---

## Appendix: Utility Functions

### A1 Notation Conversion

```python
def a1_to_indices(a1: str) -> tuple[int, int]:
    """Convert A1 notation to (row, col) indices."""
    import re
    match = re.match(r'^([A-Z]+)(\d+)$', a1.upper())
    if not match:
        raise ValueError(f"Invalid A1 notation: {a1}")

    col_str, row_str = match.groups()

    # Column: A=0, B=1, ..., Z=25, AA=26, ...
    col = 0
    for char in col_str:
        col = col * 26 + (ord(char) - ord('A') + 1)
    col -= 1  # 0-indexed

    row = int(row_str) - 1  # 0-indexed

    return (row, col)

def indices_to_a1(row: int, col: int) -> str:
    """Convert (row, col) indices to A1 notation."""
    col_str = ""
    c = col + 1
    while c > 0:
        c, remainder = divmod(c - 1, 26)
        col_str = chr(ord('A') + remainder) + col_str

    return f"{col_str}{row + 1}"
```

### Color Conversion

```python
def hex_to_color(hex_color: str) -> dict:
    """Convert hex color to API Color object."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}

def color_to_hex(color: dict) -> str:
    """Convert API Color object to hex."""
    r = int(color.get('red', 0) * 255)
    g = int(color.get('green', 0) * 255)
    b = int(color.get('blue', 0) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"
```
