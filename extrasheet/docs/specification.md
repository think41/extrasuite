# Extrasheet: Spreadsheet-to-Files Transformation Specification

Version: 1.0.0-draft
Last Updated: 2026-01-26

## 1. Overview

Extrasheet transforms Google Sheets spreadsheets into a file-based representation optimized for LLM agents. The key design goals are:

1. **Token efficiency**: Separate data, formulas, formatting, and features into distinct files so agents can load only what they need
2. **Fly-blind editing**: Enable agents to make changes via `batchUpdate` without re-fetching spreadsheet state
3. **Human readability**: Use TSV for data and JSON for structured content
4. **100% coverage**: Represent all Google Sheets API fields without loss

## 2. Directory Structure

```
<output_dir>/
└── <spreadsheet_id>/
    ├── spreadsheet.json           # Spreadsheet metadata
    ├── named_ranges.json          # Named ranges (if any)
    ├── developer_metadata.json    # Developer metadata (if any)
    ├── data_sources.json          # External data sources (if any)
    └── <sheet_title>/             # Folder per worksheet (sanitized title)
        ├── data.tsv               # Cell values (formulas show computed values)
        ├── formula.json           # Cell formulas (sparse)
        ├── format.json            # Cell formatting (sparse)
        ├── feature.json           # Features: charts, pivots, filters, etc.
        ├── dimension.json         # Row/column sizing and visibility
        └── protection.json        # Protected ranges (if any)
```

### 2.1 File Naming Conventions

- **Sheet folders**: Sheet titles are sanitized for filesystem compatibility:
  - Replace invalid characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) with `_`
  - Trim leading/trailing whitespace
  - Append `_<sheetId>` if duplicate names exist after sanitization

- **File extensions**:
  - `.tsv` for tab-separated values (cell data)
  - `.json` for structured data

## 3. Spreadsheet-Level Files

### 3.1 spreadsheet.json

Contains spreadsheet metadata and references to sheets.

```json
{
  "spreadsheetId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/.../edit",
  "properties": {
    "title": "My Spreadsheet",
    "locale": "en_US",
    "autoRecalc": "ON_CHANGE",
    "timeZone": "America/New_York",
    "defaultFormat": { /* CellFormat */ },
    "iterativeCalculationSettings": {
      "maxIterations": 1,
      "convergenceThreshold": 0.05
    },
    "spreadsheetTheme": { /* SpreadsheetTheme */ }
  },
  "sheets": [
    {
      "sheetId": 0,
      "title": "Sheet1",
      "index": 0,
      "sheetType": "GRID",
      "folder": "Sheet1",
      "gridProperties": {
        "rowCount": 1000,
        "columnCount": 26,
        "frozenRowCount": 1,
        "frozenColumnCount": 0,
        "hideGridlines": false,
        "rowGroupControlAfter": false,
        "columnGroupControlAfter": false
      },
      "hidden": false,
      "tabColorStyle": { "rgbColor": { "red": 1.0, "green": 0, "blue": 0 } },
      "rightToLeft": false
    }
  ]
}
```

**Field Mapping from Google Sheets API:**

| API Field | JSON Path | Notes |
|-----------|-----------|-------|
| `Spreadsheet.spreadsheetId` | `spreadsheetId` | |
| `Spreadsheet.spreadsheetUrl` | `spreadsheetUrl` | |
| `Spreadsheet.properties` | `properties` | Full `SpreadsheetProperties` |
| `Spreadsheet.sheets[].properties` | `sheets[]` | Core sheet metadata |
| `Spreadsheet.dataSources` | See `data_sources.json` | Separate file |
| `Spreadsheet.dataSourceSchedules` | See `data_sources.json` | Separate file |
| `Spreadsheet.namedRanges` | See `named_ranges.json` | Separate file |
| `Spreadsheet.developerMetadata` | See `developer_metadata.json` | Separate file |

### 3.2 named_ranges.json

