# SQLite Sync Model for Smartsheet

This document explores an alternative architecture: using SQLite as the local representation with bidirectional sync to Smartsheet.

## Why SQLite?

Smartsheet is fundamentally a **typed database with a web UI**, not a freeform spreadsheet:

| Smartsheet Feature | Database Equivalent |
|-------------------|---------------------|
| Columns with types | Schema with typed columns |
| Row IDs | Primary keys |
| Picklist options | Foreign key constraints / enums |
| Contact columns | Reference to users table |
| System columns | Auto-generated fields |
| Filters | WHERE clauses |
| Cross-sheet references | JOINs / foreign keys |

**SQLite is a natural fit** because:
1. Explicit schema maps directly to Smartsheet columns
2. Row IDs become primary keys
3. SQL provides powerful query/filter capabilities
4. Change tracking is well-solved (triggers, WAL)
5. Single file, portable, great tooling
6. Agents can use SQL to query and modify data

---

## Sync Model Overview

```
┌─────────────────────┐                    ┌─────────────────────┐
│   Smartsheet API    │◄──── sync ────────►│   Local SQLite DB   │
│                     │                    │                     │
│  - Sheet data       │   pull: fetch      │  - Main table       │
│  - Version tracking │   ─────────────►   │  - _sync_meta       │
│  - rowsModifiedSince│                    │  - _changes log     │
│  - Webhooks         │   push: deltas     │  - Schema matches   │
│                     │   ◄─────────────   │    Smartsheet cols  │
└─────────────────────┘                    └─────────────────────┘
```

### Key Insight: Smartsheet Has Sync Primitives

1. **`GET /sheets/{id}/version`** - Check if sheet changed (1 API call, no data)
2. **`rowsModifiedSince` parameter** - Fetch only rows modified after timestamp
3. **Webhooks** - Real-time push notifications when sheet changes
4. **Row IDs are stable** - Can track individual rows across syncs

---

## Sync Operations

### Initial Pull (Full Sync)

```bash
python -m smartsheetsync pull <sheet_url_or_id>
```

1. Fetch sheet metadata and all rows
2. Create SQLite database with matching schema
3. Insert all rows
4. Set up change tracking triggers
5. Record sync metadata (version, timestamp)

**Result:** `<sheet_id>.db` file

### Incremental Pull

```bash
python -m smartsheetsync pull <sheet_id>.db
```

1. Read last sync timestamp from `_sync_meta`
2. Call `GET /sheets/{id}/version` - quick check if changed
3. If unchanged, done (no API data transfer)
4. If changed, fetch with `rowsModifiedSince=<last_sync>`
5. Update local rows (INSERT/UPDATE)
6. Handle deletions (see below)
7. Update sync metadata

### Push (Local Changes to Remote)

```bash
python -m smartsheetsync push <sheet_id>.db
```

1. Read `_changes` table for local modifications
2. Group changes by operation type (INSERT/UPDATE/DELETE)
3. Push to Smartsheet API:
   - `POST /sheets/{id}/rows` for new rows
   - `PUT /sheets/{id}/rows` for updates
   - `DELETE /sheets/{id}/rows?ids=...` for deletions
4. Clear `_changes` table on success
5. Update sync metadata

### Bidirectional Sync

```bash
python -m smartsheetsync sync <sheet_id>.db
```

1. Pull remote changes first
2. Detect conflicts (same row modified both locally and remotely)
3. Resolve conflicts (last-write-wins, or prompt user)
4. Push local changes

---

## SQLite Schema Design

### Main Data Table

Generated from Smartsheet column definitions:

```sql
CREATE TABLE sheet_data (
    -- Smartsheet metadata (always present)
    _row_id INTEGER PRIMARY KEY,      -- Smartsheet row ID
    _row_number INTEGER,              -- Display order
    _parent_id INTEGER,               -- Hierarchy parent
    _indent INTEGER DEFAULT 0,        -- Hierarchy level
    _created_at TEXT,                 -- ISO timestamp
    _modified_at TEXT,                -- ISO timestamp

    -- User columns (from Smartsheet schema)
    "Task Name" TEXT,                 -- TEXT_NUMBER → TEXT
    "Assigned To" TEXT,               -- CONTACT_LIST → TEXT (email)
    "Due Date" TEXT,                  -- DATE → TEXT (ISO format)
    "Status" TEXT CHECK("Status" IN ('Not Started', 'In Progress', 'Complete')),
    "Priority" TEXT,                  -- PICKLIST → TEXT with CHECK
    "% Complete" REAL,                -- Percentage → REAL
    "Cost" REAL,                      -- Currency → REAL
    "Done" INTEGER,                   -- CHECKBOX → INTEGER (0/1)

    -- Indexes for common queries
    FOREIGN KEY (_parent_id) REFERENCES sheet_data(_row_id)
);

CREATE INDEX idx_parent ON sheet_data(_parent_id);
CREATE INDEX idx_modified ON sheet_data(_modified_at);
```

