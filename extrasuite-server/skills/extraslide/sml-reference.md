# SML Quick Reference

Slide Markup Language (SML) is an HTML-inspired format for representing Google Slides. This reference covers the most common elements and classes.

## Document Structure

```xml
<Presentation id="abc123" w="720pt" h="405pt" locale="en">
  <Images>
    <Img id="hash123" url="https://..."/>
  </Images>
  <Masters>
    <Master id="master_1" name="Simple Light">...</Master>
  </Masters>
  <Layouts>
    <Layout id="layout_1" master="master_1" name="Title Slide">...</Layout>
  </Layouts>
  <Slides>
    <Slide id="slide_1" layout="layout_1">...</Slide>
  </Slides>
</Presentation>
```

## Element Types

### Text Elements
- `<TextBox>` - Text container (most common)

### Basic Shapes
- `<Rect>`, `<RoundRect>`, `<Ellipse>`, `<Triangle>`, `<Diamond>`
- `<Pentagon>`, `<Hexagon>`, `<Octagon>`, `<Parallelogram>`, `<Trapezoid>`

### Arrows
- `<ArrowLeft>`, `<ArrowRight>`, `<ArrowUp>`, `<ArrowDown>`
- `<ArrowLeftRight>`, `<ArrowUpDown>`

### Callouts
- `<CalloutWedgeRect>`, `<CalloutWedgeRoundRect>`, `<CalloutWedgeEllipse>`
- `<CalloutCloud>`, `<Speech>`

### Other Elements
- `<Image>` - Images
- `<Line>` - Lines and connectors
- `<Table>` - Tables
- `<Group>` - Grouped elements

## Position & Size Classes

```xml
<!-- Position (translate) -->
<TextBox class="x-72 y-144">        <!-- x=72pt, y=144pt -->

<!-- Size -->
<TextBox class="w-400 h-50">        <!-- width=400pt, height=50pt -->

<!-- Rotation -->
<TextBox class="rotate-45">         <!-- 45 degrees clockwise -->
<TextBox class="-rotate-45">        <!-- Counter-clockwise -->
```

## Fill & Stroke Classes

```xml
<!-- Solid fill (hex color) -->
<Rect class="fill-#4285f4">         <!-- Google Blue -->
<Rect class="fill-#ffffff">         <!-- White -->

<!-- Fill with opacity -->
<Rect class="fill-#4285f4/80">      <!-- 80% opacity -->

<!-- Theme colors -->
<Rect class="fill-theme-accent1">
<Rect class="fill-theme-dark1">

<!-- No fill -->
<Rect class="fill-none">

<!-- Stroke/outline -->
<Rect class="stroke-#1a73e8 stroke-w-2">  <!-- Blue, 2pt -->
<Rect class="stroke-dash">           <!-- Dashed -->
<Rect class="stroke-none">           <!-- No stroke -->
```

## Text Content Structure

**CRITICAL**: All text must be in explicit `<P>` and `<T>` elements.

```xml
<!-- Simple text -->
<TextBox id="title" class="x-72 y-144 w-400 h-50 font-family-roboto text-size-24">
  <P><T>Hello World</T></P>
</TextBox>

<!-- Multiple paragraphs -->
<TextBox class="...">
  <P><T>First paragraph.</T></P>
  <P><T>Second paragraph.</T></P>
</TextBox>

<!-- Styled text within paragraph -->
<TextBox class="font-family-roboto text-size-14 text-color-#333333">
  <P>
    <T>Normal text </T>
    <T class="bold">bold</T>
    <T> and </T>
    <T class="italic">italic</T>
    <T>.</T>
  </P>
</TextBox>
```

### Text NEVER Rules
- NEVER put bare text in `<TextBox>` - use `<P><T>text</T></P>`
- NEVER put bare text in `<P>` - use `<T>text</T>`
- NEVER use `\n` in text content - create new `<P>` elements

## Text Styling Classes

### Font
```xml
<TextBox class="font-family-roboto">
<TextBox class="font-family-arial">
<TextBox class="font-family-[Open Sans]">  <!-- Custom font -->
```

### Size
```xml
<TextBox class="text-size-12">
<TextBox class="text-size-18">
<TextBox class="text-size-24">
<TextBox class="text-size-36">
```

### Weight & Style
```xml
<T class="bold">                <!-- Bold -->
<T class="italic">              <!-- Italic -->
<T class="underline">           <!-- Underline -->
<T class="line-through">        <!-- Strikethrough -->
<T class="font-weight-700">     <!-- Explicit weight -->
```

