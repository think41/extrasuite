# extrasmartsheet Implementation Roadmap

This document outlines the implementation plan, challenges, and recommendations for building extrasmartsheet.

---

## Feasibility Assessment: Summary

**Verdict: Highly Feasible**

The Smartsheet API is well-designed for our pull-edit-diff-push workflow:

| Requirement | Support Level | Notes |
|-------------|---------------|-------|
| Read all data | Excellent | GET /sheets/{id} returns everything |
| Targeted updates | Good | PUT /rows supports bulk cell updates |
| Formula support | Good | Set via cell.formula property |
| Format support | Moderate | Format descriptors require translation |
| Hierarchy | Excellent | Native parent-child row support |
| Rate limits | Acceptable | 300 req/min, bulk operations help |

The main adaptation needed is shifting from cell-centric (Google Sheets) to row-centric (Smartsheet) operations.

---

## Implementation Phases

### Phase 1: Core Workflow (MVP)

**Goal:** Basic pull-edit-diff-push for cell values

**Deliverables:**
1. `pull` command - Fetch sheet, create local folder
2. `diff` command - Compare against pristine, show changes
3. `push` command - Apply changes via API

**Scope:**
- sheet.json (metadata)
- columns.json (column definitions)
- data.tsv (cell values with row IDs)
- .pristine/sheet.zip
- Basic error handling and retry logic

**Excludes:**
- Formulas (show computed values only)
- Formatting
- Hierarchy (flat indent column only)
- Attachments/Discussions

**Estimated Effort:** Core module structure + 3 commands

---

### Phase 2: Formulas and Hierarchy

**Goal:** Full formula support and hierarchy editing

**Deliverables:**
1. formulas.json - Sparse formula map
2. hierarchy.json - Parent-child relationships
3. Formula diff/push support
4. Row add/delete support
5. Indent/outdent support

**Challenges:**
- Detecting column formulas (no API flag)
- Handling calculated columns in project sheets
- Row position changes during push

**Estimated Effort:** Formula engine + hierarchy tracking

---

### Phase 3: Formatting

**Goal:** Preserve and edit cell/row formatting

**Deliverables:**
1. format.json with human-readable structure
2. FormatTables caching and translation
3. Format diff detection
4. Format push support

**Challenges:**
- Format descriptor parsing
- Color code mapping
- Conditional format handling

**Estimated Effort:** Format translation layer

---

### Phase 4: Collaboration Features

**Goal:** Support attachments and discussions

**Deliverables:**
1. attachments.json - Metadata (not file contents)
2. discussions.json - Comment threads
3. Optional include/exclude flags

**Challenges:**
- File upload/download handling
- Comment threading model
- Rate limit impact (10x multiplier)

**Estimated Effort:** Additional API integration

---

## Key Challenges and Solutions

### Challenge 1: Row-Centric API Model

**Problem:**
Google Sheets API supports cell-level operations. Smartsheet requires row-level operations.

**Impact:**
- Changing one cell requires sending the entire row
- Multiple cells in same row must be batched
- Cannot update cells independently

**Solution:**
```python
# Aggregate cell changes by row
def aggregate_changes(cell_changes: list[CellChange]) -> list[RowUpdate]:
    rows = defaultdict(list)
    for change in cell_changes:
        rows[change.row_id].append({
            "columnId": change.column_id,
            "value": change.new_value
        })
    return [
        {"id": row_id, "cells": cells}
        for row_id, cells in rows.items()
    ]
```

**Agent Guidance:**
- Teach agents that editing multiple cells in a row is efficient
- Warn about editing same row in multiple diff/push cycles

---

### Challenge 2: Save Collision (Error 4004)

**Problem:**
Concurrent API calls to same sheet cause save collisions.

**Impact:**
- Cannot parallelize updates
- Background saves in UI can conflict
- Rate limiting alone doesn't prevent this

**Solution:**
```python
async def push_with_collision_handling(sheet_id: str, rows: list) -> Result:
    max_retries = 5
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            return await api.update_rows(sheet_id, rows)
        except SaveCollisionError:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)
        except RateLimitError:
            await asyncio.sleep(60)

    raise PushFailedError("Max retries exceeded")
```

