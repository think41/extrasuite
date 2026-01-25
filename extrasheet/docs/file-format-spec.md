# ExtraSheet File Format Specification

A comprehensive specification for representing Google Sheets as local files that can be edited by AI agents and synced back to Google Sheets.

---

## Table of Contents

1. [Design Principles](#design-principles)
2. [Format Overview](#format-overview)
3. [Directory Structure](#directory-structure)
4. [Spreadsheet Manifest](#spreadsheet-manifest)
5. [Sheet Data Layer](#sheet-data-layer)
6. [Sheet Formula Layer](#sheet-formula-layer)
7. [Sheet Format Layer](#sheet-format-layer)
8. [Sheet Features Layer](#sheet-features-layer)
9. [Named Ranges & References](#named-ranges--references)
10. [Charts](#charts)
11. [Pivot Tables](#pivot-tables)
12. [Conditional Formatting](#conditional-formatting)
13. [Data Validation](#data-validation)
14. [Filters & Filter Views](#filters--filter-views)
15. [Protected Ranges](#protected-ranges)
16. [Banding](#banding)
17. [Dimension Groups](#dimension-groups)
18. [Diff Algorithm](#diff-algorithm)
19. [API Mapping](#api-mapping)
20. [Complete Examples](#complete-examples)

---

## Design Principles

### 1. Separation of Concerns

The format strictly separates four layers:

| Layer | Purpose | Format | Rationale |
|-------|---------|--------|-----------|
| **Data** | Cell values (numbers, strings, booleans) | TSV | Human-readable, universally understood, easy diff |
| **Formula** | Cell formulas | JSON (sparse) | Only cells with formulas, references by address |
| **Format** | Visual styling | JSON | Range-based with inheritance, compact |
| **Features** | Charts, pivots, filters, etc. | JSON | Complex structures, API-aligned |

### 2. Intuitive and Self-Documenting

- TSV files are immediately understandable
- JSON uses human-readable keys matching Google Sheets terminology
- Each file has a single, clear purpose
- No documentation needed to understand basic structure

### 3. Optimized for Diff

- Cell addressing uses `A1:B2` notation (familiar to spreadsheet users)
- Changes at the cell level are atomic
- Sparse representations mean adding a formula doesn't change unrelated files
- Formatting uses range-based rules that can be compared

### 4. Conflict Resolution Ready

- Each cell can be independently versioned: `(sheet, row, col) → value`
- Formulas are keyed by cell address
- Format rules are ordered and can be merged
- Features have unique IDs for tracking

### 5. Efficient API Mapping

- Format maps directly to Google Sheets API batchUpdate requests
- Changes can be batched efficiently
- Minimal data transformation required

---

## Format Overview

ExtraSheet uses a multi-file format where each Google Sheet is represented as a directory:

```
spreadsheet/
├── manifest.json           # Spreadsheet metadata
├── named-ranges.json       # Named ranges (global)
├── theme.json              # Spreadsheet theme/colors
│
└── sheets/
    ├── Sheet1/
    │   ├── data.tsv        # Cell values (tab-separated)
    │   ├── formulas.json   # Cell formulas (sparse)
    │   ├── format.json     # Cell formatting (range-based)
    │   └── features.json   # Charts, pivots, filters, etc.
    │
    ├── Sheet2/
    │   ├── data.tsv
    │   ├── formulas.json
    │   ├── format.json
    │   └── features.json
    │
    └── Dashboard/          # Non-tabular sheet (e.g., chart-only)
        ├── format.json
        └── features.json   # Contains only charts/objects
```

### File Presence Rules

| File | Required | When Omitted |
|------|----------|--------------|
| `manifest.json` | Yes | - |
| `sheets/{name}/data.tsv` | No | Sheet has no cell values (e.g., chart sheet) |
| `sheets/{name}/formulas.json` | No | No cells contain formulas |
| `sheets/{name}/format.json` | No | All cells use default formatting |
| `sheets/{name}/features.json` | No | No charts, pivots, filters, etc. |

---

## Directory Structure

### Naming Conventions

- **Sheet directories** use the sheet title as the directory name
- Special characters in sheet names are URL-encoded (e.g., `Q1 2024` → `Q1%202024/`)
- Sheet order is defined in `manifest.json`, not by filesystem order

### Example: Complete Spreadsheet

```
financial-model/
├── manifest.json
├── named-ranges.json
├── theme.json
│
└── sheets/
    ├── Assumptions/
    │   ├── data.tsv
    │   ├── formulas.json
    │   └── format.json
    │
    ├── Revenue/
    │   ├── data.tsv
    │   ├── formulas.json
    │   ├── format.json
    │   └── features.json   # Contains a chart
    │
    ├── Expenses/
    │   ├── data.tsv
    │   ├── formulas.json
    │   └── format.json
    │
    └── Dashboard/
        ├── format.json
        └── features.json   # Multiple charts, no data grid
```

---

## Spreadsheet Manifest

The `manifest.json` file contains spreadsheet-level metadata.

```json
{
  "version": "1.0",
  "spreadsheetId": "1abc2def3ghi4jkl5mno",
  "title": "Q1 Financial Model",
  "locale": "en_US",
  "timeZone": "America/New_York",
  "autoRecalc": "ON_CHANGE",

  "sheets": [
    {
      "sheetId": 0,
      "title": "Assumptions",
      "index": 0,
      "type": "GRID",
      "hidden": false,
      "rightToLeft": false,
      "gridProperties": {
        "rowCount": 1000,
        "columnCount": 26,
        "frozenRowCount": 1,
        "frozenColumnCount": 1,
        "hideGridlines": false
      },
      "tabColor": "#4285f4"
    },
    {
      "sheetId": 1234567890,
      "title": "Revenue",
      "index": 1,
      "type": "GRID",
      "hidden": false,
      "gridProperties": {
        "rowCount": 500,
        "columnCount": 15
      }
    },
    {
      "sheetId": 9876543210,
      "title": "Dashboard",
      "index": 2,
      "type": "OBJECT",
      "hidden": false
    }
  ],

  "defaultFormat": {
    "font": "Arial",
    "fontSize": 10,
    "textColor": "#000000",
    "backgroundColor": "#ffffff"
  }
}
```

### Manifest Fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Format version (always "1.0") |
| `spreadsheetId` | string | Google Sheets ID (read-only) |
| `title` | string | Spreadsheet title |
| `locale` | string | Locale for formatting (e.g., "en_US") |
| `timeZone` | string | IANA time zone |
| `autoRecalc` | enum | `ON_CHANGE`, `MINUTE`, `HOUR` |
| `sheets` | array | Ordered list of sheet metadata |
| `defaultFormat` | object | Default cell format |

### Sheet Types

| Type | Description | Has `data.tsv`? |
|------|-------------|-----------------|
| `GRID` | Standard data grid | Yes |
| `OBJECT` | Chart/object sheet | No |
| `DATA_SOURCE` | Connected data source | Varies |

---

## Sheet Data Layer

### File: `sheets/{name}/data.tsv`

Cell values are stored as tab-separated values (TSV). This is the most intuitive, human-readable format for tabular data.

**Rules:**
- One row per line
- Columns separated by tabs (`\t`)
- Empty cells are empty strings between tabs
- Trailing tabs are preserved (to maintain column count)
- Newlines within cells use `\n` (literal backslash-n)
- Tabs within cells use `\t` (literal backslash-t)
- Backslashes are escaped as `\\`

### Example: data.tsv

```tsv
Name	Revenue	Cost	Profit
Alice	1000	750	250
Bob	1200	800	400
Carol	900	600	300
Total	3100	2150	950
```

### Data Types

TSV stores all values as strings. The actual type is inferred or specified in formulas:

| Google Sheets Type | TSV Representation | Notes |
|-------------------|-------------------|-------|
| String | As-is | `Hello World` |
| Number | Decimal notation | `1234.56`, `-99.9` |
| Boolean | `TRUE` / `FALSE` | Case-insensitive on read |
| Date | ISO 8601 | `2024-01-15` |
| DateTime | ISO 8601 | `2024-01-15T14:30:00` |
| Time | ISO 8601 time | `14:30:00` |
| Error | `#ERROR!` format | `#REF!`, `#VALUE!`, `#DIV/0!` |
| Empty | Empty string | `` (nothing between tabs) |

### Formula Cells in data.tsv

Cells with formulas show their **calculated value** in `data.tsv`. The formula itself is in `formulas.json`.

```tsv
Name	Revenue	Cost	Profit
Alice	1000	750	250
Bob	1200	800	400
Total	2200	1550	650
```

Where `A3` has formula `=A1+A2`, `B3` has `=B1+B2`, etc.

**Rationale:** This allows viewing/editing values without understanding formulas, and enables "preview without API call."

---

## Sheet Formula Layer

### File: `sheets/{name}/formulas.json`

A sparse JSON object mapping cell addresses to their formulas.

```json
{
  "D2": "=B2-C2",
  "D3": "=B3-C3",
  "D4": "=B4-C4",
  "B5": "=SUM(B2:B4)",
  "C5": "=SUM(C2:C4)",
  "D5": "=B5-C5"
}
```

### Formula Syntax

Formulas use Google Sheets syntax, stored exactly as entered:

- Cell references: `A1`, `$A$1`, `A$1`, `$A1`
- Range references: `A1:B10`, `Sheet2!A1:B10`
- Named ranges: `TaxRate`, `Revenue`
- Functions: `=SUM(A:A)`, `=VLOOKUP(A1,Sheet2!A:C,2,FALSE)`
- Array formulas: `=ARRAYFORMULA(A1:A10*B1:B10)`
- Lambda functions: `=LAMBDA(x,x*2)(5)`

### Special Formula Types

```json
{
  "A1": "=TODAY()",
  "A2": "=IMPORTRANGE(\"spreadsheet_id\",\"Sheet1!A1\")",
  "A3": {
    "formula": "=ARRAYFORMULA(B:B*C:C)",
    "arrayFormula": true
  },
  "A4": {
    "formula": "=UNIQUE(A:A)",
    "dynamicArray": true
  }
}
```

### Cross-Sheet References

Formulas referencing other sheets use the sheet title:

```json
{
  "A1": "=Assumptions!B2",
  "B1": "='Sheet With Spaces'!C3",
  "C1": "=SUM(Revenue!A:A)"
}
```

---

## Sheet Format Layer

### File: `sheets/{name}/format.json`

Cell formatting is stored as an ordered list of range-based rules. Later rules override earlier ones for overlapping ranges.

```json
{
  "dimensions": {
    "rowHeights": {
      "0": 30,
      "5": 25
    },
    "columnWidths": {
      "A": 150,
      "B": 100,
      "C": 100,
      "D": 120
    },
    "hiddenRows": [10, 11, 12],
    "hiddenColumns": ["F", "G"]
  },

  "rules": [
    {
      "range": "A1:D1",
      "format": {
        "bold": true,
        "backgroundColor": "#4285f4",
        "textColor": "#ffffff",
        "horizontalAlign": "CENTER"
      }
    },
    {
      "range": "B2:D100",
      "format": {
        "numberFormat": {
          "type": "CURRENCY",
          "pattern": "$#,##0.00"
        }
      }
    },
    {
      "range": "A5:D5",
      "format": {
        "bold": true,
        "borderTop": {
          "style": "SOLID_MEDIUM",
          "color": "#000000"
        }
      }
    }
  ],

  "merges": [
    "A1:D1",
    "A10:B12"
  ]
}
```

### Format Properties

| Property | Type | Values |
|----------|------|--------|
| `bold` | boolean | `true`, `false` |
| `italic` | boolean | `true`, `false` |
| `underline` | boolean | `true`, `false` |
| `strikethrough` | boolean | `true`, `false` |
| `fontSize` | number | Point size (e.g., `12`) |
| `fontFamily` | string | Font name (e.g., `"Arial"`) |
| `textColor` | string | Hex color `"#rrggbb"` |
| `backgroundColor` | string | Hex color `"#rrggbb"` |
| `horizontalAlign` | enum | `LEFT`, `CENTER`, `RIGHT`, `JUSTIFY` |
| `verticalAlign` | enum | `TOP`, `MIDDLE`, `BOTTOM` |
| `wrapStrategy` | enum | `OVERFLOW`, `CLIP`, `WRAP` |
| `textRotation` | number | Degrees (-90 to 90) or `"vertical"` |
| `numberFormat` | object | See Number Formats |
| `borders` | object | See Borders |
| `padding` | object | `{top, bottom, left, right}` in pixels |

### Number Formats

```json
{
  "numberFormat": {
    "type": "NUMBER",
    "pattern": "#,##0.00"
  }
}
```

| Type | Description | Example Pattern |
|------|-------------|-----------------|
| `TEXT` | Plain text | - |
| `NUMBER` | Numeric | `#,##0.00` |
| `PERCENT` | Percentage | `0.00%` |
| `CURRENCY` | Currency | `$#,##0.00` |
| `DATE` | Date | `yyyy-mm-dd` |
| `TIME` | Time | `hh:mm:ss` |
| `DATE_TIME` | Combined | `yyyy-mm-dd hh:mm:ss` |
| `SCIENTIFIC` | Scientific | `0.00E+00` |

### Borders

```json
{
  "borders": {
    "top": {"style": "SOLID", "color": "#000000"},
    "bottom": {"style": "SOLID_MEDIUM", "color": "#000000"},
    "left": {"style": "DASHED", "color": "#cccccc"},
    "right": {"style": "DOTTED", "color": "#cccccc"}
  }
}
```

| Border Style | Description |
|--------------|-------------|
| `NONE` | No border |
| `DOTTED` | Dotted line |
| `DASHED` | Dashed line |
| `SOLID` | Thin solid line |
| `SOLID_MEDIUM` | Medium solid line |
| `SOLID_THICK` | Thick solid line |
| `DOUBLE` | Double line |

### Theme Colors

Formats can reference theme colors instead of hex values:

```json
{
  "range": "A1:D1",
  "format": {
    "backgroundColor": {"themeColor": "ACCENT1"},
    "textColor": {"themeColor": "TEXT"}
  }
}
```

Theme color types: `TEXT`, `BACKGROUND`, `ACCENT1`-`ACCENT6`, `LINK`.

---

## Sheet Features Layer

### File: `sheets/{name}/features.json`

Contains all non-data, non-formatting features of a sheet.

```json
{
  "charts": [...],
  "pivotTables": [...],
  "conditionalFormats": [...],
  "dataValidations": [...],
  "basicFilter": {...},
  "filterViews": [...],
  "protectedRanges": [...],
  "bandedRanges": [...],
  "dimensionGroups": [...],
  "slicers": [...]
}
```

Each section is optional. Empty/null sections are omitted.

---

## Named Ranges & References

### File: `named-ranges.json`

```json
{
  "ranges": [
    {
      "namedRangeId": "abc123",
      "name": "TaxRate",
      "range": {
        "sheetTitle": "Assumptions",
        "range": "B5"
      }
    },
    {
      "namedRangeId": "def456",
      "name": "Revenue",
      "range": {
        "sheetTitle": "Revenue",
        "range": "B2:B100"
      }
    },
    {
      "namedRangeId": "ghi789",
      "name": "AllData",
      "range": {
        "sheetTitle": "Data",
        "range": "A:Z"
      }
    }
  ]
}
```

### Range Notation

Ranges use A1 notation with sheet prefixes when needed:

| Notation | Meaning |
|----------|---------|
| `A1` | Single cell |
| `A1:B10` | Rectangular range |
| `A:A` | Entire column |
| `1:1` | Entire row |
| `A:C` | Multiple columns |
| `Sheet2!A1:B10` | Cross-sheet range |

---

## Charts

Charts are defined in `features.json` under the `charts` array.

```json
{
  "charts": [
    {
      "chartId": 123456789,
      "position": {
        "anchor": "F2",
        "offset": {"x": 0, "y": 0},
        "size": {"width": 600, "height": 400}
      },
      "spec": {
        "title": "Revenue by Region",
        "subtitle": "Q1 2024",
        "chartType": "COLUMN",
        "legendPosition": "BOTTOM_LEGEND",
        "dataRange": "A1:C10",
        "series": [
          {
            "dataRange": "B2:B10",
            "label": "Revenue",
            "color": "#4285f4"
          }
        ],
        "domain": {
          "dataRange": "A2:A10"
        },
        "axes": {
          "left": {
            "title": "Amount ($)",
            "format": "#,##0"
          },
          "bottom": {
            "title": "Region"
          }
        }
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
| `AREA` | Area chart |
| `SCATTER` | Scatter/XY plot |
| `PIE` | Pie chart |
| `DOUGHNUT` | Donut chart |
| `COMBO` | Combined chart types |
| `HISTOGRAM` | Histogram |
| `WATERFALL` | Waterfall chart |
| `TREEMAP` | Treemap |
| `ORG` | Org chart |
| `CANDLESTICK` | Financial candlestick |
| `BUBBLE` | Bubble chart |
| `RADAR` | Radar/spider chart |
| `SCORECARD` | KPI scorecard |

### Chart Position

Charts are anchored to a cell with pixel offsets:

```json
{
  "position": {
    "anchor": "F2",
    "offset": {"x": 10, "y": 5},
    "size": {"width": 600, "height": 400}
  }
}
```

Alternative: overlay on `newSheet: true` creates a dedicated chart sheet.

---

## Pivot Tables

```json
{
  "pivotTables": [
    {
      "pivotTableId": 987654321,
      "anchor": "A1",
      "source": {
        "sheetTitle": "Sales Data",
        "range": "A1:F1000"
      },
      "rows": [
        {
          "sourceColumn": 0,
          "label": "Region",
          "sortOrder": "ASCENDING",
          "showTotals": true
        }
      ],
      "columns": [
        {
          "sourceColumn": 1,
          "label": "Product"
        }
      ],
      "values": [
        {
          "sourceColumn": 4,
          "label": "Total Revenue",
          "function": "SUM",
          "format": "$#,##0.00"
        },
        {
          "sourceColumn": 5,
          "label": "Avg Quantity",
          "function": "AVERAGE",
          "format": "#,##0.0"
        }
      ],
      "filters": [
        {
          "sourceColumn": 2,
          "values": ["Active", "Pending"]
        }
      ],
      "layout": "HORIZONTAL"
    }
  ]
}
```

### Pivot Value Functions

| Function | Description |
|----------|-------------|
| `SUM` | Sum of values |
| `COUNT` | Count of values |
| `COUNTA` | Count of non-empty |
| `COUNTUNIQUE` | Unique count |
| `AVERAGE` | Average |
| `MAX` | Maximum |
| `MIN` | Minimum |
| `MEDIAN` | Median |
| `PRODUCT` | Product |
| `STDEV` | Standard deviation |
| `STDEVP` | Population std dev |
| `VAR` | Variance |
| `VARP` | Population variance |
| `CUSTOM` | Custom formula |

---

## Conditional Formatting

```json
{
  "conditionalFormats": [
    {
      "id": "cf_001",
      "ranges": ["B2:B100"],
      "type": "NUMBER_GREATER",
      "values": [1000],
      "format": {
        "backgroundColor": "#d4edda",
        "textColor": "#155724"
      }
    },
    {
      "id": "cf_002",
      "ranges": ["C2:C100"],
      "type": "COLOR_SCALE",
      "minpoint": {"type": "MIN", "color": "#ffffff"},
      "midpoint": {"type": "PERCENTILE", "value": 50, "color": "#ffc107"},
      "maxpoint": {"type": "MAX", "color": "#dc3545"}
    },
    {
      "id": "cf_003",
      "ranges": ["A2:D100"],
      "type": "CUSTOM_FORMULA",
      "formula": "=$E2=\"High Priority\"",
      "format": {
        "bold": true,
        "backgroundColor": "#fff3cd"
      }
    }
  ]
}
```

### Condition Types

| Type | Description | Values |
|------|-------------|--------|
| `NUMBER_GREATER` | > value | `[number]` |
| `NUMBER_GREATER_THAN_EQ` | >= value | `[number]` |
| `NUMBER_LESS` | < value | `[number]` |
| `NUMBER_LESS_THAN_EQ` | <= value | `[number]` |
| `NUMBER_EQ` | = value | `[number]` |
| `NUMBER_NOT_EQ` | != value | `[number]` |
| `NUMBER_BETWEEN` | Between | `[min, max]` |
| `NUMBER_NOT_BETWEEN` | Not between | `[min, max]` |
| `TEXT_CONTAINS` | Contains | `[text]` |
| `TEXT_NOT_CONTAINS` | Not contains | `[text]` |
| `TEXT_STARTS_WITH` | Starts with | `[text]` |
| `TEXT_ENDS_WITH` | Ends with | `[text]` |
| `TEXT_EQ` | Exact match | `[text]` |
| `DATE_BEFORE` | Before date | `[date]` |
| `DATE_AFTER` | After date | `[date]` |
| `DATE_EQ` | On date | `[date]` |
| `DATE_IS_VALID` | Valid date | - |
| `ONE_OF_RANGE` | In range | `[range_a1]` |
| `ONE_OF_LIST` | In list | `[value1, value2, ...]` |
| `BLANK` | Is empty | - |
| `NOT_BLANK` | Not empty | - |
| `CUSTOM_FORMULA` | Custom | Formula in `formula` |
| `COLOR_SCALE` | Gradient | Points in `minpoint`, `maxpoint` |
| `DATA_BAR` | Data bars | Config in `dataBar` |

---

## Data Validation

```json
{
  "dataValidations": [
    {
      "range": "C2:C100",
      "type": "ONE_OF_LIST",
      "values": ["Approved", "Pending", "Rejected"],
      "strict": true,
      "showDropdown": true,
      "inputMessage": "Select a status"
    },
    {
      "range": "D2:D100",
      "type": "NUMBER_BETWEEN",
      "values": [0, 100],
      "strict": true,
      "inputMessage": "Enter a percentage (0-100)",
      "errorMessage": "Value must be between 0 and 100"
    },
    {
      "range": "E2:E100",
      "type": "DATE_AFTER",
      "values": ["2024-01-01"],
      "strict": false
    },
    {
      "range": "F2:F100",
      "type": "CUSTOM_FORMULA",
      "formula": "=ISNUMBER(F2)",
      "strict": true
    }
  ]
}
```

### Validation Types

Same as conditional format condition types, plus:

| Type | Description |
|------|-------------|
| `ONE_OF_RANGE` | Values from a range |
| `CHECKBOX` | Checkbox (custom checked/unchecked values) |

---

## Filters & Filter Views

### Basic Filter (Sheet-level)

```json
{
  "basicFilter": {
    "range": "A1:G100",
    "criteria": {
      "0": {
        "hiddenValues": ["Inactive"]
      },
      "2": {
        "condition": {
          "type": "NUMBER_GREATER",
          "values": [1000]
        }
      }
    },
    "sortSpecs": [
      {
        "columnIndex": 1,
        "sortOrder": "ASCENDING"
      }
    ]
  }
}
```

### Filter Views (Named Filters)

```json
{
  "filterViews": [
    {
      "filterViewId": 111222333,
      "title": "High Value Only",
      "range": "A1:G100",
      "criteria": {
        "3": {
          "condition": {
            "type": "NUMBER_GREATER_THAN_EQ",
            "values": [10000]
          }
        }
      },
      "sortSpecs": [
        {
          "columnIndex": 3,
          "sortOrder": "DESCENDING"
        }
      ]
    }
  ]
}
```

---

## Protected Ranges

```json
{
  "protectedRanges": [
    {
      "protectedRangeId": 444555666,
      "range": "A1:D1",
      "description": "Header row - do not edit",
      "warningOnly": false,
      "editors": {
        "users": ["admin@example.com"],
        "domainUsersCanEdit": false
      }
    },
    {
      "protectedRangeId": 777888999,
      "range": "E:E",
      "description": "Calculated column",
      "warningOnly": true
    }
  ]
}
```

---

## Banding

Alternating row/column colors.

```json
{
  "bandedRanges": [
    {
      "bandedRangeId": 112233445,
      "range": "A2:G100",
      "rowProperties": {
        "headerColor": "#4285f4",
        "firstBandColor": "#ffffff",
        "secondBandColor": "#f8f9fa",
        "footerColor": "#e8f0fe"
      }
    }
  ]
}
```

---

## Dimension Groups

Row/column grouping for expand/collapse.

```json
{
  "dimensionGroups": {
    "rowGroups": [
      {
        "range": {"start": 5, "end": 10},
        "depth": 1,
        "collapsed": false
      },
      {
        "range": {"start": 6, "end": 8},
        "depth": 2,
        "collapsed": true
      }
    ],
    "columnGroups": [
      {
        "range": {"start": "C", "end": "E"},
        "depth": 1,
        "collapsed": false
      }
    ]
  }
}
```

---

## Diff Algorithm

### Overview

The diff algorithm compares two versions of an ExtraSheet directory and produces a minimal set of changes.

```
Original/          Edited/
├── manifest.json  ├── manifest.json    → Compare manifests
├── sheets/        ├── sheets/
│   ├── Sheet1/    │   ├── Sheet1/
│   │   ├── data.tsv    │   ├── data.tsv     → Cell-by-cell diff
│   │   ├── formulas.json → formulas.json  → Formula diff
│   │   └── format.json → format.json    → Rule diff
```

### Data Diff (data.tsv)

1. Parse both TSV files into 2D arrays
2. Compare cell-by-cell using `(row, col)` as key
3. Generate change list:
   - `ADDED`: Cell exists in edited, not in original
   - `DELETED`: Cell exists in original, not in edited
   - `MODIFIED`: Cell exists in both, value differs

```python
# Pseudocode
changes = []
for (row, col) in union(original_cells, edited_cells):
    orig_val = original.get((row, col), None)
    edit_val = edited.get((row, col), None)

    if orig_val is None and edit_val is not None:
        changes.append(CellChange(ADDED, row, col, edit_val))
    elif orig_val is not None and edit_val is None:
        changes.append(CellChange(DELETED, row, col))
    elif orig_val != edit_val:
        changes.append(CellChange(MODIFIED, row, col, edit_val))
```

### Formula Diff (formulas.json)

Formulas are keyed by cell address, making diff trivial:

```python
for addr in union(orig_formulas, edit_formulas):
    orig = orig_formulas.get(addr)
    edit = edit_formulas.get(addr)

    if orig != edit:
        changes.append(FormulaChange(addr, orig, edit))
```

### Format Diff (format.json)

Format rules are ordered. Diff strategy:

1. Compare dimension changes (row heights, column widths)
2. Compare merge changes
3. Compare format rules by index and content
4. Generate minimal update requests

### Feature Diff (features.json)

Features have unique IDs (chartId, pivotTableId, etc.):

1. Match features by ID
2. Compare properties of matched features
3. Detect added/removed features

---

## API Mapping

### Diff to batchUpdate Requests

| Change Type | API Request |
|-------------|-------------|
| Cell value changed | `UpdateCellsRequest` |
| Formula added/changed | `UpdateCellsRequest` with `userEnteredValue.formulaValue` |
| Formula deleted | `UpdateCellsRequest` with value only |
| Format rule changed | `RepeatCellRequest` or `UpdateCellsRequest` |
| Merge cells | `MergeCellsRequest` |
| Unmerge cells | `UnmergeCellsRequest` |
| Row height changed | `UpdateDimensionPropertiesRequest` |
| Column width changed | `UpdateDimensionPropertiesRequest` |
| Chart added | `AddChartRequest` |
| Chart modified | `UpdateChartSpecRequest` |
| Chart deleted | `DeleteEmbeddedObjectRequest` |
| Pivot table added | `UpdateCellsRequest` with `pivotTable` |
| Conditional format added | `AddConditionalFormatRuleRequest` |
| Conditional format changed | `UpdateConditionalFormatRuleRequest` |
| Data validation changed | `SetDataValidationRequest` |
| Filter changed | `SetBasicFilterRequest` |
| Sheet added | `AddSheetRequest` |
| Sheet deleted | `DeleteSheetRequest` |
| Sheet renamed | `UpdateSheetPropertiesRequest` |
| Sheet reordered | `UpdateSheetPropertiesRequest` |

### Request Ordering

Requests are ordered to satisfy dependencies:

1. **Structural changes** (add sheets, dimensions)
2. **Content changes** (cell values, formulas)
3. **Format changes** (styling, merges, borders)
4. **Feature changes** (charts, pivots, filters)
5. **Deletions** (in reverse dependency order)

### Efficient Batching

Multiple cell changes are batched:

```json
{
  "updateCells": {
    "range": {
      "sheetId": 0,
      "startRowIndex": 0,
      "endRowIndex": 10,
      "startColumnIndex": 0,
      "endColumnIndex": 5
    },
    "rows": [...],
    "fields": "userEnteredValue"
  }
}
```

---

## Complete Examples

### Example 1: Simple Budget Spreadsheet

**Directory Structure:**
```
budget/
├── manifest.json
└── sheets/
    └── Budget/
        ├── data.tsv
        ├── formulas.json
        └── format.json
```

**manifest.json:**
```json
{
  "version": "1.0",
  "title": "Monthly Budget",
  "sheets": [
    {
      "sheetId": 0,
      "title": "Budget",
      "index": 0,
      "type": "GRID",
      "gridProperties": {
        "rowCount": 20,
        "columnCount": 5,
        "frozenRowCount": 1
      }
    }
  ]
}
```

**data.tsv:**
```tsv
Category	Budget	Actual	Difference	Status
Housing	2000	1950	50	Under
Food	600	720	-120	Over
Transport	400	380	20	Under
Utilities	200	210	-10	Over
Entertainment	300	450	-150	Over
Total	3500	3710	-210	Over
```

**formulas.json:**
```json
{
  "D2": "=B2-C2",
  "D3": "=B3-C3",
  "D4": "=B4-C4",
  "D5": "=B5-C5",
  "D6": "=B6-C6",
  "B7": "=SUM(B2:B6)",
  "C7": "=SUM(C2:C6)",
  "D7": "=B7-C7",
  "E2": "=IF(D2>=0,\"Under\",\"Over\")",
  "E3": "=IF(D3>=0,\"Under\",\"Over\")",
  "E4": "=IF(D4>=0,\"Under\",\"Over\")",
  "E5": "=IF(D5>=0,\"Under\",\"Over\")",
  "E6": "=IF(D6>=0,\"Under\",\"Over\")",
  "E7": "=IF(D7>=0,\"Under\",\"Over\")"
}
```

**format.json:**
```json
{
  "dimensions": {
    "columnWidths": {
      "A": 120,
      "B": 100,
      "C": 100,
      "D": 100,
      "E": 80
    }
  },
  "rules": [
    {
      "range": "A1:E1",
      "format": {
        "bold": true,
        "backgroundColor": "#4285f4",
        "textColor": "#ffffff",
        "horizontalAlign": "CENTER"
      }
    },
    {
      "range": "B2:D7",
      "format": {
        "numberFormat": {
          "type": "CURRENCY",
          "pattern": "$#,##0"
        },
        "horizontalAlign": "RIGHT"
      }
    },
    {
      "range": "A7:E7",
      "format": {
        "bold": true,
        "borderTop": {
          "style": "SOLID_MEDIUM",
          "color": "#000000"
        }
      }
    }
  ]
}
```

### Example 2: Sales Dashboard with Chart

**Directory Structure:**
```
sales-dashboard/
├── manifest.json
├── named-ranges.json
└── sheets/
    ├── Data/
    │   ├── data.tsv
    │   └── format.json
    └── Dashboard/
        ├── format.json
        └── features.json
```

**sheets/Dashboard/features.json:**
```json
{
  "charts": [
    {
      "chartId": 12345,
      "position": {
        "anchor": "A1",
        "size": {"width": 800, "height": 400}
      },
      "spec": {
        "title": "Monthly Sales",
        "chartType": "COLUMN",
        "legendPosition": "RIGHT_LEGEND",
        "series": [
          {
            "dataRange": "Data!B2:B13",
            "label": "Revenue",
            "color": "#4285f4"
          },
          {
            "dataRange": "Data!C2:C13",
            "label": "Target",
            "color": "#34a853"
          }
        ],
        "domain": {
          "dataRange": "Data!A2:A13"
        }
      }
    },
    {
      "chartId": 67890,
      "position": {
        "anchor": "A15",
        "size": {"width": 400, "height": 300}
      },
      "spec": {
        "title": "Revenue by Region",
        "chartType": "PIE",
        "series": [
          {
            "dataRange": "Data!E2:E5"
          }
        ],
        "domain": {
          "dataRange": "Data!D2:D5"
        }
      }
    }
  ]
}
```

---

## Appendix: A1 Notation Reference

| Notation | Description | Example |
|----------|-------------|---------|
| `A1` | Single cell | Column A, Row 1 |
| `A1:B10` | Range | From A1 to B10 |
| `A:A` | Entire column | All of column A |
| `1:1` | Entire row | All of row 1 |
| `A:C` | Multiple columns | Columns A through C |
| `1:5` | Multiple rows | Rows 1 through 5 |
| `$A$1` | Absolute reference | Locked cell |
| `$A1` | Mixed reference | Locked column |
| `A$1` | Mixed reference | Locked row |
| `Sheet2!A1` | Cross-sheet | Cell in Sheet2 |
| `'Sheet Name'!A1` | Quoted sheet | Sheet with spaces |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial specification |
