---
name: gsheet
description: Read, write, and manipulate Google Sheets. Use when user asks to work with Google Sheets, spreadsheets, or shares a docs.google.com/spreadsheets URL.
---

# Google Sheets Skill

Work with Google Sheets using Python and the gspread library.

## Initialization

**Step 1: Run environment checks (ALWAYS run first)**
```bash
python3 ~/.claude/skills/gsheets/checks.py
```
Creates virtual environment and installs dependencies. On failure, provides setup instructions.

**Step 2: Verify spreadsheet access**
```bash
~/.claude/skills/gsheets/venv/bin/python ~/.claude/skills/gsheets/verify_access.py <spreadsheet_url>
```
Authenticates via Google Workspace Gateway (opens browser if needed) and confirms access to the sheet. On failure, provides sharing instructions with the service account email.

**Step 3: Execute your code**
```bash
~/.claude/skills/gsheets/venv/bin/python your_script.py
```
All scripts use the skill's venv Python to access installed packages.

---

## Workflow Overview

### Table-First Approach

For worksheets with tabular data, check if it should be treated as a table:

```python
import os
import sys
sys.path.insert(0, os.path.expanduser("~/.claude/skills/gsheets"))
from gsheet_utils import open_sheet, get_shape, has_table, convert_to_table

sheet = open_sheet("https://docs.google.com/spreadsheets/d/.../edit")
ws = sheet.worksheet("Sheet1")

# Check worksheet shape - returns first/last rows for assessment
shape = get_shape(ws)
# Returns: total_rows, total_cols, first_rows, last_rows, has_data

# Check if table exists
table_info = has_table(ws)
if table_info["has_table"]:
    # Work in table mode
    pass
else:
    # Consider converting to table after reviewing shape
    convert_to_table(ws)
```

### Analysis Workflow

For data analysis, download as CSV first using gspread's export method:

```python
from gsheet_utils import open_sheet
from gspread.utils import ExportFormat

sheet = open_sheet("https://docs.google.com/spreadsheets/d/.../edit")
ws = sheet.worksheet("Data")

# Export worksheet as CSV
csv_data = ws.export(format=ExportFormat.CSV)
with open("data.csv", "wb") as f:
    f.write(csv_data)

# Analyze locally, then add formulas/columns back to sheet
```

---

## Custom Utilities (gsheet_utils.py)

These functions extend gspread with capabilities it doesn't have:

### open_sheet(url)

Open spreadsheet with automatic authentication via Google Workspace Gateway:

```python
from gsheet_utils import open_sheet

sheet = open_sheet("https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit")
ws = sheet.worksheet("Sheet1")
```

### get_shape(ws)

Get first/last rows for LLM to assess table structure:

```python
from gsheet_utils import get_shape

shape = get_shape(ws)
# Returns:
# {
#     "total_rows": 150,
#     "total_cols": 10,
#     "first_rows": [["Header1", "Header2", ...], ["Row2", ...], ...],
#     "first_row_numbers": [1, 2, 3, 4, 5],
#     "last_rows": [["Row148", ...], ["Row149", ...], ["Row150", ...]],
#     "last_row_numbers": [148, 149, 150],
#     "has_data": True
# }
```

Use this to determine:
- Does first row look like headers?
- Are rows consistently shaped?
- Should some rows/columns be deleted before converting to table?

### has_table(ws)

Check if worksheet has a table defined:

```python
from gsheet_utils import has_table

table_info = has_table(ws)
if table_info["has_table"]:
    for t in table_info["tables"]:
        print(t["name"], t["columns"])
```

### convert_to_table(ws)

Convert data range to a table via batchUpdate API:

```python
from gsheet_utils import convert_to_table

# Convert entire worksheet
result = convert_to_table(ws, name="my_table")

# Or specify range (1-indexed)
result = convert_to_table(ws, name="my_table", start_row=1, end_row=100, start_col=1, end_col=5)
```

### delete_table(ws, table_id)

Delete a table:

```python
from gsheet_utils import delete_table

delete_table(ws, table_id="table_id_here")
```

### get_service_account_email()

Get the service account email for sharing instructions:

```python
from gsheet_utils import get_service_account_email

email = get_service_account_email()
if email:
    print(f"Share your spreadsheet with: {email}")
```

---

## Standard gspread Operations

For all standard operations, use gspread directly:

### Opening and Selecting

```python
from gsheet_utils import open_sheet

sheet = open_sheet("https://docs.google.com/spreadsheets/d/.../edit")

ws = sheet.worksheet("Sheet1")    # By name
ws = sheet.sheet1                  # First sheet
ws = sheet.get_worksheet(0)        # By index

# List all worksheets
for s in sheet.worksheets():
    print(s.title)
```

### Reading Data

```python
# Single cells
val = ws.acell('B1').value              # By A1 notation
val = ws.cell(1, 2).value               # By row, column (1-indexed)

# Ranges
data = ws.get('A1:C10')                 # 2D list
row = ws.row_values(1)                  # Entire row
col = ws.col_values(1)                  # Entire column
all_data = ws.get_all_values()          # All data

# Get formula instead of value
from gspread.utils import ValueRenderOption
formula = ws.acell('B1', value_render_option=ValueRenderOption.formula).value
```

### Writing Data

