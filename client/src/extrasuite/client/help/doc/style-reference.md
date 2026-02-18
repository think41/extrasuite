# Style Reference

Styles in extradoc are CSS-like classes defined in styles.xml and applied
via class attributes in document.xml.

## How Styles Work

Styles cascade through four levels (later overrides earlier):
  1. _base style in styles.xml (document default)
  2. Section class (class on <body>, <header>, <footer>)
  3. Element class (class on <p>, <td>, <h1>, <li>, etc.)
  4. Inline formatting (<b>, <i>, <span class="...">, etc.)

Each style only defines properties that deviate from the base.

```xml
<!-- styles.xml -->
<styles>
  <style id="_base" font="Arial" size="11pt" color="#000000" bold="0" italic="0"/>
  <style id="code"  font="Courier New" size="10pt" bg="#F5F5F5"/>
  <style id="warn"  color="#CC0000" bold="1"/>
</styles>

<!-- document.xml -->
<p class="warn">Warning: check your input.</p>
```

Style IDs: _base is reserved. Other IDs are 5-char hashes (auto-generated) or
any unique short string you choose when creating new styles (e.g., warn, code).

---

## Text Style Properties

  font          Font name: font="Courier New"
  size          Size in points: size="14pt"
  color         Text color: color="#FF0000"
  bg            Text background/highlight: bg="#FFFF00"
  bold          0 or 1: bold="1"
  italic        0 or 1: italic="1"
  underline     0 or 1: underline="1"
  strikethrough 0 or 1: strikethrough="1"

---

## Paragraph Style Properties

  alignment       START, CENTER, END, JUSTIFIED
  lineSpacing     Percentage: 100=single, 150=1.5x, 200=double
  spaceAbove      Points: spaceAbove="12pt"
  spaceBelow      Points: spaceBelow="6pt"
  indentLeft      Points: indentLeft="36pt"
  indentRight     Points: indentRight="36pt"
  indentFirstLine Points: indentFirstLine="18pt"

---

## Table Cell Style Properties (id prefix: cell-)

  bg              Cell background: bg="#FFFFCC"
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

In document.xml, <style class="..."> applies a class to multiple consecutive elements:

```xml
<style class="code">
  <p>function hello() {</p>
  <p>  return "world";</p>
  <p>}</p>
</style>
```

Equivalent to applying class="code" to each <p> individually.

---

## Recipes

Code block:
  styles.xml: <style id="code" font="Courier New" size="10pt" bg="#F0F0F0"/>
  document.xml: <style class="code"><p>line 1</p><p>line 2</p></style>

Block quote:
  styles.xml: <style id="quote" italic="1" indentLeft="36pt" color="#666666"/>
  document.xml: <p class="quote">Quoted text here.</p>

Table header cell:
  styles.xml: <style id="cell-hdr" bg="#336699" valign="middle"
                     borderBottom="2,#000000,SOLID" paddingTop="4pt" paddingBottom="4pt"/>
  document.xml: <td class="cell-hdr"><p><b>Column</b></p></td>
