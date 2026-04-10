# diffmerge — design reference

`src/extradoc/diffmerge/` is the shared diff-and-merge layer that both **serde**
(3-way merge on deserialize) and **reconciler** (tree diff → API requests) build
on. This document explains how it works, why it is shaped the way it is, and
which invariants the algorithms rely on.

Read this before modifying anything in the package. The layer is small (~5 files)
but the invariants matter: getting them wrong produces invalid edit plans that
the Google Docs API rejects.

> **See also:** [`coordinate_contract.md`](coordinate_contract.md) for the
> three-state `startIndex`/`endIndex` invariant on the desired tree produced
> by `apply_ops_to_document`.

## Public surface

```python
from extradoc.diffmerge import diff, apply, DiffOp
```

| Symbol | File | Purpose |
|---|---|---|
| `diff(base, desired)` | `diff.py` | Tree-diff two `Document` models, return `list[DiffOp]`. |
| `apply(base_dict, ops)` | `apply_ops.py` | Apply ops to a base document dict, producing a new dict. |
| `DiffOp` | `model.py` | Dataclasses for every kind of document change. |
| `ContentAlignment` | `content_align.py` | Result of aligning two content sequences. |

Neither function hits the network. Both are pure in-memory computation over
Pydantic models + dicts, deterministic given the same input.

## Two consumers, two contracts

```
                         ┌──────────────┐
                         │  diffmerge   │
                         └──────┬───────┘
                    ┌───────────┴────────────┐
                    ▼                        ▼
           ┌────────────────┐       ┌──────────────────┐
           │  serde         │       │  reconcile_v3    │
           │  (3-way merge) │       │  (tree diff)     │
           └────────────────┘       └──────────────────┘
```

**serde / 3-way merge (`apply_ops.py`)**
On deserialize, the serde loads three documents:

- `base` — the full API document from `.raw/document.json` (bit-accurate).
- `ancestor` — the lossy markdown/XML form written at serialize time (`.pristine/`).
- `mine` — the user's current folder (what they edited).

It computes `ops = diff(ancestor, mine)` (changes in the lossy representation)
and then `desired = apply(base, ops)`. Because `ancestor` and `mine` go through
the same lossy conversion, systematic format bias cancels out. The merge
applies *only* the differences markdown could see, onto the rich base.

**reconcile_v3 / tree diff (`reconcile_v3/lower.py`)**
The reconciler calls `diff(base, desired)` and lowers each `DiffOp` to one or
more `BatchUpdateDocumentRequest`s with deferred-ID resolution for tab/header/
footer IDs.

## The tree diff (`diff.py`)

`diff_documents()` walks the Document tree in a fixed top-down order:

```
Document
 └── Tab (matched by tabId, positional fallback)
      ├── DocumentStyle            in-place diff
      ├── NamedStyles              matched by namedStyleType enum
      ├── Lists                    matched by listId — add/delete only
      ├── InlineObjects            matched by inlineObjectId
      ├── Headers / Footers        matched by headerId / footerId
      ├── Footnotes                matched by footnoteId
      └── Body content             → ContentAlignment DP
           └── TableCell content   → recursive ContentAlignment DP
```

At each level the diff anchors to whatever stable ID Google Docs provides. The
only place where *ordered content sequences* show up — and therefore the only
place that needs alignment — is the body (and recursively, table-cell) content
list. That's where `content_align.py` is called.

## Content alignment DP (`content_align.py`)

Given two sequences `base[0..m-1]` and `desired[0..n-1]`, produces a
`ContentAlignment`:

```python
@dataclass
class ContentAlignment:
    matches: list[ContentMatch]          # (base_idx, desired_idx) pairs
    base_deletes: list[int]              # base indices that have no partner
    desired_inserts: list[int]           # desired indices that are new
    total_cost: float
```

### Minimum-cost DP

Standard edit-distance DP with three transitions:

```
dp[i][j] = min(
    dp[i-1][j-1] + edit_cost(base[i-1], desired[j-1])   if matchable
    dp[i-1][j]   + delete_penalty(base[i-1])
    dp[i][j-1]   + insert_penalty(desired[j-1])
)
```