**Recommendations:**
1. Always serialize push operations
2. Implement exponential backoff with jitter
3. Consider adding `--force` flag to retry more aggressively
4. Document that concurrent users/automations may cause retries

---

### Challenge 3: System and Calculated Columns

**Problem:**
Some columns cannot be modified:
- System columns (Created Date, Modified By, etc.)
- Calculated columns in project sheets (parent row roll-ups)

**Impact:**
- Agents may try to edit read-only values
- Edits silently fail or are overwritten
- Confusing behavior

**Solution:**
1. Detect and flag in sheet.json:
   ```json
   {
     "readOnlyColumns": [666, 777, 888],
     "calculatedColumns": {
       "columns": ["Start Date", "End Date", "Duration"],
       "note": "Auto-calculated for parent rows with dependencies"
     }
   }
   ```

2. Exclude from diff comparison:
   ```python
   def should_compare_cell(column_id: int, row: Row) -> bool:
       if column_id in sheet.read_only_columns:
           return False
       if column_id in sheet.calculated_columns and row.has_children:
           return False
       return True
   ```

3. Warn agents in skill documentation

---

### Challenge 4: Formula Syntax Differences

**Problem:**
Smartsheet formulas use column names, not A1 notation:
- Google Sheets: `=A1+B1`
- Smartsheet: `=[Cost]@row + [Revenue]@row`

**Impact:**
- Cannot reuse extrasheet formula logic
- Agents familiar with Excel/Sheets may use wrong syntax
- Cross-sheet references need explicit setup

**Solution:**
1. **Do not translate** - Use native Smartsheet syntax
2. Document syntax in agent guide:
   ```markdown
   ## Smartsheet Formula Syntax

   | Concept | Syntax | Example |
   |---------|--------|---------|
   | Same row | `@row` | `=[Column]@row` |
   | Specific row | Row number | `=[Column]5` |
   | Column range | `:` | `=[Column]:[Column]` |
   | Hierarchy | Functions | `=SUM(CHILDREN([Cost]))` |
   ```

3. Validate formula syntax before push (basic check)

---

### Challenge 5: Column Formula Detection

**Problem:**
API doesn't expose column-level formula attribute. Each cell shows its formula individually.

**Impact:**
- Cannot distinguish "column formula" from "same formula in every cell"
- Inefficient storage if every cell formula stored

**Solution:**
Heuristic detection:
```python
def detect_column_formulas(sheet_data) -> dict[str, str]:
    """Detect columns where all non-empty cells have equivalent formulas."""
    column_formulas = {}

    for column in sheet_data.columns:
        formulas = []
        for row in sheet_data.rows:
            cell = row.get_cell(column.id)
            if cell.formula:
                # Normalize @row references
                normalized = cell.formula.replace(f"@row", "@row")
                formulas.append(normalized)

        if formulas and all(f == formulas[0] for f in formulas):
            column_formulas[column.title] = formulas[0]

    return column_formulas
```

Store detected column formulas separately in formulas.json.

---

### Challenge 6: Format Descriptor Translation

**Problem:**
Smartsheet uses opaque format strings: `",,1,1,,,,,,,,,,,,,"`.

**Impact:**
- Not human-readable
- Not agent-editable
- Requires mapping tables

**Solution:**
1. Fetch FormatTables from `/serverinfo` on first pull
2. Cache in `.smartsheet/format-tables.json`
3. Translate to/from human-readable:

```python
# Format descriptor positions (from FormatTables)
FORMAT_POSITIONS = {
    0: "fontFamily",
    1: "fontSize",
    2: "bold",
    3: "italic",
    4: "underline",
    5: "strikethrough",
    # ... etc
}

def parse_format_descriptor(descriptor: str, tables: FormatTables) -> dict:
    """Convert format descriptor to human-readable dict."""
    parts = descriptor.split(",")
    result = {}

    for i, value in enumerate(parts):
        if value and i in FORMAT_POSITIONS:
            key = FORMAT_POSITIONS[i]
            if key in ["bold", "italic", "underline", "strikethrough"]:
                result[key] = value == "1"
            elif key == "fontFamily":
                result[key] = tables.fonts[int(value)]
            elif key == "fontSize":
                result[key] = tables.font_sizes[int(value)]
            # ... etc

    return result
```

