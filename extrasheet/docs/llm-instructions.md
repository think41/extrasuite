# ExtraSheet LLM Instructions

Instructions for AI agents working with the ExtraSheet file format.

---

## Overview

ExtraSheet represents Google Sheets as a directory of files that you can read and edit directly. This guide explains how to work with the format effectively.

**Key Principle:** Each layer is independent. You can modify data without touching formatting, or update formulas without changing values.

---

## Quick Reference

| Task | File to Edit |
|------|--------------|
| Change cell values | `sheets/{name}/data.tsv` |
| Add/modify formulas | `sheets/{name}/formulas.json` |
| Change styling/formatting | `sheets/{name}/format.json` |
| Add charts, filters, pivots | `sheets/{name}/features.json` |
| Rename sheet | `manifest.json` |
| Reorder sheets | `manifest.json` |
| Create named range | `named-ranges.json` |

---

## Working with Data (data.tsv)

### Reading Data

The `data.tsv` file is a tab-separated values file. It's the simplest representation of spreadsheet data.

```tsv
Name	Age	City
Alice	28	New York
Bob	35	Chicago
Carol	42	Seattle
```

**Important:** Cells with formulas show their **calculated values** here, not the formulas themselves.

### Editing Data

To change a cell value, simply edit the TSV file:

```diff
 Name	Age	City
-Alice	28	New York
+Alice	29	New York
 Bob	35	Chicago
```

### Adding Rows

Add new lines at the appropriate position:

```diff
 Name	Age	City
 Alice	29	New York
 Bob	35	Chicago
+David	31	Boston
```

### Deleting Rows

Remove the entire line:

```diff
 Name	Age	City
 Alice	29	New York
-Bob	35	Chicago
 Carol	42	Seattle
```

### Adding Columns

Add a new value (tab-separated) to each row:

```diff
-Name	Age	City
+Name	Age	City	Country
-Alice	29	New York
+Alice	29	New York	USA
-Bob	35	Chicago
+Bob	35	Chicago	USA
```

### TSV Escaping Rules

| Character | Escape As |
|-----------|-----------|
| Tab | `\t` (literal backslash-t) |
| Newline | `\n` (literal backslash-n) |
| Backslash | `\\` |

### Empty Cells

Empty cells are represented as nothing between tabs:

```tsv
Name		City
```

This means: Name in A, empty B, City in C.

### Data Types

All values are stored as strings. The Google Sheets API interprets them:

| Type | How to Write |
|------|--------------|
| Text | `Hello World` |
| Number | `1234.56` |
| Boolean | `TRUE` or `FALSE` |
| Date | `2024-01-15` |
| Time | `14:30:00` |
| DateTime | `2024-01-15T14:30:00` |
| Empty | (nothing) |

---

## Working with Formulas (formulas.json)

### Reading Formulas

The `formulas.json` file maps cell addresses to formulas:

```json
{
  "C2": "=A2+B2",
  "C3": "=A3+B3",
  "C4": "=SUM(C2:C3)"
}
```

### Adding a Formula

Add a new key-value pair:

```json
{
  "C2": "=A2+B2",
  "C3": "=A3+B3",
  "C4": "=SUM(C2:C3)",
  "D2": "=C2*1.1"
}
```

**Important:** Also update `data.tsv` with the expected calculated value:

```diff
 A	B	Total	Adjusted
-10	20	30
+10	20	30	33
```

### Modifying a Formula

Change the value for the cell address:

```diff
 {
   "C2": "=A2+B2",
-  "C3": "=A3+B3",
+  "C3": "=A3*B3",
   "C4": "=SUM(C2:C3)"
 }
```

### Removing a Formula

Delete the key (the cell becomes a plain value):

```diff
 {
   "C2": "=A2+B2",
-  "C3": "=A3+B3",
   "C4": "=SUM(C2:C3)"
 }
```

### Formula Syntax

Use Google Sheets formula syntax:

```json
{
  "A1": "=SUM(B:B)",
  "A2": "=VLOOKUP(B2,Sheet2!A:C,3,FALSE)",
  "A3": "=IF(B3>100,\"High\",\"Low\")",
  "A4": "=ARRAYFORMULA(B2:B10*C2:C10)",
  "A5": "=QUERY(A1:D100,\"SELECT A,B WHERE C > 0\")"
}
```

### Cross-Sheet References

Reference other sheets by name:

```json
{
  "A1": "=Assumptions!B2",
  "A2": "='Sheet With Spaces'!C3",
  "A3": "=SUM(Revenue!A:A)"
}
```

---

## Working with Formatting (format.json)

### Reading Formatting

The `format.json` file contains dimension sizes, merge info, and format rules:

