# SML Reference

Slide Markup Language (SML) - HTML-inspired format for Google Slides content.

## Document Structure

```xml
<Presentation id="abc123" w="720pt" h="405pt" locale="en">
  <Slides>
    <Slide id="slide_1" layout="layout_1">
      <TextBox id="title" class="x-72 y-144 w-576 h-80 font-family-roboto text-size-36">
        <P><T>Slide Title</T></P>
      </TextBox>
      <Rect class="x-100 y-300 w-200 h-100 fill-#4285f4"/>
    </Slide>
  </Slides>
</Presentation>
```

## Critical Rules

  All text MUST be in <P><T>text</T></P> structure - never bare text
  Never use \n in text - create new <P> elements instead
  Never modify id or range attributes - they are internal references
  Use hex colors (#rrggbb) - named colors are not supported

## Element Types

Text: TextBox
Shapes: Rect, RoundRect, Ellipse, Triangle, Diamond, Pentagon, Hexagon,
        Octagon, Parallelogram, Trapezoid
Arrows: ArrowLeft, ArrowRight, ArrowUp, ArrowDown, ArrowLeftRight, ArrowUpDown
Callouts: CalloutWedgeRect, CalloutWedgeRoundRect, CalloutWedgeEllipse, Speech
Other: Image, Line, Table, Group

---

## Position & Size Classes

  x-{n}        X position in points
  y-{n}        Y position in points
  w-{n}        Width in points
  h-{n}        Height in points
  rotate-{n}   Rotation in degrees clockwise (-rotate-{n} for counter-clockwise)

---

## Fill Classes

  fill-#rrggbb          Solid hex color
  fill-#rrggbb/80       With opacity (0-100)
  fill-theme-accent1    Theme color (accent1, accent2, dark1, dark2, light1, light2)
  fill-none             No fill (transparent)

---

## Stroke Classes

  stroke-#rrggbb        Stroke color
  stroke-w-{n}          Stroke weight in points
  stroke-dash           Dashed line
  stroke-none           No stroke

---

## Text Container Classes (on TextBox)

  font-family-{name}          Font family (roboto, arial, etc.)
  font-family-[Open Sans]     Custom font (brackets for multi-word)
  text-size-{n}               Font size in points
  text-color-#rrggbb          Text color
  text-align-left/center/right   Horizontal alignment
  content-top/middle/bottom   Vertical alignment

---

## Text Run Classes (on <T>)

  bold            Bold
  italic          Italic
  underline       Underline
  line-through    Strikethrough
  font-weight-700 Explicit weight (100-900)
  href="url"      Hyperlink (or #slide_id for internal link)

---

## Paragraph Classes (on <P>)

  bullet bullet-disc       Bullet list item (disc)
  bullet bullet-digit      Numbered list item
  indent-level-1           Nesting level (0-8)
  leading-{n}              Line spacing (100=single, 150=1.5x, 200=double)
  space-above-{n}          Space above paragraph in points
  space-below-{n}          Space below paragraph in points

---

## Slide Attributes

  <Slide layout="layout_1">         Slide layout
  <Slide class="bg-#ffffff">        Slide background color
  <Slide skipped>                   Hidden slide

---

## Common Editing Patterns

Change text:
  <P><T>New text here</T></P>

Bold part of text:
  <P><T>Normal </T><T class="bold">bold part</T><T> normal again</T></P>

Hyperlink:
  <T class="text-color-#2563eb underline" href="https://example.com">link text</T>

Bullet list:
  <P class="bullet bullet-disc"><T>First item</T></P>
  <P class="bullet bullet-disc indent-level-1"><T>Nested item</T></P>

Change shape color:
  <Rect class="x-100 y-100 w-200 h-100 fill-#34a853"/>

Move/resize element:
  <TextBox class="x-150 y-144 w-500 h-50 ...">

Shadow:
  shadow, shadow-sm, shadow-md, shadow-lg, shadow-none

---

## Range Attribute (Read-Only)

The range attribute on <P> and <T> tracks character positions for the diff
algorithm. Never modify it.

  <P range="0-24"><T range="0-11">Hello World</T></P>
