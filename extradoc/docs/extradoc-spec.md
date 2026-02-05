# ExtraDoc Format Specification

## 1. Overview

ExtraDoc converts Google Docs to a flat XML format optimized for LLM editing and efficient diff generation.

### 1.1 Design Goals

1. **1:1 correspondence with Google Docs** - Every element maps directly to Google Docs primitives
2. **Minimal representation** - Fewest possible style rules to represent the document
3. **Structural styling** - Styles anchored to elements, not character indexes
4. **LLM-friendly** - Familiar tags, clean content, semantic structure
5. **Efficient diff** - Changes generate minimal batchUpdate requests

### 1.2 File Structure

```
<document_id>/
├── document.xml          # Content with structural styling
├── styles.xml            # Style definitions (factorized)
├── .pristine/
│   ├── document.xml      # Original content (for diff)
│   └── styles.xml        # Original styles (for diff)
└── .raw/
    └── document.json     # Original API response (for debugging)
```

---

## 2. Document Structure

### 2.1 Root Element

```xml
<?xml version="1.0" encoding="UTF-8"?>
<doc id="DOCUMENT_ID" revision="REVISION_ID">
  <meta>
    <title>Document Title</title>
  </meta>

  <!-- For single-tab documents -->
  <body class="_base">
    ...content...
  </body>

  <!-- For multi-tab documents -->
  <tab id="t.0" title="Tab Name" class="_base">
    <body>...content...</body>
  </tab>

  <!-- Headers (separate index space) -->
  <header id="kix.abc123" class="_base">
    ...content...
  </header>

  <!-- Footers (separate index space) -->
  <footer id="kix.def456" class="_base">
    ...content...
  </footer>

  <!-- Footnotes are inline in the body where the reference appears -->
  <!-- See Section 3.6 for footnote format -->
</doc>
```

### 2.2 Section Scoping

Each section has its own index space starting at 0:

| Section | Index Space | Style Scope |
|---------|-------------|-------------|
| `<body>` | Starts at 1 | Inherits from `class` attribute |
| `<tab>` | Each tab starts at 1 | Inherits from `class` attribute |
| `<header>` | Starts at 0 | Inherits from `class` attribute |
| `<footer>` | Starts at 0 | Inherits from `class` attribute |
| `<footnote>` | Starts at 0 | Inherits document base |

The `class` attribute on section elements defines the base style for that section. All content within inherits from this style unless overridden.

---

## 3. Content Elements

### 3.1 Paragraphs

Basic paragraph:
```xml
<p>Plain text paragraph.</p>
```

With class (style override):
```xml
<p class="JdcUE">Styled paragraph.</p>
```

### 3.2 Headings (Syntactic Sugar)

These are sugar for `<p>` with Google Docs named styles:

| Tag | Desugars To | Google Docs Style |
|-----|-------------|-------------------|
| `<title>` | `<p style="TITLE">` | Title |
| `<subtitle>` | `<p style="SUBTITLE">` | Subtitle |
| `<h1>` | `<p style="HEADING_1">` | Heading 1 |
| `<h2>` | `<p style="HEADING_2">` | Heading 2 |
| `<h3>` | `<p style="HEADING_3">` | Heading 3 |
| `<h4>` | `<p style="HEADING_4">` | Heading 4 |
| `<h5>` | `<p style="HEADING_5">` | Heading 5 |
| `<h6>` | `<p style="HEADING_6">` | Heading 6 |

Headings can also have classes:
```xml
<h1 class="Hy4Kp">Centered Heading</h1>
```

### 3.3 Lists (Syntactic Sugar)

List items are sugar for `<p>` with bullet properties:

```xml
<li type="bullet" level="0">First level bullet</li>
<li type="bullet" level="1">Nested bullet</li>
<li type="decimal" level="0">Numbered item</li>
<li type="alpha" level="0">Alphabetic item</li>
<li type="checkbox" level="0">Checkbox item</li>
```