Contains all named ranges in the spreadsheet.

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": {
        "sheetId": 0,
        "startRowIndex": 0,
        "endRowIndex": 100,
        "startColumnIndex": 0,
        "endColumnIndex": 5
      }
    }
  ]
}
```

**Note**: Only created if the spreadsheet has named ranges.

### 3.3 developer_metadata.json

Contains developer metadata at spreadsheet level.

```json
{
  "developerMetadata": [
    {
      "metadataId": 12345,
      "metadataKey": "app-version",
      "metadataValue": "1.0.0",
      "location": {
        "locationType": "SPREADSHEET"
      },
      "visibility": "DOCUMENT"
    }
  ]
}
```

**Note**: Only created if developer metadata exists.

### 3.4 data_sources.json

Contains external data source connections (BigQuery, Looker).

```json
{
  "dataSources": [
    {
      "dataSourceId": "datasource_abc",
      "spec": {
        "bigQuery": {
          "projectId": "my-project",
          "querySpec": {
            "rawQuery": "SELECT * FROM dataset.table"
          }
        },
        "parameters": []
      },
      "calculatedColumns": [],
      "sheetId": 123456
    }
  ],
  "refreshSchedules": [
    {
      "enabled": true,
      "refreshScope": "ALL_DATA_SOURCES",
      "nextRun": {
        "timeZone": "America/New_York",
        "startTime": { "hours": 6, "minutes": 0 }
      },
      "dailySchedule": {
        "startTime": { "hours": 6, "minutes": 0 }
      }
    }
  ]
}
```

**Note**: Only created if data sources are configured.

## 4. Sheet-Level Files

Each sheet folder contains the following files.

### 4.1 data.tsv

Tab-separated values representing cell data. This is the **computed value** for all cells (formulas show their result, not the formula itself).

**Format Rules:**
- First row contains column headers (A, B, C, ..., AA, AB, ...)
- Subsequent rows contain cell values
- Empty cells are represented as empty strings
- Tab characters in values are escaped as `\t`
- Newline characters in values are escaped as `\n`
- Backslash characters are escaped as `\\`
- Trailing empty columns/rows are trimmed

**Example:**
```
A	B	C	D
Name	Sales	Region	Total
Alice	1000	North	1500
Bob	500	South	1200
Carol	800	East	1300
```

**Source Fields:**
- `CellData.formattedValue` - Preferred (human-readable format)
- `CellData.effectiveValue` - Fallback (raw value)

**Special Value Handling:**
| Value Type | Representation |
|------------|----------------|
| String | Raw text |
| Number | Formatted string (respects NumberFormat) |
| Boolean | `TRUE` or `FALSE` |
| Error | Error message (e.g., `#REF!`, `#N/A`) |
| Empty | Empty string |
| Date/Time | Formatted per cell's NumberFormat |

### 4.2 formula.json

Sparse dictionary mapping cell coordinates to formulas.

```json
{
  "formulas": {
    "D2": "=B2+C2",
    "D3": "=B3+C3",
    "D4": "=B4+C4",
    "E1": "=SUM(B2:B4)"
  },
  "arrayFormulas": {
    "A10": {
      "formula": "=ARRAYFORMULA(A2:A9*B2:B9)",
      "range": {
        "startRowIndex": 9,
        "endRowIndex": 18,
        "startColumnIndex": 0,
        "endColumnIndex": 1
      }
    }
  },
  "dataSourceFormulas": [
    {
      "cell": "F1",
      "formula": "=SUM(DataSheet!Column)",
      "dataSourceId": "datasource_abc",
      "dataExecutionStatus": {
        "state": "SUCCEEDED",
        "lastRefreshTime": "2024-01-15T10:30:00Z"
      }
    }
  ]
}
```

**Source Fields:**
- `CellData.userEnteredValue.formulaValue` - Formula text
- `CellData.dataSourceFormula` - Data source formula info

**Key Design Decision:** Only cells with formulas are included. This keeps the file small and makes it easy for agents to identify which cells contain logic vs. static data.

### 4.3 format.json

Cell formatting information, organized by range for efficiency.

```json
{
  "defaultFormat": { /* CellFormat - inherited from spreadsheet */ },

  "cellFormats": {
    "A1": {
      "textFormat": {
        "bold": true,
        "fontSize": 14
      },
      "horizontalAlignment": "CENTER"
    },
    "B2:D4": {
      "numberFormat": {
        "type": "CURRENCY",
        "pattern": "$#,##0.00"
      }
    }
  },

  "conditionalFormats": [
    {
      "ranges": ["B2:B100"],
      "booleanRule": {
        "condition": {
          "type": "NUMBER_GREATER",
          "values": [{ "userEnteredValue": "1000" }]
        },
        "format": {
          "backgroundColor": { "red": 0.8, "green": 1.0, "blue": 0.8 }
        }
      }
    },
    {
      "ranges": ["C2:C100"],
      "gradientRule": {
        "minpoint": { "color": { "red": 1, "green": 0, "blue": 0 }, "type": "MIN" },
        "maxpoint": { "color": { "red": 0, "green": 1, "blue": 0 }, "type": "MAX" }
      }
    }
  ],

  "merges": [
    { "range": "A1:D1", "startRow": 0, "endRow": 1, "startColumn": 0, "endColumn": 4 }
  ],

  "textFormatRuns": {
    "A5": [
      { "startIndex": 0, "format": { "bold": true } },
      { "startIndex": 5, "format": { "italic": true } }
    ]
  }
}
```

