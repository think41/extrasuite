## Overview

Python library that declaratively edits a Google Doc. The workflow is:
pull the doc → convert to markdown/XML → LLM edits files → convert back → push
changes to Google Docs. The conversion is lossy (markdown can't represent every
Google Docs property), but a 3-way merge ensures anything the format can't
represent passes through untouched. Orchestrated by `DocsClient`
(`src/extradoc/client.py`).

## Pipeline

**Pull** fetches the document from Google Docs API and represents it in memory
as `base` `DocumentWithComments` (`src/extradoc/comments/_types.py`).

**Serialize** converts `base` into a folder of markdown or XML files that an
LLM can read and edit.

- Public interface: `Serde` protocol — `src/extradoc/serde/__init__.py`
- Implementations: `MarkdownSerde` (`serde/markdown/`), `XmlSerde` (`serde/xml/`)
- Style handling: `src/extradoc/serde/_styles.py`

**LLM edits** the files on disk.

**Deserialize** reads the edited folder, diffs it against the pristine snapshot
saved at serialize time, and applies only the detected changes to the base
document via 3-way merge. The output is two `DocumentWithComments`: `base`
(original from pull) and `desired` (base + user's edits merged in). The 3-way
merge is what preserves properties the format cannot represent. See
`src/extradoc/serde/CLAUDE.md` for details.

- 3-way merge: `src/extradoc/diffmerge/apply_ops.py` (`apply_ops_to_document()`)

**Diffmerge** (`src/extradoc/diffmerge/`) — shared diff+merge layer used by both
serde (3-way merge) and reconciler (tree diff). Public API:

- `diff()` — structural diff between two document trees (`diff.py`)
- `apply()` — apply diff ops to a base document (`apply_ops.py`)
- `DiffOp` — op types representing document changes (`model.py`)
- `docs/diffmerge-design.md` documents the design of this module.
| File | Purpose |
|------|---------|
| `model.py` | Op types (`DiffOp` and subtypes) |
| `diff.py` | Tree diff engine (`diff_documents()`) |
| `content_align.py` | Content alignment DP (`align_content()`) |
| `table_diff.py` | Table diff (`diff_tables()`) |
| `apply_ops.py` | 3-way merge: `apply_ops_to_document(base, ops)` |

Design reference with full algorithm + invariants: `docs/diffmerge-design.md`.
Read that before modifying anything in `diffmerge/`.

**Reconciler** — takes `base` and `desired` `Document` and produces a list of
`BatchUpdateDocumentRequest`s that, when executed against the live Google Doc,
will transform it from `base` into `desired`. Uses `diffmerge` for the tree diff
and produces lowered API requests.

```python
# src/extradoc/reconcile_v3/api.py
def reconcile_batches(
    base: Document,
    desired: Document,
) -> list[BatchUpdateDocumentRequest]:
```

- Lowering (ops → requests with deferred IDs): `src/extradoc/reconcile_v3/lower.py`
- API entry point: `src/extradoc/reconcile_v3/api.py`

**Executor** — takes the list of `BatchUpdateDocumentRequest`s from the
reconciler and executes them sequentially against the live Google Docs API.
After each batch completes, it resolves deferred placeholder IDs in subsequent
batches using values from the API response, then continues until all batches
are executed. At that point, the live Google Doc matches `desired`.

```python
# src/extradoc/reconcile_v3/executor.py
async def execute_request_batches(
    transport: BatchUpdateTransport,
    *,
    document_id: str,
    request_batches: Sequence[BatchUpdateDocumentRequest],
    initial_revision_id: str | None,
) -> BatchExecutionResult:
```

- Deferred ID resolution: `src/extradoc/reconcile_v3/executor.py` (`resolve_deferred_placeholders()`)
- Lowering (ops → requests with deferred IDs): `src/extradoc/reconcile_v3/lower.py` (`lower_batches()`)

- Orchestration (pull/diff/push): `src/extradoc/client.py` (`DocsClient`)

### Coordinate contract

The desired `Document` tree produced by diffmerge and consumed by the
reconciler follows a strict three-state invariant on `startIndex`/`endIndex`:

1. **Concrete indices** on regions carried through unchanged from `base`.
2. **`None`** on regions that were synthesized or mutated by `apply_ops`.
3. **Mixed within a single element is forbidden** — poisoning propagates to
   the entire region enclosed by the `_apply_content_alignment` boundary.

`apply_ops_to_document` (`diffmerge/apply_ops.py`) is the **sole producer** of
desired-tree indices; `reconcile_v3/lower.py` is the **sole consumer**. Before
changing anything in `diffmerge/apply_ops.py` or `reconcile_v3/lower.py`, read
[`docs/coordinate_contract.md`](docs/coordinate_contract.md).

### Run fragmentation pitfall

The Google Docs API creates a new text run whenever `updateTextStyle` is called
on a sub-range, even if the style is identical to an adjacent run.  Fragmented
runs survive subsequent pulls and cause the serializer to emit markers like
`**PART** **I**` instead of `**PART I**`, which then look like spurious edits.

Three places defend against this:

1. **`diffmerge/apply_ops.py` — `_merge_adjacent_same_style_runs()`**: called at
   the end of `_merge_changed_paragraph`.  Consolidates sub-runs with equal
   merged styles before the desired tree reaches the reconciler.
2. **`reconcile_v3/lower.py` — `_insert_ops_for_span()`**: coalesces consecutive
   desired spans with equal style into a single `updateTextStyle` request (the
   "pending group" pattern).  Does not coalesce across opaque-element barriers.
3. **`serde/markdown/_to_markdown.py` — `_merge_adjacent_text_runs()`**: merges
   fragmented runs before serialization so pre-existing fragmentation in `base`
   does not produce separate bold/italic markers.

If a change causes `**X** **Y**` to appear in a round-trip, check all three
layers before looking elsewhere.

### Testing

Follow TDD / red -> green tests. Test against public interface of the respective module. Don't import module internals in your test.

## Google Docs API Reference

`docs/googledocs/` contains local reference material for Google Docs API
behavior. Key guides:

- `index.md` — overview of all documentation available for google docs
- `api/` — 117 individual type/request reference files (e.g., `Document.md`,
  `BatchUpdateDocumentResponse.md`, `TableCell.md`, `ParagraphElement.md`)

Typed Python models generated from the API schema live in
`src/extradoc/api_types/`.


## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

### Live testing

Use the `./extrasuite` CLI helper at the project root (one level up) to run
end-to-end cycles against a real Google Doc:

```bash
# from the repo root
./extrasuite doc create                  # create a new doc if needed
./extrasuite doc pull <doc-id> ./tmp     # pull to a local folder
# ... edit files in ./tmp ...
./extrasuite doc push <doc-id> ./tmp     # push changes
./extrasuite doc pull <doc-id> ./tmp     # re-pull to verify round trip
```

One full cycle (pull → edit on disk → push → pull again) is the minimum bar for
validating reconciler changes. Fixture-backed tests catch regressions; live
testing is the release-confidence gate.