```python
# Single cells
ws.update_acell('B1', 'New Value')
ws.update_cell(1, 2, 'New Value')

# Ranges - use values first, then range_name (avoids deprecation warning)
ws.update(values=[['A1', 'B1'], ['A2', 'B2']], range_name='A1:B2')

# With formulas
ws.update(values=[['=SUM(A1:A10)']], range_name='B1', value_input_option='USER_ENTERED')

# Batch updates (efficient)
ws.batch_update([
    {'range': 'A1:B2', 'values': [['A1', 'B1'], ['A2', 'B2']]},
    {'range': 'D1:E2', 'values': [['D1', 'E1'], ['D2', 'E2']]}
])

# Append rows
ws.append_row(['New', 'Row', 'Data'])
ws.append_rows([['Row 1'], ['Row 2']])
```

### Row/Column Operations

```python
# Delete rows (1-indexed)
ws.delete_rows(5)              # Single row
ws.delete_rows(5, 10)          # Rows 5-10

# Delete columns
ws.delete_columns(3)           # Single column
ws.delete_columns(3, 5)        # Columns 3-5

# Insert rows
ws.insert_rows([['a', 'b'], ['c', 'd']], row=2)

# Insert columns
ws.insert_cols([['x'], ['y']], col=2)

# Freeze
ws.freeze(rows=1, cols=1)
```

### Worksheet Management

```python
# Create
new_ws = sheet.add_worksheet(title="New Sheet", rows=100, cols=20)

# Duplicate
sheet.duplicate_sheet(ws.id, new_sheet_name="Copy")

# Delete
sheet.del_worksheet(ws)

# Rename
ws.update_title("New Name")

# Resize
ws.resize(rows=200, cols=30)
```

### Finding

```python
import re

cell = ws.find("Revenue")
if cell:
    print(f"Found at row {cell.row}, col {cell.col}")

cells = ws.findall("Revenue")
cells = ws.findall(re.compile(r'Q[1-4] \d{4}'))
```

---

## Formulas

### CRITICAL: Use Formulas, Not Hardcoded Values

```python
# WRONG
total = sum(values)
ws.update_acell('B10', total)

# CORRECT
ws.update_acell('B10', '=SUM(B2:B9)')
```

### Common Formulas

```python
ws.update_acell('C1', '=A1+B1')
ws.update_acell('D1', '=SUM(A1:C1)')
ws.update_acell('E1', '=AVERAGE(A1:D1)')
ws.update_acell('F1', '=IFERROR(A1/B1,0)')
ws.update_acell('G1', '=IF(A1>0,A1*1.1,0)')

# With absolute references
ws.update_acell('B5', '=B4*(1+$C$1)')
```

### Table-Mode Formulas

In table mode, use structured references:

```python
# Instead of =A2+B2, use column names:
ws.update_acell('D2', '=[@Revenue]-[@Cost]')
```

---

## Formatting

```python
# Bold
ws.format('A1:C1', {'textFormat': {'bold': True}})

# Background color
ws.format('A1:C1', {'backgroundColor': {'red': 1, 'green': 1, 'blue': 0}})

# Number formats
ws.format('B2:B10', {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}})
ws.format('C2:C10', {'numberFormat': {'type': 'PERCENT', 'pattern': '0.0%'}})

# Alignment
ws.format('A1:C1', {'horizontalAlignment': 'CENTER'})
```

### Financial Model Color Coding

```python
# Blue text for inputs
ws.format('B2:B5', {'textFormat': {'foregroundColor': {'red': 0, 'green': 0, 'blue': 1}}})

# Green text for cross-sheet links
ws.format('D2:D5', {'textFormat': {'foregroundColor': {'red': 0, 'green': 0.5, 'blue': 0}}})

# Yellow background for assumptions
ws.format('B2:B5', {'backgroundColor': {'red': 1, 'green': 1, 'blue': 0}})
```

---

## Data Validation

```python
from gspread.utils import ValidationConditionType

# Dropdown
ws.add_validation('B2:B10', ValidationConditionType.one_of_list, ['Yes', 'No'], showCustomUi=True)

# Number range
ws.add_validation('C2:C10', ValidationConditionType.number_between, [0, 100], strict=True)
```

---

## Error Handling

```python
from gspread.exceptions import SpreadsheetNotFound, APIError, WorksheetNotFound

try:
    sheet = open_sheet(url)
    ws = sheet.worksheet("Data")
except SpreadsheetNotFound:
    print("Sheet not found or not shared")
except WorksheetNotFound:
    print("Worksheet not found:", [s.title for s in sheet.worksheets()])
except APIError as e:
    if "429" in str(e):
        print("Rate limit - wait and retry")
    else:
        print(f"API Error: {e}")
```

---

## Best Practices

### Rate Limiting

```python
# WRONG: Many API calls
for i, val in enumerate(values):
    ws.update_cell(i+1, 1, val)

# CORRECT: Single API call
ws.update('A1:A100', [[v] for v in values])
```

### Formula Best Practices

1. Place assumptions in dedicated cells
2. Use absolute references for assumptions: `=$B$2*C5`
3. Use IFERROR for division: `=IFERROR(A1/B1,0)`
4. Document sources in adjacent cells

### Number Formatting

```python
ws.format('B:B', {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0'}})
ws.format('C:C', {'numberFormat': {'type': 'PERCENT', 'pattern': '0.0%'}})
ws.format('D:D', {'numberFormat': {'type': 'NUMBER', 'pattern': '0.0"x"'}})
```

### Error Checking

```python
def check_for_errors(ws):
    errors = []
    for row_idx, row in enumerate(ws.get_all_values()):
        for col_idx, val in enumerate(row):
            if val in ['#REF!', '#DIV/0!', '#VALUE!', '#N/A', '#NAME?']:
                errors.append({'row': row_idx+1, 'col': col_idx+1, 'error': val})
    return errors
```
