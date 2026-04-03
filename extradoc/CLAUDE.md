## Overview

Python library that transforms Google Docs into an XML or markdown folder
structure for LLM-assisted editing, using a pull → edit → push workflow
orchestrated by `DocsClient` (`src/extradoc/client.py`).


## Architecture: How It Works

### Objective
Declaratively edit a Google Doc.

### Pipeline

**pull** fetches `document.json`. This is saved as `./raw/document.json` and
represented in memory as `base Document`. Comments are fetched separately and we
get a composite `DocumentWithComments`.

- Public interface: `DocumentWithComments` — `src/extradoc/comments/_types.py`
- Public exports: `src/extradoc/comments/__init__.py`

**SERDE** converts `DocumentWithComments` into a folder in a SERDE-specific
format that is suitable for LLM agents to edit (markdown or xml).

- Public interface: `serialize()`, `deserialize()` — `src/extradoc/serde/__init__.py`
- XML models: `src/extradoc/serde/_models.py`
- XML serialization: `src/extradoc/serde/_to_xml.py`, `src/extradoc/serde/_from_xml.py`
- Markdown serialization: `src/extradoc/serde/_to_markdown.py`, `src/extradoc/serde/_from_markdown.py`
- Style handling: `src/extradoc/serde/_styles.py`

**LLM agent edits** outside our boundary and calls push.

**SERDE inspects the folder**, figures out what changed, then applies those
changes to an in-memory `DocumentWithComments` with base as the starting point.
This version of `DocumentWithComments` is referred to as **desired**.

- 3-way merge: `src/extradoc/serde/_apply_ops.py` (`apply_ops_to_document()`)

**Reconciler** — we have various versions, currently at v3 — diffs base and
desired `DocumentWithComments` and creates a list of `BatchUpdateRequests`.

The Reconciler works as a tree. A `Document` is actually a tree. It has Tabs.
Tabs have Headers, Footers, Body. There are 5 things that have "content" —
header, footer, body, footnote, table cell. The content is a list of
`StructuralElement`s — which is one of 4 things: `TableOfContents`, `Paragraph`,
`Table`, `PageBreak`. So there is recursion involved.

In v3 the reconciler proved out a few things: we can decompose the tree, we can
diff the list of structural elements, we can diff a table, a list, a paragraph.
So we seem to have the building blocks correctly working.

- Public interface: `diff()`, `reconcile()`, `reconcile_batches()` — `src/extradoc/reconcile_v3/api.py`
- Op types: `src/extradoc/reconcile_v3/model.py`
- Tree diff: `src/extradoc/reconcile_v3/diff.py` (`diff_documents()`)
- Content alignment DP: `src/extradoc/reconcile_v3/content_align.py` (`align_content()`)
- Table diff: `src/extradoc/reconcile_v3/table_diff.py` (`diff_tables()`)

The Reconciler returns a list of `BatchUpdateRequests`. These
`BatchUpdateRequests` have **deferred placeholder IDs** — that instruct the
execution engine how to resolve the placeholder ID by looking at the output from
a previous batch update request.

So you could have say 5 sequential requests, with the 2nd request having some
IDs that will only be available after the 1st request completes and so on.

**The key design split — reconciler is planner, executor is executor.** The
reconciler knows exactly what needs to be done. It simply has to say "after you
create the tab, get the tab id — then for the subsequent BatchUpdateRequest,
update the tab id in all request objects". The reconciler keeps creating the
next set of requests *as though the tab already existed*. The layer after the
reconciler invokes batchUpdate request #n, picks up the ids from the response,
edits #n+1 to substitute the placeholders with the resolved ids, and keeps
going on. In other words, the reconciler is planning the requests; the next
layer is executing that plan.

**Deferred placeholder format** (`src/extradoc/reconcile_v3/lower.py`,
`CreateHeaderOp` handler): each placeholder is a dict embedded directly in the
request where the real ID would go:

```python
{"placeholder": True, "batch_index": 0, "request_index": 3, "response_path": "createHeader.headerId"}
```

The mapping `(batch_index, request_index, response_path)` tells the executor
exactly which prior response to read and which path to extract. Every subsequent
request is generated with this placeholder value in place of the real ID — the
reconciler returns this map implicitly as part of the request batches themselves.

**Segment IDs** (headers, footers, footnotes): proven and working. When a new
header is created in batch 0, all batch 1 style and content requests carry the
deferred segment ID dict. `resolve_deferred_placeholders` substitutes the real
ID before batch 1 executes. See `lower_batches()` `CreateHeaderOp` /
`CreateFooterOp` / `InsertFootnoteOp` handlers.

