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

| File | Purpose |
|------|---------|
| `model.py` | Op types (`DiffOp` and subtypes) |
| `diff.py` | Tree diff engine (`diff_documents()`) |
| `content_align.py` | Content alignment DP (`align_content()`) |
| `table_diff.py` | Table diff (`diff_tables()`) |
| `apply_ops.py` | 3-way merge: `apply_ops_to_document(base, ops)` |

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

### Testing

We test at the public interface boundaries only. **Serde** tests load a golden
document, serialize it, edit the files, deserialize, and assert only the
intended changes occurred (everything else preserved). **Reconciler** tests
construct base and desired `Document` objects, run `reconcile_batches()`, and
assert the generated `BatchUpdateDocumentRequest`s match expectations.

| Abstraction | Test file |
|-------------|-----------|
| Serde markdown (black-box, golden docs) | `tests/test_serde_markdown_blackbox.py` |
| Serde markdown (hand-crafted) | `tests/test_serde_markdown_roundtrip.py` |
| Serde markdown (bug regressions) | `tests/test_serde_markdown_bugs.py` |
| Serde XML round-trip | `tests/test_serde_xml_roundtrip.py` |
| Serde golden files | `tests/test_serde_golden.py` |
| Reconcile v3 diff | `tests/reconcile_v3/test_diff.py` |
| Reconcile v3 lowering (incl. deferred IDs) | `tests/reconcile_v3/test_lower.py` |
| DocsClient integration | `tests/test_client_reconciler_versions.py` |

## Google Docs API Reference

`docs/googledocs/` contains local reference material for Google Docs API
behavior. Key guides:

- `index.md` — overview
- `structure.md` — document tree (tabs, body, headers, footers, footnotes)
- `document.md` / `documents.md` — Document resource and methods
- `requests-and-responses.md` — batchUpdate request/response format
- `batch.md` — batching semantics
- `format-text.md` — text and paragraph styling
- `lists.md` — list/bullet behavior
- `tables.md` — table structure and operations
- `tabs.md` — multi-tab documents
- `named-ranges.md` — named range operations
- `images.md` — inline images
- `merge.md` — mail merge
- `move-text.md` — moving content
- `field-masks.md` — field mask syntax
- `rules-behavior.md` — API behavioral rules
- `best-practices.md` / `performance.md` — optimization guidance
- `api/` — 117 individual type/request reference files (e.g., `Document.md`,
  `BatchUpdateDocumentResponse.md`, `TableCell.md`, `ParagraphElement.md`)

Typed Python models generated from the API schema live in
`src/extradoc/api_types/`.

## Mock

`src/extradoc/mock/` contains an in-process mock of the Google Docs
`batchUpdate` API. It is useful for fast local iteration but **not
trustworthy** — its behavior diverges from the real API in subtle ways (style
provenance, run consolidation, edge cases). Do not treat mock results as ground
truth. Do not add compensating logic to the reconciler or serde just to make
the mock pass. When the mock disagrees with live Google Docs, the mock is
wrong.

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
