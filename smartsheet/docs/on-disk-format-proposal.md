# On-Disk Format Proposal for extrasmartsheet

This document proposes the local folder structure and file formats for extrasmartsheet, following the patterns established by extrasheet.

## Design Goals

1. **Token-efficient for LLM agents** - Progressive disclosure, summary first
2. **Human-readable and editable** - TSV for data, JSON for metadata
3. **Diff-friendly** - Line-based formats that work well with text diff
4. **Lossless** - Preserve all data needed for round-trip push
5. **Familiar to extrasheet users** - Similar patterns where applicable

---

## Folder Structure

```
<sheet_id>/
├── sheet.json              # Sheet metadata + summary
├── columns.json            # Column definitions
├── data.tsv                # Cell values (tab-separated)
├── formulas.json           # Sparse formula map (optional)
├── format.json             # Cell formatting (optional)
├── hierarchy.json          # Row parent-child relationships (optional)
├── attachments.json        # Attachment metadata (optional, Phase 4)
├── discussions.json        # Discussion threads (optional, Phase 4)
├── .pristine/
│   └── sheet.zip           # Pristine copy for diff baseline
└── .smartsheet/
    ├── raw-response.json   # Raw API response (optional, for debugging)
    ├── format-tables.json  # Cached FormatTables from /serverinfo
    └── pull-metadata.json  # Pull timestamp, API version, etc.
```

---

## Core Files

### sheet.json

Primary metadata file. LLM agents should read this first to understand the sheet.

```json
{
  "sheetId": 1234567890,
  "sheetUrl": "https://app.smartsheet.com/sheets/...",
  "name": "Project Plan",
  "version": 42,
  "accessLevel": "OWNER",
  "createdAt": "2024-01-15T10:30:00Z",
  "modifiedAt": "2024-06-20T14:45:00Z",

  "properties": {
    "totalRowCount": 150,
    "dependenciesEnabled": true,
    "resourceManagementEnabled": false,
    "ganttEnabled": true
  },

  "columnSummary": [
    { "id": 111, "title": "Task Name", "type": "TEXT_NUMBER", "primary": true },
    { "id": 222, "title": "Assigned To", "type": "CONTACT_LIST" },
    { "id": 333, "title": "Due Date", "type": "DATE" },
    { "id": 444, "title": "Status", "type": "PICKLIST", "options": ["Not Started", "In Progress", "Complete"] },
    { "id": 555, "title": "% Complete", "type": "TEXT_NUMBER", "systemColumn": false }
  ],

  "preview": {
    "firstRows": [
      ["Task Name", "Assigned To", "Due Date", "Status", "% Complete"],
      ["Phase 1: Planning", "", "", "", "75%"],
      ["  Requirements gathering", "alice@example.com", "2024-02-01", "Complete", "100%"],
      ["  Design review", "bob@example.com", "2024-02-15", "Complete", "100%"]
    ],
    "lastRows": [
      ["  Final testing", "charlie@example.com", "2024-06-30", "In Progress", "50%"],
      ["Go Live", "", "2024-07-15", "Not Started", "0%"]
    ]
  },

  "systemColumns": {
    "rowNumber": { "index": 0 },
    "autoNumber": null,
    "createdBy": { "columnId": 666, "title": "Created By" },
    "createdDate": { "columnId": 777, "title": "Created" },
    "modifiedBy": { "columnId": 888, "title": "Modified By" },
    "modifiedDate": { "columnId": 999, "title": "Modified" }
  },

  "readOnlyColumns": [666, 777, 888, 999],

  "calculatedColumns": {
    "note": "With dependencies enabled, these columns auto-calculate for parent rows",
    "columns": ["Start Date", "End Date", "Duration", "% Complete"]
  }
}
```

**Key Fields:**
- `version`: Smartsheet's internal version number (useful for conflict detection)
- `columnSummary`: Quick reference without full column details
- `preview`: First/last rows for quick context (indentation shows hierarchy)
- `systemColumns`: Identifies auto-populated, read-only columns
- `calculatedColumns`: Warns about dependency-calculated values

---

### columns.json

Full column definitions with all properties.

```json
{
  "columns": [
    {
      "id": 111,
      "index": 0,
      "title": "Task Name",
      "type": "TEXT_NUMBER",
      "primary": true,
      "width": 300,
      "validation": false,
      "locked": false
    },
    {
      "id": 222,
      "index": 1,
      "title": "Assigned To",
      "type": "CONTACT_LIST",
      "contactOptions": [
        { "name": "Alice Smith", "email": "alice@example.com" },
        { "name": "Bob Jones", "email": "bob@example.com" }
      ],
      "width": 150
    },
    {
      "id": 333,
      "index": 2,
      "title": "Due Date",
      "type": "DATE",
      "width": 100
    },
    {
      "id": 444,
      "index": 3,
      "title": "Status",
      "type": "PICKLIST",
      "options": ["Not Started", "In Progress", "Complete", "On Hold"],
      "validation": true,
      "width": 120
    },
    {
      "id": 555,
      "index": 4,
      "title": "% Complete",
      "type": "TEXT_NUMBER",
      "width": 80
    },
    {
      "id": 666,
      "index": 5,
      "title": "Created By",
      "type": "CONTACT_LIST",
      "systemColumnType": "CREATED_BY"
    },
    {
      "id": 777,
      "index": 6,
      "title": "Created",
      "type": "DATETIME",
      "systemColumnType": "CREATED_DATE"
    }
  ]
}
```

