# Smartsheet Integration Analysis

This document explores implementing a pull-edit-diff-push workflow for Smartsheet, similar to extrasheet's approach for Google Sheets.

## Executive Summary

Smartsheet's REST API is well-suited for a pull-edit-diff-push workflow. The API supports:
- Full sheet retrieval with rows, columns, and cells
- Bulk row updates (up to hundreds of rows per request)
- Cell-level formulas and formatting
- Hierarchical row structures (parent/child relationships)

Key differences from Google Sheets require design adaptations, particularly around rate limits, row-based operations (vs cell-based), and the save collision model.

---

## 1. API Overview

### Base URL and Authentication
```
Base URL: https://api.smartsheet.com/2.0
Authentication: Bearer token in Authorization header
```

Users with Smartsheet Business accounts get API access. Authentication uses OAuth 2.0 or direct API tokens.

### Core Data Model

```
Sheet
├── Columns (define structure, types, options)
├── Rows (contain data)
│   ├── Cells (values at column intersections)
│   ├── Attachments (optional)
│   └── Discussions (optional)
├── Attachments (sheet-level)
└── Discussions (sheet-level)
```

**Key difference from Google Sheets:** Smartsheet is row-oriented, not cell-oriented. You update rows, which contain cells. There's no direct "update cell" endpoint.

