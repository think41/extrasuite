# Refactor: Type MockGoogleDocsAPI Internals

## Current State (after this issue's prerequisite PR)

`MockGoogleDocsAPI` now has a **typed public interface**:

```python
class MockGoogleDocsAPI:
    def __init__(self, doc: Document) -> None: ...
    def get(self) -> Document: ...
    def batch_update(self, batch: BatchUpdateDocumentRequest) -> BatchUpdateDocumentResponse: ...
```

Internally, the document is stored as a plain `dict[str, Any]`. The 13 handler modules, `reindex.py`, `navigation.py`, and `validation.py` all operate on raw dicts. `_get_raw()` and `_batch_update_raw()` expose the dict boundary for `MockTransport` / `CompositeTransport`.

## Goal

Remove the dict layer from the mock's internals entirely. Every module — handlers, reindex, navigation, validation — should operate on the auto-generated Pydantic types (`Document`, `Tab`, `Paragraph`, `TextStyle`, etc.) rather than `dict[str, Any]`. No `request.get("text", "")`, no `document["tabs"]`, no `element["startIndex"] = N`.

The result: mypy can verify the entire mock at the type level. Bugs like misspelled field names or wrong dict structure become compile-time errors instead of runtime failures.

## Scope

| Module | Lines (est.) | Primary dict operations |
|--------|-------------|------------------------|
| `reindex.py` | ~700 | Assigns `startIndex`/`endIndex` to every element; splits `textRun` at `\n` boundaries |
| `text_ops.py` | ~600 | Slices `textRun.content`; inserts/removes `ParagraphElement`s; merges runs |
| `style_ops.py` | ~400 | Reads/writes `textStyle` fields; tracks `__explicit__` provenance |
| `table_ops.py` | ~500 | Builds table structure; inserts rows/columns; updates `tableStyle` |
| `segment_ops.py` | ~350 | Creates headers/footers/footnotes/tabs |
| `bullet_ops.py` | ~200 | Sets/removes `bullet` on paragraphs |
| `navigation.py` | ~200 | Finds elements by UTF-16 index |
| `validation.py` | ~300 | Validates ranges; tracks segment structure |
| `stubs.py` | ~50 | Stub handlers returning `{}` → typed `Response` objects |
| `named_range_ops.py` | ~150 | Creates/deletes named ranges |
| `utils.py` | ~100 | Shared helpers (styles_equal, merge_explicit, UTF-16 offset) |
| `api.py` | ~100 | Dispatcher (already has typed shell; internals need updating) |

Total: ~3,650 lines across 12 modules.

## Specific Challenges

### 1. `__explicit__` provenance tracking

**Problem:** Style provenance is currently tracked by storing an `__explicit__` key directly in `textStyle` dicts:
```python
text_run["textStyle"]["__explicit__"] = sorted(explicit_fields)
```
Pydantic's `TextStyle` model has `extra="allow"`, so you could store it as model extra (`text_style.__pydantic_extra__["__explicit__"] = [...]`). But accessing model extra is more awkward than dict keys, and `model_dump(exclude_none=True)` won't strip it automatically.

**Options:**
- **A. Model extra**: Store in `__pydantic_extra__`. Accessing: `text_style.model_extra.get("__explicit__", [])`. Stripping on output: needs explicit pop or custom serializer.
- **B. Side dict in `MockGoogleDocsAPI`**: `self._explicit: dict[int, frozenset[str]]` keyed by `id(text_style_object)`. Problem: `deepcopy` for backup/restore creates new objects, breaking identity.
- **C. Subclass `TextStyle`**: `class TextStyleWithProvenance(TextStyle): explicit: frozenset[str] = frozenset()`. Cleanest type-wise but requires the mock to use a different model than the public API.
- **D. Redesign**: Track provenance at the operation level (what was the last `updateTextStyle` that touched each range?) rather than in the object itself.

### 2. Reindex pass: mutating Pydantic model trees

The reindex pass walks the entire document and sets indices:
```python
# current dict approach
element["startIndex"] = current_index
element["endIndex"] = next_index
```
With typed models:
```python
element.start_index = current_index
element.end_index = next_index
```
Pydantic models are mutable by default, so this works syntactically. However, the reindex pass also **splits text runs at `\n` boundaries**, which requires removing an element from a list and inserting two in its place:
```python
# current
elements.pop(i)
elements.insert(i, first_half)
elements.insert(i + 1, second_half)
```
With typed models, `paragraph.elements` is `list[ParagraphElement] | None`. This list is mutable and supports `pop`/`insert`, but care is needed when the list is `None`. The reindex module is the most complex to port because it interleaves tree navigation, index arithmetic, and structural mutation.