| Attribute | Values | Description |
|-----------|--------|-------------|
| `type` | `bullet`, `decimal`, `alpha`, `roman`, `checkbox` | List style |
| `level` | `0`, `1`, `2`, ... | Nesting level |
| `class` | Style ID | Additional styling |

**Note:** No `<ul>` or `<ol>` wrapper. List items are flat, matching Google Docs' flat list model.

### 3.4 Tables

```xml
<table rows="2" cols="3">
  <tr>
    <td><p>A1</p></td>
    <td><p>B1</p></td>
    <td><p>C1</p></td>
  </tr>
  <tr>
    <td colspan="2"><p>A2-B2 merged</p></td>
    <td><p></p></td>
    <td class="a40x2"><p>C2 styled</p></td>
  </tr>
</table>
```

Table elements:
- `<table>` - Container with `rows` and `cols` attributes
- `<tr>` - Row (syntactic sugar, removed during diff)
- `<td>` - Cell with optional `colspan`, `rowspan`, `class`

**IMPORTANT: Physical Cell Structure**

Each row always has exactly `cols` physical cells, regardless of colspan. The `colspan` attribute is visual metadata only - it doesn't reduce the number of `<td>` elements.

For example, if `cols="5"` and a cell has `colspan="3"`:
- The first `<td colspan="3">` contains the merged content
- The next 2 `<td>` elements are empty (cells covered by the merge)
- All 5 `<td>` elements must be present

This matches Google Docs' internal structure where merged cells still exist as physical entities with separate indexes.

**Note:** `<tr>` is sugar for LLM readability. During diff, cells are flattened with computed row/col positions.

### 3.5 Special Elements

```xml
<!-- Horizontal rule (inside paragraph) -->
<p><hr/></p>

<!-- Page break (inside paragraph) -->
<p><pagebreak/></p>

<!-- Column break (inside paragraph) -->
<p>Text before<columnbreak/>Text after</p>

<!-- Image -->
<p><image src="URL" width="100pt" height="50pt" alt="Description"/></p>

<!-- Person mention -->
<p>Contact <person email="foo@example.com" name="Foo Bar"/> for details.</p>

<!-- Auto-generated text (page numbers, etc.) -->
<p>Page <autotext type="PAGE_NUMBER"/></p>
```

**Note:** Special elements like `<columnbreak/>`, `<pagebreak/>`, `<hr/>` each take exactly 1 index in Google Docs.

### 3.6 Footnotes (Inline Model)

Footnotes use an inline model where the `<footnote>` tag appears at the reference location and contains the footnote content:

```xml
<p>See note<footnote id="kix.fn1"><p>This is the footnote content.</p></footnote> for details.</p>
```

The inline model provides:
- **Position:** Where the `<footnote>` tag appears indicates the reference location
- **Content:** The content inside is the footnote text (structured like `<td>` content)
- **ID:** The `id` attribute links to Google Docs' internal footnote ID

This differs from `<footnoteref>` which only stores a reference. The inline model captures both reference position and content in one element, enabling proper diff detection for footnote additions, deletions, and content modifications.

**Index Space:** Footnotes have their own index space starting at 0. The footnote reference in the body takes 1 index. The content inside `<footnote>` uses the footnote's separate index space.

---

## 4. Inline Formatting

### 4.1 Inline Tags

Inline tags wrap text runs and compose via nesting:

| Tag | Style Property |
|-----|---------------|
| `<b>` | bold |
| `<i>` | italic |
| `<u>` | underline |
| `<s>` | strikethrough |
| `<sup>` | superscript |
| `<sub>` | subscript |
| `<a href="...">` | link |

Composition:
```xml
<p>Normal <b>bold</b> and <b><i>bold italic</i></b> text.</p>
<p>Visit <a href="https://example.com">our site</a> for more.</p>
```

### 4.2 Inline Style Spans

For styles not covered by semantic tags (colors, fonts, backgrounds):

```xml
<p>Text with <span class="Hy4Kp">custom styled</span> words.</p>
```