**Source Fields:**
- `CellData.userEnteredFormat` - Cell format
- `CellData.effectiveFormat` - Computed format (read-only)
- `CellData.textFormatRuns` - Rich text formatting
- `Sheet.conditionalFormats` - Conditional format rules
- `Sheet.merges` - Merged cell ranges

**Range Notation:**
- Single cell: `"A1"`
- Range: `"A1:D4"`
- Full column: `"A:A"`
- Full row: `"1:1"`

### 4.4 feature.json

Advanced features: charts, pivot tables, tables, filters, slicers, banded ranges.

```json
{
  "charts": [
    {
      "chartId": 123456,
      "position": {
        "overlayPosition": {
          "anchorCell": { "sheetId": 0, "rowIndex": 0, "columnIndex": 5 },
          "offsetXPixels": 10,
          "offsetYPixels": 10,
          "widthPixels": 400,
          "heightPixels": 300
        }
      },
      "spec": {
        "title": "Sales by Region",
        "basicChart": {
          "chartType": "BAR",
          "legendPosition": "RIGHT_LEGEND",
          "axis": [
            { "position": "BOTTOM_AXIS", "title": "Region" },
            { "position": "LEFT_AXIS", "title": "Sales" }
          ],
          "domains": [
            {
              "domain": {
                "sourceRange": {
                  "sources": [{ "sheetId": 0, "startRowIndex": 1, "endRowIndex": 5, "startColumnIndex": 0, "endColumnIndex": 1 }]
                }
              }
            }
          ],
          "series": [
            {
              "series": {
                "sourceRange": {
                  "sources": [{ "sheetId": 0, "startRowIndex": 1, "endRowIndex": 5, "startColumnIndex": 1, "endColumnIndex": 2 }]
                }
              },
              "targetAxis": "LEFT_AXIS"
            }
          ]
        }
      },
      "border": { "color": { "red": 0, "green": 0, "blue": 0 }, "colorStyle": { "rgbColor": {} } }
    }
  ],

  "pivotTables": [
    {
      "anchorCell": "G1",
      "source": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 4 },
      "rows": [
        {
          "sourceColumnOffset": 2,
          "showTotals": true,
          "sortOrder": "ASCENDING",
          "valueBucket": {}
        }
      ],
      "columns": [],
      "values": [
        {
          "summarizeFunction": "SUM",
          "sourceColumnOffset": 1
        }
      ],
      "criteria": {},
      "filterSpecs": [],
      "valueLayout": "HORIZONTAL"
    }
  ],

  "tables": [
    {
      "tableId": "table_abc",
      "name": "SalesTable",
      "range": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 50, "startColumnIndex": 0, "endColumnIndex": 5 },
      "columnProperties": [
        { "columnName": "Name", "columnType": "TEXT" },
        { "columnName": "Sales", "columnType": "NUMBER" }
      ],
      "rowsProperties": { "enableRowColorAlternation": true }
    }
  ],

  "basicFilter": {
    "range": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5 },
    "sortSpecs": [{ "dimensionIndex": 1, "sortOrder": "DESCENDING" }],
    "filterSpecs": [
      {
        "columnIndex": 2,
        "filterCriteria": {
          "condition": { "type": "TEXT_CONTAINS", "values": [{ "userEnteredValue": "North" }] }
        }
      }
    ]
  },

  "filterViews": [
    {
      "filterViewId": 789,
      "title": "Top Performers",
      "range": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5 },
      "sortSpecs": [{ "dimensionIndex": 1, "sortOrder": "DESCENDING" }],
      "filterSpecs": []
    }
  ],

  "slicers": [
    {
      "slicerId": 456,
      "position": {
        "overlayPosition": {
          "anchorCell": { "sheetId": 0, "rowIndex": 0, "columnIndex": 8 },
          "widthPixels": 200,
          "heightPixels": 100
        }
      },
      "spec": {
        "dataRange": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 2, "endColumnIndex": 3 },
        "columnIndex": 0,
        "filterCriteria": {},
        "title": "Region Filter",
        "applyToPivotTables": true
      }
    }
  ],

  "bandedRanges": [
    {
      "bandedRangeId": 111,
      "range": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 50, "startColumnIndex": 0, "endColumnIndex": 5 },
      "rowProperties": {
        "headerColor": { "red": 0.2, "green": 0.4, "blue": 0.6 },
        "firstBandColor": { "red": 1, "green": 1, "blue": 1 },
        "secondBandColor": { "red": 0.95, "green": 0.95, "blue": 0.95 }
      }
    }
  ],

  "dataSourceTables": [
    {
      "anchorCell": "M1",
      "dataSourceId": "datasource_abc",
      "columnSelectionType": "SELECTED",
      "columns": [
        { "reference": { "name": "column1" } },
        { "reference": { "name": "column2" } }
      ],
      "filterSpecs": [],
      "sortSpecs": [],
      "rowLimit": 1000
    }
  ]
}
```