### References
- [Smartsheet API Introduction](https://developers.smartsheet.com/api/smartsheet/introduction)
- [HTTP and REST Guide](https://developers.smartsheet.com/api/smartsheet/guides/basics/http-and-rest)
- [Sheets, Rows, Columns, and Cells](https://developers.smartsheet.com/api/smartsheet/guides/basics/sheets-rows-columns-and-cells)

---

## 2. API Operations for Pull-Edit-Diff-Push

### Pull Operations

#### Get Sheet (Primary)
```
GET /sheets/{sheetId}
```

Returns complete sheet data including:
- Sheet metadata (name, columns, settings)
- All rows with cell values
- Optional: formatting, discussions, attachments, cross-sheet references

**Query Parameters:**
| Parameter | Purpose |
|-----------|---------|
| `include` | Comma-separated: `attachments`, `discussions`, `format`, `objectValue`, `crossSheetReferences` |
| `exclude` | Comma-separated: `filteredOutRows`, `linkInFromCellDetails`, `linksOutToCellsDetails` |
| `level` | `0`, `1`, `2` - Controls detail level for multi-contact/multi-picklist |
| `rowNumbers` | Specific rows to return |
| `rowIds` | Specific row IDs to return |
| `columnIds` | Specific columns to return |
| `pageSize` / `page` | Pagination (default 100 rows per page) |

**Recommendation:** Use `include=format,objectValue` for full fidelity pull.

#### Get Columns
```
GET /sheets/{sheetId}/columns?includeAll=true
```

Returns column definitions including:
- Column ID, title, type, index
- Options (for PICKLIST, CONTACT_LIST)
- System column flags

#### Export as Excel (Alternative)
```
GET /sheets/{sheetId}
Accept: application/vnd.ms-excel
```

Returns Excel file. Could be useful for backup/audit but not for diff workflow.

### Push Operations

#### Update Rows (Primary)
```
PUT /sheets/{sheetId}/rows
```

**Request Body:**
```json
[
  {
    "id": 123456789,
    "cells": [
      { "columnId": 987654321, "value": "New Value" },
      { "columnId": 987654322, "formula": "=SUM([Column1]:[Column3])" }
    ]
  }
]
```

**Key Features:**
- Bulk operation: Update multiple rows in one request
- `allowPartialSuccess=true`: Continue on individual row errors
- Supports `value`, `formula`, `objectValue` (for predecessors, multi-contact)
- Supports `format` for cell formatting

#### Add Rows
```
POST /sheets/{sheetId}/rows
```

Supports location specifiers:
- `toTop`, `toBottom`
- `parentId` (for hierarchy)
- `siblingId` + `above`/`below`

#### Delete Rows
```
DELETE /sheets/{sheetId}/rows?ids=123,456,789
```

#### Update Columns
```
PUT /sheets/{sheetId}/columns/{columnId}
```

For column property changes (title, type, options).

### References
- [Update Rows](https://developers.smartsheet.com/api/smartsheet/openapi/rows/update-rows)
- [Rows API](https://developers.smartsheet.com/api/smartsheet/openapi/rows)
- [Columns API](https://developers.smartsheet.com/api/smartsheet/openapi/columns)

---

## 3. Rate Limits and Concurrency

### Rate Limits

| Operation | Limit |
|-----------|-------|
| Standard requests | 300/minute/token |
| File attachments | 30/minute/token (counts as 10x) |
| Cell history | Counts as 10x |

**Rate limit exceeded response:**
```json
{
  "errorCode": 4003,
  "message": "Rate limit exceeded."
}
```

### Concurrency Constraints

**Critical:** Smartsheet uses optimistic concurrency control. Concurrent updates to the same sheet cause **Error 4004 (Save Collision)**.

> "Executing multiple API requests in parallel to update a specific Smartsheet object results in reduced performance and often results in errors due to save collisions."

**Implications for our workflow:**
1. Push operations MUST be serialized
2. Cannot parallelize updates to different parts of the same sheet
3. Need retry logic with exponential backoff

### Recommended Handling

```python
# Pseudocode for push operation
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds

def push_with_retry(sheet_id, rows):
    for attempt in range(MAX_RETRIES):
        try:
            return api.update_rows(sheet_id, rows)
        except RateLimitError:
            sleep(60)  # Rate limit: wait 60 seconds
        except SaveCollisionError:
            backoff = INITIAL_BACKOFF * (2 ** attempt)
            sleep(backoff)
    raise MaxRetriesExceeded()
```

### References
- [Scalability Options](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/scalability-options)
- [API Best Practices](https://www.smartsheet.com/content-center/best-practices/tips-tricks/api-best-practices)
- [Limitations](https://developers.smartsheet.com/api/smartsheet/guides/basics/limitations)

---

## 4. Column Types and Special Handling

### Standard Column Types

| Type | API Value | Notes |
|------|-----------|-------|
| Text/Number | `TEXT_NUMBER` | Default type |
| Contact List | `CONTACT_LIST` | Single contact |
| Multi-Contact | `MULTI_CONTACT_LIST` | Multiple contacts |
| Dropdown | `PICKLIST` | Single selection |
| Multi-Select | `MULTI_PICKLIST` | Multiple selections |
| Date | `DATE` | Date only |
| Date/Time | `DATETIME` | Date with time |
| Duration | `DURATION` | Time duration |
| Checkbox | `CHECKBOX` | Boolean with symbol options |
| Predecessor | `PREDECESSOR` | Dependencies |
| Abstract DateTime | `ABSTRACT_DATETIME` | Flexible datetime |

### System Columns (Read-Only)

| Type | Purpose |
|------|---------|
| `AUTO_NUMBER` | Auto-incrementing IDs |
| `CREATED_BY` | Creator contact |
| `CREATED_DATE` | Creation timestamp |
| `MODIFIED_BY` | Last modifier |
| `MODIFIED_DATE` | Last modification |

**Cannot be modified via API.**

### Special Column Behaviors

1. **Project Sheets with Dependencies Enabled:**
   - `Start Date` cannot be updated if row has predecessors
   - `End Date` is calculated (Start + Duration)
   - `% Complete` rolls up from children in parent rows

2. **Parent Rows:**
   - Start Date, End Date, Duration, % Complete auto-calculated from children
   - Cannot be directly updated

3. **Dropdown/Contact Columns:**
   - Setting type requires separate call from setting options
   - Use two API calls: set type first, then add constraints

### References
- [Column Types](https://smartsheet.redoc.ly/tag/columnsRelated/)
- [systemColumnType](https://developers.smartsheet.com/api/smartsheet/openapi/schemas/systemcolumntype)
- [Column Types Reference](https://help.smartsheet.com/articles/2480241-column-type-reference)

---

## 5. Formatting

### Format Descriptor System

Smartsheet uses a positional format descriptor string:
```
",,1,1,,,,,,,,,,,,"
```

Each position represents a formatting property. A cell with bold and italic has `1` in positions 3 and 4.

### Retrieving Format Information

1. Get format tables (defines available options):
   ```
   GET /serverinfo
   ```
   Returns `FormatTables` object with all available fonts, colors, sizes.

2. Include formatting in sheet response:
   ```
   GET /sheets/{sheetId}?include=format
   ```

### Setting Formatting

Include `format` property in cell object when updating rows:
```json
{
  "id": 123,
  "cells": [{
    "columnId": 456,
    "value": "Bold text",
    "format": ",,1,,,,,,,,,,,,,"
  }]
}
```

### Limitations

- No cell borders
- Limited font selection (defined by FormatTables)
- No rich text within cells (bold/italic applies to entire cell)
- Column headers always: white bold text, grey background

### References
- [Cell Formatting](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/cell-formatting)
- [Format Your Data](https://help.smartsheet.com/articles/518246-formatting-options)

---

## 6. Formulas

### Formula Support

Formulas are set via the `formula` property on cells:
```json
{
  "columnId": 123,
  "formula": "=SUM([Cost]:[Revenue])"
}
```

### Formula Syntax Differences from Google Sheets

| Feature | Google Sheets | Smartsheet |
|---------|--------------|------------|
| Cell reference | `A1`, `$A$1` | `[Column Name]@row`, `[Column Name]1` |
| Row reference | `A:A` | `[Column Name]:[Column Name]` |
| Cross-sheet | `Sheet1!A1` | Requires cross-sheet reference setup |
| Hierarchy | N/A | `CHILDREN()`, `PARENT()`, `ANCESTORS()` |

### Column Formulas

Column formulas apply to entire columns. In the API:
- No column-level formula attribute
- Formula appears in each cell's data
- Setting formula on one cell doesn't auto-fill column

### Cross-Sheet References

Must be explicitly created before use:
```
POST /sheets/{sheetId}/crosssheetreferences
```

Defines:
- Source sheet ID
- Source range
- Reference name (used in formulas)

**Auto-cleanup:** Unused cross-sheet references are deleted after 2 hours.

### References
- [Formulas via API](https://developers.smartsheet.com/api/smartsheet/guides/basics/sheets-rows-columns-and-cells)
- [Cross-Sheet References](https://developers.smartsheet.com/api/smartsheet/openapi/crosssheetreferences)
- [FAQs: Using Formulas](https://help.smartsheet.com/articles/2476091-frequently-asked-questions-about-using-formulas)

---

## 7. Row Hierarchy

### Parent-Child Relationships

Rows can be indented to create hierarchy:
- Indent a row → becomes child of row above
- Parent rows can have auto-calculated summaries (with dependencies enabled)

### API for Hierarchy

#### Setting Parent on Row Creation/Update
```json
{
  "parentId": 789,
  "toBottom": true,
  "cells": [...]
}
```

#### Moving Rows in Hierarchy
```json
{
  "id": 123,
  "parentId": 456,  // New parent
  "toTop": true     // Position among siblings
}
```

### Hierarchy Functions

- `CHILDREN([Column]@row)` - All child values
- `PARENT([Column]@row)` - Parent value
- `ANCESTORS([Column]@row)` - All ancestor values

**Not supported in cross-sheet formulas.**

### References
- [Rows and Hierarchy](https://help.smartsheet.com/learning-track/level-1-foundations/rows-and-hierarchy)
- [Hierarchy Functions](https://help.smartsheet.com/articles/2476811-reference-children-parents-ancestors-hierarchy-functions)

---

## 8. Attachments and Discussions

### Attachments

Can be attached to:
- Sheet (sheet-level)
- Row
- Comment (within discussion)

**API Operations:**
```
GET /sheets/{sheetId}/attachments
POST /sheets/{sheetId}/attachments
GET /sheets/{sheetId}/rows/{rowId}/attachments
POST /sheets/{sheetId}/rows/{rowId}/attachments
```

**Limits:** 30MB max file size.

### Discussions and Comments

Discussions are threaded conversations attached to sheets or rows.

```
GET /sheets/{sheetId}/discussions
POST /sheets/{sheetId}/discussions
GET /sheets/{sheetId}/rows/{rowId}/discussions
```

### Recommendations for extrasmartsheet

- **Phase 1:** Exclude attachments and discussions from pull/diff/push
- **Phase 2:** Include as optional features
- Reason: These add complexity without being core to the spreadsheet workflow

### References
- [Attachments](https://developers.smartsheet.com/api/smartsheet/openapi/attachments)
- [Discussions](https://developers.smartsheet.com/api/smartsheet/openapi/discussions)
- [Comments](https://developers.smartsheet.com/api/smartsheet/openapi/comments)

---

## 9. Error Handling

### Common Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 1006 | Not found | Invalid sheet/row/column ID |
| 1007 | Invalid parameter | Check request format |
| 1012 | Access denied | Check sharing permissions |
| 1032 | Resource not accessible | Sheet may be deleted |
| 4003 | Rate limit exceeded | Wait 60s, retry |
| 4004 | Save collision | Retry with backoff |
| 5xxx | Server errors | Retry with backoff |

### Partial Success

With `allowPartialSuccess=true`:
```json
{
  "message": "PARTIAL_SUCCESS",
  "resultCode": 3,
  "result": [...],  // Successful operations
  "failedItems": [
    {
      "index": 2,
      "error": { "errorCode": 1036, "message": "..." }
    }
  ]
}
```

### References
- [Error Codes](https://developers.smartsheet.com/api/smartsheet/error-codes)

---

## 10. Comparison: Google Sheets vs Smartsheet API

| Aspect | Google Sheets | Smartsheet |
|--------|--------------|------------|
| **Data model** | Cell-centric | Row-centric |
| **Update granularity** | Single cell or range | Entire rows |
| **Batch operations** | batchUpdate (multiple ops) | Bulk rows in single endpoint |
| **Rate limits** | 60 req/min/user (Sheets API) | 300 req/min/token |
| **Concurrency** | Optimistic with revision tracking | Save collision model |
| **Formula syntax** | A1 notation | Column name notation |
| **Hierarchy** | None native | Parent/child rows |
| **Formatting** | Rich (borders, merged cells) | Limited (no borders) |
| **Export** | Multiple formats | Excel, PDF |
| **Dependencies** | None native | Built-in predecessors |

---

## 11. Challenges and Mitigations

### Challenge 1: Row-Centric vs Cell-Centric Model

**Problem:** extrasheet operates on cells; Smartsheet operates on rows.

**Mitigation:**
- Track changes at cell level internally
- Aggregate cell changes by row for API calls
- Update entire rows even if only one cell changed

### Challenge 2: Save Collision Handling

**Problem:** Concurrent edits fail with error 4004.

**Mitigation:**
- Serialize all push operations
- Implement exponential backoff retry
- Consider sheet-level locking indicator in `.smartsheet/` metadata

### Challenge 3: Formula Syntax Translation

**Problem:** Different formula syntax prevents direct copy from Google Sheets.

**Mitigation:**
- Use native Smartsheet syntax in on-disk format
- Don't attempt translation
- Document syntax differences in agent guide

### Challenge 4: Column Formulas

**Problem:** No API attribute for column-level formulas.

**Mitigation:**
- Detect column formulas by checking if all cells have identical formula pattern
- Represent as column property in on-disk format
- On push, apply to all cells in column

### Challenge 5: Project Dependencies

**Problem:** Certain columns auto-calculate when dependencies enabled.

**Mitigation:**
- Detect dependency-enabled sheets
- Mark calculated columns as read-only
- Warn agents attempting to edit calculated values

### Challenge 6: System Columns

**Problem:** System columns (Created Date, etc.) cannot be modified.

**Mitigation:**
- Identify and mark as read-only in on-disk format
- Exclude from diff comparison
- Include in pull for reference only

### Challenge 7: Format Descriptor Opacity

**Problem:** Format strings like `",,1,1,,,,,,,,,,,,,"` are not human-readable.

**Mitigation:**
- Fetch FormatTables once, cache it
- Convert to/from human-readable JSON:
  ```json
  {
    "bold": true,
    "italic": true,
    "fontSize": 12
  }
  ```
- Store mapping in `.smartsheet/format-tables.json`

---

## 12. Recommendations

### Naming
- Module name: `extrasmartsheet` (consistent with extrasheet/extraslide naming)
- Package namespace: `extrasmartsheet`

### On-Disk Format Proposal

See [on-disk-format-proposal.md](./on-disk-format-proposal.md) for detailed specification.

### Implementation Phases

**Phase 1: Core Workflow**
- Pull sheet data to local folder
- TSV for data (similar to extrasheet)
- JSON for metadata, columns, formatting
- Diff detection for cell values
- Push with bulk row updates

**Phase 2: Advanced Features**
- Formula support
- Format preservation
- Row hierarchy
- Cross-sheet references

**Phase 3: Project Features**
- Predecessor handling
- Calculated column detection
- Gantt-related metadata

**Phase 4: Collaboration Features**
- Attachments
- Discussions
- Comments

### Architecture Alignment

Reuse patterns from extrasheet:
- Transport abstraction (for testing)
- Pristine copy mechanism
- TypedDict for API types
- Async-first design
- Golden file testing

---

## 13. Next Steps

1. **Design on-disk format** - Define file structure and formats
2. **Prototype pull** - Implement basic sheet retrieval
3. **Define diff algorithm** - Cell-level tracking, row-level API calls
4. **Implement push** - With retry logic and error handling
5. **Write agent guide** - Document Smartsheet-specific considerations
6. **Create test suite** - Golden files from real Smartsheet data

---

## References

### Official Documentation
- [Smartsheet Developer Portal](https://developers.smartsheet.com/)
- [API Introduction](https://developers.smartsheet.com/api/smartsheet/introduction)
- [OpenAPI Reference](https://developers.smartsheet.com/api/smartsheet/openapi)
- [Redoc Reference](https://smartsheet.redoc.ly/)

### Guides
- [Sheets, Rows, Columns, and Cells](https://developers.smartsheet.com/api/smartsheet/guides/basics/sheets-rows-columns-and-cells)
- [Cell Formatting](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/cell-formatting)
- [Scalability Options](https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/scalability-options)
- [API Best Practices](https://www.smartsheet.com/content-center/best-practices/tips-tricks/api-best-practices)
- [Limitations](https://developers.smartsheet.com/api/smartsheet/guides/basics/limitations)

### SDKs
- [Python SDK](https://github.com/smartsheet-platform/smartsheet-python-sdk)
- [Node.js SDK](https://github.com/smartsheet-platform/smartsheet-javascript-sdk)
- [Java SDK](https://github.com/smartsheet-platform/smartsheet-java-sdk)
- [C# SDK](https://github.com/smartsheet-platform/smartsheet-csharp-sdk)
