# Mock Google Docs API

A pure-function mock of the [Google Docs batchUpdate API](../../../docs/googledocs/api/): given a document dict + a list of request dicts, it produces the updated document state.

```python
from extradoc.mock.api import MockGoogleDocsAPI

mock = MockGoogleDocsAPI(doc_dict)          # initialize with document as dict
response = mock.batch_update(request_dicts) # returns {"replies": [...]}
result = mock.get()                         # returns updated document as dict
```

**Used by `reconcile.verify()`** — which runs batches sequentially with ID resolution and compares the result against the desired `Document`.

## Status

**61/61 test scenarios pass** against the real Google Docs API via `CompositeTransport`. A small number pass via provenance leniency (B/I/U-only textStyle divergences and run consolidation differences are tolerated — see Known Limitations).

To run scenarios against a live document:
```bash
cd extradoc
uv run python scripts/test_mock_scenarios.py "https://docs.google.com/document/d/<ID>/edit"
```
Mismatch logs are saved to `mismatch_logs/scenarios/scenario_NN/`.

## How It Works

`batch_update()` processes requests sequentially. For each request, it dispatches to a handler, then runs `reindex_and_normalize_all_tabs()` from `reindex.py`. **Handlers only modify content structure — they never compute indices.** The centralized reindex pass walks all document content and assigns correct UTF-16 indices from actual text sizes.

## Style Provenance Tracking (`__explicit__`)

The mock tracks which `textStyle` properties were explicitly set via `updateTextStyle`, using an `__explicit__` metadata key (sorted list of field names) stored in each textStyle dict. This key is internal — `get()` strips it before returning.

**How it flows:**
- `updateTextStyle` → adds updated fields to `__explicit__` on affected runs
- `insertText` (non-link) → inherits `__explicit__` from source run via `deepcopy`
- `insertText` (into link run) → `_strip_link_style` uses `__explicit__` to decide which styles to keep
- `updateParagraphStyle` with heading → only clears italic/underline if NOT in `__explicit__`; always clears bold
- `createParagraphBullets` → copies italic to `bullet.textStyle` only if in `__explicit__`
- Run consolidation (delete) → ignores `__explicit__` for equality, merges (union) when consolidating

## Known Limitations

The mock passes all 61 scenarios but some rely on **provenance leniency** in `CompositeTransport._documents_match()`:

1. **B/I/U-only textStyle divergences**: `{bold: true}` vs `{}` on `textRun.textStyle` or `bullet.textStyle`
2. **Run consolidation divergences**: Mock merges adjacent same-style runs that the real API keeps separate

**Root cause:** The real API tracks full lifecycle provenance (user UI, `updateTextStyle`, `insertText` inheritance) indefinitely. The mock only tracks provenance for styles set via `updateTextStyle` in the current session. These divergences only occur in multi-operation batches combining `insertText` with a provenance-sensitive operation (heading, link insert, or bullet creation) in the same batch.

## Module Guide

| Module | When to look here |
|--------|-------------------|
| `api.py` | Entry point. Request dispatch. `_strip_explicit_keys()` removes `__explicit__` from `get()` output. |
| `reindex.py` | Index computation bugs. `reindex_segment()` walks content and assigns `startIndex`/`endIndex`. `normalize_segment()` splits text runs at `\n` boundaries. |
| `text_ops.py` | `insertText` or `deleteContentRange` bugs. `_strip_link_style()` for link insertion. Consolidation logic. |
| `style_ops.py` | `updateTextStyle` (records `__explicit__`) or `updateParagraphStyle` (provenance-aware heading clearing). |
| `bullet_ops.py` | `createParagraphBullets` / `deleteParagraphBullets`. |
| `table_ops.py` | `insertTable`, `insertTableRow/Column`, `deleteTableRow/Column`. |
| `segment_ops.py` | `createHeader/Footer/Footnote`, `addDocumentTab`, `deleteTab`. |
| `navigation.py` | Finding elements by index. |
| `validation.py` | Range validation, structure tracking. |
| `stubs.py` | Unimplemented handlers that return `{}`. |
| `utils.py` | Shared helpers: `styles_equal_ignoring_explicit()`, `merge_explicit_keys()`, UTF-16 offset calculation. |

## Key References

- [Google Docs API batchUpdate requests](../../../docs/googledocs/api/) — one file per request type
- [Index behavior rules](../../../docs/googledocs/rules-behavior.md) — how indices shift during batchUpdate
- [Lists/bullets](../../../docs/googledocs/lists.md) — bullet and numbered list behavior