### Type Mapping

| Smartsheet Type | SQLite Type | Notes |
|-----------------|-------------|-------|
| TEXT_NUMBER | TEXT or REAL | Detect from data |
| CONTACT_LIST | TEXT | Store email |
| MULTI_CONTACT_LIST | TEXT | JSON array of emails |
| DATE | TEXT | ISO 8601 date |
| DATETIME | TEXT | ISO 8601 datetime |
| DURATION | TEXT | Duration string |
| CHECKBOX | INTEGER | 0 or 1 |
| PICKLIST | TEXT | With CHECK constraint |
| MULTI_PICKLIST | TEXT | JSON array |
| PREDECESSOR | TEXT | JSON structure |
| AUTO_NUMBER | TEXT | Read-only |
| CREATED_BY | TEXT | Read-only, email |
| CREATED_DATE | TEXT | Read-only |
| MODIFIED_BY | TEXT | Read-only, email |
| MODIFIED_DATE | TEXT | Read-only |

### Sync Metadata Table

```sql
CREATE TABLE _sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Example entries:
-- ('sheet_id', '1234567890')
-- ('sheet_name', 'Project Plan')
-- ('sheet_version', '42')
-- ('last_sync_at', '2024-06-20T15:00:00Z')
-- ('last_modified_since', '2024-06-20T14:55:00Z')
-- ('smartsheet_url', 'https://app.smartsheet.com/sheets/...')
```

### Column Metadata Table

```sql
CREATE TABLE _columns (
    column_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    index_pos INTEGER,
    primary_col INTEGER DEFAULT 0,
    system_column_type TEXT,
    options TEXT,  -- JSON for picklist options
    formula TEXT,  -- Column formula if any
    read_only INTEGER DEFAULT 0
);
```

### Change Tracking Table

```sql
CREATE TABLE _changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    row_id INTEGER,           -- NULL for new rows (assigned on push)
    operation TEXT NOT NULL,  -- 'INSERT', 'UPDATE', 'DELETE'
    column_name TEXT,         -- NULL for row-level ops
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now')),
    pushed INTEGER DEFAULT 0  -- Mark as pushed
);

CREATE INDEX idx_changes_unpushed ON _changes(pushed) WHERE pushed = 0;
```

### Change Tracking Triggers

```sql
-- Track INSERTs
CREATE TRIGGER track_insert AFTER INSERT ON sheet_data
BEGIN
    INSERT INTO _changes (row_id, operation, changed_at)
    VALUES (NEW._row_id, 'INSERT', datetime('now'));
END;

-- Track UPDATEs (per column)
CREATE TRIGGER track_update AFTER UPDATE ON sheet_data
WHEN OLD."Task Name" != NEW."Task Name"
   OR OLD."Status" != NEW."Status"
   -- ... other columns
BEGIN
    INSERT INTO _changes (row_id, operation, column_name, old_value, new_value)
    SELECT NEW._row_id, 'UPDATE', 'Task Name', OLD."Task Name", NEW."Task Name"
    WHERE OLD."Task Name" IS NOT NEW."Task Name";
    -- Repeat for each column...
END;

-- Track DELETEs
CREATE TRIGGER track_delete AFTER DELETE ON sheet_data
BEGIN
    INSERT INTO _changes (row_id, operation, old_value)
    VALUES (OLD._row_id, 'DELETE', json_object(
        'Task Name', OLD."Task Name",
        'Status', OLD."Status"
        -- ... capture full row for undo
    ));
END;
```

**Alternative: Use sqlite-history library**

Simon Willison's [sqlite-history](https://github.com/simonw/sqlite-history) can auto-generate these triggers.

---

## Handling Deletions

### The Problem

`rowsModifiedSince` returns modified rows but **not deleted rows**. How do we know what was deleted remotely?

### Solutions

#### Option A: Full Row ID Comparison (Simple)