`matchable()` gates whether two elements may be paired: same broad kind
(paragraph/list/table/structural), and — for text-bearing kinds — a minimum
token-Jaccard similarity (`MIN_PARA_MATCH_SIMILARITY = 0.3` etc.). The penalty
constants bias the DP toward matching over delete+insert so the reconciler
edits in place.

### Invariant 1: segment-terminal pre-match

The Google Docs API refuses to delete the terminal paragraph of any segment
(body, header, footer, footnote, table cell). Before running the DP,
`align_content()` pre-matches `base[m-1] ↔ desired[n-1]` and runs the DP only
on the prefixes `base[:-1]`, `desired[:-1]`. The terminal pair is appended to
the result. This guarantees the DP never emits a delete or insert on the
terminal.

References: `docs/googledocs/api/DeleteContentRangeRequest.md`,
`docs/googledocs/rules-behavior.md`.

### Invariant 2: table-flanking pre-match (`_pin_table_flanks`)

In every Google Docs segment, a `table` element is always immediately preceded
**and** immediately followed by a `paragraph`. This is enforced structurally
by the API:

- `InsertTableRequest` synthesizes the bracketing paragraphs if they're not
  already present.
- `DeleteContentRangeRequest` rejects any range whose deletion would leave a
  table un-bracketed.
- Three golden documents in `tests/golden/*.json` contain 0 violations.

References: `docs/googledocs/api/InsertTableRequest.md`,
`docs/googledocs/api/DeleteContentRangeRequest.md`, `docs/insert-table-investigation.md`.

**Consequence for alignment.** The raw-text DP does not know about this
invariant. If a table-flanking paragraph's text is completely rewritten (for
example, a heading above a code-block table was changed), the DP will happily
delete the old flank and insert a new one. This produces:

1. **Spurious delete+insert churn** that defeats in-place editing and loses
   comments/formatting on the flank paragraph.
2. **Invalid edit plans** — the reconciler emits `deleteContentRange` covering
   a table-adjacent `\n`, which the API rejects with a 400.

**Fix.** `_pin_table_flanks()` runs post-DP (before `_positional_fallback`):

1. Extract `table_pairs` from the DP's matches.
2. For each `(bi, di)` table pair, pin `(bi-1, di-1)` and `(bi+1, di+1)` if
   both positions are in range **and** both elements are paragraphs.
