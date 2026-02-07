# ExtraDoc Agent Guide

Edit Google Docs via local XML files using the pull-edit-push workflow.

## Workflow

```bash
uv run python -m extradoc pull <url>       # Download document to local folder
# ... edit XML files ...
uv run python -m extradoc pushv2 <folder>  # Apply changes to Google Docs
```

**After push, always re-pull before making more changes** — the pristine state is not auto-updated.

## Directory Structure

```
<document_id>/
  document.xml            # START HERE - document content as XML
  styles.xml              # Style definitions (referenced by class attributes)
  .pristine/              # DO NOT TOUCH - used by push
  .raw/                   # Raw API response (for debugging)
```

## Reading Strategy

1. **Start with `document.xml`** — contains all document content with semantic markup
2. **Read `styles.xml` only when styling changes are needed** — contains style definitions referenced by `class` attributes
3. **Skip `.pristine/` and `.raw/`** — internal use only

---

## document.xml Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<doc id="DOCUMENT_ID" revision="REVISION_ID">
  <meta>
    <title>Document Title</title>
  </meta>

  <body class="_base">
    <!-- All document content goes here -->
  </body>

  <!-- Optional sections -->
  <header id="kix.abc123" class="_base">...</header>
  <footer id="kix.def456" class="_base">...</footer>
</doc>
```

For multi-tab documents, `<body>` is replaced by `<tab>` elements:
```xml
<tab id="t.0" title="Tab Name" class="_base">
  <body>...content...</body>
</tab>
```

---

## Block Elements

### Paragraphs

```xml
<p>Plain text paragraph.</p>
<p class="JdcUE">Paragraph with custom style.</p>
```

### Headings

```xml
<title>Document Title</title>
<subtitle>Document Subtitle</subtitle>
<h1>Heading 1</h1>
<h2>Heading 2</h2>
<h3>Heading 3</h3>
<h4>Heading 4</h4>
<h5>Heading 5</h5>
<h6>Heading 6</h6>
```

Headings can also carry a class: `<h1 class="rmHiM">Centered Heading</h1>`

### Lists

List items are flat (no `<ul>` or `<ol>` wrapper), matching Google Docs' internal model:

```xml
<li type="bullet" level="0">First item</li>
<li type="bullet" level="1">Nested item</li>
<li type="bullet" level="2">Deeply nested</li>
<li type="decimal" level="0">Numbered item</li>
<li type="alpha" level="0">Alphabetic item</li>
<li type="roman" level="0">Roman numeral item</li>
<li type="checkbox" level="0">Checkbox item</li>
```

| Attribute | Values | Description |
|-----------|--------|-------------|
| `type` | `bullet`, `decimal`, `alpha`, `roman`, `checkbox` | List style |
| `level` | `0`, `1`, `2`, ... | Nesting depth (0 = top level) |
| `class` | Style ID | Optional styling |

### Tables

```xml
<table rows="3" cols="2" id="cDyp2nz">
  <col index="0" width="150pt"/>
  <tr id="g9SKchj">
    <td id="gUEeXJW"><p>Cell A1</p></td>
    <td id="8Jw5e9F"><p>Cell B1</p></td>
  </tr>
  <tr id="hK3Lm8n">
    <td id="pQ3vN"><p>Cell A2</p></td>
    <td id="xK9mR"><p>Cell B2</p></td>
  </tr>
  <tr id="jR7Wx2y">
    <td id="a40x2"><p>Cell A3</p></td>
    <td id="JdcUE"><p>Cell B3</p></td>
  </tr>
