# Style Reference

Styles in extradoc are CSS-like classes defined in styles.xml and applied
via class attributes in document.xml.

## How Styles Work

Styles cascade through three levels (later overrides earlier):
  1. `_default` style in styles.xml (document default)
  2. Section class (class on <body>, <header>, <footer>)
  3. Element class (class on <p>, <td>, <h1>, <li>, etc.)

Each style only defines properties that deviate from the default.

```xml
<!-- styles.xml -->
<styles>
  <text class="_default" font="Arial" size="11pt" color="#000000"/>
  <text class="code"    font="Courier New" size="10pt" bgColor="#F5F5F5"/>
  <text class="warn"   color="#CC0000" bold="true"/>
</styles>

<!-- document.xml -->
<p><t class="warn">Warning: check your input.</t></p>
```

Style class names: `_default` is reserved. Other names are auto-generated
short strings (`s1`, `s2`, …) or any unique short string you choose when
creating new styles (e.g., `warn`, `code`).

---

## Text Style Properties

Defined in `<text class="...">` elements in styles.xml. Applied via `<t class="...">` in document.xml.

  font          Font name: font="Courier New"
  size          Size in points: size="14pt"
  color         Text color: color="#FF0000"
  bgColor       Text background/highlight: bgColor="#FFFF00"
  bold          bold="true"
  italic        italic="true"
  underline     underline="true"
  strikethrough strikethrough="true"

---

## Paragraph Style Properties

Defined in `<para class="...">` elements in styles.xml. Applied via class on `<p>`, `<h1>`-`<h6>`, `<li>`, etc.

  align           START, CENTER, END, JUSTIFIED
  lineSpacing     Percentage: 100=single, 150=1.5x, 200=double
  spaceAbove      Points: spaceAbove="12pt"
  spaceBelow      Points: spaceBelow="6pt"
  indentLeft      Points: indentLeft="36pt"
  indentRight     Points: indentRight="36pt"
  indentFirst     Points: indentFirst="18pt"

---

## Table Cell Style Properties

Defined in `<cell class="...">` elements in styles.xml. Applied via class on `<td>`.

  bgColor         Cell background: bgColor="#FFFFCC"
  valign          top, middle, bottom
  borderTop       width,color,style: borderTop="2,#000000,SOLID"
  borderBottom    Same format
  borderLeft      Same format
  borderRight     Same format
  paddingTop      Points: paddingTop="4pt"
  paddingBottom   Same format
  paddingLeft     Same format
  paddingRight    Same format

Border styles: SOLID, DOTTED, DASHED

---

## The <style> Wrapper Element

In document.xml, `<style class="...">` applies a class to multiple consecutive block elements:

```xml
<style class="code">
  <p>function hello() {</p>
  <p>  return "world";</p>
  <p>}</p>
</style>
```

Equivalent to applying class="code" to each `<p>` individually.

---

## Recipes

Code block (text style only — font, size, background):
  styles.xml:   `<text class="code" font="Courier New" size="10pt" bgColor="#F0F0F0"/>`
  document.xml: `<style class="code"><p>line 1</p><p>line 2</p></style>`

Block quote (paragraph indent + italic text — needs both text and para styles):
  styles.xml:   `<para class="quote" indentLeft="36pt"/>`
                `<text class="quote" italic="true" color="#666666"/>`
  document.xml: `<p class="quote"><t class="quote">Quoted text here.</t></p>`

Table header cell:
  styles.xml:   `<cell class="cell-hdr" bgColor="#336699" valign="middle"
                       borderBottom="2,#000000,SOLID" paddingTop="4pt" paddingBottom="4pt"/>`
  document.xml: `<td class="cell-hdr"><p>Column</p></td>`