Or for multi-element ranges:
```xml
<style class="Hy4Kp">
  <p>First styled paragraph.</p>
  <p>Second styled paragraph.</p>
</style>
```

### 4.3 Desugar Rules

All inline tags collapse to text runs during diff:

```xml
<!-- Sugared (LLM-facing) -->
<p>Hello <b><i>world</i></b>!</p>

<!-- Desugared (internal) -->
<p>
  <t>Hello </t>
  <t bold="1" italic="1">world</t>
  <t>!</t>
</p>
```

---

## 5. Style System

### 5.1 styles.xml Format

All styles use consistent `<style>` elements with content-hashed IDs:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<styles>
  <!--
    Style IDs are 5-character hashes derived from properties.
    Same properties always produce the same ID across runs.
    _base is reserved for the document base style.
  -->
  <style id="_base" font="Arial" size="11pt" color="#000000" bold="0" italic="0"/>

  <!-- Additional styles (deviations from base) -->
  <style id="JF4QL" bold="1"/>
  <style id="a40x2" color="#FF0000" bold="1"/>
  <style id="JdcUE" font="Courier" size="10pt" bg="#F5F5F5"/>
  <style id="xK9mR" italic="1" indentLeft="36pt" color="#666666"/>
  <style id="rmHiM" alignment="CENTER"/>
  <style id="pQ3vN" size="9pt" color="#888888"/>
</styles>
```

### 5.2 Style ID Generation

Style IDs are deterministic 5-character hashes:

- **Input:** Style properties (canonically sorted)
- **Algorithm:** MD5 hash → custom base encoding
- **Character set:**
  - First char: `A-Za-z_` (53 options)
  - Rest: `A-Za-z0-9_-.` (65 options)
- **Entropy:** ~946 million combinations
- **Special case:** Empty/base style → `_base`

```python
# Same properties always produce same ID
style_id({"bold": "1"})                    # → "JF4QL"
style_id({"bold": "1"})                    # → "JF4QL" (stable)
style_id({"font": "Courier", "bg": "#F5F5F5"})  # → "JdcUE"
```

This ensures:
- IDs are stable across runs (same doc = same IDs)
- IDs are unique per style combination
- No manual naming required

### 5.3 Style Properties

#### Text Properties

| Property | Values | Maps to |
|----------|--------|---------|
| `font` | Font name | `textStyle.weightedFontFamily.fontFamily` |
| `size` | e.g., `11pt` | `textStyle.fontSize` |
| `color` | e.g., `#FF0000` | `textStyle.foregroundColor` |
| `bg` | e.g., `#FFFF00` | `textStyle.backgroundColor` |
| `bold` | `0`, `1` | `textStyle.bold` |
| `italic` | `0`, `1` | `textStyle.italic` |
| `underline` | `0`, `1` | `textStyle.underline` |
| `strikethrough` | `0`, `1` | `textStyle.strikethrough` |

#### Paragraph Properties

| Property | Values | Maps to |
|----------|--------|---------|
| `alignment` | `START`, `CENTER`, `END`, `JUSTIFIED` | `paragraphStyle.alignment` |
| `lineSpacing` | e.g., `1.15` | `paragraphStyle.lineSpacing` |
| `spaceAbove` | e.g., `12pt` | `paragraphStyle.spaceAbove` |
| `spaceBelow` | e.g., `6pt` | `paragraphStyle.spaceBelow` |
| `indentLeft` | e.g., `36pt` | `paragraphStyle.indentStart` |
| `indentRight` | e.g., `36pt` | `paragraphStyle.indentEnd` |
| `indentFirstLine` | e.g., `18pt` | `paragraphStyle.indentFirstLine` |

### 5.4 Style Application

Styles are applied via `class` attribute:

```xml
<!-- On section (base for all content) -->
<body class="_base">

<!-- On single element -->
<p class="JdcUE">Styled paragraph</p>
<td class="Hy4Kp">Styled cell</td>
<li class="a40x2" type="bullet" level="0">Styled list item</li>

<!-- On heading -->
<h1 class="rmHiM">Centered Heading</h1>

<!-- Inline span -->
<p>Text with <span class="Hy4Kp">styled words</span> here.</p>

<!-- Multi-element wrapper -->
<style class="a40x2">
  <p>Line 1</p>
  <p>Line 2</p>
</style>
```

### 5.5 Style Inheritance

1. Section base style (from `class` on `<body>`, `<header>`, etc.)
2. Element class (from `class` on `<p>`, `<td>`, etc.)
3. Style wrapper (from `<style class="...">`)
4. Inline tags (from `<b>`, `<i>`, etc.)

Later levels override earlier levels. Properties not specified are inherited.

### 5.6 Style Factorization Algorithm

On pull, styles are factorized to minimize the number of rules:

```
Input: All text runs with their computed styles
Output: Minimal set of style definitions

Algorithm:
1. For EACH style property independently:
   a. Count occurrences weighted by character count
   b. Most common value becomes the "base" value

2. Create style s0 with all base values

3. For each text run:
   a. Compute deviation from base (properties that differ)
   b. Group runs with identical deviations

4. For each distinct deviation:
   a. Create a new style (s1, s2, ...)
   b. Include ONLY the properties that deviate

5. Merge: If two styles have identical properties, use one ID

6. Apply to document:
   a. Wrap contiguous same-styled ranges
   b. Use <style> wrapper for multi-element ranges
   c. Use class attribute for single elements
```

**Example:**

Document has 100 paragraphs:
- 80 paragraphs: Arial 11pt black
- 15 paragraphs: Arial 11pt red
- 5 paragraphs: Courier 10pt black

Factorization:
```xml
<!-- styles.xml -->
<styles>
  <style id="s0" font="Arial" size="11pt" color="#000000"/>
  <style id="s1" color="#FF0000"/>  <!-- Only the deviation -->
  <style id="s2" font="Courier" size="10pt"/>  <!-- Only the deviations -->
</styles>
```

---

## 6. Complete Example

### styles.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<styles>
  <style id="_base" font="Arial" size="11pt" color="#000000" bold="0" italic="0"/>
  <style id="JdcUE" font="Courier" size="10pt" bg="#F5F5F5"/>
  <style id="Hy4Kp" bg="#FFFF00"/>
  <style id="a40x2" color="#FF0000" bold="1"/>
  <style id="xK9mR" italic="1" indentLeft="36pt" color="#666666"/>
  <style id="rmHiM" size="9pt" color="#888888"/>
</styles>
```

### document.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<doc id="1abc2def3ghi" revision="ALm37BV">
  <meta>
    <title>Project Proposal</title>
  </meta>

  <body class="_base">
    <title>Project Proposal</title>
    <subtitle>Q4 2024 Initiative</subtitle>

    <h1>Executive Summary</h1>
    <p>This document outlines our approach to <b>digital transformation</b>.</p>
    <p>Key objectives include <span class="a40x2">critical deliverables</span> and timelines.</p>

    <h2>Background</h2>
    <p>Standard paragraph text here.</p>
    <p class="Hy4Kp">This paragraph is highlighted.</p>
    <p>Back to normal text.</p>

    <h2>Implementation</h2>

    <style class="JdcUE">
      <p>def process_data():</p>
      <p>    validate()</p>
      <p>    transform()</p>
      <p>    return result</p>
    </style>

    <h3>Phase 1: Planning</h3>
    <li type="decimal" level="0">Define requirements</li>
    <li type="decimal" level="0" class="a40x2">Critical: Security review</li>
    <li type="decimal" level="0">Timeline approval</li>

    <style class="xK9mR">
      <p>"Innovation distinguishes between a leader and a follower."</p>
      <p>— Steve Jobs</p>
    </style>

    <h2>Conclusion</h2>
    <p>Final summary with <a href="https://example.com">reference link</a>.</p>

    <p><hr/></p>

    <p>Document prepared by the Strategy Team.</p>
  </body>

  <header id="kix.hdr1" class="_base">
    <p>Project Proposal — Confidential</p>
  </header>

  <footer id="kix.ftr1" class="rmHiM">
    <p>Page <autotext type="PAGE_NUMBER"/> of <autotext type="PAGE_COUNT"/></p>
  </footer>
</doc>
```

