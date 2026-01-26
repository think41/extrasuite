# Fly-Blind Editing: LLM Agent Perspective Review

This document reviews the extrasheet specification from the perspective of an LLM agent that needs to modify spreadsheets based on user instructions, using `batchUpdate` requests without refreshing the spreadsheet state.

## 1. Use Case Scenarios

### Scenario A: Financial Analyst Tasks
- "Add a SUM formula at the bottom of column B"
- "Format the header row with bold text and blue background"
- "Create a chart showing quarterly revenue trends"
- "Add conditional formatting to highlight negative values in red"

### Scenario B: HR Analyst Tasks
- "Add a new column for employee start dates"
- "Create a pivot table summarizing headcount by department"
- "Apply data validation to the salary column (1000-500000)"
- "Protect the header row from editing"

### Scenario C: Data Maintenance Tasks
- "Update all cells containing 'Old Company' to 'New Company'"
- "Insert 5 rows after the header"
- "Delete columns E through G"
- "Sort the data by column C descending"

## 2. Information Requirements for Fly-Blind Editing

For each batchUpdate request type, I assess whether the extrasheet representation provides sufficient information.

### 2.1 Cell Value Updates (`UpdateCellsRequest`, `RepeatCellRequest`)

**Required Information:**
- Sheet ID (from `spreadsheet.json`)
- Target cell/range coordinates
- Current values (optional, but helpful for validation)

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Sheet ID | `spreadsheet.json#sheets[].sheetId` | ✅ Yes |
| Sheet title to ID mapping | `spreadsheet.json#sheets[]` | ✅ Yes |
| Grid dimensions | `spreadsheet.json#sheets[].gridProperties` | ✅ Yes |
| Current values | `data.tsv` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.2 Formula Updates

**Required Information:**
- Target cell coordinates
- Understanding of existing formulas (to avoid breaking references)
- Named ranges that might be affected

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Existing formulas | `formula.json#formulas` | ✅ Yes |
| Array formula ranges | `formula.json#arrayFormulas` | ✅ Yes |
| Named ranges | `named_ranges.json` | ✅ Yes |
| Data source formulas | `formula.json#dataSourceFormulas` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

**Caution:** The agent must understand that inserting/deleting rows/columns can shift formula references. The specification should note this risk.

### 2.3 Formatting Updates (`RepeatCellRequest`, `UpdateCellsRequest`)

**Required Information:**
- Target range
- Format properties to apply/modify
- Merged cell awareness (to avoid partial updates to merged ranges)

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Existing cell formats | `format.json#cellFormats` | ✅ Yes |
| Default format | `format.json#defaultFormat` | ✅ Yes |
| Merged ranges | `format.json#merges` | ✅ Yes |
| Conditional formats | `format.json#conditionalFormats` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.4 Structural Changes (Insert/Delete Rows/Columns)

**Required Information:**
- Sheet ID
- Current row/column count
- Understanding of what will be affected (formulas, merges, charts, etc.)

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Grid dimensions | `spreadsheet.json#sheets[].gridProperties` | ✅ Yes |
| Row/column groups | `dimension.json#rowGroups/columnGroups` | ✅ Yes |
| Formula locations | `formula.json` | ✅ Yes |
| Chart source ranges | `feature.json#charts` | ✅ Yes |
| Pivot source ranges | `feature.json#pivotTables` | ✅ Yes |
| Protected ranges | `protection.json` | ✅ Yes |

**Verdict: ⚠️ SUFFICIENT with caveats**

**Caveats:**
1. Inserting/deleting rows/columns shifts all absolute references in formulas
2. Charts, pivot tables, and named ranges reference specific ranges that will shift
3. The agent cannot predict the new state without re-fetching

**Recommendation:** After structural changes, the agent should note that formula references and feature ranges may have shifted and recommend re-pulling the spreadsheet.

### 2.5 Chart Operations

**Required Information:**
- Chart ID (for updates/deletes)
- Sheet ID
- Data source ranges
- Chart position

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Existing charts | `feature.json#charts` | ✅ Yes |
| Chart IDs | `feature.json#charts[].chartId` | ✅ Yes |
| Chart specs | `feature.json#charts[].spec` | ✅ Yes |
| Chart positions | `feature.json#charts[].position` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.6 Pivot Table Operations

**Required Information:**
- Anchor cell location
- Source data range
- Row/column grouping configuration
- Value aggregation settings

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Pivot tables | `feature.json#pivotTables` | ✅ Yes |
| Anchor cells | `feature.json#pivotTables[].anchorCell` | ✅ Yes |
| Source ranges | `feature.json#pivotTables[].source` | ✅ Yes |
| Row/column config | `feature.json#pivotTables[].rows/columns` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.7 Filter Operations