---

### data.tsv

Tab-separated values for cell data. Similar to extrasheet's format.

```tsv
_rowId	_indent	Task Name	Assigned To	Due Date	Status	% Complete	Created By	Created
10001	0	Phase 1: Planning			Not Started	75%	alice@example.com	2024-01-15T10:30:00Z
10002	1	Requirements gathering	alice@example.com	2024-02-01	Complete	100%	alice@example.com	2024-01-15T10:35:00Z
10003	1	Design review	bob@example.com	2024-02-15	Complete	100%	alice@example.com	2024-01-15T10:40:00Z
10004	0	Phase 2: Development			In Progress	50%	alice@example.com	2024-01-20T09:00:00Z
10005	1	Backend implementation	charlie@example.com	2024-04-30	Complete	100%	bob@example.com	2024-01-25T14:00:00Z
10006	1	Frontend implementation	dave@example.com	2024-05-15	In Progress	60%	bob@example.com	2024-01-25T14:05:00Z
```

**Special Columns (prefixed with `_`):**
- `_rowId`: Smartsheet row ID (required for updates)
- `_indent`: Hierarchy level (0 = top level, 1 = child, 2 = grandchild, etc.)

**Format Rules:**
- First row is header (column titles)
- Tab-separated values
- Special characters escaped: `\t` (tab), `\n` (newline), `\r` (carriage return), `\\` (backslash)
- Empty cells are empty strings
- Dates in ISO 8601 format
- Contacts as email addresses
- Checkboxes as `true`/`false`
- Multi-select as comma-separated values

**Design Decision: Include Row IDs**

Unlike extrasheet (which uses grid position), we include `_rowId` because:
1. Smartsheet APIs require row IDs for updates
2. Row IDs are stable across re-ordering
3. Enables precise targeting without position ambiguity

---

### formulas.json

Sparse map of cells containing formulas.

```json
{
  "formulas": {
    "10001": {
      "% Complete": "=AVG(CHILDREN())"
    },
    "10004": {
      "% Complete": "=AVG(CHILDREN())"
    }
  },
  "columnFormulas": {
    "Total Cost": "=[Unit Cost]@row * [Quantity]@row"
  }
}
```

**Structure:**
- `formulas`: Keyed by row ID, then by column title
- `columnFormulas`: Formulas that apply to entire columns (detected heuristically)

**Design Decision: Separate from data.tsv**

