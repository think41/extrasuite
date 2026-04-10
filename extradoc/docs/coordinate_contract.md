# Coordinate Contract for the Desired Document Tree

**Status**: Normative. Task 1 of the `coordinate-contract-direction-a` refactor.
**Audience**: Engineers modifying `diffmerge/apply_ops.py` or `reconcile_v3/lower.py`.

This document specifies the contract governing `startIndex` / `endIndex` on
`StructuralElement` nodes of the **desired** `Document` tree produced by
`apply_ops_to_document()` (`src/extradoc/diffmerge/apply_ops.py:33`) and
consumed by `reconcile_v3/lower.py`.

The **base** tree is always concrete — every read of
`base_content[i].start_index` / `.end_index` is safe. This document is
exclusively about the desired tree.

---

## Three-State Invariant {#three-state-invariant}

Every `StructuralElement` (and every nested `TableRow`, `TableCell`,
`ParagraphElement`) in the desired tree is in **exactly one** of three states
with respect to its `startIndex` / `endIndex`:

### State A — Concrete `(int, int)`

Both indices are integers, and they equal the values that would be present on
the live Google Doc **before any push ops run**.

Preconditions (all must hold):

1. The node is byte-identical (structurally and by content) to its base
   counterpart — no field of the element changed.
2. No ancestor container underwent a shape change, where "shape change" means
   any of:
   - sibling count changed (insert or delete into the container),
   - a table cell's `content` list grew or shrunk (paragraphs joined/split),
   - a table's `tableRows` length changed,
   - a row's `tableCells` length changed,
   - a terminal-empty-trailing peel occurred in the enclosing segment.