---

### Challenge 7: Large Sheets

**Problem:**
Smartsheet sheets can have 20,000+ rows. Full pull may:
- Take too long
- Exceed memory limits
- Create huge local files

**Impact:**
- Poor UX for large sheets
- Token-inefficient for LLM agents

**Solution:**
1. **Pagination support:**
   ```bash
   python -m extrasmartsheet pull <url> --max-rows 500
   ```

2. **Row filtering:**
   ```bash
   python -m extrasmartsheet pull <url> --filter "Status=Active"
   ```

3. **Truncation indicator** in sheet.json:
   ```json
   {
     "totalRowCount": 15000,
     "pulledRowCount": 500,
     "truncated": true,
     "truncationNote": "Use --max-rows to pull more rows"
   }
   ```

4. **Partial push** - Only push changed rows (already row-based)

---

### Challenge 8: Row ID Management

**Problem:**
When adding new rows:
- No row ID exists yet
- ID assigned by API after creation
- Subsequent operations need the new ID

**Impact:**
- Two-step process for add + modify
- Agent must re-pull after adding rows

**Solution:**
1. Use placeholder IDs for new rows:
   ```tsv
   _rowId	Task Name	Status
   10001	Existing Task	Done
   NEW_1	New Task	Pending
   NEW_2	Another New Task	Pending
   ```

2. Push processes new rows first:
   ```python
   async def push_changes(changes: DiffResult):
       # Step 1: Add new rows, get assigned IDs
       new_row_ids = await add_new_rows(changes.new_rows)

       # Step 2: Update existing rows (including formula refs to new rows)
       await update_rows(changes.modified_rows, new_row_ids)

       # Step 3: Delete removed rows
       await delete_rows(changes.deleted_rows)
   ```

3. Return ID mapping for agent reference:
   ```json
   {
     "created": {
       "NEW_1": 10050,
       "NEW_2": 10051
     }
   }
   ```

---

## Architecture Recommendations

### 1. Reuse extrasheet Patterns

| Pattern | Reuse Level | Notes |
|---------|-------------|-------|
| Transport abstraction | Full | Interface identical |
| Pristine mechanism | Full | Same zip-based approach |
| File writer | Partial | Adapt for single-sheet |
| Diff engine | Partial | Row-based vs range-based |
| Request generator | New | Different API structure |
| CLI structure | Full | Same pull/diff/push pattern |

### 2. Transport Interface

```python
from abc import ABC, abstractmethod

class SmartsheetTransport(ABC):
    @abstractmethod
    async def get_sheet(self, sheet_id: str, include: list[str]) -> SheetData:
        pass

    @abstractmethod
    async def update_rows(self, sheet_id: str, rows: list[RowUpdate]) -> UpdateResult:
        pass

    @abstractmethod
    async def add_rows(self, sheet_id: str, rows: list[NewRow]) -> list[Row]:
        pass

    @abstractmethod
    async def delete_rows(self, sheet_id: str, row_ids: list[int]) -> None:
        pass

class SmartsheetAPITransport(SmartsheetTransport):
    """Production implementation using Smartsheet API."""
    pass

class LocalFileTransport(SmartsheetTransport):
    """Test implementation using golden files."""
    pass
```

### 3. Use Official Python SDK

Smartsheet provides an official Python SDK with:
- Built-in retry logic for rate limits
- Request/response models
- Logging and debugging support

```python
import smartsheet

client = smartsheet.Smartsheet(access_token)
client.errors_as_exceptions(True)

# Retry settings
client.retry_max_retries = 5
client.retry_wait_time = 2
```

**Recommendation:** Use SDK for API calls, wrap in our transport interface.

### 4. Testing Strategy

Same approach as extrasheet:

1. **Golden file tests:**
   - Capture real API responses
   - Store in `tests/golden/{sheet_id}/`
   - Test pull against cached responses

