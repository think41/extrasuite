# Plan: Migrate client.py — serde + reconcile + Comments + Test CLI

## Goal

Replace the legacy pipeline in `DocsClient` with serde + reconcile. Add a first-class
`comments/` package with typed models, XML serialization, and diff support. Update serde
to operate on a `DocumentWithComments` aggregate. Minimize public exports. Add a
developer-facing test CLI.

---

## New Package: `src/extradoc/comments/`

This package owns all comment-related types, serialization, diffing, and snap-fitting.

### Types (`_types.py`)

```python
@dataclass
class Reply:
    id: str
    author: str
    created_time: str
    content: str
    action: str | None     # "resolve", "reopen" — read-only on pull
    deleted: bool

@dataclass
class Comment:
    id: str
    author: str
    created_time: str
    content: str
    anchor: str            # raw Drive API anchor string — always preserved verbatim
    resolved: bool
    deleted: bool
    replies: list[Reply]

@dataclass
class FileComments:
    file_id: str
    comments: list[Comment]

@dataclass
class DocumentWithComments:
    document: Document
    comments: FileComments
```

`DocumentWithComments` is the aggregate unit that serde, client, and the test CLI work with.

### `comments.xml` format

Written at the folder root, parallel to `index.xml`. Stores raw Drive API anchor offsets.
The agent can edit `content` of comments/replies, add `<reply>` elements, set
`resolved="true"`, or delete a `<comment>` element. All other attributes are read-only.

```xml
<comments file-id="1YicN...">
  <comment id="Abc123" author="Jane Doe" created="2024-01-15T10:00:00Z"
           resolved="false" anchor="...raw Drive API anchor string...">
    <content>This section is unclear — can we elaborate?</content>
    <replies>
      <reply id="r1" author="John Smith" created="2024-01-16T09:00:00Z">
        <content>Agreed, I'll expand this paragraph.</content>
      </reply>
    </replies>
  </comment>
</comments>
```

Key design choices:
- `anchor` is always the verbatim string from the Drive API response. Never recomputed.
- `<comment-ref>` in body XML is the only place showing where the comment lands in context.
- Deleted comments/replies (`deleted: true`) are excluded from `comments.xml`.

### `<comment-ref>` injection during serialization (`_inject.py`)

After serde writes a tab's `document.xml`, a second pass injects `<comment-ref>` tags:

1. Map each comment's anchor character offsets to positions in the tab's XML element tree.
2. **Snap-fit**: Expand or contract the range by the minimum necessary to align with
   existing XML element boundaries (paragraph, list item, table cell, table row).
   A comment anchored to 2 words mid-paragraph expands to the whole paragraph.
   A comment spanning 3.5 paragraphs contracts or expands to the nearest whole paragraph.
3. Wrap the snapped element range with `<comment-ref>`:

```xml
<comment-ref id="Abc123" comment="This section is unclear..." replies="1">
  <p>The full paragraph text that has the comment attached.</p>
</comment-ref>
```

`comment` attribute = truncated comment text (first ~80 chars). `replies` = reply count.
`<comment-ref>` and all its attributes are **read-only**. The help text in `pull` output
explains this. Changes to the comment content are made exclusively via `comments.xml`.

During **deserialization**, `<comment-ref>` tags are stripped and inner content flows as
normal document elements. The document body is reconstructed without any trace of comment
anchors — reconcile never sees them.

### Comment diff (`_diff.py`)

`diff_comments(base: FileComments, desired: FileComments) -> CommentOperations`

Compares two `FileComments` by comment `id`. Produces:

| Change | Operation |
|--------|-----------|
| Reply added to existing comment | `create_reply(comment_id, content)` |
| Comment `resolved` flipped to `true` | `create_reply(comment_id, "", action="resolve")` |
| Comment content edited | `edit_comment(comment_id, new_content)` |
| Reply content edited | `edit_reply(comment_id, reply_id, new_content)` |
| Comment deleted from XML | `delete_comment(comment_id)` |
| New comment added (no anchor) | Log warning, skip — create is blocked (see below) |

New top-level comments without an anchor are silently skipped. Creating anchored comments
via the Drive API results in "Original content deleted" — a known API limitation documented
in `docs/comment-anchoring-limitation.md`.