**Required Information:**
- Filter range
- Filter criteria
- Sort specifications

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Basic filter | `feature.json#basicFilter` | ✅ Yes |
| Filter views | `feature.json#filterViews` | ✅ Yes |
| Filter criteria | Both include `filterSpecs` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.8 Protection Operations

**Required Information:**
- Protected range ID (for updates)
- Range to protect
- Editor permissions

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Protected ranges | `protection.json` | ✅ Yes |
| Range IDs | `protection.json#protectedRanges[].protectedRangeId` | ✅ Yes |
| Editor list | `protection.json#protectedRanges[].editors` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.9 Named Range Operations

**Required Information:**
- Named range ID (for updates/deletes)
- Name
- Range definition

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Named ranges | `named_ranges.json` | ✅ Yes |
| IDs | `namedRanges[].namedRangeId` | ✅ Yes |
| Names | `namedRanges[].name` | ✅ Yes |
| Range definitions | `namedRanges[].range` | ✅ Yes |

**Verdict: ✅ SUFFICIENT for fly-blind editing**

### 2.10 Conditional Formatting Operations

**Required Information:**
- Rule index (for updates/deletes)
- Condition type and values
- Format to apply
- Target ranges

**Provided by extrasheet:**
| Information | File | Sufficient? |
|-------------|------|-------------|
| Conditional formats | `format.json#conditionalFormats` | ✅ Yes |
| Rule details | Full `ConditionalFormatRule` objects | ✅ Yes |

**Verdict: ⚠️ PARTIALLY SUFFICIENT**

**Issue:** Conditional format rules are identified by index, not ID. The index can change if rules are added/deleted. The specification should include the rule index.

**Recommendation:** Add `ruleIndex` to each conditional format rule in `format.json`.

### 2.11 Data Validation Operations

**Required Information:**
- Target cell/range
- Validation rule

**Current Status:** Data validation is referenced but not fully specified in feature.json.

**Recommendation:** Add explicit `dataValidation` section to `feature.json`:

```json
{
  "dataValidation": [
    {
      "range": "B2:B100",
      "rule": {
        "condition": {
          "type": "NUMBER_BETWEEN",
          "values": [
            { "userEnteredValue": "0" },
            { "userEnteredValue": "100" }
          ]
        },
        "inputMessage": "Enter a number between 0 and 100",
        "strict": true,
        "showCustomUi": true
      }
    }
  ]
}
```

**Verdict: ⚠️ NEEDS ENHANCEMENT - Add data validation section**

## 3. Critical IDs and References

For fly-blind editing, the agent must track various IDs to correctly target update operations.

### 3.1 ID Tracking Summary

| Object Type | ID Field | Location in extrasheet |
|-------------|----------|------------------------|
| Sheet | `sheetId` | `spreadsheet.json#sheets[].sheetId` |
| Chart | `chartId` | `feature.json#charts[].chartId` |
| Named Range | `namedRangeId` | `named_ranges.json#namedRanges[].namedRangeId` |
| Protected Range | `protectedRangeId` | `protection.json#protectedRanges[].protectedRangeId` |
| Filter View | `filterViewId` | `feature.json#filterViews[].filterViewId` |
| Slicer | `slicerId` | `feature.json#slicers[].slicerId` |
| Banded Range | `bandedRangeId` | `feature.json#bandedRanges[].bandedRangeId` |
| Table | `tableId` | `feature.json#tables[].tableId` |
| Developer Metadata | `metadataId` | `developer_metadata.json` |
| Data Source | `dataSourceId` | `data_sources.json#dataSources[].dataSourceId` |

**Verdict: ✅ All necessary IDs are captured**

### 3.2 ID Generation for New Objects

When creating new objects, the API assigns IDs automatically. The agent should:
1. Use temporary placeholder IDs (negative numbers by convention)
2. Note that actual IDs will be in the response
3. Recommend re-pulling if the agent needs to reference newly created objects

## 4. Consistency and Atomicity Considerations

### 4.1 BatchUpdate Atomicity

Google Sheets API `batchUpdate` is atomic - either all requests succeed or none do. The extrasheet representation enables building complete batch requests.

### 4.2 State Consistency Risks

| Operation | Risk | Mitigation |
|-----------|------|------------|
| Insert/Delete rows | Shifts formula references | Note in response; recommend re-pull |
| Delete sheet | Breaks cross-sheet references | Check for references before delete |
| Rename sheet | Breaks string-based references | Use sheetId in formulas when possible |
| Move dimensions | Shifts all coordinates | Note affected features |

### 4.3 Recommendations for Agents

1. **Simple value edits**: Safe to fly blind
2. **Formula edits**: Safe if not changing structure
3. **Structural changes**: Document impact; recommend re-pull
4. **Feature additions**: Safe; note new IDs will be assigned
5. **Feature updates**: Safe if using correct IDs
6. **Feature deletes**: Safe if using correct IDs

## 5. Information Gaps and Enhancements