</table>
```

**Table elements:**
- `<table>` — container with `rows`, `cols`, and `id` attributes
- `<col>` — optional column width metadata (`index` and `width` in pt)
- `<tr>` — row with `id` attribute
- `<td>` — cell with optional `colspan`, `rowspan`, `class`, `id`

**Each cell contains one or more `<p>` elements.** Even empty cells have `<p></p>`.

**Cell styling** uses `class` attribute referencing styles in `styles.xml`:
```xml
<td id="gUEeXJW" class="cell-jT0KF"><p><b>Header</b></p></td>
```

> **Physical Cell Rule:** Each row always has exactly `cols` number of `<td>` elements, regardless of `colspan`. The `colspan`/`rowspan` attributes are visual metadata only — merged cells still exist as physical `<td>` elements. See [troubleshooting.md](troubleshooting.md) for details.

---

## Inline Formatting

Wrap text with these tags. They compose via nesting:

```xml
<p>Normal <b>bold</b> and <b><i>bold italic</i></b> text.</p>
<p>Visit <a href="https://example.com">our site</a> for more.</p>
<p>Text with <span class="Hy4Kp">custom styled</span> words.</p>
```

| Tag | Effect |
|-----|--------|
| `<b>` | Bold |
| `<i>` | Italic |
| `<u>` | Underline |
| `<s>` | Strikethrough |
| `<sup>` | Superscript |
| `<sub>` | Subscript |
| `<a href="...">` | Hyperlink |
| `<span class="...">` | Custom style (font, color, background, etc.) |

---

## Style System

Styles are defined in `styles.xml` and referenced by `class` attributes throughout `document.xml`.

### styles.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<styles>
  <style id="_base" font="Arial" size="11pt" color="#000000" bold="0" italic="0"/>
  <style id="JF4QL" bold="1"/>
  <style id="a40x2" color="#FF0000" bold="1"/>
  <style id="JdcUE" font="Courier" size="10pt" bg="#F5F5F5"/>
  <style id="rmHiM" alignment="CENTER"/>
  <style id="cell-jT0KF" bg="#FFFFCC" borderBottom="2,#FF0000,SOLID" valign="top"/>
</styles>
```

- `_base` is the document-wide default style (all content inherits from it)
- Other styles define only properties that **deviate** from the base
- Style IDs are auto-generated 5-character hashes — stable across pulls

### Applying Styles

```xml
<!-- On a paragraph -->
<p class="JdcUE">Monospace paragraph.</p>

<!-- On a heading -->
<h1 class="rmHiM">Centered Heading</h1>

<!-- On inline text -->
<p>Text with <span class="a40x2">red bold words</span> here.</p>

<!-- On multiple consecutive elements -->
<style class="JdcUE">
  <p>Code line 1</p>
  <p>Code line 2</p>
  <p>Code line 3</p>
</style>

<!-- On a table cell -->
<td class="cell-jT0KF"><p>Styled cell</p></td>
```

### Common Style Properties

**Text:** `font`, `size` (e.g., `11pt`), `color` (e.g., `#FF0000`), `bg` (background), `bold` (`0`/`1`), `italic` (`0`/`1`), `underline` (`0`/`1`), `strikethrough` (`0`/`1`)

**Paragraph:** `alignment` (`START`/`CENTER`/`END`/`JUSTIFIED`), `lineSpacing` (percentage: 100=single, 150=1.5x, 200=double), `spaceAbove`, `spaceBelow`, `indentLeft`, `indentRight`, `indentFirstLine`

**Table cell:** `bg`, `valign` (`top`/`middle`/`bottom`), `borderTop`/`borderBottom`/`borderLeft`/`borderRight` (format: `width,color,style` e.g., `2,#FF0000,SOLID`), `paddingTop`/`paddingBottom`/`paddingLeft`/`paddingRight`

For the complete style property reference, see [style-reference.md](style-reference.md).

### Adding a New Style

To apply formatting not covered by existing styles:

1. Add a new `<style>` element to `styles.xml` with a unique ID (use any short alphanumeric string)
2. Include only the properties that differ from `_base`
3. Reference it via `class` attribute in `document.xml`

```xml
<!-- styles.xml -->
<style id="warn" color="#FF8800" bold="1"/>

<!-- document.xml -->
<p class="warn">Warning: check your input.</p>
```

---

## Special Elements

```xml
<!-- Horizontal rule (read-only — cannot add or remove) -->
<p><hr/></p>

<!-- Page break -->
<p><pagebreak/></p>

<!-- Column break -->
<p>Text before<columnbreak/>Text after</p>

<!-- Image (read-only — cannot add via this workflow) -->
<p><image src="URL" width="100pt" height="50pt" alt="Description"/></p>

<!-- Footnote (inline model — content is inside the tag) -->
<p>See note<footnote id="kix.fn1"><p>Footnote content here.</p></footnote> for details.</p>
```

