# ExtraDoc Agent Guide

Edit Google Docs via local XML files using the pull-edit-push workflow.

## Workflow

```bash
python -m extradoc pull <url>       # Download document to local folder
# ... edit XML files ...
python -m extradoc push <folder>    # Apply changes to Google Docs
python -m extradoc diff <folder>    # Dry run — shows batchUpdate JSON without calling API
```

**Always re-pull after push** — the `.pristine/` state is not auto-updated.

## Directory Structure

```
<document_id>/
  document.xml            # Document content — edit this
  styles.xml              # Style definitions (referenced by class attributes)
  .pristine/              # DO NOT TOUCH — used by diff/push
  .raw/                   # Raw API response (for debugging)
```

Start with `document.xml`. Read `styles.xml` only when you need to understand or modify styling.

---

## Supported Tags

### Block Elements

| Tag | Notes |
|-----|-------|
| `<p>` | Paragraph. Can carry `class`, `align`, `lineSpacing`, `spaceAbove`, `spaceBelow`, `indentLeft`, `indentRight`, `indentFirstLine` |
| `<h1>` – `<h6>` | Headings. Same optional attributes as `<p>` |
| `<title>`, `<subtitle>` | Document title/subtitle |
| `<li>` | List item. Attributes: `type`, `level`, `class` |
| `<table>` | Table container. Attribute: `id` |
| `<tr>` | Table row. Attribute: `id` |
| `<td>` | Table cell. Attributes: `id`, `class`, `colspan`, `rowspan`. Must contain at least one `<p>` |
| `<col>` | Column width (optional). Attributes: `id`, `index`, `width` (e.g. `width="150pt"`) |
| `<toc>` | Table of contents (read-only) |
| `<style class="...">` | Wrapper — applies a class to multiple consecutive children |

### Inline Elements

| Tag | Effect |
|-----|--------|
| `<b>`, `<i>`, `<u>`, `<s>` | Bold, italic, underline, strikethrough |
| `<sup>`, `<sub>` | Superscript, subscript |
| `<a href="...">` | Hyperlink |
| `<span class="...">` | Custom inline style |

### Special / Read-Only

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

## Lists

Flat structure — no `<ul>`/`<ol>` wrappers. Nesting is controlled by `level`.

```xml
<li type="bullet" level="0">Top item</li>
<li type="bullet" level="1">Nested item</li>
```

**Types:** `bullet`, `decimal`, `alpha`, `roman`, `checkbox`

---

## Tables

```xml
<table id="abc123">
  <col id="xK9mR" index="0" width="150pt"/>
  <tr id="row1">
    <td id="c1" class="cell-hdr"><p><b>Name</b></p></td>
    <td id="c2"><p><b>Value</b></p></td>
  </tr>
  <tr id="row2">
    <td id="c3"><p>Alice</p></td>
    <td id="c4"><p>100</p></td>
  </tr>
</table>
```

- `<table>` has only `id` (no `rows`/`cols` attributes)
- `<col>` elements are optional — only present when column widths are explicitly set
- Every `<td>` must contain at least one `<p>`, even if empty
- `colspan`/`rowspan` are visual metadata — merged cells still exist as physical `<td>` elements (each row always has the same number of `<td>` elements)

---

## Style System

Styles are CSS-like classes defined in `styles.xml`, referenced via `class` attributes in `document.xml`.

### styles.xml

```xml
<styles>
  <style id="_base" font="Arial" size="11pt" color="#000000" bold="0" italic="0"/>
  <style id="JdcUE" font="Courier" size="10pt" bg="#F5F5F5"/>
  <style id="rmHiM" alignment="CENTER"/>
  <style id="cell-jT0KF" bg="#FFFFCC" borderBottom="2,#FF0000,SOLID" valign="top"/>
</styles>
```

- `_base` is the document default — all content inherits from it
- Other styles define only properties that **deviate** from the base

### Style Properties

**Text:** `font`, `size`, `color`, `bg`, `bold`, `italic`, `underline`, `strikethrough` (0/1 for toggles, hex for colors, `Npt` for sizes)

**Paragraph:** `alignment` (`START`/`CENTER`/`END`/`JUSTIFIED`), `lineSpacing` (100=single, 200=double), `spaceAbove`, `spaceBelow`, `indentLeft`, `indentRight`, `indentFirstLine`

**Table cell:** `bg`, `valign` (`top`/`middle`/`bottom`), `borderTop`/`borderBottom`/`borderLeft`/`borderRight` (format: `width,color,style`), `paddingTop`/`paddingBottom`/`paddingLeft`/`paddingRight`

### Creating a New Style

```xml
<!-- styles.xml -->
<style id="warn" color="#FF8800" bold="1"/>

<!-- document.xml -->
<p class="warn">Warning: check your input.</p>
```

Use any unique short string as the ID. For full property reference, see [style-reference.md](style-reference.md).

---

## Document Structure

```xml
<doc id="DOCUMENT_ID" revision="REVISION_ID">
  <meta><title>Document Title</title></meta>
  <tab id="t.0" title="Tab 1" class="_base">
    <body>
      <!-- All document content -->
    </body>
    <header id="kix.abc123" class="_base">...</header>
    <footer id="kix.def456" class="_base">...</footer>
  </tab>
</doc>
```

Each `<tab>` contains `<body>` plus optional `<header>`, `<footer>`, and `<footnote>` elements. Multi-tab documents have multiple `<tab>` elements.

---

## Key Rules

1. **Always re-pull after push.** The `.pristine/` state is not auto-updated.
2. **Do not modify `.pristine/` or `.raw/`.** Internal directories used by push.
3. **Every `<td>` must contain at least one `<p>`.** Even empty cells.
4. **`<hr/>`, `<image/>`, `<autotext/>`, `<person/>` are read-only.** Cannot add/remove.
5. **XML-escape special characters.** `&amp;` `&lt;` `&gt;` `&quot;` in text content.
6. **List items are flat.** No `<ul>`/`<ol>` wrappers — nesting via `level` attribute only.
7. **The `<style>` wrapper applies a class to multiple consecutive elements.** Not a style definition.

---

## Specialized Guides

- **[style-reference.md](style-reference.md)** — Complete style property reference, inheritance rules, table cell styling
- **[troubleshooting.md](troubleshooting.md)** — Common errors, API limitations, debugging tips