2. **Diff tests:**
   - Start from golden pulled state
   - Apply known edits
   - Assert generated API request matches expected

3. **Integration tests:**
   - Use test Smartsheet account
   - Create/modify/delete real sheets
   - Run sparingly (rate limits)

---

## SDK vs Direct API

### Option A: Use Official Smartsheet Python SDK

**Pros:**
- Built-in retry logic
- Type hints and models
- Maintained by Smartsheet
- Handles auth token refresh

**Cons:**
- Adds dependency
- May lag behind API changes
- Less control over request details

### Option B: Direct HTTP (like extrasheet)

**Pros:**
- Full control
- Consistent with extrasheet approach
- Lighter dependency

**Cons:**
- Must implement retry logic
- Must track API changes
- More code to maintain

**Recommendation:** Start with SDK, wrap in transport interface. Can swap to direct HTTP later if needed.

---

## Authentication Integration

### Approach 1: Reuse extrasuite.client

Extend the existing auth system:
```bash
uvx extrasuite login --service smartsheet
```

Server issues Smartsheet OAuth tokens alongside Google tokens.

**Pros:**
- Unified auth experience
- Server manages tokens
- Consistent with extrasheet

**Cons:**
- Requires server changes
- More complex OAuth setup

### Approach 2: Standalone Auth

Separate token management:
```bash
uvx extrasmartsheet login
```

Store token in OS keyring under different key.

**Pros:**
- Independent of server
- Simpler initial implementation
- Users can use their own API tokens

**Cons:**
- Inconsistent UX
- Multiple login commands

**Recommendation:** Start with Approach 2 (standalone), migrate to Approach 1 later.

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Rate limits hit frequently | Medium | Medium | Bulk operations, caching |
| Save collisions in team use | High | Low | Retry logic, documentation |
| Large sheet performance | Medium | Medium | Pagination, row limits |
| Formula syntax confusion | Medium | Low | Clear documentation |
| API changes | Low | Medium | SDK abstracts changes |
| Calculated column edits fail | Medium | Low | Read-only flagging |

---

## Success Metrics

1. **Pull works correctly** - All cell values, formulas, formatting preserved
2. **Diff is accurate** - Detects all changes, no false positives
3. **Push is reliable** - Handles retries, partial success
4. **Agent usability** - Clear documentation, predictable behavior
5. **Performance** - Reasonable time for 1000-row sheets

---

## Timeline Suggestion

| Phase | Estimated Duration | Dependencies |
|-------|-------------------|--------------|
| Phase 1 (Core) | 2-3 weeks | None |
| Phase 2 (Formulas/Hierarchy) | 2 weeks | Phase 1 |
| Phase 3 (Formatting) | 1-2 weeks | Phase 1 |
| Phase 4 (Attachments) | 1 week | Phase 1 |
| Documentation | Ongoing | All phases |
| Testing | Ongoing | All phases |

---

## Open Questions for Stakeholders

1. **Should extrasmartsheet be part of extrasuite or standalone package?**
   - Standalone: `pip install extrasmartsheet`
   - Bundled: Part of extrasuite monorepo

2. **Authentication model?**
   - Per-user Smartsheet tokens via extrasuite server
   - Direct API token input
   - OAuth flow within extrasmartsheet

3. **Workspace/folder support?**
   - Should we support pulling entire workspaces?
   - Or stick to individual sheets only?

4. **Priority of phases?**
   - Is formatting important for initial release?
   - Is hierarchy critical (most project sheets use it)?

---

## Conclusion

Building extrasmartsheet is highly feasible. The Smartsheet API provides all necessary capabilities for a pull-edit-diff-push workflow. Key adaptations from extrasheet:

1. **Row-centric operations** instead of cell-centric
2. **Row IDs** instead of position-based addressing
3. **Single sheet per folder** instead of multi-sheet
4. **Save collision handling** with retry logic
5. **Native formula syntax** (no translation)

The architecture can closely follow extrasheet, with the transport layer abstracting API differences. Phase 1 can deliver a functional MVP quickly, with subsequent phases adding advanced features.