**Tab IDs**: same pattern. When a new tab is created via `addDocumentTab`, the
body content requests carry a deferred tab ID with `response_path =
"addDocumentTab.tabProperties.tabId"`. A legacy string sentinel
`"__LAST_ADDED_TAB_ID__"` exists in `executor.py` as an interim workaround; the
structured placeholder dict is the correct approach and replaces it.

**Table cell recursion**: this is the exact same thing, but we already know the
segment id and the starting index. No deferred IDs are needed — cell positions
are computable from the table's insert index and structure. This is pure
synchronous recursion in the lowerer: `insertTable` is emitted, then each cell's
content is emitted at the computed absolute index in the same batch. The index
arithmetic is proven in `tests/reconcile_v3/test_lower.py`
(`make_indexed_table`, `make_indexed_cell`).

- Lowering (ops → requests with deferred IDs): `src/extradoc/reconcile_v3/lower.py` (`lower_batches()`)
- Deferred ID resolution: `src/extradoc/reconcile_v2/executor.py` (`resolve_deferred_placeholders()`)
- Batch execution: `src/extradoc/reconcile_v2/executor.py` (`execute_request_batches()`)

When all the batch update requests have completed, the document is considered to
have reconciled. In other words, the Google Doc now matches the desired document.

- Orchestration (pull/diff/push): `src/extradoc/client.py` (`DocsClient`)

### Testing Philosophy

We test at the boundaries of the core interfaces. Anything testing internals is
useless and must be deleted.

One cycle of live testing involves: pull a document → edit it on disk → push →
pull again to confirm the round trip. Use `./extrasuite doc create` if you don't
have a doc yet.

**Tests that cover the public abstractions:**

| Abstraction | Test file |
|-------------|-----------|
| Reconcile v3 diff | `tests/reconcile_v3/test_diff.py` |
| Reconcile v3 lowering (incl. deferred IDs) | `tests/reconcile_v3/test_lower.py` |
| SERDE round-trip (XML) | `tests/test_serde_xml_roundtrip.py` |
| SERDE round-trip (markdown) | `tests/test_serde_markdown_roundtrip.py` |
| SERDE golden files | `tests/test_serde_golden.py` |
| DocsClient integration | `tests/test_client_reconciler_versions.py` |

Test helpers (factory functions for constructing test documents):
`tests/reconcile_v3/helpers.py`

## Key Packages

| Package | Purpose |
|---------|---------|
| `src/extradoc/serde/` | `DocumentWithComments ↔ XML folder` |
| `src/extradoc/reconcile_v3/` | `Document` diff -> `BatchUpdateDocumentRequest` batches (**active**) |
| `src/extradoc/reconcile_v2/` | Previous reconciler; executor and deferred-ID resolution still used |
| `src/extradoc/comments/` | `comments.xml`, inline `comment-ref`, and comment diffs |
| `src/extradoc/mock/` | In-process mock of the Docs `batchUpdate` API |
| `src/extradoc/api_types/` | Generated typed models from the Docs API schema |
| `src/extradoc/transport.py` | Transport interfaces and implementations |
| `src/extradoc/client.py` | `DocsClient` pull/diff/push orchestration |

## Documentation

- `docs/on-disk-format.md` — authoritative file/folder/XML format
- `docs/comment-anchoring-limitation.md` — Drive API limitation for anchored comments
- `docs/googledocs/` — local reference material for Google Docs API behavior

## Key Gotchas

- Google Docs indices are UTF-16 code units, not Python character offsets.
- Headers, footers, footnotes, and table cells each have their own index rules.
- New tabs require an `index.xml` entry and a `<sectionbreak>` as the first
  element of `<body>`.
- `styles.xml` is written on serialize, but deserialize also tolerates a
  missing `styles.xml` and treats it as empty `<styles />`.
- After `push`, always re-pull before making further edits.
- `comment-ref` elements in `document.xml` are display metadata derived from
  `comments.xml`, not primary editable content.
- `src/extradoc/mock/` is useful for fast local regressions, but it is not a
  release-confidence source and must not be treated as the transport truth.
  For reconciler changes, prefer fixture-backed live Google Docs replay before
  trusting the result.
- Do not add compensating reconciler logic just to satisfy the mock. If mock
  behavior disagrees with live Google Docs, the mock is wrong for that purpose
  and live fixtures win.

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