```json
{
  "dimensions": {
    "rowHeights": {"0": 30},
    "columnWidths": {"A": 150, "B": 100}
  },
  "rules": [
    {
      "range": "A1:B1",
      "format": {
        "bold": true,
        "backgroundColor": "#4285f4"
      }
    }
  ],
  "merges": ["C1:D1"]
}
```

### Adding a Format Rule

Add to the `rules` array:

```json
{
  "rules": [
    {
      "range": "A1:B1",
      "format": {"bold": true}
    },
    {
      "range": "A2:A10",
      "format": {"italic": true, "textColor": "#666666"}
    }
  ]
}
```

### Format Properties

| Property | Values |
|----------|--------|
| `bold` | `true`, `false` |
| `italic` | `true`, `false` |
| `underline` | `true`, `false` |
| `strikethrough` | `true`, `false` |
| `fontSize` | `10`, `12`, `14`, etc. |
| `fontFamily` | `"Arial"`, `"Roboto"`, etc. |
| `textColor` | `"#rrggbb"` |
| `backgroundColor` | `"#rrggbb"` |
| `horizontalAlign` | `"LEFT"`, `"CENTER"`, `"RIGHT"` |
| `verticalAlign` | `"TOP"`, `"MIDDLE"`, `"BOTTOM"` |
| `wrapStrategy` | `"OVERFLOW"`, `"CLIP"`, `"WRAP"` |

### Number Formats

```json
{
  "range": "B2:B100",
  "format": {
    "numberFormat": {
      "type": "CURRENCY",
      "pattern": "$#,##0.00"
    }
  }
}
```

| Type | Example Pattern |
|------|-----------------|
| `NUMBER` | `#,##0.00` |
| `PERCENT` | `0.00%` |
| `CURRENCY` | `$#,##0.00` |
| `DATE` | `yyyy-mm-dd` |

### Changing Column Width

```json
{
  "dimensions": {
    "columnWidths": {
      "A": 200,
      "B": 150
    }
  }
}
```

### Merging Cells

Add to the `merges` array:

```json
{
  "merges": ["A1:C1", "D5:D10"]
}
```

---

## Working with Features (features.json)

### Adding a Chart

```json
{
  "charts": [
    {
      "chartId": 1,
      "position": {
        "anchor": "F2",
        "size": {"width": 600, "height": 400}
      },
      "spec": {
        "title": "Sales Over Time",
        "chartType": "LINE",
        "series": [
          {"dataRange": "B2:B10", "label": "Revenue"}
        ],
        "domain": {"dataRange": "A2:A10"}
      }
    }
  ]
}
```

### Chart Types

| Type | Description |
|------|-------------|
| `BAR` | Horizontal bars |
| `COLUMN` | Vertical bars |
| `LINE` | Line chart |
| `AREA` | Filled area |
| `PIE` | Pie chart |
| `SCATTER` | XY scatter |

### Adding Conditional Formatting

```json
{
  "conditionalFormats": [
    {
      "id": "cf1",
      "ranges": ["B2:B100"],
      "type": "NUMBER_GREATER",
      "values": [1000],
      "format": {"backgroundColor": "#d4edda"}
    }
  ]
}
```

### Condition Types

| Type | Values |
|------|--------|
| `NUMBER_GREATER` | `[number]` |
| `NUMBER_LESS` | `[number]` |
| `NUMBER_BETWEEN` | `[min, max]` |
| `TEXT_CONTAINS` | `[text]` |
| `BLANK` | - |
| `NOT_BLANK` | - |
| `CUSTOM_FORMULA` | Use `formula` field |

### Adding Data Validation

```json
{
  "dataValidations": [
    {
      "range": "C2:C100",
      "type": "ONE_OF_LIST",
      "values": ["Yes", "No", "Maybe"],
      "strict": true,
      "showDropdown": true
    }
  ]
}
```

### Adding a Filter

```json
{
  "basicFilter": {
    "range": "A1:D100",
    "criteria": {
      "0": {"hiddenValues": ["Inactive"]}
    }
  }
}
```

---

## Working with the Manifest (manifest.json)

### Renaming a Sheet

```diff
 {
   "sheets": [
     {
       "sheetId": 0,
-      "title": "Sheet1",
+      "title": "Sales Data",
       "index": 0
     }
   ]
 }
```

**Important:** Also rename the directory:

```bash
mv sheets/Sheet1 sheets/Sales%20Data
```

### Reordering Sheets

Change the `index` values:

```diff
 {
   "sheets": [
-    {"sheetId": 0, "title": "Sheet1", "index": 0},
-    {"sheetId": 1, "title": "Sheet2", "index": 1}
+    {"sheetId": 0, "title": "Sheet1", "index": 1},
+    {"sheetId": 1, "title": "Sheet2", "index": 0}
   ]
 }
```

### Adding a New Sheet

1. Add to `manifest.json`:

```json
{
  "sheets": [
    {"sheetId": 0, "title": "Existing", "index": 0},
    {
      "sheetId": 999,
      "title": "New Sheet",
      "index": 1,
      "type": "GRID",
      "gridProperties": {"rowCount": 100, "columnCount": 10}
    }
  ]
}
```

2. Create the directory and files:

```
sheets/New%20Sheet/
├── data.tsv
└── format.json
```

### Changing Frozen Rows/Columns

```json
{
  "sheets": [
    {
      "sheetId": 0,
      "title": "Data",
      "gridProperties": {
        "frozenRowCount": 2,
        "frozenColumnCount": 1
      }
    }
  ]
}
```

---

## Common Tasks

### Task: Create a Simple Table

1. **Create `data.tsv`:**
```tsv
Product	Price	Quantity	Total
Widget	10.00	5	50.00
Gadget	25.00	3	75.00
```

2. **Create `formulas.json`:**
```json
{
  "D2": "=B2*C2",
  "D3": "=B3*C3"
}
```

3. **Create `format.json`:**
```json
{
  "rules": [
    {
      "range": "A1:D1",
      "format": {"bold": true, "backgroundColor": "#e3f2fd"}
    },
    {
      "range": "B2:D3",
      "format": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}}
    }
  ]
}
```

### Task: Add a SUM Row

1. **Update `data.tsv`:**
```tsv
Product	Price	Quantity	Total
Widget	10.00	5	50.00
Gadget	25.00	3	75.00
Total			125.00
```

2. **Update `formulas.json`:**
```json
{
  "D2": "=B2*C2",
  "D3": "=B3*C3",
  "D4": "=SUM(D2:D3)"
}
```

### Task: Highlight Values Over Threshold

Add to `features.json`:

```json
{
  "conditionalFormats": [
    {
      "id": "highlight_high",
      "ranges": ["D2:D100"],
      "type": "NUMBER_GREATER",
      "values": [100],
      "format": {
        "backgroundColor": "#c8e6c9",
        "textColor": "#1b5e20"
      }
    }
  ]
}
```

### Task: Create a Dropdown List

Add to `features.json`:

```json
{
  "dataValidations": [
    {
      "range": "E2:E100",
      "type": "ONE_OF_LIST",
      "values": ["Pending", "Approved", "Rejected"],
      "strict": true,
      "showDropdown": true
    }
  ]
}
```

### Task: Add a Column Chart

Add to `features.json`:

```json
{
  "charts": [
    {
      "chartId": 1,
      "position": {
        "anchor": "F2",
        "size": {"width": 500, "height": 300}
      },
      "spec": {
        "title": "Sales by Product",
        "chartType": "COLUMN",
        "series": [
          {"dataRange": "D2:D10", "label": "Total"}
        ],
        "domain": {"dataRange": "A2:A10"}
      }
    }
  ]
}
```

---

## Best Practices

### 1. Always Update data.tsv for Formula Cells

When adding a formula, also add the expected value to `data.tsv`. This enables preview without executing formulas.

### 2. Use Consistent Formatting

Apply format rules to ranges, not individual cells. This is more efficient and matches how humans think about formatting.

### 3. Keep formulas.json Minimal

Only include cells that have formulas. Cells with plain values should only appear in `data.tsv`.

### 4. Use Named Ranges for Complex Formulas

Instead of:
```json
{"A1": "=SUM(Sheet2!B2:B100)*Config!C5"}
```

Create named ranges and use:
```json
{"A1": "=SUM(SalesData)*TaxRate"}
```

### 5. Comment Complex Structures

For complex `features.json` files, you can add a `_comment` field (ignored by the processor):

```json
{
  "charts": [
    {
      "_comment": "Main revenue chart for Q1 report",
      "chartId": 1,
      ...
    }
  ]
}
```

---

## Troubleshooting

### Issue: Formula Not Calculating

**Cause:** The formula syntax is incorrect or references don't exist.

**Solution:** Check:
- Cell references are valid (A1, not a1)
- Sheet names with spaces are quoted (`'Sheet Name'!A1`)
- Function names are uppercase (`SUM`, not `sum`)

### Issue: Formatting Not Applied

**Cause:** Rules are applied in order; later rules override earlier ones.

**Solution:** Check rule order in `format.json`. More specific rules should come after general rules.

### Issue: Chart Shows Wrong Data

**Cause:** Data range doesn't include all data or includes headers.

**Solution:** Verify:
- `dataRange` covers all data cells
- `domain` covers labels/categories
- Ranges don't include empty rows

### Issue: Merge Not Working

**Cause:** Merge range includes cells with content.

**Solution:** Clear content from all cells except the top-left before merging.

---

## File Encoding

- All files use UTF-8 encoding
- TSV files have no BOM
- JSON files are pretty-printed with 2-space indentation
- Line endings are LF (Unix-style)
