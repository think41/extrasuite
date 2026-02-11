---
name: extradoc
description: Read, write, and edit existing Google Docs. Use when user asks to work with Google Docs, documents, or shares a docs.google.com/documents URL.
---

# ExtraDoc Agent Guide

Edit Google Docs via local XML files using the pull-edit-push workflow.

## Workflow

```bash
uvx extrasuite doc pull <url> [output_dir]    # Download document to local folder
# <output_dir>/<document_id>/ now has document.xml and styles.xml that you can edit
uvx extrasuite doc diff <folder>              # Preview changes (dry run)
uvx extrasuite doc push <folder>              # Push changes back to the Google document
```

**Always re-pull after push** — the `.pristine/` state is not auto-updated.

## Directory Structure

```
<document_id>/
  document.xml            # Document content
  styles.xml              # Style definitions
  .pristine/              # DO NOT TOUCH — used by diff/push
  .raw/                   # Raw API response (only for debugging)
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

### Special Elements

| Element | Can Add | Can Modify | Can Delete | Notes |
|---------|---------|------------|------------|-------|
| `<hr/>` | No | No | No | API limitation |
| `<pagebreak/>` | Yes | N/A | Yes | |
| `<columnbreak/>` | No | No | No | API limitation — no `insertColumnBreak` |
| `<image/>` | No | No | No | API exists (`insertInlineImage`) but not yet implemented |
| `<footnote>` | Yes | Yes | Yes | |
| `<autotext/>` | No | No | No | API limitation |
| `<person/>` | Yes | Yes | Yes | Attr: `email`. The `name` attr is read-only (auto-resolved by Google) |
| `<date/>` | Yes | Yes | Yes | E.g. `<date timestamp="2025-12-25T00:00:00Z" dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"/>`. See [date-time.md](date-time.md) for all formats |
| `<richlink/>` | No | No | No | Rich link chip. Attrs: `url`, `title`. Takes 1 index unit |
| `<equation/>` | No | No | No | Equation. Attr: `length` (index units consumed) |

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

1. **No newline characters inside content elements.** Each `<p>`, `<h1>`–`<h6>`, `<li>`, `<title>`, `<subtitle>`, and inline tags (`<b>`, `<i>`, `<span>`, `<a>`, etc.) must be a single line of text. To start a new line, close the element and open a new one. Newlines inside content are misinterpreted by the Google Docs API and cause corruption (e.g. spurious list items). Container elements (`<doc>`, `<tab>`, `<body>`, `<table>`, `<tr>`, `<td>`, `<header>`, `<footer>`, `<footnote>`, `<toc>`, `<style>`, `<meta>`) may contain whitespace/newlines between their children. **Diff/push will reject documents that violate this rule.**
2. **Always re-pull after push.** The `.pristine/` state is not auto-updated.
3. **Do not modify `.pristine/` or `.raw/`.** Internal directories used by push.
4. **Every `<td>` must contain at least one `<p>`.** Even empty cells.
5. **`<hr/>`, `<image/>`, `<autotext/>` are read-only.** Cannot add/remove.
6. **XML-escape special characters.** `&amp;` `&lt;` `&gt;` `&quot;` in text content.
7. **List items are flat.** No `<ul>`/`<ol>` wrappers — nesting via `level` attribute only.
8. **The `<style>` wrapper applies a class to multiple consecutive elements.** Not a style definition.

---

## Comments

Comments appear in two files: inline `<comment-ref>` tags in `document.xml` show where comments are, and `comments.xml` stores the full comment content and replies.

### Reading Comments

In `document.xml`, commented text is wrapped with `<comment-ref>`:

```xml
<p>Some text <comment-ref id="AABcdEf" message="This needs revisi..." replies="2" resolved="false"><b>important section</b></comment-ref> more text.</p>
```

- `id` links to the full comment in `comments.xml`
- `message`, `replies`, `resolved` are read-only summaries (regenerated on pull)

In `comments.xml`, full comment details:

```xml
<comments fileId="DOCUMENT_ID">
  <comment id="AABcdEf" author="John Doe &lt;john@example.com&gt;"
           time="2025-01-15T10:30:00Z" resolved="false">
    <content>This paragraph needs revision.</content>
    <replies>
      <reply id="BBBcdEf" author="Jane Smith &lt;jane@example.com&gt;"
             time="2025-01-15T11:00:00Z">I agree, let me fix it.</reply>
    </replies>
  </comment>
</comments>
```

### Adding a New Comment

1. Wrap the target text in `document.xml` with `<comment-ref id="any_unique_id">`:

```xml
<p>This <comment-ref id="my_comment_1">section needs work</comment-ref> badly.</p>
```

2. Add a matching entry in `comments.xml`:

```xml
<comment id="my_comment_1">
  <content>This section needs a citation.</content>
</comment>
```

For unanchored comments (no specific text), just add in `comments.xml` without a `<comment-ref>`.

### Replying to a Comment

Add a `<reply>` without `id` inside an existing comment's `<replies>` in `comments.xml`:

```xml
<comment id="AABcdEf">
  <replies>
    <reply id="BBBcdEf" ...>Existing reply</reply>
    <reply>I will revise this paragraph.</reply>
  </replies>
</comment>
```

### Resolving a Comment

Set `resolved="true"` on an existing comment in `comments.xml`:

```xml
<comment id="AABcdEf" resolved="true"/>
```

### Workflow Tip

When instructed to address a comment, make the document edit in `document.xml` AND add a reply in `comments.xml` explaining what was done. Then resolve the comment if appropriate.

---

## Specialized Guides

- **[date-time.md](date-time.md)** — Date/time element formats, attributes, and examples
- **[style-reference.md](style-reference.md)** — Complete style property reference, inheritance rules, table cell styling
- **[troubleshooting.md](troubleshooting.md)** — Common errors, API limitations, debugging tips