**Source Fields:**
| Feature | API Field |
|---------|-----------|
| Charts | `Sheet.charts[]` → `EmbeddedChart` |
| Pivot Tables | `CellData.pivotTable` → `PivotTable` |
| Tables | `Sheet.tables[]` → `Table` |
| Basic Filter | `Sheet.basicFilter` → `BasicFilter` |
| Filter Views | `Sheet.filterViews[]` → `FilterView` |
| Slicers | `Sheet.slicers[]` → `Slicer` |
| Banded Ranges | `Sheet.bandedRanges[]` → `BandedRange` |
| Data Source Tables | `CellData.dataSourceTable` → `DataSourceTable` |

### 4.5 dimension.json

Row and column dimensions, grouping, and visibility.

```json
{
  "rowMetadata": [
    { "index": 0, "pixelSize": 21, "hidden": false },
    { "index": 1, "pixelSize": 21, "hidden": false },
    { "index": 10, "pixelSize": 50, "hidden": false },
    { "index": 15, "pixelSize": 21, "hidden": true }
  ],

  "columnMetadata": [
    { "index": 0, "pixelSize": 100, "hidden": false },
    { "index": 1, "pixelSize": 80, "hidden": false },
    { "index": 5, "pixelSize": 150, "hidden": false }
  ],

  "rowGroups": [
    {
      "range": { "dimension": "ROWS", "startIndex": 5, "endIndex": 10 },
      "depth": 1,
      "collapsed": false
    }
  ],

  "columnGroups": [
    {
      "range": { "dimension": "COLUMNS", "startIndex": 2, "endIndex": 5 },
      "depth": 1,
      "collapsed": true
    }
  ],

  "developerMetadata": [
    {
      "metadataId": 67890,
      "metadataKey": "row-category",
      "metadataValue": "header",
      "location": {
        "locationType": "ROW",
        "dimensionRange": { "sheetId": 0, "dimension": "ROWS", "startIndex": 0, "endIndex": 1 }
      },
      "visibility": "DOCUMENT"
    }
  ]
}
```

**Notes:**
- Only non-default dimensions are included (sparse representation)
- Default row height: 21 pixels
- Default column width: 100 pixels

**Source Fields:**
- `GridData.rowMetadata[]` → `DimensionProperties`
- `GridData.columnMetadata[]` → `DimensionProperties`
- `Sheet.rowGroups[]` → `DimensionGroup`
- `Sheet.columnGroups[]` → `DimensionGroup`
- `Sheet.developerMetadata[]` (dimension-specific)

### 4.6 protection.json

Protected ranges and their permissions.

```json
{
  "protectedRanges": [
    {
      "protectedRangeId": 12345,
      "range": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10 },
      "namedRangeId": null,
      "description": "Header row - do not modify",
      "warningOnly": false,
      "requestingUserCanEdit": true,
      "unprotectedRanges": [],
      "editors": {
        "users": ["admin@example.com"],
        "groups": ["admins@example.com"],
        "domainUsersCanEdit": false
      }
    }
  ],

  "sheetProtection": {
    "protectedRangeId": 99999,
    "description": "Entire sheet protected",
    "warningOnly": true,
    "requestingUserCanEdit": true,
    "editors": {
      "users": [],
      "groups": [],
      "domainUsersCanEdit": true
    }
  }
}
```

**Notes:**
- Only created if protected ranges exist
- Sheet-level protection (when the entire sheet is protected) is listed separately

