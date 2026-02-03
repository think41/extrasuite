# Extradoc HTML Format Design

This document specifies how Google Docs are converted to HTML format and how the diff/push operations work.

---

## Table of Contents

1. [Overview](#overview)
2. [Design Goals](#design-goals)
3. [On-Disk Format](#on-disk-format)
4. [Document Structure](#document-structure)
5. [HTML Element Mapping](#html-element-mapping)
6. [Custom Elements](#custom-elements)
7. [Headers and Footers](#headers-and-footers)
8. [Tables](#tables)
9. [Multi-Tab Support](#multi-tab-support)
10. [Index Reconstruction](#index-reconstruction)
11. [Diff Algorithm](#diff-algorithm)
12. [BatchUpdate Generation](#batchupdate-generation)
13. [Limitations and Constraints](#limitations-and-constraints)

---

## Overview

Extradoc converts Google Docs to a clean HTML representation optimized for LLM editing. The key insight is that **document indexes can be derived from structure** without explicit tracking, enabling simple diff-based editing.

### Key Principles

1. **Semantic HTML**: Use meaningful tags (`h1`-`h6`, `p`, `ul`, `ol`, `table`)
2. **Custom elements for Google Docs concepts**: Use `<PageBreak/>`, `<Person/>` instead of comments or class attributes
3. **Atomic elements stay atomic**: Special elements like `<FootnoteRef/>` are single self-closing tags
4. **No explicit indexes**: Indexes are calculated during diff, not stored in HTML
5. **Single file**: Entire document (all tabs) in one HTML file
6. **Embedded metadata**: Document metadata in `<script type="application/json">` in `<head>`
7. **Styles in separate JSON**: Complex styling (fonts, colors, spacing) in `styles.json`

---

## Design Goals

| Goal | Solution |
|------|----------|
| LLM-friendly | Semantic HTML with custom elements for Docs concepts |
| Atomic elements | Special elements are self-closing tags, not splittable |
| Index reconstruction | UTF-16 length calculation from text content |
| Multi-tab support | `<article id="..." data-title="...">` for each tab |
| Round-trip fidelity | HTML → indexes → batchUpdate → identical result |

---

## On-Disk Format

After `pull`, the folder structure is:

```
<document_id>/
  document.html           # Main document content (all tabs)
  styles.json             # Extracted styles (fonts, colors, spacing)
  .raw/
    document.json         # Raw API response (for debugging)
  .pristine/
    document.zip          # Zip of HTML/styles for diff comparison
```

Note: No separate `metadata.json` - metadata is embedded in the HTML `<head>`.

---

## Document Structure

### Complete HTML Structure

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Document Title</title>
  <script type="application/json" id="doc-metadata">
  {
    "documentId": "1abc2def...",
    "title": "Document Title",
    "revisionId": "ALm37BV...",
    "locale": "en-US"
  }
  </script>
</head>
<body>
  <!-- Single-tab document (legacy - no tab ID) -->
  <article>
    <Header id="kix.header1">...</Header>
    <main>
      <!-- Body content -->
    </main>
    <Footer id="kix.footer1">...</Footer>
  </article>

  <!-- OR Multi-tab document (one article per tab) -->
  <article id="t.0" data-title="Tab 1">
    <Header id="kix.header1">...</Header>
    <main>...</main>
    <Footer id="kix.footer1">...</Footer>
  </article>
  <article id="t.abc123" data-title="Second Tab">
    <Header id="kix.header2">...</Header>
    <main>...</main>
    <Footer id="kix.footer2">...</Footer>
  </article>
</body>
</html>
```

### Article Elements

- **All tabs use `<article>`**: Standard HTML element for self-contained content
- **Tab ID in `id` attribute**: `<article id="t.0">`
- **Tab title in `data-title`**: `<article data-title="My Tab">`
- **Legacy single-tab documents**: `<article>` without ID (body at root level in API)

---

## HTML Element Mapping

### Structural Elements

| Google Docs | HTML | Notes |
|-------------|------|-------|
| Document body | `<main>` | Main content container per tab |
| Section break | (implicit) | First element, index 0-1 |
| Header | `<Header id="...">` | Custom element, own index space |
| Footer | `<Footer id="...">` | Custom element, own index space |
| Tab | `<article id="..." data-title="...">` | Standard HTML for multi-tab |

### Paragraph Styles

| Google Docs | HTML | Example |
|-------------|------|---------|
| TITLE | `<h1 class="title">` | `<h1 class="title">Document Title</h1>` |
| SUBTITLE | `<p class="subtitle">` | `<p class="subtitle">A subtitle</p>` |
| HEADING_1 | `<h1 id="...">` | `<h1 id="kix.abc">Heading</h1>` |
| HEADING_2 | `<h2 id="...">` | `<h2 id="kix.def">Subheading</h2>` |
| HEADING_3-6 | `<h3 id="...">`-`<h6 id="...">` | With heading IDs |
| NORMAL_TEXT | `<p>` | `<p>Regular text</p>` |

Note: Heading IDs from Google Docs **are preserved** in the HTML for internal links to work correctly.

### List Elements

| Google Docs | HTML | Example |
|-------------|------|---------|
| Bulleted list | `<ul class="bullet">` | `<ul class="bullet"><li>Item</li></ul>` |
| Numbered (decimal) | `<ol class="decimal">` | `<ol class="decimal"><li>Item</li></ol>` |
| Numbered (alpha) | `<ol class="alpha">` | `<ol class="alpha"><li>Item</li></ol>` |
| Numbered (roman) | `<ol class="roman">` | `<ol class="roman"><li>Item</li></ol>` |
| Checkbox list | `<ul class="checkbox">` | `<ul class="checkbox"><li>Item</li></ul>` |
| Nested list | Nested with same class | Proper nesting with type preserved |

### Inline Text Formatting

| Google Docs | HTML | Index Cost |
|-------------|------|------------|
| TextRun | text | UTF-16 length |
| Bold | `<strong>` | 0 (styling only) |
| Italic | `<em>` | 0 (styling only) |
| Underline | `<u>` | 0 (styling only) |
| Strikethrough | `<s>` | 0 (styling only) |
| Superscript | `<sup>` | 0 (styling only) |
| Subscript | `<sub>` | 0 (styling only) |
| Link | `<a href="...">` | 0 (styling only) |

---

## Custom Elements

For Google Docs concepts that don't have HTML equivalents, we use custom self-closing elements. This keeps them atomic and prevents LLMs from accidentally breaking them.

### Special Inline Elements

| Google Docs | HTML Element | Index Cost | Attributes |
|-------------|--------------|------------|------------|
| HorizontalRule | `<hr/>` | 1 | none (standard HTML) |
| PageBreak | `<PageBreak/>` | 1 | none |
| ColumnBreak | `<ColumnBreak/>` | 1 | none |
| FootnoteReference | `<FootnoteRef id="..." num="..."/>` | 1 | `id`, `num` |
| InlineObject (image) | `<Image src="..." width="..." height="..."/>` | 1 | `src`, `width`, `height`, `title`, `alt` |
| Person | `<Person email="..." name="..."/>` | 1 | `email`, `name` |
| RichLink | `<RichLink url="..." title="..."/>` | 1 | `url`, `title` |
| DateElement | `<Date/>` | 1 | none |
| Equation | `<Equation/>` | variable | none |
| AutoText | `<AutoText type="..."/>` | variable | `type` |

### Structural Custom Elements

| Google Docs | HTML Element | Notes |
|-------------|--------------|-------|
| Header | `<Header id="...">` | Contains paragraphs, own index space |
| Footer | `<Footer id="...">` | Contains paragraphs, own index space |
| Tab | `<article id="..." data-title="...">` | Standard HTML, contains Header, main, Footer |
| Table of Contents | `<nav>` | Standard HTML nav element |
| Footnote content | `<Footnote id="...">` | At end of document |

### Example with Custom Elements

```html
<p>This is a paragraph with a <PageBreak/> page break.</p>

<p>See footnote<FootnoteRef id="fn1" num="1"/> for details.</p>

<p>Contact <Person email="john@example.com" name="John Doe"/> for help.</p>

<p>Check out <RichLink url="https://docs.google.com/..." title="Project Plan"/> for more.</p>

<p><Image src="https://..." width="400pt" height="300pt" alt="Diagram"/></p>

<hr/>

<p>Next section...</p>
```

---

## Headers and Footers

Headers and footers are special sections with their own index spaces (each starts at 0).

### Structure

```html
<article id="t.0" data-title="Main">
  <Header id="kix.abc123">
    <p>Company Name</p>
    <p>Page <AutoText type="PAGE_NUMBER"/></p>
  </Header>

  <main>
    <!-- Body content, indexes start at 0 -->
    <p>Document body...</p>
  </main>

  <Footer id="kix.xyz789">
    <p>Confidential - Page <AutoText type="PAGE_NUMBER"/> of <AutoText type="PAGE_COUNT"/></p>
  </Footer>
</article>
```

### Index Spaces

Each section has its own independent index space:
- **Body**: Indexes 0 to N (main content)
- **Header kix.abc123**: Indexes 0 to M (independent)
- **Footer kix.xyz789**: Indexes 0 to P (independent)
- **Footnote fn1**: Indexes 0 to Q (independent)

When generating batchUpdate requests, you must specify the `segmentId` for non-body content.

### First Page Headers/Footers

Google Docs supports different headers/footers for the first page:

```html
<Header id="kix.firstpage" first-page="true">
  <p>First Page Header</p>
</Header>

<Header id="kix.default">
  <p>Default Header</p>
</Header>
```

---

## Tables

Tables use standard HTML table elements with support for merged cells.

### Basic Table

```html
<table>
  <tr>
    <td>Cell 1</td>
    <td>Cell 2</td>
  </tr>
  <tr>
    <td>Cell 3</td>
    <td>Cell 4</td>
  </tr>
</table>
```

### Merged Cells

```html
<table>
  <tr>
    <td colspan="2">Merged across 2 columns</td>
  </tr>
  <tr>
    <td rowspan="2">Merged across 2 rows</td>
    <td>Normal cell</td>
  </tr>
  <tr>
    <td>Another cell</td>
  </tr>
</table>
```

### Table Index Overhead

Tables have significant index overhead:
- Table start marker: +1
- Each row start: +1
- Each cell start: +1
- Table end marker: +1

Example 2x2 table indexes:
```
[table start]     index 0 (+1)
  [row 1 start]   index 1 (+1)
    [cell 1]      index 2 (+1) + cell content
    [cell 2]      index N (+1) + cell content
  [row 2 start]   index M (+1)
    [cell 3]      index M+1 (+1) + cell content
    [cell 4]      index P (+1) + cell content
[table end]       index Q (+1)
```

### Table Operations

| Operation | batchUpdate Request |
|-----------|---------------------|
| Insert table | `InsertTableRequest` |
| Delete table | `DeleteContentRangeRequest` (entire table) |
| Add row | `InsertTableRowRequest` |
| Delete row | `DeleteTableRowRequest` |
| Add column | `InsertTableColumnRequest` |
| Delete column | `DeleteTableColumnRequest` |
| Merge cells | `MergeTableCellsRequest` |
| Unmerge cells | `UnmergeTableCellsRequest` |
| Edit cell text | `InsertTextRequest` / `DeleteContentRangeRequest` |

### Table Constraints

From Google Docs API:
- Cannot partially delete a table (must delete entire table)
- Cannot insert text at table boundaries
- Cell content follows same rules as body content
- Each cell's content ends with a required newline

---

## Multi-Tab Support

Google Docs supports multiple tabs (like spreadsheet tabs). We always request tabs in the API call.

### API Request

Always use `includeTabsContent=true`:
```python
doc = service.documents().get(
    documentId=DOCUMENT_ID,
    includeTabsContent=True
).execute()
```

### HTML Representation

**Single Tab** (use `<article>`):
```html
<body>
  <article>
    <main>
      <p>Content...</p>
    </main>
  </article>
</body>
```

**Multiple Tabs** (use `<article>` for each):
```html
<body>
  <article id="t.0" data-title="Introduction">
    <main>
      <p>Intro content...</p>
    </main>
  </article>

  <article id="t.abc123" data-title="Chapter 1">
    <main>
      <p>Chapter 1 content...</p>
    </main>
  </article>

  <article id="t.xyz789" data-title="Appendix">
    <main>
      <p>Appendix content...</p>
    </main>
  </article>
</body>
```

### Article Attributes for Tabs

| Attribute | Required | Description |
|-----------|----------|-------------|
| `id` | Yes | Tab ID from API (e.g., "t.0", "t.abc123") |
| `data-title` | Optional | Tab display name |

### BatchUpdate with Tabs

When targeting content in a specific tab, include `tabId`:

```json
{
  "insertText": {
    "location": {
      "index": 10,
      "tabId": "t.abc123"
    },
    "text": "New text"
  }
}
```

---

## Index Reconstruction

### UTF-16 Length Calculation

Google Docs uses UTF-16 code units for indexing:

```python
def utf16_len(text: str) -> int:
    """Calculate length in UTF-16 code units."""
    length = 0
    for char in text:
        if ord(char) > 0xFFFF:  # Surrogate pair needed
            length += 2
        else:
            length += 1
    return length
```

### Index Calculation Rules

| Element | Index Cost |
|---------|------------|
| Text character (BMP) | 1 |
| Text character (emoji, etc.) | 2 |
| Newline | 1 |
| `<hr/>` | 1 |
| `<PageBreak/>` | 1 |
| `<ColumnBreak/>` | 1 |
| `<FootnoteRef/>` | 1 |
| `<Image/>` | 1 |
| `<Person/>` | 1 |
| `<RichLink/>` | 1 |
| `<Date/>` | 1 |
| Table start | 1 |
| Table end | 1 |
| Row start | 1 |
| Cell start | 1 |

### Algorithm

```
current_index = 0

for element in body.content:
    if element.type == SECTION_BREAK:
        current_index = 1  # Section break at 0-1

    elif element.type == PARAGRAPH:
        element.startIndex = current_index
        for inline in paragraph.elements:
            if inline.type == TEXT_RUN:
                current_index += utf16_len(inline.content)
            else:  # Special elements
                current_index += 1
        element.endIndex = current_index

    elif element.type == TABLE:
        # See table index calculation above
```

---

## Diff Algorithm

### Overview

```
1. Load pristine HTML from .pristine/document.zip
2. Load current HTML from document.html
3. Parse both into structured representations
4. For each tab:
   a. Compare body content
   b. Compare headers
   c. Compare footers
5. Generate batchUpdate requests (reverse index order)
```

### Change Detection

| Change | Detection | Request |
|--------|-----------|---------|
| Text inserted | New text in edited | `InsertTextRequest` |
| Text deleted | Text missing in edited | `DeleteContentRangeRequest` |
| Style changed | Same text, different tags | `UpdateTextStyleRequest` |
| Table added | New `<table>` element | `InsertTableRequest` |
| Table deleted | Missing `<table>` | `DeleteContentRangeRequest` |
| Row added | New `<tr>` in table | `InsertTableRowRequest` |
| Cells merged | `colspan`/`rowspan` changed | `MergeTableCellsRequest` |

### Critical: Edit Backwards

Process requests from highest to lowest index:

```python
# Sort by index descending
requests.sort(key=lambda r: get_index(r), reverse=True)
```

---

## BatchUpdate Generation

### Request Types

#### InsertTextRequest
```json
{
  "insertText": {
    "location": {"index": 100, "tabId": "t.0"},
    "text": "New text"
  }
}
```

#### DeleteContentRangeRequest
```json
{
  "deleteContentRange": {
    "range": {"startIndex": 100, "endIndex": 150, "tabId": "t.0"}
  }
}
```

#### UpdateTextStyleRequest
```json
{
  "updateTextStyle": {
    "range": {"startIndex": 100, "endIndex": 110, "tabId": "t.0"},
    "textStyle": {"bold": true},
    "fields": "bold"
  }
}
```

#### InsertTableRequest
```json
{
  "insertTable": {
    "location": {"index": 100, "tabId": "t.0"},
    "rows": 3,
    "columns": 2
  }
}
```

#### MergeTableCellsRequest
```json
{
  "mergeTableCells": {
    "tableRange": {
      "tableCellLocation": {
        "tableStartLocation": {"index": 100, "tabId": "t.0"},
        "rowIndex": 0,
        "columnIndex": 0
      },
      "rowSpan": 2,
      "columnSpan": 2
    }
  }
}
```

---

## Limitations and Constraints

### Not Editable via HTML

| Element | Representation | Notes |
|---------|----------------|-------|
| Equations | `<Equation/>` | Read-only placeholder |
| Drawings | Not represented | Skipped |
| Comments | Not represented | Use API directly |
| Suggestions | Not represented | Use API directly |

### API Constraints

1. **Cannot delete final newline**: Every body/cell/header/footer must end with newline
2. **Cannot partially delete tables**: Must delete entire table
3. **Cannot insert at table boundary**: Insert in paragraph before table
4. **Surrogate pairs**: Cannot split emoji/astral characters

### styles.json

Captures styling not represented in HTML:

```json
{
  "paragraphStyles": {
    "p[0]": {
      "spaceAbove": {"magnitude": 12, "unit": "PT"},
      "lineSpacing": 150
    }
  },
  "textStyles": {
    "p[0].span[0]": {
      "fontSize": {"magnitude": 11, "unit": "PT"},
      "fontFamily": "Arial"
    }
  },
  "tableStyles": {
    "table[0]": {
      "borderWidth": {"magnitude": 1, "unit": "PT"}
    }
  },
  "lists": {
    "kix.abc123": {
      "nestingLevels": [{"glyphType": "DECIMAL"}]
    }
  }
}
```

---

## Complete Example

### Input (Google Docs API Response Summary)

- Title: "Project Plan"
- 2 tabs: "Overview", "Details"
- Header with page numbers
- Body with heading, paragraphs, table, list

### Output (document.html)

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Project Plan</title>
  <script type="application/json" id="doc-metadata">
  {
    "documentId": "1abc2def...",
    "title": "Project Plan",
    "revisionId": "ALm37BV...",
    "locale": "en-US"
  }
  </script>
</head>
<body>
  <article id="t.0" data-title="Overview">
    <Header id="kix.header1">
      <p>Project Plan - Page <AutoText type="PAGE_NUMBER"/></p>
    </Header>

    <main>
      <h1 class="title">Project Overview</h1>

      <p>This document outlines the <strong>key milestones</strong> for Q1.</p>

      <hr/>

      <h2 id="kix.timeline">Timeline</h2>

      <table>
        <tr>
          <td><strong>Phase</strong></td>
          <td><strong>Date</strong></td>
        </tr>
        <tr>
          <td>Planning</td>
          <td>Jan 15</td>
        </tr>
        <tr>
          <td>Development</td>
          <td>Feb 1</td>
        </tr>
      </table>

      <h2 id="kix.team">Team</h2>

      <ul class="bullet">
        <li>Lead: <Person email="alice@example.com" name="Alice"/></li>
        <li>Dev: <Person email="bob@example.com" name="Bob"/></li>
      </ul>

      <p>See details<FootnoteRef id="fn1" num="1"/> in the appendix.</p>
    </main>

    <Footer id="kix.footer1">
      <p>Confidential</p>
    </Footer>

    <Footnote id="fn1">
      <p>Additional context about the project scope.</p>
    </Footnote>
  </article>

  <article id="t.abc123" data-title="Details">
    <main>
      <h1 id="kix.details">Detailed Specifications</h1>
      <p>...</p>
    </main>
  </article>
</body>
</html>
```
