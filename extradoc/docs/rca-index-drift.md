# Root Cause Analysis: Index Drift in Multi-Block Diff Operations

## Problem Statement

When the diff engine generates operations for documents with multiple change blocks, the resulting Google Doc content becomes corrupted. Text fragments appear in wrong positions, content gets jumbled, and the final document doesn't match the intended changes.

**Example of corruption:**
- Expected: `<p>Experienced engineer with 8+ years.</p>`
- Actual: `<p>E with 8+ Languages: Python, TypeScript</p>`

## Background: How the Diff Engine Works

### 1. Sequence Diff Phase
The engine compares pristine and current documents element-by-element using `sequence_diff()`, producing change blocks:

```
Changes: 7
  replace: pristine=[1-19], p_count=2, c_count=2
  equal: pristine=[19-27], p_count=1, c_count=1
  replace: pristine=[27-40], p_count=1, c_count=1
  equal: pristine=[40-47], p_count=1, c_count=1
  replace: pristine=[47-59], p_count=1, c_count=1
  equal: pristine=[59-70], p_count=1, c_count=1
  replace: pristine=[70-97], p_count=3, c_count=4
```

### 2. Operation Generation Phase
For each change block, the engine generates `DiffOperation` objects:
- **Delete operations**: Use pristine indexes directly (e.g., delete [27-40])
- **Insert operations**: Start at `change.pristine_start` and increment cumulatively within the block

### 3. Sort Phase
Operations are sorted for application:
1. **Deletes first**, in descending index order (70→47→27→1)
2. **Inserts second**, in ascending index order (1→27→47→70)

### 4. Application Phase
Google Docs applies operations sequentially. Each operation modifies the document, affecting subsequent operations.

## Root Cause

**The fundamental issue: Insert indexes from different change blocks are all based on PRISTINE positions, but they're applied to a document that has been modified by prior operations.**

### Detailed Walkthrough

Consider these change blocks:
- Block 1: Replace pristine [1-19] with new content
- Block 3: Replace pristine [27-40] with new content

After generation:
- Block 1 generates: Delete [1-19], Insert at index 1
- Block 3 generates: Delete [27-40], Insert at index 27

After sorting:
1. Delete [27-40] ✓ (descending order)
2. Delete [1-19] ✓ (descending order)
3. Insert at 1 ✓ (works fine)
4. Insert at 27 ✗ **PROBLEM!**

**Why step 4 fails:**
- The insert at index 27 assumes the document still has content from pristine positions [1-26]
- But Delete [1-19] removed 18 characters
- After that delete, pristine index 27 is now at document index 9 (27 - 18 = 9)
- The insert happens at wrong position, causing corruption

### Why Single Change Blocks Work

When there's only ONE change block (e.g., replacing entire document):
- All inserts have correct **relative** positions within the block
- `insert_idx` increments after each element: `insert_idx += added`
- No cross-block index conflicts

This is why the 6-element test passed but the 11-element test (with 7 change blocks) failed.

## Why Previous Fix Attempts Failed

### Attempt 1: Descending Order for All Operations
**Hypothesis**: Process all operations in descending index order to avoid shifts.

**Why it failed**: Insert operations reference positions that don't exist yet. An insert at index 200 fails if the document only has 50 characters. Inserts must happen in ascending order to build up the document.

### Attempt 2: Index Adjustment Function
**Hypothesis**: After sorting, adjust insert indexes based on cumulative prior inserts.

**Why it failed**: The adjustment was applied to ALL operations, including those within the same change block. Within a block, indexes are already correct (cumulative). The adjustment corrupted intra-block relationships.

## Constraints

1. **Google Docs API**: Operations are applied sequentially; each modifies the document
2. **Delete order**: Must be descending (higher indexes first) so deletions don't shift lower content
3. **Insert order**: Must be ascending (lower indexes first) so earlier inserts create space for later ones
4. **Intra-block correctness**: Within a change block, the current index calculation (cumulative) is correct
5. **Cross-block drift**: Only operations from DIFFERENT change blocks need adjustment

## Proposed Solutions

### Solution A: Track Change Groups and Adjust Cross-Group Only

Add a `change_group` identifier to each operation. After sorting, adjust only operations whose `change_group` differs from prior operations at lower indexes.

**Pros**: Minimal changes to existing logic
**Cons**: Complex adjustment calculation; need to track net change per group

### Solution B: Process Change Blocks Sequentially

Instead of sorting all operations globally, process each change block completely before moving to the next:

```
For each change_block:
    1. Apply deletes (descending within block)
    2. Apply inserts (ascending within block)
    3. Calculate net_change = inserted_length - deleted_length
    4. Offset subsequent blocks by cumulative net_change
```

**Pros**: Cleaner mental model; matches document evolution
**Cons**: Requires restructuring sort/apply logic

### Solution C: Compute Final-State Indexes During Generation

During generation, track the cumulative document state and compute what each index will be in the final document after all prior operations.

**Pros**: Each operation has its "true" final index
**Cons**: Complex bookkeeping; need to simulate document state

### Solution D: Generate Operations with Pristine-Relative Indexes, Adjust at Apply Time

Keep current generation logic. At apply time (in `_operation_to_request` or a wrapper), adjust indexes based on:
- All deletes that will happen at higher indexes
- All inserts that will happen at lower indexes

**Pros**: Separation of concerns
**Cons**: Requires knowing full operation list at conversion time

## Recommendation

**Solution B (Sequential Block Processing)** appears cleanest because:
1. It matches how the document actually evolves
2. It keeps intra-block logic unchanged (which works)
3. The offset calculation is straightforward: `cumulative_offset += (current_length - pristine_length)` per block
4. It's easier to reason about and debug

## Implementation Sketch for Solution B

```python
def _diff_section(pristine, current):
    diff_result = sequence_diff(p_elements, c_elements)

    all_operations = []
    cumulative_offset = 0

    for change in diff_result:
        block_ops = generate_block_operations(change, cumulative_offset)
        all_operations.extend(block_ops)

        # Calculate this block's net change
        pristine_length = change.pristine_end - change.pristine_start
        current_length = sum(elem_length(e) for e in change.current_elements)
        cumulative_offset += (current_length - pristine_length)

    # Sort: deletes descending, then inserts ascending
    # But indexes are already adjusted for final document state
    return sorted_operations(all_operations)
```

## Test Cases for Validation

1. **Single replace block**: Should work (baseline)
2. **Multiple replace blocks**: Core failing case
3. **Mixed equal/replace blocks**: Tests offset accumulation
4. **Insert at end**: Tests end-of-segment handling
5. **Delete only**: Tests delete-only paths
6. **Style changes within equal blocks**: Tests intra-element diffing

## Appendix: Failing Test Case

**Pristine (7 elements):**
```
[1-11] Name
[11-24] Contact info
[24-32] Summary
[32-45] Summary text
[45-52] Skills
[52-64] Skills list
[64-65] (empty)
```

**Current (11 elements):**
```
Alex Chen
Engineer | SF
Summary
Experienced engineer.
Skills
Python, Go
Experience
Senior Engineer
Lead developer.
Education
BS Computer Science
```

**Sequence Diff (7 blocks):**
- Blocks 1, 3, 5, 7: replace (content changes)
- Blocks 2, 4, 6: equal (headings match)

**Result**: Corrupted content due to index drift across the 4 replace blocks.