3. No sibling inside the same `_apply_content_alignment` region (see
   [Poisoning](#poisoning-rule)) was mutated or inserted.

When all three hold, the index is safe to pass verbatim to the Google Docs API
as a live-doc coordinate.

### State B — `(None, None)`

Both indices are `None`. This means the node was either:

- newly inserted by the user edit (no base counterpart exists), or
- lives inside a region whose shape changed, so its live-doc offset cannot be
  inferred from its base offset.

`reconcile_v3/lower.py` **MUST** synthesize a live-doc coordinate for such
nodes from base anchors plus cumulative shift (see
[`_lower_story_content_update`](../src/extradoc/reconcile_v3/lower.py#L1012)),
or raise (see [Failure mode](#failure-mode)).

### State C — Mixed (one `None`, one `int`)

**FORBIDDEN**. Enforced by assertion in `apply_ops.py`. A mixed state is
always a bug in a producer helper (e.g. a merge function that stripped
`startIndex` but forgot `endIndex`, or vice versa). Crashing loudly is
preferable to leaking a half-valid coordinate into lowering.

---

## Poisoning Propagation Rule {#poisoning-rule}

**Rule**: if any child of a container is mutated or inserted, **every**
sibling of that child AND the container itself have `startIndex` / `endIndex`
reset to `None`.

### Why

Google Docs coordinates are a single flat byte-offset space. Any byte-level
delta at offset `k` shifts every element at offset `> k` by that delta. Within
a touched sibling run, each sibling's pre-push base offset is no longer the
right post-partial-apply offset, because preceding siblings in the same run
may expand or contract. The only safe thing to do is refuse to carry the base
coordinate forward: the desired tree says "unknown, recompute from scratch".

### Boundary — where poisoning stops

Poisoning is bounded by the enclosing `UpdateBodyContentOp` region — the
contiguous run of elements handed to `_apply_content_alignment`
(`apply_ops.py:1609`). Regions outside this run — a different tab, a
different header/footer segment, a body slice untouched by the op — keep
their concrete indices. They were not byte-mutated, so their base coordinates
remain valid for reading (although the lowerer will still shift them by
cumulative deltas accumulated from preceding ops at push time).

### Recursion into tables

Poisoning is recursive through tables. When `_merge_table_cell`
(`apply_ops.py:1523`) grows or shrinks a cell's `content`, that cell is
poisoned. Per the rule, every **sibling cell in the same row** and the
**containing `table`** element itself must also be poisoned. Rows in the same
table that were not touched follow the same rule: if any row is touched, all
row-level indices in that table become `None`, because the table as a whole
is a poisoned sibling in its parent region.

### Interaction with `_strip_indices_inplace`

`_strip_indices_inplace` (`apply_ops.py:714`) is the low-level tool used to
realise poisoning: it recursively removes `startIndex` / `endIndex` from a
nested dict / list structure. The poisoning rule governs **where** it must
be called; `_strip_indices_inplace` governs **how**.

---

## Producers and Consumers {#producers-consumers}

### Producer — sole owner

`apply_ops_to_document()` (`apply_ops.py:33`) and its private helpers are the
**only** code allowed to set or clear `startIndex` / `endIndex` on elements
that will reach the reconciler. The producer is responsible for leaving every
desired-tree node in State A or State B — never State C.

### Forbidden — serde

The serde layer (`src/extradoc/serde/`) **MUST NOT** set `startIndex` or
`endIndex` on any `StructuralElement` it emits from deserialization. All
coordinates on desired-tree nodes originate from `apply_ops_to_document`
merging raw base dicts in. If serde leaks a fabricated index (e.g. a
parser-computed offset into the markdown source), it will look like State A
to the consumer and cause silent drift.

### Consumer — sole reader

`reconcile_v3/lower.py` is the **only** consumer of desired-tree coordinates.
Every read must be guarded: call `_element_range()` / `_element_start()`
(`lower.py:3321`, `lower.py:3330`) and branch on `None` before treating a
value as a live-doc coordinate.

The base tree is read via the same helpers but is guaranteed to return
concrete values — see [Who reads what](#who-reads-what).

---

## Failure Mode {#failure-mode}

If `reconcile_v3/lower.py` encounters `None` where it needs a concrete
coordinate **and** cannot recompute the coordinate from base anchors plus
cumulative shift, it **MUST** raise `CoordinateNotResolvedError` (a new
exception to be added alongside `ReconcileV3InvariantError` in
`src/extradoc/diffmerge/errors.py`).

It **MUST NOT**:

- silently continue past the `None`,
- substitute `0` or `-1`,
- emit a `deleteContentRange` / `insertText` request with a fabricated index,
- skip the op without recording the failure.

Loud failure is the only acceptable behaviour. A silent skip produces a
document that diverges from `desired` without the user knowing; a fabricated
index produces a 400 from the API (as in the FORM-15G bug) or, worse,
corrupts unrelated content.

---

## Worked Example — FORM-15G Cell Drift {#form-15g-example}

### Setup

Base document has a table cell spanning `[414..496)` containing 3 paragraphs:

```
414  P1: "Name of the assessee"
438  P2: "PAN of the assessee"
460  P3: "Status"
495  (cell terminator "\n")
```

The cell's base range is `[414..496)`.

### Edit

The user collapses the 3 paragraphs into 1 via the editable format (GFM
table cell flattens to a single line). `_merge_table_cell` (`apply_ops.py:1523`)
takes the join branch: `len(desired) == 1 < len(raw) == 3`, and
`len(ancestor) == 1 < len(raw) == 3`, so it truncates `raw_cell_content` to
one paragraph. This is a cell shape change.

### Contract consequences

Per the [poisoning rule](#poisoning-rule):

1. The merged cell is poisoned → `(None, None)`.
2. Every sibling cell in the same row is poisoned → `(None, None)`.
3. Every paragraph-element and text-run nested inside any of those cells is
   poisoned.
4. The containing `table` element is poisoned → `(None, None)`.

The base tree's copy of the same cell is **unchanged**: it still carries
`start_index=414`, `end_index=496`. The base tree is always concrete.

### Lowering

When `_lower_story_content_update` (`lower.py:1012`) emits the
`deleteContentRange` for the content the user removed, it **reads from the
base tree**, not from the desired tree:

```python
start, end = _element_range(base_content[base_idx])   # 414, 496 — concrete
```

The insertion position for the replacement paragraph is likewise computed
from base anchors (the cell start, `414`) plus the cumulative shift
accumulated from earlier ops in the same batch.

The desired-tree cell's `(None, None)` is never used as a coordinate. The
lowerer may read its content and style fields freely — only indices are
poisoned.

### Result

No delete op lands on a cell boundary. Specifically, the pathological
`delete[496..497)` that hits the row terminator and triggers API 400 cannot
be produced: `496` is only ever reached by reading the base tree, which does
not motivate a delete at that offset (the base cell ends there — there is
nothing to delete past it).

---

## Who Reads What {#who-reads-what}

| Tree      | Index state                         | Reader obligation                              |
| --------- | ------------------------------------ | ---------------------------------------------- |
| `base`    | Always State A (concrete)            | Read freely; no `None` guard needed.           |
| `desired` | State A or State B (never State C)   | Guard every index read; branch on `None`.      |

The lowerer should prefer **base-tree reads** for any coordinate it emits
into a `Request`, and prefer **desired-tree reads** for any content / style
it emits. The two trees are read for complementary purposes; mixing them up
is the origin of coordinate drift bugs.
