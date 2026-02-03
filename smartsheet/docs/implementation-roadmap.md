# Smartsheet SQLite Sync - Implementation Roadmap

This document outlines the implementation plan for `smartsheetsync`, a bidirectional sync tool between Smartsheet and local SQLite databases.

---

## Design Philosophy

**Key Insight:** Smartsheet is a typed database with a web UI, not a freeform spreadsheet.

The SQLite sync model is superior to the TSV-based extrasheet approach for Smartsheet because:

| Requirement | SQLite Advantage |
|-------------|-----------------|
| Typed columns | Schema with constraints |
| Large sheets (20k+ rows) | Efficient B-tree storage |
| Incremental sync | Row-level updates via triggers |
| Agent queries | SQL instead of file parsing |
| Change detection | Built-in via triggers |
| Conflict handling | Version tracking natural |

---

## Feasibility: Confirmed

Smartsheet API provides excellent sync primitives:

| Feature | API Support | Use Case |
|---------|-------------|----------|
| Version check | `GET /sheets/{id}/version` | Skip unchanged sheets (cheap) |
| Incremental fetch | `rowsModifiedSince` param | Fetch only changed rows |
| Bulk updates | `PUT /rows` with array | Efficient push |
| Real-time events | Webhooks | Optional push notifications |
| Stable row IDs | Always returned | Track rows across syncs |

---

## Implementation Phases

### Phase 1: Core Sync (MVP)

**Goal:** Bidirectional sync of cell values

**Deliverables:**
1. `pull` command - Full and incremental fetch to SQLite
2. `push` command - Local changes to Smartsheet
3. `status` command - Show sync state and pending changes
4. Change tracking via SQLite triggers

**Schema:**
```sql
-- Main data table (generated from Smartsheet columns)
CREATE TABLE sheet_data (
    _row_id INTEGER PRIMARY KEY,
    _row_number INTEGER,
    _parent_id INTEGER,
    _modified_at TEXT,
    -- ... user columns from schema
);

-- Sync metadata
CREATE TABLE _sync_meta (key TEXT PRIMARY KEY, value TEXT);

-- Change log
CREATE TABLE _changes (
    id INTEGER PRIMARY KEY,
    row_id INTEGER,
    operation TEXT,  -- INSERT/UPDATE/DELETE
    column_name TEXT,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT,
    pushed INTEGER DEFAULT 0
);
```

**API Operations:**
- `GET /sheets/{id}` - Initial pull
- `GET /sheets/{id}?rowsModifiedSince=...` - Incremental pull
- `PUT /sheets/{id}/rows` - Update rows
- `POST /sheets/{id}/rows` - Add rows
- `DELETE /sheets/{id}/rows?ids=...` - Delete rows

---

### Phase 2: Robust Sync

**Goal:** Handle edge cases and conflicts

**Deliverables:**
1. Deletion detection (compare row ID sets)
2. Conflict detection and resolution
3. `sync` command (pull + push with conflict handling)
4. Retry logic with exponential backoff

**Conflict Resolution Options:**
- `--strategy=remote-wins` (default)
- `--strategy=local-wins`
- `--strategy=manual` (prompt)
- `--strategy=merge` (column-level)

---

### Phase 3: Schema Features

**Goal:** Support Smartsheet-specific features

**Deliverables:**
1. Hierarchy (parent/child rows)
2. Formulas (store in `_formulas` table)
3. Column types with constraints
4. Picklist validation via CHECK constraints

**Schema additions:**
```sql
CREATE TABLE _columns (
    column_id INTEGER PRIMARY KEY,
    title TEXT,
    type TEXT,
    options TEXT,  -- JSON for picklist
    formula TEXT,  -- Column formula
    read_only INTEGER
);

CREATE TABLE _formulas (
    row_id INTEGER,
    column_id INTEGER,
    formula TEXT,
    PRIMARY KEY (row_id, column_id)
);
```

---

### Phase 4: Advanced Features