On each pull:
1. Fetch all row IDs from Smartsheet (lightweight call)
2. Compare with local row IDs
3. Delete local rows not in remote set

```sql
-- After fetching remote_row_ids
DELETE FROM sheet_data
WHERE _row_id NOT IN (remote_row_ids)
  AND _row_id NOT IN (SELECT row_id FROM _changes WHERE operation = 'INSERT');
```

**Pros:** Simple, always correct
**Cons:** Requires fetching all row IDs (though not full data)

#### Option B: Webhook Notifications (Real-time)

Set up webhook to receive deletion events:

```json
{
  "events": [{
    "objectType": "row",
    "eventType": "deleted",
    "id": 123456789
  }]
}
```

**Pros:** Real-time, no polling
**Cons:** Requires server endpoint, more complex setup

#### Option C: Periodic Full Sync

Treat `rowsModifiedSince` as optimization; periodically do full sync:

```python
if time_since_full_sync > timedelta(hours=24):
    full_sync()
else:
    incremental_sync()
```

**Pros:** Simple, catches all edge cases
**Cons:** Occasional heavy operation

### Recommendation

Use **Option A** for initial implementation. The row ID list is small (just integers) and API allows fetching just IDs efficiently.

---

## Conflict Resolution

### Conflict Detection

A conflict occurs when:
- Same `_row_id` modified both locally (in `_changes`) and remotely (different `_modified_at`)

```sql
-- Find conflicts before push
SELECT c.row_id, c.column_name, c.new_value as local_value
FROM _changes c
JOIN sheet_data s ON c.row_id = s._row_id
WHERE c.pushed = 0
  AND s._modified_at > (SELECT value FROM _sync_meta WHERE key = 'last_sync_at');
```

### Resolution Strategies

| Strategy | Behavior |
|----------|----------|
| **last-write-wins** | Remote wins (most common) |
| **local-wins** | Local changes override remote |
| **manual** | Prompt user for each conflict |
| **merge** | Combine at column level (if different columns changed) |

### Default: Last-Write-Wins with Warning

```python
if conflicts:
    print(f"Warning: {len(conflicts)} conflicts detected")
    print("Remote changes will be preserved. Local changes:")
    for c in conflicts:
        print(f"  Row {c.row_id}: {c.column} = {c.local_value}")
    if not force:
        print("Use --force to overwrite remote with local changes")
        return
```

---

## CLI Interface

```bash
# Initial setup
smartsheetsync pull https://app.smartsheet.com/sheets/xxx123
# Creates: xxx123.db

# Check status
smartsheetsync status xxx123.db
# Output:
#   Sheet: Project Plan
#   Local version: 42
#   Remote version: 45 (3 versions behind)
#   Unpushed changes: 5 rows modified, 2 rows added

# Incremental pull (fetch remote changes)
smartsheetsync pull xxx123.db

# Push local changes
smartsheetsync push xxx123.db

# Bidirectional sync
smartsheetsync sync xxx123.db

# Force overwrite
smartsheetsync push xxx123.db --force

# View local changes
smartsheetsync changes xxx123.db

# Query data (convenience wrapper)
smartsheetsync query xxx123.db "SELECT * FROM sheet_data WHERE Status = 'In Progress'"

# Export to CSV (for compatibility)
smartsheetsync export xxx123.db --format csv
```

---

## Agent Workflow

For LLM agents, SQLite provides powerful capabilities:

### Reading Data

```python
import sqlite3

conn = sqlite3.connect("xxx123.db")
cursor = conn.cursor()

# Find overdue tasks
cursor.execute("""
    SELECT "Task Name", "Assigned To", "Due Date"
    FROM sheet_data
    WHERE "Due Date" < date('now')
      AND "Status" != 'Complete'
    ORDER BY "Due Date"
""")
overdue = cursor.fetchall()
```

### Modifying Data

```python
# Update a task
cursor.execute("""
    UPDATE sheet_data
    SET "Status" = 'Complete',
        "% Complete" = 100
    WHERE "Task Name" = 'Design review'
""")
conn.commit()

# Changes automatically tracked by triggers
# Push when ready:
# $ smartsheetsync push xxx123.db
```

### Adding Rows

```python
# Insert new task
cursor.execute("""
    INSERT INTO sheet_data ("Task Name", "Assigned To", "Status", _parent_id)
    VALUES ('New subtask', 'alice@example.com', 'Not Started',
            (SELECT _row_id FROM sheet_data WHERE "Task Name" = 'Phase 1'))
""")
conn.commit()
# Note: _row_id will be NULL until pushed, then backfilled from API response
```

