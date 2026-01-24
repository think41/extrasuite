# SML Reconciliation Specification

A complete specification for converting SML diffs into Google Slides API `batchUpdate` requests.

---

## Table of Contents

1. [Overview](#overview)
2. [SML Lifecycle](#sml-lifecycle)
3. [Core Principles](#core-principles)
4. [Text Content Model](#text-content-model)
5. [Diff Detection](#diff-detection)
6. [Operation Ordering](#operation-ordering)
7. [Actions Processing](#actions-processing)
8. [Request Generation by Change Type](#request-generation-by-change-type)
9. [Field Mask Computation](#field-mask-computation)
10. [Editing Constraints](#editing-constraints)
11. [Error Handling](#error-handling)
12. [Examples](#examples)

---

## Overview

The reconciliation process converts differences between two SML documents into a minimal, optimized `batchUpdate` request for the Google Slides API.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Fetch     │     │   User      │     │    Diff     │     │  batchUpdate│
│   from API  │ ──→ │   Edits     │ ──→ │   Engine    │ ──→ │   Request   │
│   → SML     │     │   SML       │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                                                            │
       │                    ┌─────────────┐                         │
       └────────────────────│  SML is now │←────────────────────────┘
                            │   STALE     │
                            │  Re-fetch   │
                            └─────────────┘
```

### Goals

1. **Correctness**: Generated requests must accurately reflect user intent
2. **Optimality**: Minimize the number of API requests
3. **Determinism**: Same diff always produces same requests
4. **Safety**: Never corrupt the presentation state

---

## SML Lifecycle

### Single-Transaction Model

SML operates as a **single-transaction snapshot**:

1. **Fetch**: Retrieve presentation from API, convert to SML
2. **Edit**: User modifies SML content and structure
3. **Diff**: Compare original SML with edited SML
4. **Apply**: Generate and execute `batchUpdate` request
5. **Discard**: Edited SML is now **invalid** - must re-fetch

```
Original SML (from API)     Edited SML (by user)
         │                          │
         │    ┌──────────────┐      │
         └───→│     DIFF     │←─────┘
              └──────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ batchUpdate  │
              │   Request    │
              └──────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Both SMLs    │
              │ now invalid  │
              └──────────────┘
```

### Why Single-Transaction?

After a `batchUpdate`:
- Object IDs may change (for newly created objects)
- Text indices shift (after insertions/deletions)
- Element positions change (after reordering)

The edited SML contains stale references that no longer match the server state.

---

## Core Principles

### 1. Object IDs are Immutable References

Every element's `id` attribute maps to Google Slides' `objectId`:

```html
<TextBox id="title_1" ...>  <!-- id = objectId for all API requests -->
```

- Use existing IDs for updates and deletes
- Generate new UUIDs for created elements
- IDs must be unique within the presentation

### 2. Ranges are Read-Only Coordinates

The `range` attribute on `<P>` and `<T>` elements contains character indices from the **original** document:

```html
<P range="0-24">
  <T range="0-6">Hello </T>
  <T range="6-11" class="bold">world</T>
</P>
```

**Critical Rule**: Users must **NEVER** modify `range` attributes. They are used to:
- Identify text positions for delete operations
- Generate correct `textRange` parameters
- Track what changed between original and edited

### 3. Smallest Edit Unit is `<T>`

Text operations are atomic at the `<T>` (TextRun) level:

- A `<T>` is either unchanged, modified, added, or deleted
- We do not perform character-level diffing within a `<T>`
- Content or style changes trigger delete + insert + style operations

### 4. All Text Lives in `<P>` and `<T>` Elements

Every shape's text content must use explicit structure:

```html
<!-- Correct: explicit P and T -->
<TextBox id="tb1">
  <P range="0-12">
    <T range="0-6">Hello </T>
    <T range="6-11">world</T>
  </P>
</TextBox>

<!-- INVALID: bare text in TextBox -->
<TextBox id="tb2">Hello world</TextBox>

<!-- INVALID: bare text in P -->
<TextBox id="tb3">
  <P>Hello world</P>
</TextBox>

<!-- INVALID: newline in content -->
<TextBox id="tb4">
  <P><T>Line1\nLine2</T></P>
</TextBox>
```

**Validation:** The parser must reject SML with bare text or newlines in content.

### 5. Newlines are Implicit

Each `<P>` implicitly ends with `\n`:
- The `\n` is NOT included in SML content
- The `\n` IS included in range calculations
- Users cannot add `\n` - they create new `<P>` elements instead

---

## Text Content Model

### Structure

```
Shape (TextBox, Rect, etc.)
  └── Paragraphs (<P>)
        └── TextRuns (<T>)
              └── Text content
```

### Range Semantics

Ranges use `start-end` format (0-indexed, end-exclusive):

```html
<TextBox id="tb1">
  <P range="0-12">                    <!-- "Hello world\n" -->
    <T range="0-6">Hello </T>         <!-- Characters 0-5 -->
    <T range="6-11">world</T>         <!-- Characters 6-10 -->
  </P>                                 <!-- Implicit \n at index 11 -->
  <P range="12-25">                   <!-- "Second line.\n" -->
    <T range="12-24">Second line.</T>
  </P>
</TextBox>
```

### Range Calculation Rules

1. **Paragraph range**: Start of first `<T>` to end of last `<T>` + 1 (for `\n`)
2. **TextRun range**: Exact character span of the content
3. **Shape text length**: End of last paragraph's range

```
Text: "Hello world\nSecond line.\n"
       ├─────┬────┤├────────────┤
       0     6   11 12         24  25

P1: range="0-12"   (includes \n at 11)
P2: range="12-25"  (includes \n at 24)
```

---

## Diff Detection

### Element Matching

Elements are matched between original and edited SML by:

1. **Primary**: `id` attribute (exact match)
2. **Fallback**: Position within parent (for elements without ID)

### Change Types

| Change Type | Detection | Example |
|-------------|-----------|---------|
| **Added** | ID exists in edited, not in original | New `<TextBox id="new_1">` |
| **Deleted** | ID exists in original, not in edited | Removed element |
| **Modified** | ID exists in both, attributes/content differ | Changed `class` or text |
| **Moved** | Same ID, different parent or position | Slide reordering |
| **Unchanged** | ID exists in both, identical content | No operation needed |

### Attribute Diffing

For modified elements, compare:

1. **Element type**: Cannot change (delete + create instead)
2. **Class attribute**: Parse into individual classes, diff sets
3. **Other attributes**: Direct comparison (`src`, `href`, etc.)
4. **Children**: Recursive diff for containers

### Text Content Diffing

Within a shape containing text:

1. Match `<P>` elements by position (order matters)
2. Within each `<P>`, match `<T>` elements by position
3. Compare content and classes of matched `<T>` elements

---

## Operation Ordering

### The Index Shifting Problem

When multiple text operations occur in the same shape, earlier operations shift indices for later ones:

```
Original: "Hello world today"
           0     6     12   17

Delete "world " (6-12):
Result:   "Hello today"
           0     6    11

The word "today" moved from index 12 to index 6!
```

### Solution: Reverse Index Order

**Within each shape, process operations from highest startIndex to lowest.**

This ensures earlier indices remain valid because we only modify content after them.

```python
# Pseudocode
operations = collect_all_operations(shape)
operations.sort(key=lambda op: op.start_index, reverse=True)

for op in operations:
    execute(op)  # Indices are still valid
```

### Operation Categories and Order

Within a single shape, group and order operations:

```
1. Delete operations (highest index first)
2. Insert operations (highest index first)
3. Style operations (any order - indices computed fresh)
```

### Cross-Shape Operations

Operations on different shapes are independent and can be parallelized. Order only matters within a single shape's text content.

### Slide-Level Operations

For slide ordering and deletion, process in reverse order:

```python
# Delete slides from end to start
slides_to_delete.sort(key=lambda s: s.index, reverse=True)
```

---

## Operation Ordering (Topological Sort)

The reconciler **must** order operations to satisfy dependencies. This is critical for correctness.

### Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPERATION ORDERING                           │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 1: Structural Creates (objects that others depend on)   │
│    1. createSlide                                               │
│    2. createShape, createImage, createLine, createTable,        │
│       createVideo, createSheetsChart                            │
│    3. duplicateObject (creates copy of existing)                │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 2: Content Operations (require shapes to exist)          │
│    4. insertText (into shapes/tables)                           │
│    5. insertTableRows, insertTableColumns                       │
│    6. mergeTableCells, unmergeTableCells                        │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 3: Style Updates (require content to exist)              │
│    7. updateTextStyle, updateParagraphStyle                     │
│    8. updateShapeProperties, updateImageProperties,             │
│       updateLineProperties, updateVideoProperties               │
│    9. updateTableCellProperties, updateTableBorderProperties    │
│   10. updatePageElementTransform                                │
│   11. updatePageProperties, updateSlideProperties               │
│   12. updateLineCategory                                        │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 4: Grouping (requires all children to exist)             │
│   13. groupObjects                                              │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 5: Imperative Actions (from <Actions> section)           │
│   14. updatePageElementsZOrder (BringToFront, SendToBack, etc.) │
│   15. rerouteLine                                               │
│   16. refreshSheetsChart                                        │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 6: Layout Operations                                     │
│   17. updateSlidesPosition                                      │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 7: Deletions (reverse order, ungroup before delete)      │
│   18. ungroupObjects                                            │
│   19. deleteText (highest index first within each shape)        │
│   20. deleteParagraphBullets                                    │
│   21. deleteTableRow, deleteTableColumn (highest index first)   │
│   22. deleteObject (shapes, then slides)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Ordering Rules

#### Phase 1: Creates
```python
# Order: Slides first, then elements within slides
creates = []
creates.extend(sorted(slide_creates, key=lambda s: s.insertion_index))
creates.extend(shape_creates)  # Order doesn't matter within a slide
creates.extend(duplicate_creates)  # After originals exist
```

#### Phase 2-3: Text and Styling
```python
# Within each shape, process text operations by descending index
for shape_id in shapes_with_text_changes:
    ops = get_text_operations(shape_id)
    ops.sort(key=lambda op: op.start_index, reverse=True)

    # Deletes first, then inserts, then styles
    for op in ops:
        if op.type == 'delete':
            yield op
    for op in ops:
        if op.type == 'insert':
            yield op
    for op in ops:
        if op.type == 'style':
            yield op
```

#### Phase 4: Grouping
```python
# Groups must be created after all children exist
# Process in dependency order (nested groups: inner first)
groups.sort(key=lambda g: g.nesting_depth)
for group in groups:
    yield GroupObjectsRequest(group.id, group.children)
```

#### Phase 6: Deletions
```python
# Ungroup before deleting group members
for group_id in groups_to_ungroup:
    yield UngroupObjectsRequest(group_id)

# Delete in reverse z-order / creation order
for element_id in reversed(elements_to_delete):
    yield DeleteObjectRequest(element_id)

# Delete slides last, in reverse order
for slide_id in reversed(slides_to_delete):
    yield DeleteObjectRequest(slide_id)
```

### Example: Complex Operation Sequence

Given these edits:
1. Create new slide
2. Add TextBox with styled text
3. Duplicate an existing shape
4. Group the new elements
5. Delete an old shape

Generated request order:
```json
{
  "requests": [
    {"createSlide": {"objectId": "new_slide"}},
    {"createShape": {"objectId": "new_textbox", "shapeType": "TEXT_BOX", ...}},
    {"duplicateObject": {"objectId": "existing_shape"}},
    {"insertText": {"objectId": "new_textbox", "text": "Hello World"}},
    {"updateTextStyle": {"objectId": "new_textbox", ...}},
    {"groupObjects": {"groupObjectId": "new_group", "childrenObjectIds": ["new_textbox", "existing_shape_copy"]}},
    {"deleteObject": {"objectId": "old_shape"}}
  ]
}
```

---

## Actions Processing

Actions represent **imperative operations** that are processed after all declarative changes. They are specified in an `<Actions>` section within slides.

### Why Actions Are Special

Unlike declarative element properties (fill color, position, etc.), actions represent operations that:
- Are not idempotent (applying twice has no additional effect)
- Represent commands, not state
- Cannot be meaningfully diffed

### Supported Actions

| SML Action | API Request | Description |
|------------|-------------|-------------|
| `<BringToFront target="id"/>` | `updatePageElementsZOrder` | Move element to front of z-order |
| `<BringForward target="id"/>` | `updatePageElementsZOrder` | Move element forward one level |
| `<SendBackward target="id"/>` | `updatePageElementsZOrder` | Move element backward one level |
| `<SendToBack target="id"/>` | `updatePageElementsZOrder` | Move element to back of z-order |
| `<RerouteLine target="id"/>` | `rerouteLine` | Reroute connector to closest points |
| `<RefreshChart target="id"/>` | `refreshSheetsChart` | Refresh embedded Sheets chart |

### Z-Order Actions

```html
<Actions>
  <BringToFront target="box1"/>
</Actions>
```

Generates:

```json
{
  "updatePageElementsZOrder": {
    "pageElementObjectIds": ["box1"],
    "operation": "BRING_TO_FRONT"
  }
}
```

**Multiple targets:** Z-order actions can target multiple elements (space-separated):

```html
<BringToFront target="box1 box2 box3"/>
```

```json
{
  "updatePageElementsZOrder": {
    "pageElementObjectIds": ["box1", "box2", "box3"],
    "operation": "BRING_TO_FRONT"
  }
}
```

### Line Rerouting

Reroutes a connector line to connect at the closest connection sites on connected shapes.

```html
<Actions>
  <RerouteLine target="connector1"/>
</Actions>
```

```json
{
  "rerouteLine": {
    "objectId": "connector1"
  }
}
```

**Note:** Only works on lines with a category indicating they are connectors (bent or curved connectors, not straight lines).

### Chart Refresh

Refreshes an embedded Google Sheets chart with the latest data.

```html
<Actions>
  <RefreshChart target="chart1"/>
</Actions>
```

```json
{
  "refreshSheetsChart": {
    "objectId": "chart1"
  }
}
```

**Note:** Requires appropriate OAuth scopes (`spreadsheets.readonly`, `spreadsheets`, `drive.readonly`, or `drive`).

### Actions Ordering

Actions within an `<Actions>` section are processed in document order. If order matters (e.g., multiple z-order operations), specify them in the desired sequence:

```html
<Actions>
  <BringToFront target="box1"/>  <!-- First: bring box1 to front -->
  <BringForward target="box2"/>  <!-- Then: bring box2 forward (now behind box1) -->
</Actions>
```

### Actions vs Declarative Diff

**Important:** Actions are **not** diffed like declarative properties. If an `<Actions>` section is present in the edited SML, all actions in it are executed. Actions are not "removed" - they are simply present or absent.

---

## Request Generation by Change Type

### Slide Operations

#### Create Slide

```html
<!-- Added in edited SML -->
<Slide id="new_slide_uuid" layout="layout_1">
  ...
</Slide>
```

```json
{
  "createSlide": {
    "objectId": "new_slide_uuid",
    "insertionIndex": 2,
    "slideLayoutReference": {
      "layoutId": "layout_1"
    }
  }
}
```

#### Delete Slide

```html
<!-- Removed from edited SML -->
<Slide id="slide_to_delete">
```

```json
{
  "deleteObject": {
    "objectId": "slide_to_delete"
  }
}
```

#### Reorder Slides

```html
<!-- Slide moved to different position -->
<Slide id="slide_3">  <!-- Was at index 2, now at index 0 -->
```

```json
{
  "updateSlidesPosition": {
    "slideObjectIds": ["slide_3"],
    "insertionIndex": 0
  }
}
```

#### Update Slide Properties

```html
<!-- Changed -->
<Slide id="slide_1" class="bg-#3b82f6">  <!-- Was bg-#ffffff -->
```

```json
{
  "updatePageProperties": {
    "objectId": "slide_1",
    "pageProperties": {
      "pageBackgroundFill": {
        "solidFill": {
          "color": { "rgbColor": { "red": 0.26, "green": 0.52, "blue": 0.96 }}
        }
      }
    },
    "fields": "pageBackgroundFill.solidFill.color"
  }
}
```

---

### Shape Operations

#### Create Shape

```html
<!-- Added in edited SML -->
<TextBox id="new_textbox_uuid" class="x-100 y-100 w-400 h-50">
  <P range="0-6"><T range="0-5">Hello</T></P>
</TextBox>
```

Generates multiple requests:

```json
[
  {
    "createShape": {
      "objectId": "new_textbox_uuid",
      "shapeType": "TEXT_BOX",
      "elementProperties": {
        "pageObjectId": "slide_1",
        "size": {
          "width": { "magnitude": 400, "unit": "PT" },
          "height": { "magnitude": 50, "unit": "PT" }
        },
        "transform": {
          "scaleX": 1, "scaleY": 1,
          "translateX": 100, "translateY": 100,
          "unit": "PT"
        }
      }
    }
  },
  {
    "insertText": {
      "objectId": "new_textbox_uuid",
      "insertionIndex": 0,
      "text": "Hello"
    }
  }
]
```

#### Delete Shape

```html
<!-- Removed from edited SML -->
<Rect id="shape_to_delete" .../>
```

```json
{
  "deleteObject": {
    "objectId": "shape_to_delete"
  }
}
```

#### Update Shape Transform (Position/Size/Rotation)

```html
<!-- Changed position -->
<TextBox id="tb1" class="x-200 y-150 w-400 h-50">  <!-- Was x-100 y-100 -->
```

```json
{
  "updatePageElementTransform": {
    "objectId": "tb1",
    "applyMode": "ABSOLUTE",
    "transform": {
      "scaleX": 1, "scaleY": 1,
      "shearX": 0, "shearY": 0,
      "translateX": 200, "translateY": 150,
      "unit": "PT"
    }
  }
}
```

#### Update Shape Properties (Fill/Stroke/Shadow)

```html
<!-- Changed fill color -->
<Rect id="rect1" class="fill-#ef4444">  <!-- Was fill-#3b82f6 -->
```

```json
{
  "updateShapeProperties": {
    "objectId": "rect1",
    "shapeProperties": {
      "shapeBackgroundFill": {
        "solidFill": {
          "color": { "rgbColor": { "red": 0.96, "green": 0.26, "blue": 0.21 }}
        }
      }
    },
    "fields": "shapeBackgroundFill.solidFill.color"
  }
}
```

#### Duplicate Element

```html
<!-- Original -->
<TextBox id="template" class="x-50 y-100 w-200 h-100 fill-#3b82f6">
  <P><T>Template</T></P>
</TextBox>

<!-- Duplicate with overrides -->
<TextBox id="copy_1" duplicate-of="template" class="x-280 y-100 fill-#22c55e">
  <P><T>Copy 1</T></P>
</TextBox>
```

Generates multiple requests:

```json
[
  {
    "duplicateObject": {
      "objectId": "template",
      "objectIds": {
        "template": "copy_1"
      }
    }
  },
  {
    "updateShapeProperties": {
      "objectId": "copy_1",
      "shapeProperties": {
        "shapeBackgroundFill": {
          "solidFill": {
            "color": { "rgbColor": { "red": 0.13, "green": 0.77, "blue": 0.37 }}
          }
        }
      },
      "fields": "shapeBackgroundFill.solidFill.color"
    }
  },
  {
    "updatePageElementTransform": {
      "objectId": "copy_1",
      "applyMode": "ABSOLUTE",
      "transform": {
        "scaleX": 1, "scaleY": 1,
        "translateX": 280, "translateY": 100,
        "unit": "PT"
      }
    }
  },
  {
    "deleteText": {
      "objectId": "copy_1",
      "textRange": { "type": "ALL" }
    }
  },
  {
    "insertText": {
      "objectId": "copy_1",
      "insertionIndex": 0,
      "text": "Copy 1"
    }
  }
]
```

#### Duplicate Detection

An element is a duplicate if:
1. It has a `duplicate-of` attribute pointing to an existing element ID
2. The `duplicate-of` target exists in the **original** SML (not another new element)

#### Duplicate Processing Rules

| Scenario | Action |
|----------|--------|
| `duplicate-of` only, no class overrides | Just `duplicateObject` |
| `duplicate-of` with class overrides | `duplicateObject` + `updateShapeProperties` / `updatePageElementTransform` |
| `duplicate-of` with new content | `duplicateObject` + `deleteText` + `insertText` |
| `duplicate-of` with content omitted | Copy content from source (no text operations needed) |

#### Group Duplication

When duplicating a group, child elements get auto-generated IDs:

```html
<Group id="original_group" class="x-50 y-100">
  <Rect id="child_1" .../>
  <TextBox id="child_2" .../>
</Group>

<!-- Duplicate -->
<Group id="group_copy" duplicate-of="original_group" class="x-300 y-100"/>
```

```json
{
  "duplicateObject": {
    "objectId": "original_group",
    "objectIds": {
      "original_group": "group_copy",
      "child_1": "group_copy_child_1",
      "child_2": "group_copy_child_2"
    }
  }
}
```

**Note:** The `objectIds` map must include entries for all nested objects. The reconciler generates deterministic IDs for children based on the group's new ID.

---

### Text Operations

#### Delete Text Run

```html
<!-- Original -->
<P range="0-18">
  <T range="0-6">Hello </T>
  <T range="6-12" class="bold">world </T>  <!-- DELETED -->
  <T range="12-17">today</T>
</P>

<!-- Edited -->
<P range="0-18">
  <T range="0-6">Hello </T>
  <T range="12-17">today</T>
</P>
```

Use the **original range** for deletion:

```json
{
  "deleteText": {
    "objectId": "shape_id",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 6,
      "endIndex": 12
    }
  }
}
```

#### Insert Text Run

```html
<!-- Original -->
<P range="0-12">
  <T range="0-6">Hello </T>
  <T range="6-11">world</T>
</P>

<!-- Edited (new T added) -->
<P range="0-12">
  <T range="0-6">Hello </T>
  <T class="italic">beautiful </T>  <!-- NEW - no range -->
  <T range="6-11">world</T>
</P>
```

Insert at the position of the preceding element's end:

```json
[
  {
    "insertText": {
      "objectId": "shape_id",
      "insertionIndex": 6,
      "text": "beautiful "
    }
  },
  {
    "updateTextStyle": {
      "objectId": "shape_id",
      "textRange": {
        "type": "FIXED_RANGE",
        "startIndex": 6,
        "endIndex": 16
      },
      "style": { "italic": true },
      "fields": "italic"
    }
  }
]
```

#### Modify Text Run Content

```html
<!-- Original -->
<T range="6-11" class="bold">world</T>

<!-- Edited -->
<T range="6-11" class="bold">universe</T>  <!-- Content changed -->
```

Delete original, insert new, apply style:

```json
[
  {
    "deleteText": {
      "objectId": "shape_id",
      "textRange": { "type": "FIXED_RANGE", "startIndex": 6, "endIndex": 11 }
    }
  },
  {
    "insertText": {
      "objectId": "shape_id",
      "insertionIndex": 6,
      "text": "universe"
    }
  },
  {
    "updateTextStyle": {
      "objectId": "shape_id",
      "textRange": { "type": "FIXED_RANGE", "startIndex": 6, "endIndex": 14 },
      "style": { "bold": true },
      "fields": "bold"
    }
  }
]
```

#### Modify Text Run Style Only

```html
<!-- Original -->
<T range="6-11" class="bold">world</T>

<!-- Edited -->
<T range="6-11" class="bold italic">world</T>  <!-- Added italic -->
```

Use original range (content unchanged):

```json
{
  "updateTextStyle": {
    "objectId": "shape_id",
    "textRange": { "type": "FIXED_RANGE", "startIndex": 6, "endIndex": 11 },
    "style": { "italic": true },
    "fields": "italic"
  }
}
```

#### Delete Paragraph

```html
<!-- Original -->
<P range="0-12">...</P>
<P range="12-25">...</P>  <!-- DELETED -->
<P range="25-40">...</P>

<!-- Edited -->
<P range="0-12">...</P>
<P range="25-40">...</P>
```

Delete the paragraph's full range (including `\n`):

```json
{
  "deleteText": {
    "objectId": "shape_id",
    "textRange": { "type": "FIXED_RANGE", "startIndex": 12, "endIndex": 25 }
  }
}
```

#### Add Paragraph

```html
<!-- Original -->
<P range="0-12">...</P>

<!-- Edited -->
<P range="0-12">...</P>
<P><T>New paragraph</T></P>  <!-- NEW -->
```

Insert at end of previous paragraph (after `\n`):

```json
[
  {
    "insertText": {
      "objectId": "shape_id",
      "insertionIndex": 12,
      "text": "New paragraph\n"
    }
  }
]
```

---

### Paragraph Style Operations

#### Update Paragraph Style

```html
<!-- Original -->
<P range="0-12" class="text-left">...</P>

<!-- Edited -->
<P range="0-12" class="text-center">...</P>
```

```json
{
  "updateParagraphStyle": {
    "objectId": "shape_id",
    "textRange": { "type": "FIXED_RANGE", "startIndex": 0, "endIndex": 12 },
    "paragraphStyle": {
      "alignment": "CENTER"
    },
    "fields": "alignment"
  }
}
```

#### Add Bullets

```html
<!-- Original -->
<P range="0-12">...</P>

<!-- Edited -->
<P range="0-12" class="bullet bullet-disc">...</P>
```

```json
{
  "createParagraphBullets": {
    "objectId": "shape_id",
    "textRange": { "type": "FIXED_RANGE", "startIndex": 0, "endIndex": 12 },
    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
  }
}
```

#### Remove Bullets

```html
<!-- Original -->
<P range="0-12" class="bullet bullet-disc">...</P>

<!-- Edited -->
<P range="0-12">...</P>
```

```json
{
  "deleteParagraphBullets": {
    "objectId": "shape_id",
    "textRange": { "type": "FIXED_RANGE", "startIndex": 0, "endIndex": 12 }
  }
}
```

---

### Image Operations

#### Create Image

```html
<Image id="new_img_uuid" class="x-100 y-100 w-300 h-200" src="https://example.com/image.png"/>
```

```json
{
  "createImage": {
    "objectId": "new_img_uuid",
    "url": "https://example.com/image.png",
    "elementProperties": {
      "pageObjectId": "slide_1",
      "size": { "width": { "magnitude": 300, "unit": "PT" }, "height": { "magnitude": 200, "unit": "PT" }},
      "transform": { "scaleX": 1, "scaleY": 1, "translateX": 100, "translateY": 200, "unit": "PT" }
    }
  }
}
```

#### Replace Image

```html
<!-- Original -->
<Image id="img1" src="https://old-url.com/image.png"/>

<!-- Edited -->
<Image id="img1" src="https://new-url.com/image.png"/>
```

```json
{
  "replaceImage": {
    "imageObjectId": "img1",
    "url": "https://new-url.com/image.png",
    "imageReplaceMethod": "CENTER_INSIDE"
  }
}
```

---

### Line Operations

#### Create Line

```html
<Line id="new_line_uuid" class="line-straight x1-100 y1-100 x2-300 y2-200 stroke-#6b7280 stroke-w-2"/>
```

```json
{
  "createLine": {
    "objectId": "new_line_uuid",
    "lineCategory": "STRAIGHT",
    "elementProperties": {
      "pageObjectId": "slide_1",
      "size": { "width": { "magnitude": 200, "unit": "PT" }, "height": { "magnitude": 100, "unit": "PT" }},
      "transform": { "scaleX": 1, "scaleY": 1, "translateX": 100, "translateY": 100, "unit": "PT" }
    }
  }
}
```

#### Update Line Properties

```html
<!-- Changed arrow style -->
<Line id="line1" class="arrow-end-fill">  <!-- Was arrow-end-none -->
```

```json
{
  "updateLineProperties": {
    "objectId": "line1",
    "lineProperties": {
      "endArrow": "FILL_ARROW"
    },
    "fields": "endArrow"
  }
}
```

#### Update Line Category

When a line's category changes (e.g., from straight to bent connector):

```html
<!-- Original -->
<Line id="line1" class="line-straight x1-100 y1-100 x2-300 y2-200"/>

<!-- Edited -->
<Line id="line1" class="line-bent-2 x1-100 y1-100 x2-300 y2-200"/>
```

```json
{
  "updateLineCategory": {
    "objectId": "line1",
    "lineCategory": "BENT"
  }
}
```

| Line Class Pattern | API lineCategory |
|--------------------|------------------|
| `line-straight`, `line-straight-1` | `STRAIGHT` |
| `line-bent-2`, `line-bent-3`, `line-bent-4`, `line-bent-5` | `BENT` |
| `line-curved-2`, `line-curved-3`, `line-curved-4`, `line-curved-5` | `CURVED` |

**Note:** Only connector lines can have their category updated. The exact line type within the category is determined automatically based on the connection points.

---

### Table Operations

Tables use **explicit row and column indices** (`r` and `c` attributes) on cells for unambiguous addressing.

#### Create Table

```html
<Table id="new_table_uuid" class="x-72 y-200 w-576 h-200" rows="3" cols="4">
  <Row r="0">
    <Cell r="0" c="0">Header 1</Cell>
    <Cell r="0" c="1">Header 2</Cell>
    ...
  </Row>
  ...
</Table>
```

```json
{
  "createTable": {
    "objectId": "new_table_uuid",
    "rows": 3,
    "columns": 4,
    "elementProperties": {
      "pageObjectId": "slide_1",
      "size": { "width": { "magnitude": 576, "unit": "PT" }, "height": { "magnitude": 200, "unit": "PT" }},
      "transform": { "translateX": 72, "translateY": 200, "unit": "PT" }
    }
  }
}
```

#### Insert Table Row

When a new row is detected (row with `r` index not in original):

```html
<!-- New row added at index 2 -->
<Row r="2">
  <Cell r="2" c="0">New data</Cell>
  ...
</Row>
```

```json
{
  "insertTableRows": {
    "tableObjectId": "table1",
    "cellLocation": { "rowIndex": 1 },
    "insertBelow": true,
    "number": 1
  }
}
```

#### Delete Table Row

When a row is removed (row with `r` index in original but not in edited):

```json
{
  "deleteTableRow": {
    "tableObjectId": "table1",
    "cellLocation": { "rowIndex": 2 }
  }
}
```

**Important:** Delete rows in reverse order (highest index first) to avoid index shifting.

#### Update Table Cell

Cells are matched by their explicit `r` and `c` attributes:

```html
<!-- Original -->
<Cell r="0" c="0" class="fill-#ffffff">Data</Cell>

<!-- Edited -->
<Cell r="0" c="0" class="fill-#fef3c7">Data</Cell>
```

```json
{
  "updateTableCellProperties": {
    "objectId": "table1",
    "tableRange": {
      "location": { "rowIndex": 0, "columnIndex": 0 },
      "rowSpan": 1,
      "columnSpan": 1
    },
    "tableCellProperties": {
      "tableCellBackgroundFill": {
        "solidFill": {
          "color": { "rgbColor": { "red": 1, "green": 0.98, "blue": 0.8 }}
        }
      }
    },
    "fields": "tableCellBackgroundFill.solidFill.color"
  }
}
```

#### Merge Table Cells

When a cell gains `colspan` or `rowspan` attributes:

```html
<!-- Original -->
<Cell r="0" c="0">A</Cell>
<Cell r="0" c="1">B</Cell>

<!-- Edited (cells merged) -->
<Cell r="0" c="0" colspan="2">A + B</Cell>
<!-- r="0" c="1" is now covered -->
```

```json
{
  "mergeTableCells": {
    "objectId": "table1",
    "tableRange": {
      "location": { "rowIndex": 0, "columnIndex": 0 },
      "rowSpan": 1,
      "columnSpan": 2
    }
  }
}
```

#### Unmerge Table Cells

When a cell loses `colspan` or `rowspan` attributes:

```html
<!-- Original -->
<Cell r="0" c="0" colspan="2">Merged</Cell>

<!-- Edited (cells unmerged) -->
<Cell r="0" c="0">A</Cell>
<Cell r="0" c="1">B</Cell>
```

```json
{
  "unmergeTableCells": {
    "objectId": "table1",
    "tableRange": {
      "location": { "rowIndex": 0, "columnIndex": 0 },
      "rowSpan": 1,
      "columnSpan": 2
    }
  }
}
```

**Note:** After unmerging, the original merged content remains in the origin cell (r=0, c=0).

---

### Group Operations

#### Create Group

```html
<Group id="new_group_uuid">
  <Rect id="rect1" .../>
  <TextBox id="tb1" .../>
</Group>
```

First create children, then group:

```json
{
  "groupObjects": {
    "groupObjectId": "new_group_uuid",
    "childrenObjectIds": ["rect1", "tb1"]
  }
}
```

#### Ungroup

```html
<!-- Group removed, children now siblings -->
```

```json
{
  "ungroupObjects": {
    "objectIds": ["group1"]
  }
}
```

---

### Video Operations

#### Create Video

```html
<Video id="new_video_uuid" class="x-100 y-100 w-480 h-270" src="youtube:dQw4w9WgXcQ"/>
```

```json
{
  "createVideo": {
    "objectId": "new_video_uuid",
    "source": "YOUTUBE",
    "id": "dQw4w9WgXcQ",
    "elementProperties": {
      "pageObjectId": "slide_1",
      "size": { "width": { "magnitude": 480, "unit": "PT" }, "height": { "magnitude": 270, "unit": "PT" }},
      "transform": { "translateX": 100, "translateY": 100, "unit": "PT" }
    }
  }
}
```

---

### Z-Order Operations

```html
<Rect id="rect1" class="z-front">  <!-- Bring to front -->
```

```json
{
  "updatePageElementsZOrder": {
    "pageElementObjectIds": ["rect1"],
    "operation": "BRING_TO_FRONT"
  }
}
```

---

## Property State Semantics

### Understanding Property States

The Google Slides API uses `PropertyState` to indicate how a property value should be interpreted:

| State | API Value | Meaning |
|-------|-----------|---------|
| Rendered | `RENDERED` | Property has an explicit value |
| Not Rendered | `NOT_RENDERED` | Property is explicitly turned off/transparent |
| Inherit | `INHERIT` | Property inherits from parent (placeholder, master, default) |

### SML Class Mapping

| SML Class | PropertyState | Description |
|-----------|---------------|-------------|
| `fill-#rrggbb` | `RENDERED` | Explicit color value |
| `fill-theme-{name}` | `RENDERED` | Explicit theme color reference |
| `fill-none` | `NOT_RENDERED` | Explicitly no fill (transparent) |
| `fill-inherit` | `INHERIT` | Inherit from parent/default |
| (class removed) | `INHERIT` | Treated as `fill-inherit` |

### Class Removal Behavior

When a styling class is **removed** during editing (present in original, absent in edited), the reconciler treats this as a request to **inherit** the property value:

```html
<!-- Original -->
<Rect id="box" class="x-100 y-100 w-200 h-100 fill-#3b82f6 stroke-#1e3a8a"/>

<!-- Edited (fill class removed) -->
<Rect id="box" class="x-100 y-100 w-200 h-100 stroke-#1e3a8a"/>
```

Generated request:
```json
{
  "updateShapeProperties": {
    "objectId": "box",
    "shapeProperties": {
      "shapeBackgroundFill": {
        "propertyState": "INHERIT"
      }
    },
    "fields": "shapeBackgroundFill.propertyState"
  }
}
```

### Explicit Property States

To explicitly control property state, use the appropriate class:

```html
<!-- Explicitly no fill (transparent) -->
<Rect class="fill-none"/>

<!-- Explicitly inherit from parent -->
<Rect class="fill-inherit"/>

<!-- Same for stroke -->
<Rect class="stroke-none"/>      <!-- No outline -->
<Rect class="stroke-inherit"/>   <!-- Inherit outline -->

<!-- Same for shadow -->
<Rect class="shadow-none"/>      <!-- No shadow -->
<Rect class="shadow-inherit"/>   <!-- Inherit shadow -->
```

### Property State Decision Matrix

| Original | Edited | Action |
|----------|--------|--------|
| `fill-#aaa` | `fill-#bbb` | Update to new color (`RENDERED`) |
| `fill-#aaa` | `fill-none` | Set `NOT_RENDERED` |
| `fill-#aaa` | `fill-inherit` | Set `INHERIT` |
| `fill-#aaa` | (removed) | Set `INHERIT` (same as `fill-inherit`) |
| `fill-none` | `fill-#aaa` | Update to color (`RENDERED`) |
| `fill-inherit` | `fill-#aaa` | Update to color (`RENDERED`) |
| (absent) | `fill-#aaa` | Update to color (`RENDERED`) |

---

## Field Mask Computation

### Purpose

The `fields` parameter in update requests specifies which properties to modify. This prevents accidentally overwriting unmodified properties.

### Computation from Class Diff

Compare classes between original and edited:

```html
<!-- Original -->
<Rect class="fill-#3b82f6 stroke-w-2 shadow-md">

<!-- Edited -->
<Rect class="fill-#ef4444 stroke-w-2 shadow-lg">
```

Changed classes:
- `fill-#3b82f6` → `fill-#ef4444` (fill color changed)
- `shadow-md` → `shadow-lg` (shadow changed)
- `stroke-w-2` (unchanged)

Field mask: `"shapeBackgroundFill.solidFill.color,shadow"`

### Class-to-Field Mapping

| Class Pattern | API Field Path |
|---------------|----------------|
| `fill-#rrggbb` | `shapeBackgroundFill.solidFill.color` |
| `fill-#rrggbb/{opacity}` | `shapeBackgroundFill.solidFill.color,shapeBackgroundFill.solidFill.alpha` |
| `fill-theme-{name}` | `shapeBackgroundFill.solidFill.color` (with themeColor) |
| `fill-none` | `shapeBackgroundFill.propertyState` → `NOT_RENDERED` |
| `fill-inherit` | `shapeBackgroundFill.propertyState` → `INHERIT` |
| `stroke-#rrggbb` | `outline.outlineFill.solidFill.color` |
| `stroke-theme-{name}` | `outline.outlineFill.solidFill.color` (with themeColor) |
| `stroke-none` | `outline.propertyState` → `NOT_RENDERED` |
| `stroke-inherit` | `outline.propertyState` → `INHERIT` |
| `stroke-w-{n}` | `outline.weight` |
| `stroke-{dash}` | `outline.dashStyle` |
| `shadow-*` | `shadow` |
| `shadow-none` | `shadow.propertyState` → `NOT_RENDERED` |
| `shadow-inherit` | `shadow.propertyState` → `INHERIT` |
| `bold` | `bold` |
| `italic` | `italic` |
| `underline` | `underline` |
| `text-size-{n}` | `fontSize` |
| `font-family-{name}` | `fontFamily` |
| `font-weight-{weight}` | `weightedFontFamily.weight` |
| `text-color-#rrggbb` | `foregroundColor` |
| `text-color-theme-{name}` | `foregroundColor` (with themeColor) |
| `text-align-left/center/right` | `alignment` |
| `leading-{n}` | `lineSpacing` |
| `space-above-{n}` | `spaceAbove` |
| `space-below-{n}` | `spaceBelow` |

### Only Include Changed Fields

```python
# Pseudocode
def compute_field_mask(original_classes, edited_classes):
    original_set = parse_classes(original_classes)
    edited_set = parse_classes(edited_classes)

    changed = original_set.symmetric_difference(edited_set)

    fields = []
    for cls in changed:
        field = CLASS_TO_FIELD_MAP.get(cls.property)
        if field:
            fields.append(field)

    return ",".join(fields)
```

---

## Editing Constraints

### Rules for SML Authors

These constraints ensure reliable diff-to-request conversion:

| Constraint | Reason |
|------------|--------|
| **Never modify `range` attributes** | Used for text index calculations |
| **Never modify `id` attributes** | Used to match elements between versions |
| **All text in explicit `<P><T>` structure** | No bare text in shapes or paragraphs |
| **Each `<P>` must contain `<T>` children** | No bare text allowed |
| **No newlines in text content** | Create new `<P>` instead of `\n` |
| **Use UUIDs for new element IDs** | Prevent collisions |
| **Use hex colors (`#rrggbb`)** | No named palette colors like `blue-500` |
| **Use `fill-none` to remove fill** | Don't just remove the class |

### Valid Edits

| Edit Type | Valid | Example |
|-----------|-------|---------|
| Change text content | ✅ | `<T>world</T>` → `<T>universe</T>` |
| Change classes | ✅ | `class="bold"` → `class="bold italic"` |
| Add element | ✅ | Add new `<TextBox id="uuid">` |
| Delete element | ✅ | Remove entire element |
| Add `<T>` | ✅ | Insert new `<T>` element |
| Delete `<T>` | ✅ | Remove `<T>` element |
| Add `<P>` | ✅ | Insert new `<P>` element |
| Delete `<P>` | ✅ | Remove `<P>` element |
| Duplicate element | ✅ | `<Rect id="copy" duplicate-of="original"/>` |
| Remove style class | ✅ | Treated as `*-inherit` (reset to default) |
| Change `id` | ❌ | Breaks element matching |
| Change `range` | ❌ | Breaks index calculation |
| Add `\n` in text | ❌ | Create `<P>` instead |
| Bare text in shape | ❌ | Must use `<P><T>text</T></P>` |
| Named palette colors | ❌ | Use hex `#rrggbb` or `theme-*` |

### Invalid Edit Examples

```html
<!-- ❌ WRONG: Changed id -->
<TextBox id="new_id">  <!-- Was id="old_id" -->

<!-- ❌ WRONG: Changed range -->
<T range="0-10">Hello</T>  <!-- Range doesn't match content -->

<!-- ❌ WRONG: Bare text in TextBox -->
<TextBox>Hello world</TextBox>

<!-- ❌ WRONG: Bare text in P -->
<P>Hello world</P>

<!-- ❌ WRONG: Newline in content -->
<T>Hello\nWorld</T>

<!-- ❌ WRONG: Named palette color -->
<Rect class="fill-blue-500"/>

<!-- ✅ CORRECT: Explicit structure -->
<TextBox>
  <P><T>Hello</T></P>
  <P><T>World</T></P>
</TextBox>

<!-- ✅ CORRECT: Hex color -->
<Rect class="fill-#3b82f6"/>

<!-- ✅ CORRECT: Theme color -->
<Rect class="fill-theme-accent1"/>
```

---

## Error Handling

### Validation Errors

Before generating requests, validate:

| Check | Error |
|-------|-------|
| All IDs unique | `DUPLICATE_ID` |
| All `<P>` have `<T>` children | `BARE_TEXT_IN_PARAGRAPH` |
| `range` attributes unchanged | `RANGE_MODIFIED` |
| `id` attributes unchanged (existing) | `ID_MODIFIED` |
| New elements have valid UUIDs | `INVALID_NEW_ID` |

### API Error Recovery

If `batchUpdate` fails:

1. **Partial failure**: Some requests may have succeeded
2. **Must re-fetch**: SML state is now indeterminate
3. **Report error**: Include request index and error message

```json
{
  "error": {
    "code": 400,
    "message": "Invalid requests[2].updateTextStyle: startIndex out of range",
    "status": "INVALID_ARGUMENT"
  }
}
```

### Conflict Detection

If the presentation was modified between fetch and update:

1. API may return `ABORTED` or `CONFLICT` error
2. Re-fetch and re-apply user edits (merge)
3. Or discard and re-fetch

---

## API Limitations

The Google Slides API has several limitations that affect what SML can represent and modify. Understanding these limitations is critical for setting correct expectations.

### Features Not Supported by API

The following features exist in the Google Slides UI but are **not available through the API**:

| Feature | Status | Impact on SML |
|---------|--------|---------------|
| **Animations** | ❌ Not supported | Cannot create, read, or modify element animations |
| **Transitions** | ❌ Not supported | Slide transitions cannot be set or read |
| **Audio elements** | ❌ Not supported | Audio cannot be added or manipulated |
| **Comments** | ❌ Not supported | Presentation comments are not accessible |
| **Themes** | ❌ Limited | Cannot create new themes; can only reference existing masters/layouts |
| **Presenter notes formatting** | ⚠️ Limited | Basic text only; limited styling support |

### Cannot Create Masters or Layouts

The API cannot create new master slides or layouts. SML can only:
- **Reference existing** masters/layouts by ID
- **Modify elements** on existing masters/layouts
- **Read** master/layout structure for serialization

```html
<!-- ✅ VALID: Reference existing layout -->
<Slide id="new_slide" layout="existing_layout_id"/>

<!-- ❌ INVALID: Cannot create new master via API -->
<Master id="new_master">...</Master>  <!-- Will fail at batchUpdate -->
```

**Reconciler behavior:** If SML contains a new `<Master>` or `<Layout>` element (ID not in original), the reconciler should **reject** with a clear error rather than attempting to create it.

### Read-Only Image Properties

The following image properties can be **read** from the API but **cannot be modified**:

| Property | SML Class | API Behavior |
|----------|-----------|--------------|
| Brightness | `brightness-*` | Read-only; changes ignored |
| Contrast | `contrast-*` | Read-only; changes ignored |
| Transparency | `opacity-*` | Read-only; changes ignored |
| Crop | `crop-*` | Read-only; changes ignored |
| Recolor | `recolor-*` | Read-only; changes ignored |

**Reconciler behavior:** If these properties change between original and edited SML, the reconciler should:
1. **Warn** the user that changes will be ignored
2. **Skip** generating update requests for these properties
3. **Not fail** the entire operation

### Limited Gradient Support

Gradient fills have limited write support:

| Element Type | Gradient Support |
|--------------|------------------|
| Page backgrounds | ⚠️ Partial - can set linear gradients |
| Shape fills | ❌ Read-only - cannot set via API |
| Text backgrounds | ❌ Not supported |

**Reconciler behavior:** Changes to gradient classes on shapes should generate a warning, not a request.

### Table Limitations

| Operation | Support |
|-----------|---------|
| Create table | ✅ Supported |
| Insert/delete rows | ✅ Supported |
| Insert/delete columns | ✅ Supported |
| Merge cells | ✅ Supported |
| Unmerge cells | ✅ Supported |
| Cell text content | ✅ Supported |
| Cell background | ✅ Supported |
| Resize columns | ✅ Supported via `updateTableColumnProperties` |
| Resize rows | ✅ Supported via `updateTableRowProperties` |
| Cell padding | ❌ Read-only |

### Unit Conversion

SML uses **points (pt)** for all dimensions. The API uses **EMU (English Metric Units)**.

**Conversion constant:** `1 pt = 12700 EMU`

```python
def pt_to_emu(pt):
    return int(pt * 12700)

def emu_to_pt(emu):
    return emu / 12700.0
```

**Note:** Rounding may cause small differences when round-tripping values.

### Object ID Format

New element IDs must be valid Google Slides object IDs:
- Alphanumeric characters only (a-z, A-Z, 0-9)
- Underscores allowed
- Length: 1-64 characters
- Must be unique within the presentation

**Recommendation:** Use UUIDs without hyphens: `a1b2c3d4e5f6...`

---

## Examples

### Example 1: Simple Text Edit

**Original:**
```html
<TextBox id="title" class="x-72 y-100 w-576 h-50 font-family-roboto text-size-24">
  <P range="0-14">
    <T range="0-12">Hello World!</T>
  </P>
</TextBox>
```

**Edited:**
```html
<TextBox id="title" class="x-72 y-100 w-576 h-50 font-family-roboto text-size-24">
  <P range="0-14">
    <T range="0-12">Hello Universe!</T>
  </P>
</TextBox>
```

**Generated Requests:**
```json
{
  "requests": [
    {
      "deleteText": {
        "objectId": "title",
        "textRange": { "type": "FIXED_RANGE", "startIndex": 0, "endIndex": 13 }
      }
    },
    {
      "insertText": {
        "objectId": "title",
        "insertionIndex": 0,
        "text": "Hello Universe!"
      }
    }
  ]
}
```

---

### Example 2: Multiple Text Changes (Reverse Order)

**Original:**
```html
<TextBox id="body">
  <P range="0-30">
    <T range="0-6">Hello </T>
    <T range="6-12" class="bold">world </T>
    <T range="12-29">how are you today</T>
  </P>
</TextBox>
```

**Edited:**
```html
<TextBox id="body">
  <P range="0-30">
    <T range="0-6">Hello </T>
    <T range="12-29">how are you</T>
  </P>
</TextBox>
```

Changes:
1. T at range 6-12 deleted
2. T at range 12-29 content changed

**Generated Requests (reverse index order):**
```json
{
  "requests": [
    {
      "deleteText": {
        "objectId": "body",
        "textRange": { "type": "FIXED_RANGE", "startIndex": 12, "endIndex": 29 }
      }
    },
    {
      "insertText": {
        "objectId": "body",
        "insertionIndex": 12,
        "text": "how are you"
      }
    },
    {
      "deleteText": {
        "objectId": "body",
        "textRange": { "type": "FIXED_RANGE", "startIndex": 6, "endIndex": 12 }
      }
    }
  ]
}
```

---

### Example 3: Add New Shape

**Edited (new element):**
```html
<Slide id="slide_1">
  <!-- existing elements -->

  <Rect id="a1b2c3d4-uuid" class="x-100 y-200 w-200 h-100 fill-#3b82f6 stroke-none"/>
</Slide>
```

**Generated Requests:**
```json
{
  "requests": [
    {
      "createShape": {
        "objectId": "a1b2c3d4-uuid",
        "shapeType": "RECTANGLE",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": {
            "width": { "magnitude": 200, "unit": "PT" },
            "height": { "magnitude": 100, "unit": "PT" }
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 100,
            "translateY": 200,
            "unit": "PT"
          }
        }
      }
    },
    {
      "updateShapeProperties": {
        "objectId": "a1b2c3d4-uuid",
        "shapeProperties": {
          "shapeBackgroundFill": {
            "solidFill": {
              "color": { "rgbColor": { "red": 0.23, "green": 0.51, "blue": 0.96 }}
            }
          },
          "outline": { "propertyState": "NOT_RENDERED" }
        },
        "fields": "shapeBackgroundFill.solidFill.color,outline.propertyState"
      }
    }
  ]
}
```

---

### Example 4: Style-Only Changes

**Original:**
```html
<TextBox id="tb1" class="x-72 y-100 w-400 h-50">
  <P range="0-12">
    <T range="0-5" class="bold">Hello</T>
    <T range="5-11"> world</T>
  </P>
</TextBox>
```

**Edited:**
```html
<TextBox id="tb1" class="x-72 y-100 w-400 h-50">
  <P range="0-12">
    <T range="0-5" class="bold italic underline">Hello</T>
    <T range="5-11" class="text-color-#ef4444"> world</T>
  </P>
</TextBox>
```

**Generated Requests:**
```json
{
  "requests": [
    {
      "updateTextStyle": {
        "objectId": "tb1",
        "textRange": { "type": "FIXED_RANGE", "startIndex": 5, "endIndex": 11 },
        "style": {
          "foregroundColor": {
            "opaqueColor": { "rgbColor": { "red": 0.94, "green": 0.27, "blue": 0.27 }}
          }
        },
        "fields": "foregroundColor"
      }
    },
    {
      "updateTextStyle": {
        "objectId": "tb1",
        "textRange": { "type": "FIXED_RANGE", "startIndex": 0, "endIndex": 5 },
        "style": {
          "italic": true,
          "underline": true
        },
        "fields": "italic,underline"
      }
    }
  ]
}
```

Note: Requests ordered by descending startIndex (5, then 0).

---

### Example 5: Complex Slide Edit

**Original:**
```html
<Slide id="slide_1" class="bg-#ffffff">
  <TextBox id="title" class="x-72 y-50 w-576 h-50 text-size-24">
    <P range="0-10"><T range="0-9">Old Title</T></P>
  </TextBox>
  <Rect id="box1" class="x-100 y-150 w-200 h-100 fill-#3b82f6"/>
  <Rect id="box2" class="x-350 y-150 w-200 h-100 fill-#ef4444"/>
</Slide>
```

**Edited:**
```html
<Slide id="slide_1" class="bg-#f3f4f6">
  <TextBox id="title" class="x-72 y-50 w-576 h-50 text-size-32">
    <P range="0-10"><T range="0-9">New Title</T></P>
  </TextBox>
  <Rect id="box1" class="x-100 y-150 w-200 h-100 fill-#22c55e"/>
  <!-- box2 deleted -->
  <Ellipse id="new-ellipse-uuid" class="x-350 y-150 w-200 h-100 fill-#a855f7"/>
</Slide>
```

**Generated Requests (ordered per topological sort):**
```json
{
  "requests": [
    {
      "createShape": {
        "objectId": "new-ellipse-uuid",
        "shapeType": "ELLIPSE",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": { "width": { "magnitude": 200, "unit": "PT" }, "height": { "magnitude": 100, "unit": "PT" }},
          "transform": { "scaleX": 1, "scaleY": 1, "translateX": 350, "translateY": 150, "unit": "PT" }
        }
      }
    },
    {
      "deleteText": {
        "objectId": "title",
        "textRange": { "type": "FIXED_RANGE", "startIndex": 0, "endIndex": 9 }
      }
    },
    {
      "insertText": {
        "objectId": "title",
        "insertionIndex": 0,
        "text": "New Title"
      }
    },
    {
      "updateTextStyle": {
        "objectId": "title",
        "textRange": { "type": "ALL" },
        "style": { "fontSize": { "magnitude": 32, "unit": "PT" }},
        "fields": "fontSize"
      }
    },
    {
      "updateShapeProperties": {
        "objectId": "box1",
        "shapeProperties": {
          "shapeBackgroundFill": {
            "solidFill": { "color": { "rgbColor": { "red": 0.13, "green": 0.77, "blue": 0.37 }}}
          }
        },
        "fields": "shapeBackgroundFill.solidFill.color"
      }
    },
    {
      "updateShapeProperties": {
        "objectId": "new-ellipse-uuid",
        "shapeProperties": {
          "shapeBackgroundFill": {
            "solidFill": { "color": { "rgbColor": { "red": 0.66, "green": 0.33, "blue": 0.97 }}}
          }
        },
        "fields": "shapeBackgroundFill.solidFill.color"
      }
    },
    {
      "updatePageProperties": {
        "objectId": "slide_1",
        "pageProperties": {
          "pageBackgroundFill": {
            "solidFill": { "color": { "rgbColor": { "red": 0.95, "green": 0.96, "blue": 0.96 }}}
          }
        },
        "fields": "pageBackgroundFill.solidFill.color"
      }
    },
    {
      "deleteObject": {
        "objectId": "box2"
      }
    }
  ]
}
```

Note: Requests are ordered according to the topological sort: creates first, then text operations, then style updates, then deletes last.

---

## Appendix: Request Type Reference

### Create Requests

| SML Change | API Request |
|------------|-------------|
| Add `<Slide>` | `createSlide` |
| Add `<TextBox>`, `<Rect>`, etc. | `createShape` |
| Add `<Image>` | `createImage` |
| Add `<Line>` | `createLine` |
| Add `<Table>` | `createTable` |
| Add `<Video>` | `createVideo` |
| Add `<Chart>` | `createSheetsChart` |

### Delete Requests

| SML Change | API Request |
|------------|-------------|
| Remove any element | `deleteObject` |
| Remove `<T>` or `<P>` | `deleteText` |
| Remove bullets | `deleteParagraphBullets` |
| Remove table row | `deleteTableRow` |
| Remove table column | `deleteTableColumn` |

### Update Requests

| SML Change | API Request |
|------------|-------------|
| Change slide properties | `updatePageProperties` |
| Change slide skip status | `updateSlideProperties` |
| Reorder slides | `updateSlidesPosition` |
| Change shape fill/stroke/shadow | `updateShapeProperties` |
| Change position/size/rotation | `updatePageElementTransformRequest` |
| Change text styling | `updateTextStyle` |
| Change paragraph styling | `updateParagraphStyle` |
| Change image properties | `updateImageProperties` |
| Change line properties | `updateLineProperties` |
| Change video properties | `updateVideoProperties` |
| Change table cell | `updateTableCellProperties` |
| Change table border | `updateTableBorderProperties` |
| Change z-order | `updatePageElementsZOrder` |
| Change alt text | `updatePageElementAltText` |

### Insert Requests

| SML Change | API Request |
|------------|-------------|
| Add `<T>` or `<P>` | `insertText` |
| Add table row | `insertTableRows` |
| Add table column | `insertTableColumns` |
| Add bullets | `createParagraphBullets` |

### Other Requests

| SML Change | API Request |
|------------|-------------|
| `duplicate-of` attribute | `duplicateObject` |
| Create `<Group>` | `groupObjects` |
| Remove `<Group>` | `ungroupObjects` |
| Change image `src` | `replaceImage` |
| Merge table cells | `mergeTableCells` |
| Unmerge table cells | `unmergeTableCells` |
| Change line category | `updateLineCategory` |

### Action Requests

| SML Action | API Request |
|------------|-------------|
| `<BringToFront target="..."/>` | `updatePageElementsZOrder` (BRING_TO_FRONT) |
| `<BringForward target="..."/>` | `updatePageElementsZOrder` (BRING_FORWARD) |
| `<SendBackward target="..."/>` | `updatePageElementsZOrder` (SEND_BACKWARD) |
| `<SendToBack target="..."/>` | `updatePageElementsZOrder` (SEND_TO_BACK) |
| `<RerouteLine target="..."/>` | `rerouteLine` |
| `<RefreshChart target="..."/>` | `refreshSheetsChart` |

---

*Version 1.1 - SML Reconciliation Specification*