### Color
```xml
<TextBox class="text-color-#333333">      <!-- Hex color -->
<TextBox class="text-color-theme-text1">  <!-- Theme color -->
```

### Alignment
```xml
<TextBox class="text-align-left">
<TextBox class="text-align-center">
<TextBox class="text-align-right">
<TextBox class="content-top">      <!-- Vertical: top -->
<TextBox class="content-middle">   <!-- Vertical: middle -->
<TextBox class="content-bottom">   <!-- Vertical: bottom -->
```

## Paragraph Styling

```xml
<!-- Line spacing -->
<P class="leading-100">             <!-- Single -->
<P class="leading-150">             <!-- 1.5 lines -->
<P class="leading-200">             <!-- Double -->

<!-- Paragraph spacing -->
<P class="space-above-12">
<P class="space-below-6">
```

## Bullets & Lists

```xml
<TextBox class="...">
  <P class="bullet bullet-disc"><T>First item</T></P>
  <P class="bullet bullet-disc indent-level-1"><T>Nested item</T></P>
</TextBox>

<!-- Numbered list -->
<TextBox class="...">
  <P class="bullet bullet-digit"><T>First item</T></P>
  <P class="bullet bullet-digit"><T>Second item</T></P>
</TextBox>
```

## Images

```xml
<Image id="img1" class="x-100 y-100 w-300 h-200" src="img:hash123"/>

<!-- Image adjustments -->
<Image class="opacity-50">          <!-- Transparency -->
<Image class="brightness-50">       <!-- Brighter -->
<Image class="contrast-50">         <!-- Higher contrast -->
```

## Lines

```xml
<!-- Straight line -->
<Line id="line1" class="line-straight stroke-#3b82f6 stroke-w-2"/>

<!-- With arrows -->
<Line class="arrow-end-fill">       <!-- Arrow at end -->
<Line class="arrow-start-fill arrow-end-fill">  <!-- Both ends -->
```

## Links

```xml
<!-- Shape-level link -->
<TextBox href="https://example.com">Click me</TextBox>

<!-- Text run link -->
<T class="text-color-#2563eb underline" href="https://example.com">link text</T>

<!-- Internal slide link -->
<T href="#slide_5">Go to slide 5</T>
```

## Shadow

```xml
<Rect class="shadow">               <!-- Default shadow -->
<Rect class="shadow-md">            <!-- Medium shadow -->
<Rect class="shadow-lg">            <!-- Large shadow -->
<Rect class="shadow-none">          <!-- No shadow -->
```

## Slide Operations

### Slide Attributes
```xml
<Slide id="slide_1" layout="layout_title" master="master_1">
<Slide id="slide_2" layout="layout_body" skipped>  <!-- Hidden slide -->
```

### Slide Background
```xml
<Slide class="bg-#ffffff">          <!-- White background -->
<Slide class="bg-theme-light1">     <!-- Theme color -->
<Slide bg-src="https://...">        <!-- Image background -->
```

## Range Attribute (Read-Only)

The `range` attribute on `<P>` and `<T>` contains character indices from the original document:

```xml
<P range="0-24">
  <T range="0-6">Hello </T>
  <T range="6-11">world</T>
</P>
```

**NEVER modify `range` attributes** - they are used internally for diff calculations.

## Common Editing Patterns

### Change Text Content
```xml
<!-- Before -->
<P><T>Old text</T></P>

<!-- After -->
<P><T>New text</T></P>
```

### Add Bold/Italic
```xml
<!-- Before -->
<P><T>Important text</T></P>

<!-- After -->
<P><T class="bold">Important text</T></P>
```

### Change Color
```xml
<!-- Before -->
<TextBox class="fill-#ffffff">

<!-- After -->
<TextBox class="fill-#4285f4">
```

### Add New Paragraph
```xml
<!-- Before -->
<TextBox>
  <P><T>First paragraph.</T></P>
</TextBox>

<!-- After -->
<TextBox>
  <P><T>First paragraph.</T></P>
  <P><T>Second paragraph.</T></P>
</TextBox>
```

### Style Part of Text
```xml
<!-- Before -->
<P><T>Click here for more info.</T></P>

<!-- After -->
<P>
  <T>Click </T>
  <T class="text-color-#2563eb underline" href="https://example.com">here</T>
  <T> for more info.</T>
</P>
```
