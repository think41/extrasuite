# Style Reference

Complete reference for the ExtraDoc style system. Styles are defined in `styles.xml` and applied throughout `document.xml` via `class` attributes.

---

## How Styles Work

### Style Inheritance

Styles cascade through four levels. Later levels override earlier ones:

1. **Base style** — `_base` in `styles.xml` (document default)
2. **Section class** — `class` on `<body>`, `<header>`, `<footer>` elements
3. **Element class** — `class` on `<p>`, `<td>`, `<h1>`, `<li>`, etc.
4. **Inline formatting** — `<b>`, `<i>`, `<span class="...">`, etc.

Properties not specified at a given level are inherited from the level above.

### Style Definitions

Each `<style>` in `styles.xml` only includes properties that **deviate** from the base:

```xml
<styles>
  <!-- Base: everything inherits from this -->
  <style id="_base" font="Arial" size="11pt" color="#000000" bold="0" italic="0"/>

  <!-- Only bold differs from base -->
  <style id="JF4QL" bold="1"/>

  <!-- Color and bold differ -->
  <style id="a40x2" color="#FF0000" bold="1"/>

  <!-- Font, size, and background differ -->
  <style id="JdcUE" font="Courier" size="10pt" bg="#F5F5F5"/>
</styles>
```

### Style IDs

- `_base` is reserved for the document base style
- Other IDs are auto-generated 5-character hashes based on the property values
- Same properties always produce the same ID (deterministic)
- When creating new styles, use any unique short string (e.g., `warn`, `code`, `hi1`)

---

## Text Style Properties

Applied via `<span class="...">` on inline text or via `class` on block elements.

| Property | Format | Example | Description |
|----------|--------|---------|-------------|
| `font` | Font name | `font="Courier New"` | Font family |
| `size` | Number + `pt` | `size="14pt"` | Font size in points |
| `color` | Hex color | `color="#FF0000"` | Text color |
| `bg` | Hex color | `bg="#FFFF00"` | Text background/highlight |
| `bold` | `0` or `1` | `bold="1"` | Bold |
| `italic` | `0` or `1` | `italic="1"` | Italic |
| `underline` | `0` or `1` | `underline="1"` | Underline |
| `strikethrough` | `0` or `1` | `strikethrough="1"` | Strikethrough |

### Text Style Examples

```xml
<!-- Highlighted text -->
<style id="hilite" bg="#FFFF00"/>

<!-- Code-style text -->
<style id="code" font="Courier New" size="10pt" bg="#F5F5F5"/>

<!-- Error text -->
<style id="err" color="#CC0000" bold="1"/>

<!-- Subtle text -->
<style id="muted" color="#888888" size="9pt"/>
```

---

## Paragraph Style Properties

Applied via `class` on `<p>`, `<h1>`-`<h6>`, `<li>`, or `<style>` wrapper elements.

| Property | Format | Example | Description |
|----------|--------|---------|-------------|
| `alignment` | Enum | `alignment="CENTER"` | Text alignment |
| `lineSpacing` | Number | `lineSpacing="1.5"` | Line spacing multiplier |
| `spaceAbove` | Number + `pt` | `spaceAbove="12pt"` | Space above paragraph |
| `spaceBelow` | Number + `pt` | `spaceBelow="6pt"` | Space below paragraph |
| `indentLeft` | Number + `pt` | `indentLeft="36pt"` | Left indent |
| `indentRight` | Number + `pt` | `indentRight="36pt"` | Right indent |
| `indentFirstLine` | Number + `pt` | `indentFirstLine="18pt"` | First line indent |

**Alignment values:** `START`, `CENTER`, `END`, `JUSTIFIED`

### Paragraph Style Examples

```xml
<!-- Centered paragraph -->
<style id="center" alignment="CENTER"/>

<!-- Block quote style -->
<style id="quote" italic="1" indentLeft="36pt" color="#666666"/>

<!-- Double-spaced -->
<style id="dbl" lineSpacing="2.0"/>

<!-- Paragraph with spacing -->
<style id="spaced" spaceAbove="12pt" spaceBelow="12pt"/>
```

### Combining Text and Paragraph Properties

A single style can include both text and paragraph properties:

```xml
<style id="quote" italic="1" color="#666666" indentLeft="36pt" spaceAbove="6pt" spaceBelow="6pt"/>
```

---

## Table Cell Style Properties

Applied via `class` on `<td>` elements. Cell style IDs typically start with `cell-`.