| Element | Can Add | Can Modify | Can Delete |
|---------|---------|------------|------------|
| `<hr/>` | No | No | No |
| `<pagebreak/>` | Yes | N/A | Yes |
| `<columnbreak/>` | Yes | N/A | Yes |
| `<image/>` | No | No | No |
| `<footnote>` | Partial | Yes | Yes |
| `<autotext/>` | No | No | No |
| `<person/>` | No | No | No |

---

## Headers and Footers

Headers and footers appear as top-level sections after `<body>`:

```xml
<header id="kix.hdr1" class="_base">
  <p>Company Name — Confidential</p>
</header>

<footer id="kix.ftr1" class="rmHiM">
  <p>Page <autotext type="PAGE_NUMBER"/> of <autotext type="PAGE_COUNT"/></p>
</footer>
```

- Edit content of existing headers/footers by modifying their `<p>` elements
- Add a new header/footer by adding a `<header>` or `<footer>` element
- Each header/footer is a separate section with its own styling scope

---

## Common Editing Patterns

### Add a paragraph

Insert a `<p>` element at the desired position within `<body>`:
```xml
<h2>Introduction</h2>
<p>This is a new paragraph added after the heading.</p>
```

### Change text content

Edit the text directly:
```xml
<!-- Before -->
<p>The project deadline is March 15.</p>
<!-- After -->
<p>The project deadline is April 30.</p>
```

### Apply formatting to text

Wrap text with inline tags:
```xml
<!-- Before -->
<p>Important notice about the deadline.</p>
<!-- After -->
<p><b>Important notice</b> about the <i>deadline</i>.</p>
```

### Change a heading level

Change the tag name:
```xml
<!-- Before -->
<h2>Section Title</h2>
<!-- After -->
<h3>Section Title</h3>
```

### Convert paragraph to list item

Replace `<p>` with `<li>`:
```xml
<!-- Before -->
<p>First task</p>
<p>Second task</p>
<!-- After -->
<li type="bullet" level="0">First task</li>
<li type="bullet" level="0">Second task</li>
```

### Add a table

```xml
<table rows="2" cols="3">
  <tr>
    <td><p>Name</p></td>
    <td><p>Role</p></td>
    <td><p>Status</p></td>
  </tr>
  <tr>
    <td><p>Alice</p></td>
    <td><p>Engineer</p></td>
    <td><p>Active</p></td>
  </tr>
</table>
```

### Add a row to an existing table

Update the `rows` attribute and add a `<tr>`:
```xml
<!-- Before: rows="2" -->
<table rows="3" cols="3" id="cDyp2nz">
  <!-- ... existing rows ... -->
  <tr>
    <td><p>Bob</p></td>
    <td><p>Designer</p></td>
    <td><p>Active</p></td>
  </tr>
</table>
```

### Delete content

Remove the XML elements. For example, to delete a paragraph, remove the entire `<p>...</p>` line.

---

## Key Rules

1. **Always re-pull after push.** The `.pristine/` state is not updated automatically. Making further edits without re-pulling will produce incorrect diffs.

2. **Do not modify `.pristine/` or `.raw/`.** These are internal directories used by the push workflow.

3. **Every `<td>` must contain at least one `<p>`.** Even empty cells need `<td><p></p></td>`.

4. **Table `rows` and `cols` attributes must match actual content.** If you add or remove rows/columns, update these attributes accordingly.

5. **Horizontal rules are read-only.** Do not add or remove `<hr/>` elements — the API does not support it.

6. **Images and person mentions are read-only.** These require special API flows not supported in this workflow.

7. **`<autotext/>` elements cannot be inserted.** Page numbers and similar auto-text cannot be added via the API.

8. **Style IDs are opaque.** Don't try to decode them. When creating new styles, use any unique short string as the ID.

9. **List items are flat.** There are no `<ul>` or `<ol>` wrappers. Nesting is controlled entirely by the `level` attribute.

10. **The `<style>` wrapper tag is for applying a class to multiple consecutive elements.** It is not a style definition — those live in `styles.xml`.

---

## Specialized Guides

- **[style-reference.md](style-reference.md)** — Complete style property reference, inheritance rules, table cell styling
- **[troubleshooting.md](troubleshooting.md)** — Common errors, API limitations, debugging tips