### 5.1 Must-Have Enhancements

1. **Add `ruleIndex` to conditional format rules** in `format.json`
2. **Add `dataValidation` section** to `feature.json`
3. **Add cell notes** to `format.json` (currently missing)

### 5.2 Nice-to-Have Enhancements

1. **Add `hyperlinks` section** in `format.json` for cells with HYPERLINK functions
2. **Add `comments` support** (if using Google Sheets comments API)
3. **Add `lastModifiedTime` metadata** for staleness detection

### 5.3 Updated format.json Structure

```json
{
  "defaultFormat": { /* CellFormat */ },

  "cellFormats": { /* ... */ },

  "conditionalFormats": [
    {
      "ruleIndex": 0,  // ADD THIS
      "ranges": ["B2:B100"],
      "booleanRule": { /* ... */ }
    }
  ],

  "merges": [ /* ... */ ],

  "textFormatRuns": { /* ... */ },

  "notes": {  // ADD THIS SECTION
    "A1": "This is a note on cell A1",
    "B5": "Another note"
  }
}
```

### 5.4 Updated feature.json Structure

```json
{
  /* existing sections */

  "dataValidation": [  // ADD THIS SECTION
    {
      "range": "B2:B100",
      "rule": {
        "condition": { "type": "NUMBER_BETWEEN", "values": [{"userEnteredValue": "0"}, {"userEnteredValue": "100"}] },
        "inputMessage": "Enter 0-100",
        "strict": true,
        "showCustomUi": true
      }
    }
  ]
}
```

## 6. Example Fly-Blind Editing Workflows

### 6.1 Add SUM Formula

**User request:** "Add a SUM formula at B10 that totals B2:B9"

**Agent reads:** `spreadsheet.json` (to get sheetId), `data.tsv` (to verify data range)

**Agent generates:**
```json
{
  "requests": [
    {
      "updateCells": {
        "rows": [{ "values": [{ "userEnteredValue": { "formulaValue": "=SUM(B2:B9)" } }] }],
        "fields": "userEnteredValue",
        "start": { "sheetId": 0, "rowIndex": 9, "columnIndex": 1 }
      }
    }
  ]
}
```

**Fly-blind safe:** ✅ Yes

### 6.2 Insert Row

**User request:** "Insert a new row after row 5"

**Agent reads:** `spreadsheet.json` (sheetId, dimensions), `formula.json` (to warn about shifts)

**Agent generates:**
```json
{
  "requests": [
    {
      "insertDimension": {
        "range": { "sheetId": 0, "dimension": "ROWS", "startIndex": 5, "endIndex": 6 },
        "inheritFromBefore": true
      }
    }
  ]
}
```

**Agent notes:** "This will shift all rows below row 5. Formulas referencing rows 6+ will update automatically, but you may want to re-pull the spreadsheet to see the new state."

**Fly-blind safe:** ⚠️ With caveats

### 6.3 Update Chart Title

**User request:** "Change the chart title to 'Q1 2024 Revenue'"

**Agent reads:** `feature.json` (to get chartId and current spec)

**Agent generates:**
```json
{
  "requests": [
    {
      "updateChartSpec": {
        "chartId": 123456,
        "spec": {
          "title": "Q1 2024 Revenue",
          "basicChart": { /* preserve existing spec */ }
        }
      }
    }
  ]
}
```

**Fly-blind safe:** ✅ Yes

### 6.4 Add Conditional Formatting

**User request:** "Highlight cells in column C that are greater than 1000 with green background"

**Agent reads:** `spreadsheet.json` (sheetId), `format.json` (existing rules)

**Agent generates:**
```json
{
  "requests": [
    {
      "addConditionalFormatRule": {
        "rule": {
          "ranges": [{ "sheetId": 0, "startColumnIndex": 2, "endColumnIndex": 3 }],
          "booleanRule": {
            "condition": { "type": "NUMBER_GREATER", "values": [{ "userEnteredValue": "1000" }] },
            "format": { "backgroundColorStyle": { "rgbColor": { "red": 0.8, "green": 1.0, "blue": 0.8 } } }
          }
        },
        "index": 0
      }
    }
  ]
}
```

**Fly-blind safe:** ✅ Yes

## 7. Conclusion

The extrasheet specification provides **sufficient information for most fly-blind editing scenarios**. The key enhancements needed are:

1. **Add `ruleIndex` to conditional format rules**
2. **Add `dataValidation` section to feature.json**
3. **Add `notes` section to format.json**

With these additions, an LLM agent can confidently:
- Read the file representation
- Generate correct `batchUpdate` requests
- Apply changes without re-fetching spreadsheet state

The main scenarios where re-fetching is recommended:
- After structural changes (insert/delete rows/columns)
- After creating new objects that need to be referenced (charts, named ranges)
- After operations that may have cascading effects (sheet deletion, name changes)