**Goal:** Full feature parity

**Deliverables:**
1. Formatting support (`_formats` table)
2. Webhook integration for real-time sync
3. Multi-sheet workspace sync
4. Attachments metadata

---

## Key Challenges and Solutions

### Challenge 1: Deletion Detection

**Problem:** `rowsModifiedSince` doesn't report deleted rows.

**Solution:** Compare row ID sets on each pull:
```python
remote_ids = set(fetch_all_row_ids(sheet_id))
local_ids = set(db.execute("SELECT _row_id FROM sheet_data").fetchall())
deleted_ids = local_ids - remote_ids
```

This is efficient because we only fetch IDs, not full row data.

---

### Challenge 2: Save Collisions (Error 4004)

**Problem:** Concurrent updates to same sheet fail.

**Solution:** Serialize pushes with retry:
```python
async def push_with_retry(sheet_id, rows, max_retries=5):
    for attempt in range(max_retries):
        try:
            return await api.update_rows(sheet_id, rows)
        except SaveCollisionError:
            await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
        except RateLimitError:
            await asyncio.sleep(60)
    raise PushFailed("Max retries exceeded")
```

---

### Challenge 3: New Row ID Assignment

**Problem:** New rows don't have Smartsheet IDs until pushed.

**Solution:** Use negative temporary IDs locally:
```python
# Insert with temp ID
db.execute("INSERT INTO sheet_data (_row_id, ...) VALUES (-1, ...)")

# After push, API returns real ID
real_id = api_response.result[0].id
db.execute("UPDATE sheet_data SET _row_id = ? WHERE _row_id = -1", [real_id])
db.execute("UPDATE _changes SET row_id = ? WHERE row_id = -1", [real_id])
```

---

### Challenge 4: Schema Changes

**Problem:** What if Smartsheet columns change between syncs?

**Solution:** Detect and handle schema drift:
```python
def detect_schema_changes(db, remote_columns):
    local_cols = db.execute("SELECT * FROM _columns").fetchall()

    added = [c for c in remote_columns if c.id not in local_col_ids]
    removed = [c for c in local_cols if c.id not in remote_col_ids]
    renamed = detect_renames(local_cols, remote_columns)

    if added or removed or renamed:
        prompt_user_for_migration()
```

---

### Challenge 5: System/Calculated Columns

**Problem:** Some columns are read-only (Created Date, parent roll-ups).

**Solution:** Mark in schema and exclude from push:
```python
def get_pushable_changes(db):
    return db.execute("""
        SELECT c.* FROM _changes c
        JOIN _columns col ON c.column_name = col.title
        WHERE c.pushed = 0
          AND col.read_only = 0
    """).fetchall()
```

---

## Architecture

### Module Structure

```
smartsheetsync/
├── src/smartsheetsync/
│   ├── __init__.py
│   ├── __main__.py          # CLI entry point
│   ├── client.py            # Main sync orchestrator
│   ├── transport.py         # API abstraction
│   ├── schema.py            # SQLite schema generation
│   ├── triggers.py          # Change tracking setup
│   ├── pull.py              # Pull operations
│   ├── push.py              # Push operations
│   ├── conflicts.py         # Conflict detection/resolution
│   ├── credentials.py       # Auth token management
│   └── types.py             # Type definitions
├── tests/
│   ├── golden/              # Cached API responses
│   └── ...
└── pyproject.toml
```

### Transport Abstraction

```python
from abc import ABC, abstractmethod

class SmartsheetTransport(ABC):
    @abstractmethod
    async def get_sheet(self, sheet_id: str, modified_since: str = None) -> SheetData:
        pass

    @abstractmethod
    async def get_version(self, sheet_id: str) -> int:
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

    @abstractmethod
    async def get_row_ids(self, sheet_id: str) -> list[int]:
        pass

class SmartsheetAPITransport(SmartsheetTransport):
    """Production: calls real Smartsheet API"""
    pass

class LocalFileTransport(SmartsheetTransport):
    """Testing: reads from golden files"""
    pass
```

