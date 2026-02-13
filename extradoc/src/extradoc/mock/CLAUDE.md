# Mock Google Docs API

A pure-function mock of the [Google Docs batchUpdate API](../../../docs/googledocs/api/): given an existing document + a `batchUpdate` request, it produces the new document state. See `MockGoogleDocsAPI` in `api.py` for the interface (`get()` and `batch_update()`).

## Status: Work in Progress

**45/61 test scenarios pass** (6 genuine failures + 10 stale-index real API errors). We test by sending the same `batchUpdate` request to both Google's real API and our mock via `CompositeTransport` (see `composite_transport.py`), then diffing the output. IDs are excluded from comparison.

```bash
cd extradoc
uv run python scripts/test_mock_scenarios.py "https://docs.google.com/document/d/<ID>/edit"
```

The script currently uses an LLM to generate 61 diverse `batchUpdate` scenarios (insert text, apply styles, table operations, etc.). In principle, any `batchUpdate` request can be tested this way — the mock could be fuzz-tested by generating random valid requests.

Mismatch logs are saved to `mismatch_logs/scenarios/scenario_NN/` for debugging.

## How It Works

`MockGoogleDocsAPI.batch_update()` processes requests sequentially. For each request, it dispatches to a handler (see `_process_request()` in `api.py` → handler map), then runs `reindex_and_normalize_all_tabs()` from `reindex.py`. **Handlers only modify content structure — they never compute indices.** After each handler, the centralized reindex pass walks all document content and assigns correct UTF-16 indices from actual text sizes. This is the key architectural invariant.

## Module Guide

| Module | When to look here |
|--------|-------------------|
| `api.py` | Entry point. Request dispatch. Start here to trace any request. |
| `reindex.py` | Index computation bugs. The `reindex_segment()` function walks body/header/footer/footnote content and assigns `startIndex`/`endIndex`. `normalize_segment()` splits text runs at `\n` boundaries. |
| `text_ops.py` | `insertText` or `deleteContentRange` bugs. Handles paragraph splitting (on `\n` insertion) and paragraph merging (on `\n` deletion). |
| `style_ops.py` | `updateTextStyle` or `updateParagraphStyle` bugs. |
| `bullet_ops.py` | `createParagraphBullets` / `deleteParagraphBullets` bugs. |
| `table_ops.py` | `insertTable`, `insertTableRow/Column`, `deleteTableRow/Column` bugs. |
| `segment_ops.py` | `createHeader/Footer/Footnote`, `addDocumentTab`, `deleteTab` bugs. |
| `navigation.py` | Finding elements by index (`get_tab`, `get_segment`, `find_table_at_index`, `get_paragraphs_in_range`). |
| `validation.py` | Range validation, structure tracking. |
| `stubs.py` | Unimplemented handlers that return `{}` (merge cells, inline image, page break, etc.). |
| `utils.py` | Shared helpers: `table_cell_paragraph_style()`, `make_empty_cell()`, UTF-16 offset calculation. |

## Key References

- [Google Docs API batchUpdate requests](../../../docs/googledocs/api/) — one file per request type
- [Index behavior rules](../../../docs/googledocs/rules-behavior.md) — how indices shift during batchUpdate
- [Lists/bullets](../../../docs/googledocs/lists.md) — bullet and numbered list behavior