**Source Fields:**
- `Sheet.protectedRanges[]` → `ProtectedRange`

## 5. Google Sheets API Field Coverage Matrix

This section provides complete coverage of all Google Sheets API fields.

### 5.1 Spreadsheet Object

| API Field | Output Location | Notes |
|-----------|-----------------|-------|
| `spreadsheetId` | `spreadsheet.json` | |
| `spreadsheetUrl` | `spreadsheet.json` | |
| `properties` | `spreadsheet.json` | Full SpreadsheetProperties |
| `sheets` | `spreadsheet.json` + sheet folders | Metadata in JSON, content in folders |
| `namedRanges` | `named_ranges.json` | |
| `developerMetadata` | `developer_metadata.json` | Spreadsheet-level only |
| `dataSources` | `data_sources.json` | |
| `dataSourceSchedules` | `data_sources.json` | |

### 5.2 Sheet Object

| API Field | Output Location | Notes |
|-----------|-----------------|-------|
| `properties` | `spreadsheet.json#sheets[]` | Core metadata |
| `data` | `<sheet>/data.tsv` + related files | Split across files |
| `merges` | `<sheet>/format.json#merges` | |
| `conditionalFormats` | `<sheet>/format.json#conditionalFormats` | |
| `filterViews` | `<sheet>/feature.json#filterViews` | |
| `protectedRanges` | `<sheet>/protection.json` | |
| `basicFilter` | `<sheet>/feature.json#basicFilter` | |
| `charts` | `<sheet>/feature.json#charts` | |
| `bandedRanges` | `<sheet>/feature.json#bandedRanges` | |
| `developerMetadata` | `<sheet>/dimension.json#developerMetadata` | Sheet-level metadata |
| `rowGroups` | `<sheet>/dimension.json#rowGroups` | |
| `columnGroups` | `<sheet>/dimension.json#columnGroups` | |
| `slicers` | `<sheet>/feature.json#slicers` | |
| `tables` | `<sheet>/feature.json#tables` | |

### 5.3 CellData Object

| API Field | Output Location | Notes |
|-----------|-----------------|-------|
| `userEnteredValue` | `<sheet>/formula.json` (formulas), `<sheet>/data.tsv` (values) | Split by type |
| `effectiveValue` | `<sheet>/data.tsv` | Via formattedValue |
| `formattedValue` | `<sheet>/data.tsv` | Primary source for TSV |
| `userEnteredFormat` | `<sheet>/format.json#cellFormats` | |
| `effectiveFormat` | Not exported | Read-only, computed |
| `hyperlink` | `<sheet>/format.json#cellFormats` | Via textFormat.link |
| `note` | `<sheet>/format.json#cellFormats` | As separate property |
| `textFormatRuns` | `<sheet>/format.json#textFormatRuns` | |
| `dataValidation` | `<sheet>/feature.json` | In validation section |
| `pivotTable` | `<sheet>/feature.json#pivotTables` | |
| `dataSourceTable` | `<sheet>/feature.json#dataSourceTables` | |
| `dataSourceFormula` | `<sheet>/formula.json#dataSourceFormulas` | |
| `chipRuns` | `<sheet>/format.json` | Smart chips |

### 5.4 CellFormat Object

| API Field | Output Location | Notes |
|-----------|-----------------|-------|
| `numberFormat` | `<sheet>/format.json#cellFormats[].numberFormat` | |
| `backgroundColor` | `<sheet>/format.json#cellFormats[].backgroundColorStyle` | Deprecated, use Style |
| `backgroundColorStyle` | `<sheet>/format.json#cellFormats[].backgroundColorStyle` | |
| `borders` | `<sheet>/format.json#cellFormats[].borders` | |
| `padding` | `<sheet>/format.json#cellFormats[].padding` | |
| `horizontalAlignment` | `<sheet>/format.json#cellFormats[].horizontalAlignment` | |
| `verticalAlignment` | `<sheet>/format.json#cellFormats[].verticalAlignment` | |
| `wrapStrategy` | `<sheet>/format.json#cellFormats[].wrapStrategy` | |
| `textDirection` | `<sheet>/format.json#cellFormats[].textDirection` | |
| `textFormat` | `<sheet>/format.json#cellFormats[].textFormat` | |
| `hyperlinkDisplayType` | `<sheet>/format.json#cellFormats[].hyperlinkDisplayType` | |
| `textRotation` | `<sheet>/format.json#cellFormats[].textRotation` | |

