# Mock Google Docs API

A pure-function mock of the [Google Docs batchUpdate API](../../../docs/googledocs/api/): given an existing document + a `batchUpdate` request, it produces the new document state. See `MockGoogleDocsAPI` in `api.py` for the interface (`get()` and `batch_update()`).

## Status: Work in Progress

**61/61 test scenarios pass.** We test by sending the same `batchUpdate` request to both Google's real API and our mock via `CompositeTransport` (see `composite_transport.py`), then diffing the output. IDs are excluded from comparison. When the real API returns 400, the mock must also reject the request — `CompositeTransport` verifies this. A small number of scenarios pass via provenance leniency (B/I/U-only textStyle and bullet.textStyle divergences, and run consolidation differences are tolerated).

```bash
cd extradoc
uv run python scripts/test_mock_scenarios.py "https://docs.google.com/document/d/<ID>/edit"
```

The script generates 61 diverse `batchUpdate` scenarios (insert text, apply styles, table operations, etc.). In principle, any `batchUpdate` request can be tested this way — the mock could be fuzz-tested by generating random valid requests.

Mismatch logs are saved to `mismatch_logs/scenarios/scenario_NN/` for debugging.

## Style Provenance Tracking (`__explicit__`)

The mock tracks which textStyle properties were set via `updateTextStyle` using an `__explicit__` metadata key (a sorted list of field names) stored in each textStyle dict. This key is internal — `get()` strips it before returning.

**How it flows:**
- `updateTextStyle` → adds updated fields to `__explicit__` on affected runs
- `insertText` (non-link) → inherits `__explicit__` from source run via `deepcopy`
- `insertText` (into link run) → `_strip_link_style` uses `__explicit__` to decide which styles to keep
- `updateParagraphStyle` with heading → only clears italic/underline if NOT in `__explicit__`; always clears bold
- `createParagraphBullets` → copies italic to `bullet.textStyle` only if in `__explicit__`
- Run consolidation (delete) → ignores `__explicit__` for equality, merges (union) when consolidating

## Known Limitations (tolerated via provenance leniency)

The mock passes all 61 scenarios, but a few pass via **provenance leniency** in `CompositeTransport._documents_match()`. These tolerate:

1. **B/I/U-only textStyle divergences**: One side has `{bold: true}`, the other `{}` — on `textRun.textStyle` or `bullet.textStyle`
2. **Run consolidation divergences**: Mock merges adjacent same-style runs that the real API keeps separate (same text content, same styles, different run boundaries)

### Root cause

The real Google Docs API tracks **full lifecycle provenance** — whether each style property on each run was set by the user in the UI, via `updateTextStyle`, or inherited during `insertText`. This provenance survives across API calls indefinitely.

The mock only tracks provenance for styles set via `updateTextStyle` during its session (via the `__explicit__` key). Styles present when the mock is constructed have no provenance info.

### When does this matter in practice?

These divergences only occur in **multi-operation batchUpdate requests** where:
1. Text is inserted into an already-styled run (inheriting styles), AND
2. A subsequent operation in the same batch queries style provenance (heading, link insert, or bullet creation)

Single-operation requests and multi-operation requests that don't combine insertText with provenance-sensitive operations are unaffected.

## How It Works

`MockGoogleDocsAPI.batch_update()` processes requests sequentially. For each request, it dispatches to a handler (see `_process_request()` in `api.py` → handler map), then runs `reindex_and_normalize_all_tabs()` from `reindex.py`. **Handlers only modify content structure — they never compute indices.** After each handler, the centralized reindex pass walks all document content and assigns correct UTF-16 indices from actual text sizes. This is the key architectural invariant.

## Module Guide

| Module | When to look here |
|--------|-------------------|
| `api.py` | Entry point. Request dispatch. `_strip_explicit_keys()` removes `__explicit__` from `get()` output. |
| `reindex.py` | Index computation bugs. `reindex_segment()` walks content and assigns `startIndex`/`endIndex`. `normalize_segment()` splits text runs at `\n` boundaries. |
| `text_ops.py` | `insertText` or `deleteContentRange` bugs. `_strip_link_style()` uses `__explicit__` for link insertion. Consolidation uses `styles_equal_ignoring_explicit()`. |
| `style_ops.py` | `updateTextStyle` (records `__explicit__`) or `updateParagraphStyle` (provenance-aware heading clearing). |
| `bullet_ops.py` | `createParagraphBullets` (copies italic when in `__explicit__`) / `deleteParagraphBullets`. |
| `table_ops.py` | `insertTable`, `insertTableRow/Column`, `deleteTableRow/Column` bugs. |
| `segment_ops.py` | `createHeader/Footer/Footnote`, `addDocumentTab`, `deleteTab` bugs. |
| `navigation.py` | Finding elements by index (`get_tab`, `get_segment`, `find_table_at_index`, `get_paragraphs_in_range`). |
| `validation.py` | Range validation, structure tracking. |
| `stubs.py` | Unimplemented handlers that return `{}` (merge cells, inline image, page break, etc.). |
| `utils.py` | Shared helpers: `styles_equal_ignoring_explicit()`, `merge_explicit_keys()`, `table_cell_paragraph_style()`, `make_empty_cell()`, UTF-16 offset calculation. |

## Key References

- [Google Docs API batchUpdate requests](../../../docs/googledocs/api/) — one file per request type
- [Index behavior rules](../../../docs/googledocs/rules-behavior.md) — how indices shift during batchUpdate
- [Lists/bullets](../../../docs/googledocs/lists.md) — bullet and numbered list behavior