Formulas are stored separately because:
1. data.tsv shows computed values (what user sees)
2. Formulas are sparse (most cells don't have them)
3. Easier to diff formula changes vs value changes

---

### format.json

Cell and row formatting in human-readable form.

```json
{
  "defaultFormat": {
    "fontFamily": "Arial",
    "fontSize": 10,
    "bold": false,
    "italic": false,
    "underline": false,
    "strikethrough": false,
    "textColor": "#000000",
    "backgroundColor": "#FFFFFF"
  },

  "rowFormats": {
    "10001": {
      "bold": true,
      "backgroundColor": "#E8F0FE"
    }
  },

  "cellFormats": {
    "10005": {
      "Status": {
        "backgroundColor": "#C6EFCE",
        "textColor": "#006100"
      }
    }
  },

  "conditionalFormats": [
    {
      "scope": "column",
      "column": "Status",
      "rules": [
        {
          "condition": { "equals": "Complete" },
          "format": { "backgroundColor": "#C6EFCE", "textColor": "#006100" }
        },
        {
          "condition": { "equals": "In Progress" },
          "format": { "backgroundColor": "#FFEB9C", "textColor": "#9C5700" }
        }
      ]
    }
  ],

  "rawFormats": {
    "_note": "Raw Smartsheet format descriptors, for reference",
    "10001": ",,1,,,,,,,,,,,,,"
  }
}
```

**Design Decision: Human-Readable + Raw**

Store both:
1. Human-readable JSON for agent editing
2. Raw format descriptors for lossless round-trip

---

### hierarchy.json

Explicit parent-child relationships.

```json
{
  "relationships": [
    { "rowId": 10002, "parentId": 10001 },
    { "rowId": 10003, "parentId": 10001 },
    { "rowId": 10005, "parentId": 10004 },
    { "rowId": 10006, "parentId": 10004 }
  ],

  "tree": {
    "10001": {
      "children": [10002, 10003]
    },
    "10004": {
      "children": [10005, 10006]
    }
  }
}
```

**Design Decision: Redundant Representations**

Include both flat list and tree structure:
- Flat list: Easy for diff detection
- Tree: Easy for agents to understand hierarchy

The `_indent` column in data.tsv provides a third view.

---

## Metadata Files

### .smartsheet/pull-metadata.json

```json
{
  "pulledAt": "2024-06-20T15:00:00Z",
  "sheetVersion": 42,
  "apiVersion": "2.0",
  "extrasmartsheetVersion": "0.1.0",
  "includeParams": ["format", "objectValue"],
  "rowLimit": null,
  "truncated": false
}
```

Tracks pull parameters for accurate diff/push.

### .smartsheet/format-tables.json

Cached output from `/serverinfo` endpoint. Contains:
- Available fonts
- Available colors (with hex codes)
- Font sizes
- Format descriptor position mappings

Used to translate between raw format descriptors and human-readable JSON.

---

## Pristine Copy

### .pristine/sheet.zip

Contains all files at pull time (excluding `.smartsheet/` and `.pristine/`).

```
sheet.zip
├── sheet.json
├── columns.json
├── data.tsv
├── formulas.json
├── format.json
└── hierarchy.json
```

Used as baseline for diff operations. Same pattern as extrasheet.

---

## File Creation Rules

Files are created only when they contain meaningful data:

| File | Created When |
|------|--------------|
| sheet.json | Always |
| columns.json | Always |
| data.tsv | Always (even if empty) |
| formulas.json | Sheet has any formulas |
| format.json | Any non-default formatting exists |
| hierarchy.json | Sheet has parent-child rows |
| attachments.json | Sheet has attachments (Phase 4) |
| discussions.json | Sheet has discussions (Phase 4) |

---

## Diff Behavior

### What Can Be Diffed

| Change Type | Supported | Notes |
|-------------|-----------|-------|
| Cell value | Yes | Core functionality |
| Cell formula | Yes | Via formulas.json |
| Cell format | Yes | Via format.json |
| Row add | Yes | New row ID generated by API |
| Row delete | Yes | By row ID |
| Row reorder | Yes | Via position specifiers |
| Row indent/outdent | Yes | Via parentId changes |
| Column add | Phase 2 | Requires careful ID handling |
| Column delete | Phase 2 | May break formulas |
| Column rename | Phase 2 | |
| Column reorder | Phase 2 | |

### What Cannot Be Diffed (Must Use Imperative)

- Complex structural changes (safest to re-pull after)
- Attachment file contents
- Cross-sheet reference creation/deletion

---

## Comparison with extrasheet

| Aspect | extrasheet | extrasmartsheet |
|--------|------------|-----------------|
| Primary data file | `data.tsv` | `data.tsv` |
| Row identifiers | Position (row number) | `_rowId` column |
| Formulas | `formula.json` (range keys) | `formulas.json` (row ID keys) |
| Formatting | `format.json` (range-based) | `format.json` (row/cell keys) |
| Hierarchy | N/A | `hierarchy.json` + `_indent` column |
| Multiple sheets | Subdirectories per sheet | Single file (Smartsheet = 1 sheet) |
| Pristine | `.pristine/spreadsheet.zip` | `.pristine/sheet.zip` |

**Key Difference: Single vs Multiple Sheets**

- Google Sheets: One spreadsheet contains multiple sheets (tabs)
- Smartsheet: Each sheet is standalone (though workspaces group them)

This simplifies extrasmartsheet's folder structure.

---

## Example Workflow

### Pull
```bash
python -m extrasmartsheet pull https://app.smartsheet.com/sheets/xxx123
```

Creates:
```
xxx123/
├── sheet.json
├── columns.json
├── data.tsv
├── formulas.json
├── .pristine/sheet.zip
└── .smartsheet/pull-metadata.json
```

### Edit
Agent modifies `data.tsv`:
```diff
-10006	1	Frontend implementation	dave@example.com	2024-05-15	In Progress	60%
+10006	1	Frontend implementation	dave@example.com	2024-05-20	Complete	100%
```

### Diff
```bash
python -m extrasmartsheet diff xxx123/
```

Output:
```json
{
  "updateRows": [
    {
      "id": 10006,
      "cells": [
        { "columnId": 333, "value": "2024-05-20" },
        { "columnId": 444, "value": "Complete" },
        { "columnId": 555, "value": "100%" }
      ]
    }
  ]
}
```

### Push
```bash
python -m extrasmartsheet push xxx123/
```

Executes `PUT /sheets/{sheetId}/rows` with the diff payload.

---

## Open Questions

1. **Row ID stability**: What happens when rows are deleted and re-added? Should we support ID reassignment?

2. **Large sheets**: Should we support pagination/partial pull? Smartsheet allows sheets with 20,000+ rows.

3. **Multi-contact cells**: How to represent `["alice@example.com", "bob@example.com"]` in TSV? Options:
   - JSON array in cell: `["alice@example.com","bob@example.com"]`
   - Delimiter: `alice@example.com;bob@example.com`

4. **Checkbox symbols**: Smartsheet supports star, flag, etc. How to represent in TSV?
   - `true`/`false` for all?
   - Symbol-specific like `star:true`?

5. **Comments in cells**: Smartsheet supports cell-level notes. Include in data.tsv or separate file?

---

## Implementation Priority

1. **Phase 1**: sheet.json, columns.json, data.tsv, .pristine/
2. **Phase 2**: formulas.json, hierarchy.json
3. **Phase 3**: format.json with human-readable conversion
4. **Phase 4**: attachments.json, discussions.json