## 6. Coordinate Systems and References

### 6.1 A1 Notation

Used in `formula.json` and `format.json` for human readability.

| Examples | Description |
|----------|-------------|
| `A1` | Single cell |
| `A1:D4` | Range |
| `A:A` | Entire column |
| `1:1` | Entire row |
| `A1:D` | Column bounded, row unbounded |
| `Sheet2!A1:D4` | Cross-sheet reference |

### 6.2 Zero-Based Indexes

Used in GridRange and internal representations.

```json
{
  "sheetId": 0,
  "startRowIndex": 0,
  "endRowIndex": 10,
  "startColumnIndex": 0,
  "endColumnIndex": 5
}
```

**Notes:**
- Indexes are zero-based
- Ranges are half-open: `[start, end)`
- Missing index means unbounded

### 6.3 Column Index to Letter Conversion

```
0 → A, 1 → B, ..., 25 → Z
26 → AA, 27 → AB, ..., 51 → AZ
52 → BA, ..., 701 → ZZ
702 → AAA, ...
```

## 7. Data Type Handling

### 7.1 ExtendedValue Types

| Type | `data.tsv` Representation | `formula.json` Handling |
|------|---------------------------|-------------------------|
| `stringValue` | Raw string | N/A |
| `numberValue` | Formatted per NumberFormat | N/A |
| `boolValue` | `TRUE` or `FALSE` | N/A |
| `formulaValue` | Computed result | Formula stored |
| `errorValue` | Error string (e.g., `#REF!`) | Formula stored |

### 7.2 Date/Time Handling

Google Sheets stores dates as serial numbers (days since December 30, 1899).

| Serial Number | Date |
|---------------|------|
| 1 | 1899-12-31 |
| 44197 | 2021-01-01 |

In `data.tsv`, dates are formatted according to the cell's `NumberFormat`. The raw serial number is not exposed.

### 7.3 Error Values

| Error | Meaning |
|-------|---------|
| `#NULL!` | Null error |
| `#DIV/0!` | Division by zero |
| `#VALUE!` | Wrong value type |
| `#REF!` | Invalid reference |
| `#NAME?` | Unknown name |
| `#NUM!` | Invalid number |
| `#N/A` | Not available |
| `#ERROR!` | General error |
| `#LOADING!` | Loading (data source) |

## 8. Special Considerations

### 8.1 Large Spreadsheets

For spreadsheets exceeding 10,000 rows or 100 columns:
- `data.tsv` may be split into multiple files: `data_0.tsv`, `data_1.tsv`, etc.
- Each file contains up to 10,000 rows
- `spreadsheet.json#sheets[].dataFiles` lists all data files

### 8.2 Object Sheets

Sheets with `sheetType: "OBJECT"` contain only embedded objects (charts/images) without grid data:
- No `data.tsv` file
- No `formula.json` file
- `feature.json` contains the embedded object

### 8.3 Data Source Sheets

Sheets with `sheetType: "DATA_SOURCE"`:
- `data.tsv` contains preview data (read-only)
- `feature.json` contains data source configuration
- No `formula.json` (data source formulas are in parent sheet)

### 8.4 Character Encoding

- All files use UTF-8 encoding
- BOM (Byte Order Mark) is not included
- Line endings use LF (`\n`) only

### 8.5 Empty Files

Files are created only if they contain data:
- `formula.json` - Only if sheet has formulas
- `format.json` - Only if sheet has non-default formatting
- `feature.json` - Only if sheet has charts, pivots, etc.
- `protection.json` - Only if sheet has protected ranges
- `named_ranges.json` - Only if spreadsheet has named ranges

## 9. Implementation Notes

### 9.1 API Request for Full Data

To fetch all data needed for transformation:

```python
service.spreadsheets().get(
    spreadsheetId=spreadsheet_id,
    includeGridData=True,
    fields="*"  # All fields
).execute()
```

### 9.2 Performance Considerations

1. **Sparse representation**: Only non-empty/non-default values are stored
2. **Range compression**: Adjacent cells with same format are merged into ranges
3. **Lazy file creation**: Empty files are not created

### 9.3 Version Compatibility

This specification targets Google Sheets API v4. The `discovery.json` version used for type generation should be recorded in generated files.

## 10. Appendix: Complete Schema Reference

See `api_types.py` for complete TypedDict definitions generated from the Google Sheets API discovery document.