---

## Comparison: TSV vs SQLite

| Aspect | TSV/JSON (extrasheet model) | SQLite |
|--------|----------------------------|--------|
| **Format** | Multiple text files | Single binary file |
| **Querying** | Read entire file | SQL queries |
| **Change tracking** | Diff against pristine | Triggers + _changes table |
| **Type safety** | Manual validation | Schema constraints |
| **Large sheets** | Memory issues | Efficient (B-tree) |
| **Agent editing** | Text manipulation | SQL statements |
| **Git-friendliness** | Excellent (text diff) | Poor (binary) |
| **Partial sync** | Harder | Natural (row-level) |
| **Tooling** | Text editors | SQLite browsers, Python, etc. |

### When to Use Each

**TSV/JSON (extrasheet model):**
- Git-based workflows where diffs matter
- Small to medium sheets
- Human review of changes

**SQLite:**
- Large sheets (1000+ rows)
- Frequent incremental syncs
- Agent-driven modifications
- Complex queries needed
- Database-like Smartsheets (project management, inventory, etc.)

---

## Implementation Notes

### Python Libraries

```python
# Core
import sqlite3  # Built-in

# Optional enhancements
import sqlite_utils  # Simon Willison's library for easier table operations
# pip install sqlite-utils

# Smartsheet SDK
import smartsheet
# pip install smartsheet-python-sdk
```

### sqlite-utils Example

```python
from sqlite_utils import Database

db = Database("xxx123.db")

# Create table from Smartsheet columns
db["sheet_data"].create({
    "_row_id": int,
    "_parent_id": int,
    "Task Name": str,
    "Status": str,
    "Due Date": str,
}, pk="_row_id", foreign_keys=[("_parent_id", "sheet_data", "_row_id")])

# Insert rows
db["sheet_data"].insert_all(rows_from_smartsheet)

# Enable change tracking
db["sheet_data"].enable_fts(["Task Name"], create_triggers=True)
```

### Handling New Rows

New rows don't have Smartsheet row IDs yet:

```sql
-- New rows have _row_id = NULL or negative (temp ID)
INSERT INTO sheet_data (_row_id, "Task Name", "Status")
VALUES (-1, 'New Task', 'Not Started');

-- _changes records this
-- On push, API returns assigned row ID
-- Update local row with real ID:
UPDATE sheet_data SET _row_id = 9876543 WHERE _row_id = -1;
UPDATE _changes SET row_id = 9876543 WHERE row_id = -1;
```

---

## Open Questions

1. **Formulas:** Store formula text or computed value? Both?
   - Suggestion: Store computed value in main column, formula in `_formulas` table

2. **Formatting:** Track in SQLite or ignore?
   - Suggestion: Separate `_formats` table, optional sync

3. **Attachments:** Include references in SQLite?
   - Suggestion: `_attachments` table with metadata, not file contents

4. **Multi-sheet sync:** Support syncing entire workspace?
   - Suggestion: One DB per sheet initially, workspace support later

5. **Offline-first:** How long can you work offline?
   - Suggestion: Indefinitely, but warn about potential conflicts

---

## Next Steps

1. **Prototype pull** - Basic sheet → SQLite conversion
2. **Implement change tracking** - Triggers for INSERT/UPDATE/DELETE
3. **Implement push** - Read _changes, call API
4. **Add incremental pull** - rowsModifiedSince optimization
5. **Handle deletions** - Row ID comparison approach
6. **Add conflict detection** - Warn on sync conflicts

---

## References

### SQLite Resources
- [sqlite-history](https://github.com/simonw/sqlite-history) - Change tracking library
- [sqlite-utils](https://sqlite-utils.datasette.io/) - Python utility library
- [Track timestamped changes](https://til.simonwillison.net/sqlite/track-timestamped-changes-to-a-table) - Tutorial

### Smartsheet Sync Features
- [Get Sheet Version](https://developers.smartsheet.com/api/smartsheet/openapi/sheets/get-sheetversion)
- [rowsModifiedSince parameter](https://developers.smartsheet.com/api/smartsheet/openapi/sheets/getsheet)
- [Webhooks Guide](https://developers.smartsheet.com/api/smartsheet/guides/webhooks)
- [Webhook Callbacks](https://developers.smartsheet.com/api/smartsheet/guides/webhooks/webhook-callbacks)