---

## CLI Design

```bash
# Authentication
smartsheetsync login
smartsheetsync logout

# Core operations
smartsheetsync pull <sheet_url_or_id> [output.db]
smartsheetsync pull <existing.db>  # Incremental
smartsheetsync push <file.db>
smartsheetsync sync <file.db>

# Inspection
smartsheetsync status <file.db>
smartsheetsync changes <file.db>
smartsheetsync schema <file.db>

# Utilities
smartsheetsync query <file.db> "<SQL>"
smartsheetsync export <file.db> --format csv|json
```

---

## Testing Strategy

### Golden File Tests

Same approach as extrasheet:
1. Capture real API responses
2. Store in `tests/golden/{sheet_id}/`
3. Test against cached responses

```python
def test_pull_creates_correct_schema():
    transport = LocalFileTransport("tests/golden/project_sheet/")
    db = pull_sheet(transport, "123456")

    # Verify schema
    columns = db.execute("SELECT * FROM _columns").fetchall()
    assert len(columns) == 8
    assert columns[0].title == "Task Name"
```

### Sync Round-Trip Tests

```python
def test_push_round_trip():
    # Pull
    db = pull_sheet(transport, "123456")

    # Modify
    db.execute("UPDATE sheet_data SET Status = 'Complete' WHERE _row_id = 1")

    # Push
    changes = get_unpushed_changes(db)
    assert len(changes) == 1
    assert changes[0].operation == "UPDATE"
    assert changes[0].column_name == "Status"
```

---

## Dependencies

```toml
[project]
dependencies = [
    "smartsheet-python-sdk>=3.0",  # Official SDK with retry logic
    "sqlite-utils>=3.0",           # SQLite convenience library
    "httpx>=0.24",                 # Async HTTP (if not using SDK)
    "keyring>=24.0",               # Secure token storage
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "ruff>=0.1",
    "mypy>=1.0",
]
```

---

## Open Questions

1. **Package name:** `smartsheetsync` or `extrasmartsheet`?
   - Leaning toward `smartsheetsync` since model is fundamentally different

2. **Relationship to extrasuite:**
   - Standalone package? Part of extrasuite monorepo?
   - Share auth with extrasuite.client?

3. **Webhook support:**
   - Phase 4 or earlier?
   - Requires server component - same as extrasuite.server?

4. **Binary compatibility:**
   - SQLite files not git-diffable
   - Should we support export to TSV for version control?

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Rate limits | Medium | Medium | Bulk ops, incremental sync |
| Save collisions | High | Low | Retry with backoff |
| Deletion edge cases | Medium | Medium | Row ID comparison |
| Schema drift | Low | High | Migration prompts |
| Large sheets | Medium | Medium | SQLite handles well |
| Offline conflicts | Medium | Medium | Clear conflict UX |

---

## Success Criteria

1. **Pull works:** Schema inferred, data correct, triggers installed
2. **Change tracking works:** All local edits captured
3. **Push works:** Changes applied, retries handle collisions
4. **Incremental sync:** Only changed rows transferred
5. **Conflicts detected:** User warned before data loss
6. **Agent-friendly:** SQL queries work naturally

---

## Next Steps

1. **Prototype pull:** Sheet → SQLite with schema inference
2. **Add triggers:** Change tracking for INSERT/UPDATE/DELETE
3. **Implement push:** Read _changes, call API, clear on success
4. **Add incremental pull:** rowsModifiedSince optimization
5. **Handle deletions:** Row ID comparison
6. **Add conflict detection:** Compare versions before push

---

## References

- [SQLite sync model details](./sqlite-sync-model.md)
- [API analysis](./smartsheet-integration-analysis.md)
- [Smartsheet API docs](https://developers.smartsheet.com/)
- [sqlite-utils library](https://sqlite-utils.datasette.io/)
- [sqlite-history](https://github.com/simonw/sqlite-history)