### 3. Handler return types

Handlers currently return `dict[str, Any]` — mostly `{}`, but a few return structured data:
- `createHeader` → `{"createHeader": {"headerId": "hxxx"}}`
- `createFooter` → `{"createFooter": {"footerId": "fxxx"}}`
- `addDocumentTab` → `{"addDocumentTab": {"tabProperties": {"tabId": "txx"}}}`

With typed internals, handlers should return `Response` (the auto-generated reply union model). Empty handlers return `Response()`. Handlers that create IDs return e.g. `Response(create_header=CreateHeaderResponse(header_id="hxxx"))`.

### 4. `DeferredID` in request types

`DeferredID` is a Python dataclass placeholder for IDs not yet known. The auto-generated types have `tabId: str | None`, not `str | DeferredID | None`. By the time requests reach `batch_update()`, all DeferredIDs are resolved (that's what `resolve_deferred_ids()` does). So the typed mock will only ever see real `str` IDs — no change needed here.

### 5. `DocumentStructureTracker` in `validation.py`

Currently takes and walks `dict[str, Any]`. Needs to be rewritten to accept `Document` and navigate via model attributes. This is used by segment_ops (createHeader, createFooter) to enforce uniqueness constraints.

## Open Questions

1. **`__explicit__` tracking**: Which option (A/B/C/D above) is right? Option C (subclass) is cleanest but requires the mock to use a different model class than `api_types._generated.TextStyle`. Is that acceptable?

2. **Incremental vs big-bang**: The 13 modules are tightly coupled — `text_ops` calls `navigation`, `style_ops` calls `utils`, `table_ops` calls `text_ops`. Typing one module requires typing its dependencies. Can we define a "typed boundary" between groups, or does this have to be a single large PR?

3. **Reindex as dict utility**: Could `reindex_and_normalize_all_tabs()` remain a dict-based utility that the typed layer converts to/from? (`doc.model_dump() → reindex → Document.model_validate()`) This would isolate the most complex module from the refactor, at the cost of a round-trip per request.

4. **Performance**: Currently every `batch_update()` call avoids any serialization. The typed public interface adds one `model_dump` + one `model_validate` per call. The full refactor would eliminate those, but reindex-as-dict-utility would add two more. Is performance a concern given the mock is only used in tests?

5. **Provenance leniency**: The `CompositeTransport._documents_match()` currently tolerates B/I/U-only textStyle divergences and run consolidation differences as "provenance leniency." If the `__explicit__` tracking is redesigned during this refactor, some of those leniencies might become unnecessary. Should the refactor aim to remove leniency, or leave it unchanged?

## Testing Strategy

The existing 61 mock scenarios in `scripts/test_mock_scenarios.py` use `CompositeTransport` to compare mock vs real API. All 61 must continue to pass after the refactor. This is the ground truth.

**Test document for development**: https://docs.google.com/document/d/1sOVZ2O3pGYSqqtxbb_pnaOZeX9Ootdveb4s0V1962Jc/edit?tab=t.0

Run scenarios:
```bash
cd extradoc
uv run python scripts/test_mock_scenarios.py "https://docs.google.com/document/d/1sOVZ2O3pGYSqqtxbb_pnaOZeX9Ootdveb4s0V1962Jc/edit"
```

**Recommended approach**: Port one module at a time in dependency order (utils → navigation → validation → text_ops → style_ops → bullet_ops → table_ops → segment_ops → named_range_ops → stubs → reindex → api), running all 61 scenarios after each module.

## Why This Matters

- mypy currently reports `Success: no issues found` for `src/extradoc` but cannot verify anything inside the mock — all 13 modules are `Any` from mypy's perspective.
- Bugs in handler logic (wrong field name, wrong nesting depth) are invisible until a scenario test fails at runtime.
- A fully typed mock would let mypy catch these bugs at development time.
- The existing 61 scenario tests would become a safety net for the refactor rather than the primary discovery mechanism.