```python
@dataclass
class CommentOperations:
    new_replies: list[NewReply]
    resolves: list[Resolve]
    edits: list[EditComment]
    reply_edits: list[EditReply]
    deletes: list[DeleteComment]

    @property
    def has_operations(self) -> bool: ...
```

### Files in `src/extradoc/comments/`

| File | Purpose |
|------|---------|
| `__init__.py` | Public exports: `Comment`, `Reply`, `FileComments`, `DocumentWithComments`, `CommentOperations` |
| `_types.py` | Dataclass definitions |
| `_xml.py` | `FileComments.to_xml()` / `FileComments.from_xml()` for `comments.xml` |
| `_from_raw.py` | `FileComments.from_raw(file_id, raw_comments)` — parse Drive API response |
| `_inject.py` | Inject / strip `<comment-ref>` tags in tab XML strings |
| `_snap.py` | Snap-fit character offset range to XML element boundaries |
| `_diff.py` | `diff_comments(base, desired) -> CommentOperations` |

---

## Updated Serde Interface

Serde's `serialize` and `deserialize` are updated to operate on `DocumentWithComments`.
The lower-level `from_document()` and `to_document()` stay `Document`-based — they are
internal utilities unchanged.

### `serialize(bundle: DocumentWithComments, folder: Path) -> list[Path]`

1. Call existing `from_document(bundle.document)` → `(index_xml, tabs)`
2. Write `index.xml` as before
3. For each tab, write `document.xml`, `styles.xml`, extras as before
4. For each tab's `document.xml`, run comment injection pass:
   `inject_comment_refs(xml_str, bundle.comments)` — modifies the XML in place before writing
5. Write `folder/comments.xml` from `bundle.comments.to_xml()`
6. Return list of created paths (includes `comments.xml`)

### `deserialize(folder: Path) -> DocumentWithComments`

1. Read `comments.xml` if present → `FileComments.from_xml()`; else empty `FileComments`
2. Read each tab's `document.xml` and strip `<comment-ref>` tags before parsing
3. Continue existing deserialization → `Document`
4. Return `DocumentWithComments(document, comments)`

**Files changed in serde:**
- `src/extradoc/serde/__init__.py` — update `serialize`/`deserialize` signatures
- `src/extradoc/serde/_to_xml.py` — no change (called before injection pass)
- `src/extradoc/serde/_from_xml.py` — strip `<comment-ref>` before parsing

---

## Transport Additions

`Transport` ABC grows four new abstract methods to support full comment CRUD:

```python
@abstractmethod
async def edit_comment(self, file_id: str, comment_id: str, content: str) -> dict: ...

@abstractmethod
async def delete_comment(self, file_id: str, comment_id: str) -> None: ...

@abstractmethod
async def edit_reply(self, file_id: str, comment_id: str, reply_id: str, content: str) -> dict: ...

@abstractmethod
async def delete_reply(self, file_id: str, comment_id: str, reply_id: str) -> None: ...
```

Existing methods (`list_comments`, `create_reply`) stay unchanged.

`GoogleDocsTransport` implements all four via Drive API v3 `PATCH`/`DELETE` endpoints.
`LocalFileTransport` provides no-op / mock implementations.

**File changed:** `src/extradoc/transport.py`

---

## Migrate `client.py`

### `DiffResult` (new internal dataclass)

```python
@dataclass
class DiffResult:
    document_id: str
    batches: list[BatchUpdateDocumentRequest]
    comment_ops: CommentOperations
```

Used internally between `diff()` and `push()`. Not exported publicly (diff is discouraged).

### `pull()` new path

```
transport.get_document(doc_id)       → DocumentData
transport.list_comments(doc_id)      → list[dict]

Document.model_validate(data.raw)    → doc
FileComments.from_raw(doc_id, raw)   → comments
DocumentWithComments(doc, comments)  → bundle

serde.serialize(bundle, folder)      → writes index.xml, tab XMLs, comments.xml
_create_pristine_zip(folder)         → zips entire serde output into .pristine/document.zip
optionally write .raw/document.json and .raw/comments.json
```

Pristine zip contains the **entire serde output**: `index.xml`, all tab folders, and
`comments.xml`. This is a breaking change from the old zip (which had flat `document.xml` +
`styles.xml`). Any folder pulled with the old client must be re-pulled.

### `diff()` new path