| Property | Format | Example | Description |
|----------|--------|---------|-------------|
| `bg` | Hex color | `bg="#FFFFCC"` | Cell background color |
| `valign` | Enum | `valign="top"` | Vertical alignment |
| `borderTop` | `width,color,style` | `borderTop="2,#FF0000,SOLID"` | Top border |
| `borderBottom` | `width,color,style` | `borderBottom="1,#000000,SOLID"` | Bottom border |
| `borderLeft` | `width,color,style` | `borderLeft="1,#CCCCCC,SOLID"` | Left border |
| `borderRight` | `width,color,style` | `borderRight="1,#CCCCCC,SOLID"` | Right border |
| `paddingTop` | Number + `pt` | `paddingTop="5pt"` | Top padding |
| `paddingBottom` | Number + `pt` | `paddingBottom="5pt"` | Bottom padding |
| `paddingLeft` | Number + `pt` | `paddingLeft="5pt"` | Left padding |
| `paddingRight` | Number + `pt` | `paddingRight="5pt"` | Right padding |

**Vertical alignment values:** `top`, `middle`, `bottom`

**Border format:** `width,color,style` where:
- `width` — border width in points (e.g., `1`, `2`, `3`)
- `color` — hex color (e.g., `#000000`, `#FF0000`)
- `style` — border style: `SOLID`, `DOTTED`, `DASHED`

### Table Cell Style Examples

```xml
<!-- Header cell with background and borders -->
<style id="cell-hdr" bg="#336699" valign="middle"
       borderBottom="2,#000000,SOLID"
       paddingTop="4pt" paddingBottom="4pt" paddingLeft="6pt" paddingRight="6pt"/>

<!-- Alternating row background -->
<style id="cell-alt" bg="#F5F5F5"/>

<!-- Cell with red border -->
<style id="cell-warn" borderTop="2,#FF0000,SOLID" borderBottom="2,#FF0000,SOLID"
       borderLeft="2,#FF0000,SOLID" borderRight="2,#FF0000,SOLID"/>
```

### Applying Cell Styles

```xml
<table rows="2" cols="2" id="abc123">
  <tr id="row1">
    <td id="c1" class="cell-hdr"><p><b>Name</b></p></td>
    <td id="c2" class="cell-hdr"><p><b>Value</b></p></td>
  </tr>
  <tr id="row2">
    <td id="c3"><p>Alice</p></td>
    <td id="c4" class="cell-alt"><p>100</p></td>
  </tr>
</table>
```

---

## Column Widths

Set fixed column widths using `<col>` elements inside `<table>`:

```xml
<table rows="2" cols="3" id="abc123">
  <col index="0" width="200pt"/>
  <col index="1" width="100pt"/>
  <tr>...</tr>
</table>
```

- `index` — 0-based column index
- `width` — width in points
- Columns without `<col>` elements use automatic sizing
- `<col>` elements must appear before the first `<tr>`

---

## The `<style>` Wrapper Element

The `<style>` element (in `document.xml`, not `styles.xml`) applies a class to multiple consecutive elements:

```xml
<style class="JdcUE">
  <p>def process_data():</p>
  <p>    validate()</p>
  <p>    transform()</p>
  <p>    return result</p>
</style>
```

This is equivalent to applying `class="JdcUE"` to each `<p>` individually. Use it when multiple consecutive elements share the same style.

---

## Creating Custom Styles: Recipes

### Highlighted paragraph
```xml
<!-- styles.xml -->
<style id="hilite" bg="#FFFF00"/>

<!-- document.xml -->
<p class="hilite">This entire paragraph is highlighted.</p>
```

### Code block
```xml
<!-- styles.xml -->
<style id="code" font="Courier New" size="10pt" bg="#F0F0F0"/>

<!-- document.xml -->
<style class="code">
  <p>function hello() {</p>
  <p>  console.log("Hello!");</p>
  <p>}</p>
</style>
```

### Callout/warning box
```xml
<!-- styles.xml -->
<style id="callout" bg="#FFF3CD" indentLeft="18pt" indentRight="18pt"
       spaceAbove="6pt" spaceBelow="6pt"/>

<!-- document.xml -->
<style class="callout">
  <p><b>Warning:</b> This action cannot be undone.</p>
</style>
```

### Styled table header
```xml
<!-- styles.xml -->
<style id="cell-thdr" bg="#1A73E8" valign="middle" paddingTop="4pt" paddingBottom="4pt"/>
<style id="thdr-text" color="#FFFFFF" bold="1"/>

<!-- document.xml -->
<tr>
  <td class="cell-thdr"><p><span class="thdr-text">Column 1</span></p></td>
  <td class="cell-thdr"><p><span class="thdr-text">Column 2</span></p></td>
</tr>
```
