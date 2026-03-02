# insertTable Index Bug Investigation

## Experiments

Document used: https://docs.google.com/document/d/146bUTw38Vc8fJXw7D2sQ2JaAVUdmxZLCscHNXGBh-J0

Raw observations from `.raw/document.json`:

### Tab: "1 Table Only - no explicit newlines"
User created a 2×2 table in an empty doc without pressing Enter.
```
[0-1]   sectionBreak
[1-2]   paragraph '\n'          ← phantom BEFORE table
[2-30]  table 2x2
[30-31] paragraph '\n'          ← phantom AFTER table
```
Table size = 28 = 2 + R + R×C + Σcell_content = 2+2+4+20

### Tab: "Table between paragraphs"
User typed a paragraph, inserted a table, typed another paragraph — no Enter pressed.
```
[0-1]   sectionBreak
[1-30]  paragraph 'This is the first paragraph.\n'
[30-46] table 2x2  (size=16)
[46-47] paragraph '\n'          ← phantom AFTER table
[47-96] paragraph 'This is the last paragraph...\n'
```
No phantom paragraph between the first paragraph and the table.

---

## Table Index Formula (verified)

```
table_size = 2 + R + R×C + Σ(cell_content_sizes)
```

Where:
- `2` = table START marker + table END marker
- `R` = one ROW marker per row
- `R×C` = one CELL marker per cell
- Cell content = all paragraph content (text + each paragraph's own `\n`)

Index layout inside table:
```
table.startIndex         = TABLE_START_MARKER
table.startIndex + 1     = ROW[0]_START_MARKER
table.startIndex + 2     = CELL[0][0]_START_MARKER
table.startIndex + 3..   = cell[0][0] paragraph content (in cell's own index space: starts at 1)
...
table.endIndex - 1       = TABLE_END_MARKER
```

---

## API Contract (from local docs + online research)

**Source: `docs/googledocs/api/InsertTableRequest.md`**

> "Inserts a table at the specified location. **A newline character will be inserted before the inserted table.**"
> "The table start index will be at the **specified location index + 1**."

**Source: `docs/googledocs/rules-behavior.md`**

Invalid deletions (400 error):
- Removing the final newline from body, header, footer, footnote, or table cell
- **Removing the newline character before a table without also deleting the table**
- Partially deleting a table (must delete entire element: startIndex to endIndex)
- Deleting individual rows or cells (use `deleteTableRow` / `deleteTableColumn`)

---

## What `insertTable(I)` Actually Does

Calling `insertTable` with `location.index = I`:

1. Inserts a **mandatory `\n` at index `I`** (the pre-table paragraph separator)
2. Places the **table structure at `[I+1, I+1+table_size)`**
3. Everything previously at `I+` is **shifted right by `1 + table_size`**

The character that was at position `I` (typically a preceding paragraph's own `\n`)
is displaced to position `I + 1 + table_size`, becoming the **phantom post-table paragraph**.

### Tracing "1 Table Only"

Original body: `sectionBreak[0-1]` + `segment-terminal \n at index 1`.

Call `insertTable(1)`:
- New `\n` at index 1 (pre-table separator)
- Table at `[2, 30)`
- Old segment-terminal `\n` displaced from 1 to `1+1+28=30` → becomes `[30-31]`

Result: `\n[1-2]` | `table[2-30]` | `\n[30-31]` ✓

### Tracing "Table between paragraphs"

Original body: `para[1-30]` (its `\n` at index 29) + `segment-terminal \n at 29` (same char).

Call `insertTable(29)`:
- New `\n` at index 29 (becomes the first para's new terminal — para boundary stays `[1-30]`)
- Table at `[30, 46)`
- Old `\n` displaced from 29 to `29+1+16=46` → becomes phantom `[46-47]`

Result: `para[1-30]` | `table[30-46]` | `\n[46-47]` | `last-para[47-96]` ✓

**Key insight:** There is ALWAYS exactly one phantom post-table `\n`. It is the character
that was at position `I` (the call site), displaced to `I + 1 + table_size`. It is NOT
something the caller inserted — it is the **displaced original content**.

---

## The Conceptual Misunderstanding in the Current Code

### What the code thinks

The code calls `insertTable(insert_idx)` where `insert_idx = _el_start(right_anchor)`.
It believes `insertTable` creates a "spurious `\n`" that is a nuisance to manage, and
tries to avoid it via the `spurious_pending` mechanism — having the paragraph that
comes BEFORE the table (in document order, processed AFTER in the reversed loop)
strip its own trailing `\n` so the insertTable's `\n` fills that role.

### What actually happens

When `insertTable(insert_idx)` is called where `insert_idx = _el_start(right_anchor)`:

```
... [left_anchor \n at insert_idx-1] [insert_reqs' \n at insert_idx] [table] [right_anchor] ...
```

There are now **two consecutive `\n` before the table**:
1. The left_anchor's own `\n` at `insert_idx - 1`
2. The mandatory `\n` from `insertTable` at `insert_idx`

Two consecutive `\n` = **empty paragraph = the spurious `<p />`** seen in testing.
The rule "cannot delete `\n` immediately before a table" means #2 cannot be removed.

### Why `spurious_pending` is the wrong abstraction

`spurious_pending` tries to strip the trailing `\n` from the paragraph that comes
BEFORE the table in document order (processed AFTER in the reversed adds loop). This
works only when:
- There IS such a paragraph in the adds list, AND
- It appears before the table in document order (i.e., after the table in the reversed loop)

It breaks when:
- The table is first in the adds list with deletes present (the `not deletes` guard
  prevents the special-case path)
- The only adds after the table in document order are headings/paragraphs that come
  AFTER the table (processed before the table in reversed order, so `spurious_pending`
  is False when they run)

This is exactly the bug observed in Edit 3: `adds = [table, h2 "Action Items"]`,
reversed loop processes h2 first (spurious_pending=False), then table (spurious_pending=True),
loop ends with no paragraph to absorb the spurious `\n` → phantom `<p />` emitted.

---

## The Correct Mental Model

### The invariant

Every element in a segment's body ends with a `\n`. For paragraphs, it's their own
content `\n`. The `\n` immediately before a table belongs to the **preceding paragraph**,
not to the table. The `\n` immediately after a table also belongs to a paragraph —
the one that was displaced there by `insertTable`.

### The correct call site for `insertTable`

Always call `insertTable` at `_el_end(left_anchor) - 1`, i.e., at the position of
the **preceding paragraph's own `\n`**.

Effect:
- `insertTable`'s mandatory pre-table `\n` goes at `_el_end(left_anchor) - 1`
  (takes over the preceding paragraph's `\n` slot — the para keeps its structure)
- Table is placed at `[_el_end(left_anchor), _el_end(left_anchor) + table_size)`
- The preceding paragraph's old `\n` is displaced to `_el_end(left_anchor) + table_size`
  → this becomes the **phantom post-table `\n`**
- The phantom can be **deleted** (it is after the table, not before it — the
  "cannot delete `\n` before table" rule does NOT apply here)

### Operation structure

For a slot with `deletes = [old_content]`, `adds = [table, ...]`:

```
# Group A — higher index, runs first in right-to-left sort
deleteContentRange [delete_start, delete_end)    # remove old content

# Group B — lower index, runs second
insertTable at _el_end(left_anchor) - 1          # insert table
deleteContentRange [_el_end(left_anchor) + table_size,
                    _el_end(left_anchor) + table_size + 1)  # delete phantom
insertText / other adds at insert_idx            # remaining adds
```

Group B contains operations that must run sequentially. The phantom delete targets
a position that only exists after `insertTable` runs, so it cannot be independently
sorted — it must immediately follow its `insertTable` in the request list.

### Why the current special case only works without deletes

The existing code does the right thing for `first_add_is_table and not deletes`:
it calls `insertTable` at `_el_end(left_anchor) - 1` and explicitly deletes the
phantom. But the guard `not deletes` prevents this correct path when there are
deletions in the same slot, falling back to `insertTable(insert_idx)` which
creates the spurious empty paragraph.

The fix: **remove the `not deletes` guard** and always use `_el_end(left_anchor) - 1`
as the table insert position, regardless of whether there are deletions. The delete
of old content is at a higher index (runs first in right-to-left sort) and does
not interfere with the insertTable at the lower index.

---

## Summary of Index Computations Actually Needed

The user's intuition is correct: right-to-left ordering makes most index arithmetic
unnecessary. The only necessary computations are:

| Computation | Where needed |
|---|---|
| `_el_end(left_anchor) - 1` | insert point for `insertTable` |
| `_el_end(left_anchor) + table_size` | position of phantom `\n` to delete |
| `I + 4 + r*(1+2*C) + 2*c` | cell content positions after `insertTable(I)` for population |
| `_RowTable.row_start(entry)` | row positions during column add/delete structural diff |

The `spurious_pending` flag, `table_size_extra` parameter, and the `not deletes`
guard are all artefacts of the wrong abstraction and should be removed once the
call site is fixed.