```python
def diff(self, folder: str | Path) -> DiffResult:
    folder = Path(folder)
    document_id = _read_document_id(folder)   # from index.xml

    with tempfile.TemporaryDirectory() as tmp:
        _extract_pristine_zip(folder, Path(tmp))
        base_bundle = serde.deserialize(Path(tmp))

    desired_bundle = serde.deserialize(folder)

    base = reindex_document(base_bundle.document)
    desired = reindex_document(desired_bundle.document)
    batches = reconcile(base, desired)

    comment_ops = diff_comments(base_bundle.comments, desired_bundle.comments)

    return DiffResult(document_id, batches, comment_ops)
```

Return type changes from `tuple[str, list[dict], Any, CommentOperations]` to `DiffResult`.
The `change_tree` from the old engine is gone.

### `push()` new path

Comment ops execute **before** document changes. Comment anchors reference positions in the
current live document (which equals pristine), so comment ops must run before any document
mutations shift character offsets.

```python
async def push(self, folder, *, force=False) -> PushResult:
    result = self.diff(folder)

    if not result.batches and not result.comment_ops.has_operations:
        return PushResult(success=True, ..., message="No changes")

    # 1. Comment ops (Drive API — before document changes)
    replies_created, comments_resolved, edits, deletes = 0, 0, 0, 0
    ops = result.comment_ops
    for r in ops.new_replies:
        await self._transport.create_reply(result.document_id, r.comment_id, r.content)
        replies_created += 1
    for s in ops.resolves:
        await self._transport.create_reply(result.document_id, s.comment_id, "", action="resolve")
        comments_resolved += 1
    for e in ops.edits:
        await self._transport.edit_comment(result.document_id, e.comment_id, e.content)
        edits += 1
    for d in ops.deletes:
        await self._transport.delete_comment(result.document_id, d.comment_id)
        deletes += 1
    for re_ in ops.reply_edits:
        await self._transport.edit_reply(result.document_id, re_.comment_id, re_.reply_id, re_.content)
        edits += 1

    # 2. Document batches (Docs API — reconcile output)
    prior_responses: list[dict] = []
    changes_applied = 0
    for i, batch in enumerate(result.batches):
        if i > 0:
            batch = resolve_deferred_ids(prior_responses, batch)
        resp = await self._transport.batch_update(
            result.document_id,
            [r.model_dump(by_alias=True, exclude_none=True) for r in (batch.requests or [])]
        )
        prior_responses.append(resp)
        changes_applied += len(batch.requests or [])

    return PushResult(
        success=True,
        document_id=result.document_id,
        changes_applied=changes_applied,
        replies_created=replies_created,
        comments_resolved=comments_resolved,
    )
```

### Imports removed from `client.py`

```
extradoc.comments_converter   (replaced by extradoc.comments)
extradoc.desugar
extradoc.engine.DiffEngine
extradoc.request_generators.structural
extradoc.xml_converter.convert_document_to_xml
```

### Imports added to `client.py`

```
extradoc.api_types: Document, BatchUpdateDocumentRequest
extradoc.serde: serialize, deserialize
extradoc.serde._models: IndexXml
extradoc.reconcile: reconcile, reindex_document, resolve_deferred_ids
extradoc.comments: DocumentWithComments, FileComments, diff_comments, CommentOperations
```

### Helper functions

Remove: `_create_pristine_copy()`, `_new_tab_ids()`

Add:
- `_create_pristine_zip(folder: Path)` — zip everything in `folder/` except `.pristine/`
  and `.raw/` into `folder/.pristine/document.zip`
- `_extract_pristine_zip(folder: Path, dest: Path)` — unzip into `dest`
- `_read_document_id(folder: Path) -> str` — read `index.xml`, parse `id` attribute

---

## Minimize `__init__.py` Exports

The public surface of `extradoc` is `DocsClient` and the transport classes needed to
construct it. Everything else is internal.

```python
# src/extradoc/__init__.py
from extradoc.client import DocsClient, PushResult
from extradoc.transport import (
    Transport,
    GoogleDocsTransport,
    LocalFileTransport,
    TransportError,
    AuthenticationError,
    NotFoundError,
    APIError,
)

__all__ = [
    "DocsClient",
    "PushResult",
    "Transport",
    "GoogleDocsTransport",
    "LocalFileTransport",
    "TransportError",
    "AuthenticationError",
    "NotFoundError",
    "APIError",
]
```