---

## 7. Pull Workflow

### 7.1 Overview

```
Google Docs API
      │
      ▼
┌─────────────────┐
│ documents.get() │
└────────┬────────┘
         │ JSON response
         ▼
┌─────────────────┐
│ Style Factorize │──────► styles.xml
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Content Convert │──────► document.xml
│ + Sugar Pass    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save Pristine   │──────► .pristine/
└─────────────────┘
```

### 7.2 Style Factorization

1. **Collect all styles** from text runs
2. **Compute base** (mode for each property)
3. **Compute deviations** for each run
4. **Group identical deviations** → one style per group
5. **Generate style IDs** (s0, s1, s2, ...)
6. **Output styles.xml**

### 7.3 Content Conversion

1. **Convert structural elements** (paragraphs, tables, etc.)
2. **Apply sugar transforms:**
   - `<p style="HEADING_1">` → `<h1>`
   - `<p>` with bullet → `<li>`
   - `<t bold="1">` → `<b>`
3. **Apply style classes** to elements
4. **Wrap multi-element ranges** with `<style class="...">`

---

## 8. Diff Workflow

### 8.1 Overview

```
document.xml (edited)          .pristine/document.xml
         │                              │
         ▼                              ▼
┌─────────────────┐            ┌─────────────────┐
│  Desugar Pass   │            │  Desugar Pass   │
└────────┬────────┘            └────────┬────────┘
         │                              │
         ▼                              ▼
   Internal XML                  Internal XML
   (current)                     (pristine)
         │                              │
         └──────────┬───────────────────┘
                    │
                    ▼
            ┌───────────────┐
            │  Diff Engine  │
            └───────┬───────┘
                    │
                    ▼
            batchUpdate JSON
```

### 8.2 Desugar Transforms

| Sugared | Desugared |
|---------|-----------|
| `<h1>` | `<p style="HEADING_1">` |
| `<h2>` | `<p style="HEADING_2">` |
| `<title>` | `<p style="TITLE">` |
| `<subtitle>` | `<p style="SUBTITLE">` |
| `<li type="..." level="...">` | `<p bullet="..." level="...">` |
| `<tr><td>...</td></tr>` | `<td row="r" col="c">` |
| `<b>text</b>` | `<t bold="1">text</t>` |
| `<i>text</i>` | `<t italic="1">text</t>` |
| `<span class="JdcUE">text</span>` | `<t class="JdcUE">text</t>` |
| `<style class="JdcUE">...</style>` | Class applied to children |

### 8.3 Diff Algorithm

```python
def diff(pristine: Document, current: Document) -> list[Request]:
    requests = []

    for section in ['body', 'headers', 'footers', 'footnotes']:
        pristine_elems = flatten(pristine[section])
        current_elems = flatten(current[section])

        # Calculate pristine indexes
        pristine_indexes = calculate_indexes(pristine_elems)

        # Sequence diff
        for op in diff_sequences(pristine_elems, current_elems):
            if op.type == 'delete':
                requests.append(delete_request(op, pristine_indexes))
            elif op.type == 'insert':
                requests.append(insert_request(op, pristine_indexes))
            elif op.type == 'update':
                requests.extend(update_requests(op, pristine_indexes))

    # Sort by index descending (apply from end to start)
    requests.sort(key=lambda r: r.index, reverse=True)

    return requests
```

### 8.4 Style Change Detection

When `<style>` wrapper or `class` attribute changes:

1. **New style applied** → Generate `updateTextStyle` or `updateParagraphStyle`
2. **Style removed** → Reset to base style (from section's class)
3. **Content added inside `<style>`** → Auto-inherits (no explicit style request needed)

---

## 9. batchUpdate Generation

### 9.1 Request Types

| Change | Request Type |
|--------|--------------|
| Text deleted | `deleteContentRange` |
| Text inserted | `insertText` |
| Paragraph inserted | `insertText` (with newline) |
| List item added | `insertText` + `createParagraphBullets` |
| List item removed | `deleteParagraphBullets` + content change |
| Style applied | `updateTextStyle` or `updateParagraphStyle` |
| Heading changed | `updateParagraphStyle` with `namedStyleType` |
| Table row added | `insertTableRow` |
| Table row deleted | `deleteTableRow` |

### 9.2 Index Calculation

```python
def calculate_indexes(elements: list[Element]) -> dict[Element, tuple[int, int]]:
    """Calculate (start_index, end_index) for each element."""
    indexes = {}
    current = 1  # Body starts at 1; headers/footers start at 0

    for elem in elements:
        start = current

        if isinstance(elem, Paragraph):
            # Text content + newline
            text_len = sum(utf16_len(run.text) for run in elem.runs)
            current += text_len + 1
        elif isinstance(elem, TableStart):
            current += 1
        elif isinstance(elem, TableEnd):
            current += 1
        elif isinstance(elem, RowStart):
            current += 1
        elif isinstance(elem, CellStart):
            current += 1
        elif isinstance(elem, HorizontalRule):
            current += 1
        elif isinstance(elem, PageBreak):
            current += 1

        indexes[elem] = (start, current)

    return indexes
```

### 9.3 Ordering

Requests are sorted by index **descending** to prevent cascade effects:

```python
# Good: Apply from end to start
[
  {"deleteContentRange": {"range": {"startIndex": 100, "endIndex": 110}}},
  {"deleteContentRange": {"range": {"startIndex": 50, "endIndex": 60}}},
  {"insertText": {"location": {"index": 20}, "text": "new"}}
]

# Bad: Earlier operations shift later indexes
[
  {"insertText": {"location": {"index": 20}, "text": "new"}},  # Shifts everything after 20
  {"deleteContentRange": {"range": {"startIndex": 50, ...}}}   # Index 50 is now wrong!
]
```

---

## 10. Three-Way Merge

### 10.1 Conflict Detection

Before push, check if remote has changed:

```python
def check_conflicts(local_doc: Document) -> ConflictStatus:
    pristine_revision = local_doc.pristine_revision
    remote_revision = fetch_current_revision(local_doc.id)

    if pristine_revision == remote_revision:
        return ConflictStatus.NO_CONFLICT
    else:
        return ConflictStatus.REMOTE_CHANGED
```

### 10.2 Merge Strategy

When conflicts detected:

```
┌─────────────────────────────────────────────────────────────────┐
│                     THREE-WAY MERGE                              │
│                                                                  │
│  BASE (pristine)         LOCAL (your edits)    REMOTE (others)  │
│        │                       │                      │         │
│        └───────────────────────┼──────────────────────┘         │
│                                │                                 │
│                                ▼                                 │
│                    ┌─────────────────────┐                      │
│                    │  Merge Algorithm    │                      │
│                    │  or LLM Resolution  │                      │
│                    └──────────┬──────────┘                      │
│                               │                                  │
│                               ▼                                  │
│                         MERGED RESULT                            │
│                               │                                  │
│                               ▼                                  │
│                    Diff against REMOTE                           │
│                    (remote is new base)                          │
│                               │                                  │
│                               ▼                                  │
│                         batchUpdate                              │
└─────────────────────────────────────────────────────────────────┘
```

### 10.3 Auto-Merge

Non-conflicting changes can be merged automatically:

```python
def can_auto_merge(base, local, remote) -> bool:
    local_changes = diff(base, local)
    remote_changes = diff(base, remote)

    # Check for overlapping ranges
    for l_change in local_changes:
        for r_change in remote_changes:
            if ranges_overlap(l_change.range, r_change.range):
                return False

    return True
```

### 10.4 LLM-Assisted Merge

For conflicts, present to LLM:

```markdown
## Merge Conflict at Paragraph 5

**BASE (original):**
```xml
<p>The project timeline is 6 months.</p>
```

**LOCAL (your changes):**
```xml
<p>The project timeline is <b>8 months</b> due to scope expansion.</p>
```

**REMOTE (changes by others):**
```xml
<p>The project timeline is 6 months, starting Q1 2025.</p>
```

Please provide the merged version:
```

---

## 11. CLI Interface

```bash
# Pull a document
extradoc pull <document_url_or_id> [output_dir]

# Preview changes (dry run)
extradoc diff <folder>

# Push changes
extradoc push <folder>

# Push with merge (when conflicts detected)
extradoc push <folder> --merge

# Force push (skip conflict check)
extradoc push <folder> --force
```

---

## 12. Appendices

### A. Index Cost Reference

| Element | Index Cost |
|---------|-----------|
| Document start | 1 (body starts at index 1) |
| Paragraph text | `utf16_len(text)` |
| Paragraph end (newline) | 1 |
| Horizontal rule | 1 |
| Page break | 1 |
| Inline image | 1 |
| Person mention | 1 |
| Footnote reference | 1 |
| Table start | 1 |
| Table row start | 1 |
| Table cell start | 1 |
| Table end | 1 |

### B. UTF-16 Length Calculation

```python
def utf16_len(text: str) -> int:
    """Calculate UTF-16 code unit length."""
    length = 0
    for char in text:
        code_point = ord(char)
        if code_point > 0xFFFF:
            length += 2  # Surrogate pair (emoji, etc.)
        else:
            length += 1
    return length
```

### C. Bullet Presets

| Type | batchUpdate Preset |
|------|-------------------|
| `bullet` | `BULLET_DISC_CIRCLE_SQUARE` |
| `decimal` | `NUMBERED_DECIMAL_NESTED` |
| `alpha` | `NUMBERED_ALPHA_LOWER` |
| `roman` | `NUMBERED_ROMAN_LOWER` |
| `checkbox` | `BULLET_CHECKBOX` |

### D. Complete Tag Reference

#### Block Elements

| Tag | Description | Attributes |
|-----|-------------|------------|
| `<p>` | Paragraph | `class` |
| `<title>` | Document title | `class` |
| `<subtitle>` | Document subtitle | `class` |
| `<h1>`-`<h6>` | Headings | `class` |
| `<li>` | List item | `type`, `level`, `class` |
| `<table>` | Table | `rows`, `cols` |
| `<tr>` | Table row (sugar) | - |
| `<td>` | Table cell | `colspan`, `rowspan`, `class` |

#### Inline Elements

| Tag | Description | Attributes |
|-----|-------------|------------|
| `<b>` | Bold | - |
| `<i>` | Italic | - |
| `<u>` | Underline | - |
| `<s>` | Strikethrough | - |
| `<sup>` | Superscript | - |
| `<sub>` | Subscript | - |
| `<a>` | Link | `href` |
| `<span>` | Styled span | `class` |

#### Special Elements

| Tag | Description | Attributes |
|-----|-------------|------------|
| `<hr/>` | Horizontal rule | - |
| `<pagebreak/>` | Page break | - |
| `<image/>` | Image | `src`, `width`, `height`, `alt`, `title` |
| `<person/>` | Person mention | `email`, `name` |
| `<footnote>` | Inline footnote (contains content) | `id` |
| `<autotext/>` | Auto-generated text | `type` |

#### Structural Elements

| Tag | Description | Attributes |
|-----|-------------|------------|
| `<doc>` | Document root | `id`, `revision` |
| `<meta>` | Metadata container | - |
| `<body>` | Main content | `class` |
| `<tab>` | Document tab | `id`, `title`, `class` |
| `<header>` | Header section | `id`, `class` |
| `<footer>` | Footer section | `id`, `class` |
| `<style>` | Style wrapper | `class` |