3. Detect conflicts (same `bi` or `di` appearing in multiple anchor pairs) and
   drop the lower-similarity table pair until anchors are consistent and
   monotonic. Bounded by O(#tables) iterations.
4. Partition the sequences into gaps between consecutive anchors; re-run
   `_dp_align` on any gap whose original matches straddled a new anchor
   boundary. Preserve matches in untouched gaps.
5. Recompute `total_cost`.

The result is that flank paragraphs are **always** matched when their tables
are matched — regardless of textual similarity — forcing the reconciler to emit
in-place paragraph updates rather than delete+reinsert.

### Invariant 3: positional fallback

After DP + flank pinning, `_positional_fallback()` promotes same-kind
singletons in 1:1 gaps to matches: if an unmatched base element and an
unmatched desired element sit alone between two anchors and share a kind,
match them. This catches structurally-equivalent elements whose text changed
too much for `matchable()` to accept them in the DP.

### Call order

```python
terminal_match = (base[m-1], desired[n-1])       # pre-matched
prefix_alignment = _dp_align(base[:-1], desired[:-1])
prefix_alignment = _pin_table_flanks(prefix_alignment, ...)
prefix_alignment = _positional_fallback(prefix_alignment, ...)
return ContentAlignment(matches=[*prefix_alignment.matches, terminal_match], ...)
```

## Table diff (`table_diff.py`)

When two tables are matched by the content-alignment DP, `diff_tables()`
performs a structural diff of their rows and columns and emits row/column
insert/delete ops plus recursive cell-content updates. `table_similarity()`
powers both the initial DP `matchable()` decision and the conflict-resolution
tie-breaker in `_pin_table_flanks`.

## 3-way merge (`apply_ops.py`)

`apply_ops_to_document(base_dict, ops)` walks the op list and mutates a deep
copy of the base dict. Most ops are self-contained (create header, delete
list, update document style, etc.). The complex one is `UpdateBodyContentOp`,
which carries a `ContentAlignment` produced by diffing `ancestor` vs `mine`
and must apply it onto `raw_base` (which is the same tree as ancestor but
transport-accurate).

### `_apply_content_alignment`

The function has to reconcile **three** index spaces:

| Space | What it is |
|---|---|
| `raw_base` | The full API document's content list (rich, dict-form). |
| `ancestor` | The parsed serde snapshot — lossy, same element ordering. |
| `desired` (mine) | The user's edited folder parsed back. |

The alignment is `ancestor ↔ desired`. To apply it onto `raw_base`, the merge
first aligns `raw_base ↔ ancestor` (via `_align_raw_to_ancestor`), then walks
desired in order, mapping each desired index back through
`desired → ancestor → raw_base`.

### Invariant 4: raw_base monotonic alignment

`_align_raw_to_ancestor` runs in two phases:

1. **Phase 1** — sequentially match content-bearing elements (paragraphs with
   text, tables, TOCs). Their ordering is identical in both sequences because
   the serde write order is deterministic.
2. **Phase 2** — match remaining trivial elements (bare `\n` paragraphs used
   as separators) within a monotonic window bounded by the surrounding
   matched anchors. This phase **must** preserve monotonicity: if
   `anc_to_raw[a] < anc_to_raw[a+1]` fails for any `a`, the downstream
   "carry-through unmatched raw elements" logic goes haywire and produces a
   result that is vastly longer than desired.

A simple min-distance heuristic (pre-#59) violated monotonicity when raw_base
had many more trivial elements than ancestor. The current window-bounded
order-preserving algorithm is monotonic by construction.

### Serde preservation promise

When `desired` is emitted, the merge walks `desired_content` in order. For
each matched desired element it emits the *reconciled* version of its
raw_base counterpart (base structure + desired text/markdown-representable
style overlay). **Additionally**, raw_base elements that have no ancestor
counterpart are carried through at their original relative position. This is
how the serde keeps its promise:

> The serde will not corrupt anything it doesn't understand.

Elements the format cannot round-trip (custom paragraph properties, unusual
inline objects, future API fields) appear in `raw_base` but not in `ancestor`.
The merge emits them unchanged at their original position, between the
raw_base elements they were flanked by.

## What `diffmerge` does **not** do

- **No API calls.** Every function is offline.
- **No lowering.** Producing `BatchUpdateDocumentRequest`s is the reconciler's
  job (`reconcile_v3/lower.py`).
- **No document construction.** Inputs are `Document` models produced
  elsewhere.

## Testing

| Test file | What it covers |
|---|---|
| `tests/diffmerge/test_content_align.py` | DP, terminal pre-match, matchable/edit_cost. |
| `tests/diffmerge/test_table_flank_pinning.py` | Flank-pinning invariant, conflict resolution, unequal table counts. |
| `tests/diffmerge/test_table_diff.py` | Row/column ops, table_similarity. |
| `tests/diffmerge/test_diff.py` | End-to-end tree diff. |
| `tests/test_serde_markdown_blackbox.py` | 3-way merge end-to-end (serde consumer). |
| `tests/reconcile_v3/*.py` | 3-way merge consumers (reconciler consumer). |

When adding a new invariant, write an xfail test first that demonstrates the
broken behaviour, then implement the fix and un-xfail. Every invariant in
this document earned its place because it was violated at least once.

## Related documents

- `docs/insert-table-investigation.md` — empirical model of insertTable semantics.
- `docs/googledocs/api/InsertTableRequest.md`
- `docs/googledocs/api/DeleteContentRangeRequest.md`
- `docs/googledocs/rules-behavior.md`
- `src/extradoc/serde/CLAUDE.md` — serde contract + the "promise".
- `docs/reconcile-v3.md` — reconciler-side design.