`DocumentData`, `DocumentWithComments`, `FileComments`, `Comment`, `Reply` are not
re-exported at the top level. Callers who need them can import from `extradoc.transport`
or `extradoc.comments` directly.

---

## Test CLI (`extradoc-test`)

Entry point registered in `pyproject.toml`:
```toml
[project.scripts]
extradoc-test = "extradoc.test_cli:main"
```

### Commands

```bash
# Mock pull: read golden JSON, serialize to folder (no auth)
extradoc-test pull --mock <golden.json> <output-dir>

# Real pull: use credentials from env/config
extradoc-test pull <document-id-or-url> <output-dir>

# Show what diff would produce (batch requests + comment ops)
extradoc-test diff <folder>

# Push to mock: apply reconcile to in-memory mock, verify result, print summary
extradoc-test push --mock <folder>

# Real push: apply to live doc, then auto re-pull, verify re-pulled vs desired
extradoc-test push <folder>
```

### Key behaviours that differ from the public `extrasuite doc` CLI

| Feature | `extrasuite doc` | `extradoc-test` |
|---------|------------------|-----------------|
| Auth required | Always | Optional (`--mock` skips auth) |
| `diff` output | Not shown | Printed: request types + comment op counts |
| After `push` | Done | Auto re-pulls and runs `verify` |
| Verify | No | Compares re-pulled document against desired |
| Mock transport | No | Yes — applies to in-memory mock, no API calls |

### Mock push flow

1. `desired_bundle = serde.deserialize(folder)`
2. `base_bundle = serde.deserialize(pristine_zip_extracted)`
3. `batches = reconcile(reindex(base), reindex(desired))`
4. Apply batches to `MockGoogleDocsAPI`
5. `actual = mock.get()` → `Document`
6. `assert documents_match(actual, desired.document)` — print PASS or FAIL + diff

### File

`src/extradoc/test_cli.py` — standalone module, no production dependencies beyond extradoc itself.

---

## File Inventory

| File | Change |
|------|--------|
| `src/extradoc/comments/__init__.py` | **New** — public exports |
| `src/extradoc/comments/_types.py` | **New** — `Comment`, `Reply`, `FileComments`, `DocumentWithComments`, `CommentOperations` |
| `src/extradoc/comments/_xml.py` | **New** — `comments.xml` serialization |
| `src/extradoc/comments/_from_raw.py` | **New** — parse Drive API response |
| `src/extradoc/comments/_inject.py` | **New** — inject / strip `<comment-ref>` in XML |
| `src/extradoc/comments/_snap.py` | **New** — snap-fit character offsets to XML boundaries |
| `src/extradoc/comments/_diff.py` | **New** — `diff_comments()` |
| `src/extradoc/serde/__init__.py` | Update `serialize`/`deserialize` signatures |
| `src/extradoc/serde/_from_xml.py` | Strip `<comment-ref>` before parsing |
| `src/extradoc/transport.py` | Add `edit_comment`, `delete_comment`, `edit_reply`, `delete_reply` |
| `src/extradoc/client.py` | Rewrite `pull`, `diff`, `push`; add `DiffResult`; delete legacy imports |
| `src/extradoc/__init__.py` | Minimize to `DocsClient` + transport classes |
| `src/extradoc/test_cli.py` | **New** — `extradoc-test` entry point |
| `docs/reconciliation-gaps.md` | Add: new top-level comment creation is blocked |

---

## Verification

```bash
cd extradoc

# Unit tests for new comments package
uv run pytest tests/test_comments.py -v

# Serde round-trip still passes
uv run pytest tests/test_serde.py -v

# Reconcile tests still pass
uv run pytest tests/test_reconcile.py -v

# Full suite
uv run pytest tests/ -v

# Type checking
uv run mypy src/extradoc

# Lint
uv run ruff check . && uv run ruff format .
```

Smoke test (if credentials available):
```bash
extradoc-test pull --mock tests/golden/1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc.json /tmp/out
# Edit /tmp/out/1YicN.../tab_1/document.xml
extradoc-test diff /tmp/out/1YicN...
extradoc-test push --mock /tmp/out/1YicN...

# With real credentials:
extradoc-test pull 1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc /tmp/out
extradoc-test push /tmp/out/1YicN...   # pushes, re-pulls, verifies
```
