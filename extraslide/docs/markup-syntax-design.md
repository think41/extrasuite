# Slide Markup Language (SML) - Tailwind-Inspired Syntax

A complete specification for representing Google Slides as HTML-inspired markup with Tailwind-style classes.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Document Structure](#document-structure)
3. [Presentation Metadata](#presentation-metadata)
4. [Page Types & Properties](#page-types--properties)
5. [Color Scheme](#color-scheme)
6. [Element Types](#element-types)
7. [Position & Transform](#position--transform)
8. [Size & Dimensions](#size--dimensions)
9. [Fill Styling](#fill-styling)
10. [Stroke/Outline Styling](#strokeoutline-styling)
11. [Shadow Styling](#shadow-styling)
12. [Text Content & Styling](#text-content--styling)
13. [Paragraph Styling](#paragraph-styling)
14. [Image Elements](#image-elements)
15. [Line Elements](#line-elements)
16. [Table Elements](#table-elements)
17. [Video Elements](#video-elements)
18. [WordArt Elements](#wordart-elements)
19. [SheetsChart Elements](#sheetschart-elements)
20. [Group Elements](#group-elements)
21. [Speaker Spotlight](#speaker-spotlight)
22. [Notes Pages](#notes-pages)
23. [Actions](#actions)
24. [Placeholders](#placeholders)
25. [Links](#links)
26. [Accessibility](#accessibility)
27. [Complete Examples](#complete-examples)
28. [Class Reference](#class-reference)
29. [Parsing & Serialization Notes](#parsing--serialization-notes)
30. [Limitations](#limitations)
31. [API Coverage Summary](#api-coverage-summary)

---

## Core Principles

1. **Element name = Shape type**: `<TextBox>` not `<Shape shapeType="TEXT_BOX">`
2. **`id` = objectId**: Standard HTML id attribute
3. **`class` = inherited styles**: Points to parent object for style inheritance
4. **All styling as classes**: Tailwind-inspired utility classes
5. **Flat structure**: No nesting (shapes are siblings)
6. **Units**: All dimensions in `pt` (points) unless specified

### Class Syntax Pattern

```
{property}-{subproperty}-{value}[/{modifier}]
```

The class naming uses **unambiguous prefixes** to eliminate parsing ambiguity:

Examples:
- `fill-#4285f4` - Blue fill
- `fill-#4285f4/80` - Blue fill at 80% opacity
- `stroke-#d1d5db stroke-w-2` - Gray stroke, 2pt weight
- `text-size-24` - 24pt font size
- `text-color-#333333` - Dark gray text color
- `text-align-center` - Center aligned text
- `font-family-roboto` - Roboto font
- `font-weight-bold` - Bold weight

---

## Document Structure

```html
<Presentation id="abc123" w="720pt" h="405pt" locale="en">

  <Images>
    <Img id="maGcIV09" url="https://lh7-rt.googleusercontent.com/slidesz/AGV..."/>
    <Img id="xYz12345" url="https://example.com/image.png"/>
  </Images>

  <Masters>
    <Master id="master_1" name="Simple Light">
      <!-- Master slide elements -->
    </Master>
  </Masters>

  <Layouts>
    <Layout id="layout_1" master="master_1" name="Title Slide">
      <!-- Layout elements -->
    </Layout>
  </Layouts>

  <Slides>
    <Slide id="slide_1" layout="layout_1" master="master_1">
      <!-- Slide elements -->
    </Slide>

    <Slide id="slide_2" layout="layout_2" master="master_1" skipped>
      <!-- Skipped slide -->
    </Slide>
  </Slides>

</Presentation>
```

### Image URL Shortening

Long Google Slides image URLs are shortened to compact `img:` references. The `<Images>` section at the top of the document maps these short IDs to full URLs:

```html
<!-- Short reference in Image element -->
<Image id="img_1" src="img:maGcIV09"/>

<!-- Full URL in Images section -->
<Images>
  <Img id="maGcIV09" url="https://lh7-rt.googleusercontent.com/slidesz/AGV_vUcyvlo3..."/>
</Images>
```

The hash is generated using SHA256 truncated to 8 characters (base64url encoding).

---

## Presentation Metadata

The `<Presentation>` element contains metadata about the entire presentation.

```html
<Presentation
    id="1abc2def3ghi"
    title="Quarterly Business Review"
    w="720pt"
    h="405pt"
    locale="en-US"
    revision="12345">

  <!-- Masters, Layouts, Slides -->

</Presentation>
```

| Attribute | Maps to | Description |
|-----------|---------|-------------|
| `id` | `presentationId` | Unique presentation identifier |
| `title` | `title` | Presentation title |
| `w`, `h` | `pageSize` | Slide dimensions in points |
| `locale` | `locale` | IETF BCP 47 language tag (e.g., "en-US", "ja") |
| `revision` | `revisionId` | Revision ID for optimistic locking (read-only) |

### Standard Slide Sizes

```html
<!-- Standard 16:9 (default) -->
<Presentation w="720pt" h="405pt">

<!-- Standard 4:3 -->
<Presentation w="720pt" h="540pt">

<!-- Widescreen 16:10 -->
<Presentation w="720pt" h="450pt">

<!-- Custom size -->
<Presentation w="1920pt" h="1080pt">
```

---

## Page Types & Properties

### Page Types

Google Slides has 5 page types:

| Type | Element | Description |
|------|---------|-------------|
| `SLIDE` | `<Slide>` | Regular presentation slides |
| `MASTER` | `<Master>` | Master slides defining base styles |
| `LAYOUT` | `<Layout>` | Layout templates based on masters |
| `NOTES` | `<Notes>` | Speaker notes pages |
| `NOTES_MASTER` | `<NotesMaster>` | Master for notes pages |

### Master Slides

```html
<Master id="master_1" name="Simple Light">
  <!-- Color scheme definition -->
  <ColorScheme>
    <Color type="dark1" value="#000000"/>
    <Color type="light1" value="#ffffff"/>
    <Color type="accent1" value="#4285f4"/>
    <!-- ... -->
  </ColorScheme>

  <!-- Master page elements (backgrounds, logos, etc.) -->
  <Rect id="bg" class="x-0 y-0 w-full h-full fill-#ffffff"/>
</Master>
```

### Layout Slides

```html
<Layout id="layout_title" master="master_1" name="TITLE" display-name="Title Slide">
  <!-- Placeholder definitions -->
  <TextBox id="title_ph" class="x-72 y-180 w-576 h-80"
           placeholder="title" placeholder-index="0">
    Title
  </TextBox>
  <TextBox id="subtitle_ph" class="x-72 y-280 w-576 h-40"
           placeholder="subtitle" placeholder-index="1">
    Subtitle
  </TextBox>
</Layout>
```

#### Predefined Layout Types

```html
<!-- Layout name attribute can be one of these predefined types -->
<Layout name="BLANK">                          <!-- Empty slide -->
<Layout name="TITLE">                          <!-- Title slide -->
<Layout name="TITLE_AND_BODY">                 <!-- Title + body text -->
<Layout name="TITLE_AND_TWO_COLUMNS">          <!-- Title + 2 columns -->
<Layout name="TITLE_ONLY">                     <!-- Title only -->
<Layout name="SECTION_HEADER">                 <!-- Section divider -->
<Layout name="SECTION_TITLE_AND_DESCRIPTION">  <!-- Section with description -->
<Layout name="ONE_COLUMN_TEXT">                <!-- Single text column -->
<Layout name="MAIN_POINT">                     <!-- Main point emphasis -->
<Layout name="BIG_NUMBER">                     <!-- Big number display -->
<Layout name="CAPTION_ONLY">                   <!-- Caption only -->
```

### Slides

```html
<Slide id="slide_1"
       layout="layout_title"
       master="master_1"
       skipped="false">
  <!-- Slide elements -->
</Slide>

<!-- Skipped slide (hidden during presentation) -->
<Slide id="slide_2" layout="layout_body" skipped>
  ...
</Slide>
```

### Page Background

Backgrounds can be solid colors, theme colors, or images.

```html
<!-- Solid color background -->
<Slide id="slide_1" class="bg-#ffffff">
<Slide id="slide_1" class="bg-#f0f0f0">
<Slide id="slide_1" class="bg-#4285f4">

<!-- Theme color background -->
<Slide id="slide_1" class="bg-theme-light1">
<Slide id="slide_1" class="bg-theme-accent1">

<!-- Image background (stretched to fill) -->
<Slide id="slide_1" bg-src="https://example.com/background.jpg">

<!-- No background (transparent/inherit) -->
<Slide id="slide_1" class="bg-none">
<Slide id="slide_1" class="bg-inherit">
```

---

## Color Scheme

Masters define a color scheme with 16 named colors that can be referenced throughout the presentation.

### Defining Color Scheme

```html
<Master id="master_1" name="Custom Theme">
  <ColorScheme>
    <!-- Base colors -->
    <Color type="dark1" value="#000000"/>      <!-- Primary dark (usually black) -->
    <Color type="light1" value="#ffffff"/>     <!-- Primary light (usually white) -->
    <Color type="dark2" value="#1f1f1f"/>      <!-- Secondary dark -->
    <Color type="light2" value="#f5f5f5"/>     <!-- Secondary light -->

    <!-- Accent colors -->
    <Color type="accent1" value="#4285f4"/>    <!-- Google Blue -->
    <Color type="accent2" value="#ea4335"/>    <!-- Google Red -->
    <Color type="accent3" value="#fbbc04"/>    <!-- Google Yellow -->
    <Color type="accent4" value="#34a853"/>    <!-- Google Green -->
    <Color type="accent5" value="#ff6d01"/>    <!-- Orange -->
    <Color type="accent6" value="#46bdc6"/>    <!-- Teal -->

    <!-- Text colors (usually same as dark1/dark2) -->
    <Color type="text1" value="#000000"/>
    <Color type="text2" value="#666666"/>

    <!-- Background colors (usually same as light1/light2) -->
    <Color type="background1" value="#ffffff"/>
    <Color type="background2" value="#f8f9fa"/>

    <!-- Link colors -->
    <Color type="hyperlink" value="#1a73e8"/>
    <Color type="followed-hyperlink" value="#681da8"/>
  </ColorScheme>
</Master>
```

### Using Theme Colors

```html
<!-- Reference theme colors with fill-theme-{name} or text-theme-{name} -->
<Rect class="fill-theme-accent1"/>
<Rect class="fill-theme-dark1"/>
<TextBox class="text-theme-text1"/>
<TextBox class="text-theme-hyperlink"/>
```

### Theme Color Reference

| SML Class | API ThemeColorType | Description |
|-----------|-------------------|-------------|
| `fill-theme-dark1` | `DARK1` | Primary dark color |
| `fill-theme-light1` | `LIGHT1` | Primary light color |
| `fill-theme-dark2` | `DARK2` | Secondary dark color |
| `fill-theme-light2` | `LIGHT2` | Secondary light color |
| `fill-theme-accent1` | `ACCENT1` | Accent color 1 |
| `fill-theme-accent2` | `ACCENT2` | Accent color 2 |
| `fill-theme-accent3` | `ACCENT3` | Accent color 3 |
| `fill-theme-accent4` | `ACCENT4` | Accent color 4 |
| `fill-theme-accent5` | `ACCENT5` | Accent color 5 |
| `fill-theme-accent6` | `ACCENT6` | Accent color 6 |
| `fill-theme-text1` | `TEXT1` | Primary text color |
| `fill-theme-text2` | `TEXT2` | Secondary text color |
| `fill-theme-background1` | `BACKGROUND1` | Primary background |
| `fill-theme-background2` | `BACKGROUND2` | Secondary background |
| `fill-theme-hyperlink` | `HYPERLINK` | Hyperlink color |
| `fill-theme-followed-hyperlink` | `FOLLOWED_HYPERLINK` | Visited link color |

*Replace `fill-theme-` with `text-theme-` for text colors, `stroke-theme-` for strokes, or `bg-theme-` for backgrounds.*

---

## Element Types

### Shape Elements (143 types → Element names)

| Category | Elements |
|----------|----------|
| **Text** | `<TextBox>` |
| **Basic Shapes** | `<Rect>`, `<RoundRect>`, `<Ellipse>`, `<Triangle>`, `<RightTriangle>`, `<Diamond>`, `<Pentagon>`, `<Hexagon>`, `<Heptagon>`, `<Octagon>`, `<Decagon>`, `<Dodecagon>`, `<Parallelogram>`, `<Trapezoid>` |
| **Rounded Rect Variants** | `<Round1Rect>`, `<Round2DiagRect>`, `<Round2SameRect>`, `<SnipRoundRect>` |
| **Snip Rect Variants** | `<Snip1Rect>`, `<Snip2DiagRect>`, `<Snip2SameRect>` |
| **Stars** | `<Star4>`, `<Star5>`, `<Star6>`, `<Star7>`, `<Star8>`, `<Star10>`, `<Star12>`, `<Star16>`, `<Star24>`, `<Star32>`, `<Starburst>` |
| **Fancy** | `<Heart>`, `<Moon>`, `<Sun>`, `<Cloud>`, `<Lightning>`, `<Teardrop>`, `<SmileyFace>`, `<NoSmoking>`, `<IrregularSeal1>`, `<IrregularSeal2>` |
| **Arrows (Basic)** | `<ArrowLeft>`, `<ArrowRight>`, `<ArrowUp>`, `<ArrowDown>`, `<ArrowNorth>`, `<ArrowEast>`, `<ArrowNorthEast>` |
| **Arrows (Bidirectional)** | `<ArrowLeftRight>`, `<ArrowUpDown>`, `<ArrowLeftRightUp>`, `<ArrowLeftUp>`, `<ArrowQuad>` |
| **Arrows (Bent/Curved)** | `<ArrowBent>`, `<ArrowBentUp>`, `<ArrowUturn>`, `<ArrowCurvedLeft>`, `<ArrowCurvedRight>`, `<ArrowCurvedUp>`, `<ArrowCurvedDown>` |
| **Arrows (Styled)** | `<ArrowNotchedRight>`, `<ArrowStripedRight>` |
| **Arrow Callouts** | `<CalloutArrowLeft>`, `<CalloutArrowRight>`, `<CalloutArrowUp>`, `<CalloutArrowDown>`, `<CalloutArrowLeftRight>`, `<CalloutArrowQuad>` |
| **Callouts** | `<CalloutWedgeRect>`, `<CalloutWedgeRoundRect>`, `<CalloutWedgeEllipse>`, `<CalloutCloud>`, `<Speech>` |
| **Brackets & Braces** | `<BracePair>`, `<BracketPair>`, `<BraceLeft>`, `<BraceRight>`, `<BracketLeft>`, `<BracketRight>` |
| **Math** | `<MathPlus>`, `<MathMinus>`, `<MathMultiply>`, `<MathDivide>`, `<MathEqual>`, `<MathNotEqual>` |
| **Flowchart** | `<FlowProcess>`, `<FlowAlternateProcess>`, `<FlowDecision>`, `<FlowTerminator>`, `<FlowIO>`, `<FlowDocument>`, `<FlowMultiDoc>`, `<FlowPreparation>`, `<FlowPredefinedProcess>`, `<FlowConnector>`, `<FlowOffpageConnector>`, `<FlowMerge>`, `<FlowExtract>`, `<FlowSort>`, `<FlowCollate>`, `<FlowSummingJunction>`, `<FlowOr>`, `<FlowManualInput>`, `<FlowManualOperation>`, `<FlowDelay>`, `<FlowDisplay>`, `<FlowInternalStorage>`, `<FlowMagneticDisk>`, `<FlowMagneticDrum>`, `<FlowMagneticTape>`, `<FlowOnlineStorage>`, `<FlowOfflineStorage>`, `<FlowPunchedCard>`, `<FlowPunchedTape>` |
| **Ribbons** | `<Ribbon>`, `<Ribbon2>`, `<EllipseRibbon>`, `<EllipseRibbon2>` |
| **3D & Containers** | `<Cube>`, `<Can>`, `<Bevel>`, `<Frame>`, `<HalfFrame>`, `<Corner>`, `<Plaque>`, `<FoldedCorner>` |
| **Circular** | `<Donut>`, `<Arc>`, `<BlockArc>`, `<Chord>`, `<Pie>` |
| **Wavy & Scrolls** | `<Wave>`, `<DoubleWave>`, `<Scroll>`, `<ScrollV>` |
| **Other** | `<Chevron>`, `<Plus>`, `<DiagonalStripe>`, `<HomeBase>`, `<CustomShape>` |

### Other Element Types

```html
<Image>      <!-- Raster/vector images -->
<Video>      <!-- Embedded videos -->
<Line>       <!-- Lines and connectors -->
<Table>      <!-- Tables -->
<WordArt>    <!-- WordArt text -->
<Chart>      <!-- Embedded Sheets charts -->
<Group>      <!-- Grouped elements -->
<Spotlight>  <!-- Speaker spotlight -->
```

---

## Position & Transform

### Position Classes (AffineTransform)

The `x-{n}` and `y-{n}` classes map directly to the `translateX` and `translateY` properties of the Google Slides API's `AffineTransform`.

**Important:** These are transform translation values, not visual positions. When rotation or shear is applied, the visual position of an element differs from its translateX/translateY values.

```html
<!-- Translation (translateX, translateY in AffineTransform) -->
<TextBox class="x-72 y-144">        <!-- translateX: 72pt, translateY: 144pt -->
<TextBox class="x-0 y-0">           <!-- translateX: 0, translateY: 0 -->

<!-- Fractional positions (percentage of slide dimensions) -->
<TextBox class="x-1/2 y-1/3">       <!-- translateX: 50% of slide width, translateY: 33% of slide height -->
```

**Visual Position vs Transform:**
```html
<!-- No rotation: visual position = (100, 100) -->
<Rect class="x-100 y-100 w-200 h-100 rotate-0"/>

<!-- With rotation: visual position ≠ (100, 100) -->
<!-- The element rotates around its transform origin -->
<Rect class="x-100 y-100 w-200 h-100 rotate-45"/>
```

The full AffineTransform matrix is: `[scaleX, shearX, translateX; shearY, scaleY, translateY]`

### Transform Classes

```html
<!-- Rotation (degrees) -->
<TextBox class="rotate-0">          <!-- No rotation -->
<TextBox class="rotate-45">         <!-- 45 degrees clockwise -->
<TextBox class="rotate-90">
<TextBox class="rotate-180">
<TextBox class="-rotate-45">        <!-- Counter-clockwise -->

<!-- Scale -->
<TextBox class="scale-100">         <!-- Normal size (1.0) -->
<TextBox class="scale-x-100 scale-y-100">
<TextBox class="scale-x-50">        <!-- 50% horizontal scale -->
<TextBox class="scale-y-150">       <!-- 150% vertical scale -->
<TextBox class="-scale-x-100">      <!-- Horizontal flip -->
<TextBox class="-scale-y-100">      <!-- Vertical flip -->

<!-- Shear (skew) -->
<TextBox class="shear-x-0 shear-y-0">
```

### Combined Example

```html
<TextBox id="title" class="x-72 y-50 rotate-5 scale-x-100 scale-y-100">
```

### Z-Order (Stacking)

Z-order is controlled through **Actions**, not element classes. See the [Actions](#actions) section for details.

**Note:** Z-order is relative to sibling elements on the same page. Elements are rendered in stacking order from back to front. The actual z-order operations (`BRING_TO_FRONT`, `BRING_FORWARD`, `SEND_BACKWARD`, `SEND_TO_BACK`) are imperative commands, not declarative state, so they are specified in the `<Actions>` section.

---

## Size & Dimensions

### Width & Height

```html
<!-- Fixed dimensions in points -->
<TextBox class="w-400 h-50">        <!-- 400pt × 50pt -->
<Rect class="w-200 h-200">          <!-- Square 200pt -->

<!-- Fractional (percentage of slide) -->
<TextBox class="w-1/2 h-auto">      <!-- 50% of slide width -->
<TextBox class="w-full h-1/4">      <!-- Full width, 25% height -->

<!-- Common shortcuts -->
<TextBox class="w-full">            <!-- 100% width -->
<TextBox class="h-full">            <!-- 100% height -->
```

### Aspect Ratio (for shapes)

```html
<Ellipse class="w-100 aspect-square">   <!-- Circle -->
<Ellipse class="w-200 aspect-video">    <!-- 16:9 ellipse -->
```

---

## Fill Styling

### Solid Colors (RGB Hex)

All colors must be specified as 6-digit hexadecimal values with a `#` prefix:

```html
<Rect class="fill-#4285f4">         <!-- Google Blue -->
<Rect class="fill-#ffffff">         <!-- White -->
<Rect class="fill-#000000">         <!-- Black -->
<Rect class="fill-#f3f4f6">         <!-- Light gray -->
<Rect class="fill-#ef4444">         <!-- Red -->
```

### Theme Colors

Theme colors reference the color scheme defined in the presentation's master slides:

```html
<Rect class="fill-theme-dark1">
<Rect class="fill-theme-light1">
<Rect class="fill-theme-dark2">
<Rect class="fill-theme-light2">
<Rect class="fill-theme-accent1">
<Rect class="fill-theme-accent2">
<Rect class="fill-theme-accent3">
<Rect class="fill-theme-accent4">
<Rect class="fill-theme-accent5">
<Rect class="fill-theme-accent6">
<Rect class="fill-theme-text1">
<Rect class="fill-theme-text2">
<Rect class="fill-theme-background1">
<Rect class="fill-theme-background2">
<Rect class="fill-theme-hyperlink">
<Rect class="fill-theme-followed-hyperlink">
```

**Note:** Named color palettes (e.g., `blue-500`, `gray-300`) are **not supported**. Use hex colors or theme colors only. This ensures color values are explicit and unambiguous.

### Fill Opacity

```html
<Rect class="fill-#4285f4/100">     <!-- 100% opacity (default) -->
<Rect class="fill-#4285f4/80">      <!-- 80% opacity -->
<Rect class="fill-#4285f4/50">      <!-- 50% opacity -->
<Rect class="fill-#4285f4/0">       <!-- Fully transparent -->
<Rect class="fill-theme-accent1/75"> <!-- Theme color at 75% opacity -->
```

### Gradient Fills

**Note:** The Google Slides API has limited support for gradient fills. Gradients are primarily read-only for shapes. For backgrounds and some elements, gradients can be specified.

```html
<!-- Linear gradient (angle in degrees, 0 = left to right) -->
<Rect class="fill-gradient-0 from-#3b82f6 to-#1e3a8a"/>
<Rect class="fill-gradient-90 from-#ef4444 to-#eab308"/>   <!-- Top to bottom -->
<Rect class="fill-gradient-45 from-#8b5cf6 to-#ec4899"/>   <!-- Diagonal -->

<!-- With color stops -->
<Rect class="fill-gradient-0 from-#ef4444 via-#eab308 to-#22c55e"/>

<!-- Radial gradient (limited support) -->
<Rect class="fill-radial from-#ffffff to-#d1d5db"/>
```

#### Gradient Syntax

```
fill-gradient-{angle}     <!-- Linear gradient at angle (degrees) -->
fill-radial               <!-- Radial gradient from center -->
from-{color}              <!-- Start color (hex or theme) -->
via-{color}               <!-- Middle color (optional) -->
to-{color}                <!-- End color (hex or theme) -->
```

**Limitation:** Most shape fills in Google Slides only support solid colors via the API. Gradients are often read-only or only supported for specific properties like page backgrounds.

### No Fill / Property States

Fill properties support three explicit states:

```html
<Rect class="fill-none">            <!-- Explicitly no fill (NOT_RENDERED) -->
<Rect class="fill-inherit">         <!-- Inherit from parent/placeholder (INHERIT) -->
```

| Class | API PropertyState | Description |
|-------|-------------------|-------------|
| `fill-{color}` | `RENDERED` | Explicitly set to this color |
| `fill-none` | `NOT_RENDERED` | Explicitly transparent/no fill |
| `fill-inherit` | `INHERIT` | Inherit from parent placeholder or default |

**Class Removal Behavior:** If a fill class is removed during editing (e.g., `fill-#4285f4` removed), the reconciler treats this as `fill-inherit` - resetting the property to its inherited/default value.

---

## Stroke/Outline Styling

### Stroke Color

```html
<Rect class="stroke-#1a73e8">        <!-- Hex color -->
<Rect class="stroke-theme-accent1">  <!-- Theme color -->
<Rect class="stroke-none">           <!-- No stroke (NOT_RENDERED) -->
<Rect class="stroke-inherit">        <!-- Inherit from parent (INHERIT) -->
```

**Note:** Named color palettes are not supported. Use hex colors (`#rrggbb`) or theme colors (`theme-{name}`) only.

### Stroke Weight

```html
<Rect class="stroke-w-0">           <!-- Hairline / no stroke -->
<Rect class="stroke-w-1">           <!-- 1pt -->
<Rect class="stroke-w-2">           <!-- 2pt -->
<Rect class="stroke-w-4">           <!-- 4pt -->
<Rect class="stroke-w-8">           <!-- 8pt -->
```

### Stroke Dash Style

```html
<Rect class="stroke-solid">         <!-- Solid line (default) -->
<Rect class="stroke-dot">           <!-- Dotted -->
<Rect class="stroke-dash">          <!-- Dashed -->
<Rect class="stroke-dash-dot">      <!-- Dash-dot pattern -->
<Rect class="stroke-long-dash">     <!-- Long dashes -->
<Rect class="stroke-long-dash-dot"> <!-- Long dash-dot -->
```

### Combined Stroke

```html
<Rect class="stroke-#3b82f6 stroke-w-2 stroke-dash"/>
<Rect class="stroke-#333333/50 stroke-w-1 stroke-solid"/>  <!-- With opacity -->
<Rect class="stroke-theme-accent1 stroke-w-3 stroke-dot"/>
```

---

## Shadow Styling

### Shadow Presets

```html
<Rect class="shadow-none">          <!-- No shadow -->
<Rect class="shadow">               <!-- Default shadow -->
<Rect class="shadow-sm">            <!-- Small shadow -->
<Rect class="shadow-md">            <!-- Medium shadow -->
<Rect class="shadow-lg">            <!-- Large shadow -->
<Rect class="shadow-xl">            <!-- Extra large shadow -->
```

### Shadow Properties (Detailed)

```html
<!-- Shadow color (hex only) -->
<Rect class="shadow-#000000">
<Rect class="shadow-#1f2937">

<!-- Shadow opacity -->
<Rect class="shadow-opacity-50">    <!-- 50% opacity -->

<!-- Shadow blur radius -->
<Rect class="shadow-blur-4">        <!-- 4pt blur -->
<Rect class="shadow-blur-8">        <!-- 8pt blur -->

<!-- Shadow position/alignment -->
<Rect class="shadow-tl">            <!-- Top-left -->
<Rect class="shadow-tc">            <!-- Top-center -->
<Rect class="shadow-tr">            <!-- Top-right -->
<Rect class="shadow-cl">            <!-- Center-left -->
<Rect class="shadow-c">             <!-- Center -->
<Rect class="shadow-cr">            <!-- Center-right -->
<Rect class="shadow-bl">            <!-- Bottom-left -->
<Rect class="shadow-bc">            <!-- Bottom-center -->
<Rect class="shadow-br">            <!-- Bottom-right (default) -->
```

### Combined Shadow

```html
<Rect class="shadow shadow-blur-8 shadow-#000000/30 shadow-br">
```

---

## Text Content & Styling

### Text Content Structure

A Shape (TextBox, Rect, etc.) can contain text. The text is structured as:
- **Paragraphs** (`<P>`): A shape can have multiple paragraphs
- **Text Runs** (`<T>`): Each paragraph can have multiple styled runs
- **Auto Text** (`<Auto>`): Dynamic content like slide numbers

#### Explicit Text Structure Rules

All text content **must** be wrapped in explicit `<P>` and `<T>` elements:

1. **Every paragraph** must be a `<P>` element
2. **Every text run** must be a `<T>` element inside a `<P>`
3. **No bare text** is allowed directly inside `<TextBox>`, `<P>`, or any shape element
4. **No newlines** (`\n`) are allowed in text content - create new `<P>` elements instead

#### Parsing Rules

| Markup | Valid? | Notes |
|--------|--------|-------|
| `<TextBox><P><T>Hello</T></P></TextBox>` | ✅ | Correct: explicit P and T |
| `<TextBox><P><T>A</T></P><P><T>B</T></P></TextBox>` | ✅ | Correct: 2 paragraphs |
| `<TextBox><P><T>Hello </T><T class="bold">world</T></P></TextBox>` | ✅ | Correct: 2 runs in 1 paragraph |
| `<TextBox>Hello</TextBox>` | ❌ | Invalid: bare text, no P/T |
| `<TextBox><P>Hello</P></TextBox>` | ❌ | Invalid: bare text in P, no T |
| `<P><T>Line1\nLine2</T></P>` | ❌ | Invalid: newline in content |

#### Style Inheritance

Text styling cascades from TextBox → Paragraph → TextRun:

```html
<!-- TextBox defines defaults; all text inherits these -->
<TextBox class="font-family-roboto text-size-14 text-color-#111827">
  <P><T>This text is Roboto 14pt dark gray.</T></P>
</TextBox>

<!-- <T> only specifies what DIFFERS from the default -->
<TextBox class="font-family-roboto text-size-14 text-color-#111827">
  <P>
    <T>Normal text </T>
    <T class="bold">bold text</T>
    <T> back to normal.</T>
  </P>
</TextBox>

<!-- Paragraph can override TextBox defaults -->
<TextBox class="font-family-roboto text-size-14 text-color-#111827">
  <P class="text-size-18"><T>This paragraph is 18pt, still dark gray.</T></P>
  <P><T>This paragraph is back to 14pt.</T></P>
</TextBox>
```

#### Examples

```html
<!-- Simplest: single paragraph, single run -->
<TextBox id="simple" class="x-72 y-144 w-400 h-50 font-family-arial text-size-24">
  <P><T>Hello World</T></P>
</TextBox>

<!-- Multiple paragraphs -->
<TextBox id="multi" class="x-72 y-144 w-400 h-100 font-family-roboto text-size-14">
  <P><T>First paragraph of text.</T></P>
  <P><T>Second paragraph of text.</T></P>
  <P><T>Third paragraph of text.</T></P>
</TextBox>

<!-- Mixed styling within a paragraph -->
<TextBox id="styled" class="x-72 y-144 w-400 h-50 font-family-roboto text-size-14 text-color-#333333">
  <P>
    <T>This is normal text with </T>
    <T class="bold">bold</T>
    <T>, </T>
    <T class="italic">italic</T>
    <T>, and </T>
    <T class="text-color-#ef4444">colored</T>
    <T> words.</T>
  </P>
</TextBox>

<!-- Complex: multiple paragraphs with mixed styling -->
<TextBox id="complex" class="x-72 y-144 w-400 h-150 font-family-roboto text-size-14 text-color-#333333">
  <P class="text-size-18 font-weight-bold"><T>Heading Paragraph</T></P>
  <P>
    <T>Body text with </T>
    <T class="italic">emphasis</T>
    <T> and </T>
    <T class="text-color-#2563eb underline" href="https://example.com">a link</T>
    <T>.</T>
  </P>
  <P class="text-size-12 text-color-#6b7280"><T>Footer note in smaller gray text.</T></P>
</TextBox>

<!-- Auto text (slide numbers, dates, etc.) -->
<TextBox id="slide_num" class="x-648 y-380 w-50 h-20 font-family-roboto text-size-10 text-color-#9ca3af">
  <P><Auto type="slide-number"/></P>
</TextBox>
```

#### What `<T>` Can Style

The `<T>` element supports all TextStyle properties:

```html
<T class="bold">                    <!-- Bold -->
<T class="italic">                  <!-- Italic -->
<T class="underline">               <!-- Underline -->
<T class="line-through">            <!-- Strikethrough -->
<T class="small-caps">              <!-- Small caps -->
<T class="superscript">             <!-- Superscript -->
<T class="subscript">               <!-- Subscript -->
<T class="font-family-arial">       <!-- Override font family -->
<T class="text-size-18">            <!-- Override font size -->
<T class="font-weight-bold">        <!-- Override font weight -->
<T class="text-color-#ef4444">      <!-- Text color -->
<T class="bg-#fef08a">              <!-- Background/highlight color -->
<T class="text-color-#ef4444/80">   <!-- Text color with opacity -->
<T href="https://...">              <!-- Hyperlink -->
<T href="#slide_5">                 <!-- Internal link -->

<!-- Multiple styles combined -->
<T class="bold italic text-color-#2563eb underline" href="https://example.com">
  styled link
</T>
```

### Font Family

```html
<TextBox class="font-family-arial">
<TextBox class="font-family-roboto">
<TextBox class="font-family-google-sans">
<TextBox class="font-family-times">
<TextBox class="font-family-courier">
<TextBox class="font-family-[Open Sans]">  <!-- Custom font with spaces -->
```

### Font Size

```html
<TextBox class="text-size-8">            <!-- 8pt -->
<TextBox class="text-size-10">
<TextBox class="text-size-12">
<TextBox class="text-size-14">
<TextBox class="text-size-16">
<TextBox class="text-size-18">
<TextBox class="text-size-20">
<TextBox class="text-size-24">
<TextBox class="text-size-28">
<TextBox class="text-size-32">
<TextBox class="text-size-36">
<TextBox class="text-size-48">
<TextBox class="text-size-64">
<TextBox class="text-size-72">
<TextBox class="text-size-96">
```

### Font Weight

```html
<TextBox class="font-weight-100">          <!-- Thin -->
<TextBox class="font-weight-200">          <!-- Extra Light -->
<TextBox class="font-weight-300">          <!-- Light -->
<TextBox class="font-weight-400">          <!-- Normal (default) -->
<TextBox class="font-weight-500">          <!-- Medium -->
<TextBox class="font-weight-600">          <!-- Semi Bold -->
<TextBox class="font-weight-700">          <!-- Bold -->
<TextBox class="font-weight-800">          <!-- Extra Bold -->
<TextBox class="font-weight-900">          <!-- Black -->

<!-- Shortcuts -->
<TextBox class="font-weight-light">        <!-- 300 -->
<TextBox class="font-weight-normal">       <!-- 400 -->
<TextBox class="font-weight-medium">       <!-- 500 -->
<TextBox class="font-weight-semibold">     <!-- 600 -->
<TextBox class="font-weight-bold">         <!-- 700 -->
```

### Font Style & Decoration

```html
<TextBox class="italic">
<TextBox class="underline">
<TextBox class="line-through">      <!-- Strikethrough -->
<TextBox class="small-caps">
<TextBox class="superscript">
<TextBox class="subscript">
```

### Text Color

```html
<TextBox class="text-color-#333333">      <!-- Hex color -->
<TextBox class="text-color-#ffffff">      <!-- White -->
<TextBox class="text-color-#000000">      <!-- Black -->
<TextBox class="text-color-theme-text1">  <!-- Theme color -->
<TextBox class="text-color-theme-dark1">  <!-- Theme color -->
```

**Note:** Named color palettes are not supported. Use hex colors (`#rrggbb`) or theme colors (`theme-{name}`) only.

### Horizontal Text Alignment

```html
<TextBox class="text-align-left">         <!-- START -->
<TextBox class="text-align-center">       <!-- CENTER -->
<TextBox class="text-align-right">        <!-- END -->
<TextBox class="text-align-justify">      <!-- JUSTIFIED -->
```

### Vertical Content Alignment

```html
<TextBox class="content-top">       <!-- TOP -->
<TextBox class="content-middle">    <!-- MIDDLE -->
<TextBox class="content-bottom">    <!-- BOTTOM -->
```

### Text Direction

```html
<TextBox class="dir-ltr">           <!-- Left to right -->
<TextBox class="dir-rtl">           <!-- Right to left -->
```

### Autofit

```html
<TextBox class="autofit-none">      <!-- No autofit -->
<TextBox class="autofit-text">      <!-- Shrink text to fit -->
<TextBox class="autofit-shape">     <!-- Resize shape to fit text -->
```

### Text Ranges

When applying styles to portions of text (via the API), a range specifies which text to target.

```html
<!-- Explicit range with start and end indices -->
<T range="0:10">First 10 characters</T>

<!-- Range from start index to end of text -->
<T range="5:">From index 5 to end</T>

<!-- All text in the shape -->
<T range="all">All text</T>
```

| Range Syntax | API Type | Description |
|--------------|----------|-------------|
| `{start}:{end}` | `FIXED_RANGE` | Explicit start and end character indices (0-based) |
| `{start}:` | `FROM_START_INDEX` | From start index to end of text content |
| `all` | `ALL` | Entire text content of the shape |

**Note:** In SML markup, text ranges are typically implicit based on `<T>` tag positions. The `range` attribute is optional and primarily useful for round-trip serialization or programmatic text manipulation.

---

## Paragraph Styling

### Line Spacing

```html
<P class="leading-100">             <!-- 100% / single -->
<P class="leading-115">             <!-- 115% -->
<P class="leading-150">             <!-- 150% / 1.5 lines -->
<P class="leading-200">             <!-- 200% / double -->
```

### Paragraph Spacing

```html
<P class="space-above-0">           <!-- No space above -->
<P class="space-above-6">           <!-- 6pt above -->
<P class="space-above-12">          <!-- 12pt above -->
<P class="space-below-0">           <!-- No space below -->
<P class="space-below-6">           <!-- 6pt below -->
<P class="space-below-12">          <!-- 12pt below -->
```

### Spacing Mode

Controls how paragraph spacing behaves, especially in lists.

```html
<P class="spacing-never-collapse">  <!-- Always preserve spacing -->
<P class="spacing-collapse-lists">  <!-- Collapse spacing in lists -->
```

| Class | API Value | Description |
|-------|-----------|-------------|
| `spacing-never-collapse` | `NEVER_COLLAPSE` | Space above/below is always rendered |
| `spacing-collapse-lists` | `COLLAPSE_LISTS` | Space collapses between list items |

### Property States

Many styling properties support three states that indicate how the property value should be interpreted.

```html
<!-- Explicitly set property (rendered) -->
<TextBox class="fill-#3b82f6">          <!-- RENDERED: Blue fill is applied -->

<!-- Explicitly no fill (not rendered) -->
<TextBox class="fill-none">              <!-- NOT_RENDERED: No fill applied -->

<!-- Inherit from parent (default behavior) -->
<TextBox class="fill-inherit">           <!-- INHERIT: Use parent's fill -->
```

| State | API PropertyState | Description |
|-------|-------------------|-------------|
| Explicit value | `RENDERED` | Property has an explicitly set value |
| `*-none` | `NOT_RENDERED` | Property is explicitly not rendered |
| `*-inherit` | `INHERIT` | Property value is inherited from parent element |

**Applicable properties:**
- Fill: `fill-{value}`, `fill-none`, `fill-inherit`
- Stroke: `stroke-{value}`, `stroke-none`, `stroke-inherit`
- Shadow: `shadow-{value}`, `shadow-none`, `shadow-inherit`
- Text styling: `bold`, `bold-none`, `bold-inherit` (same pattern for italic, underline, etc.)

**Note:** Most properties default to `INHERIT` when not explicitly specified. Use `*-none` when you want to explicitly remove an inherited property.

### Indentation

```html
<P class="indent-start-0">          <!-- No start indent -->
<P class="indent-start-18">         <!-- 18pt start indent -->
<P class="indent-end-0">            <!-- No end indent -->
<P class="indent-first-0">          <!-- No first line indent -->
<P class="indent-first-18">         <!-- 18pt first line indent -->
<P class="indent-first--18">        <!-- Hanging indent (negative) -->
```

### Bullets & Lists

```html
<!-- Bulleted list -->
<TextBox class="...">
  <P class="bullet bullet-disc">First item</P>
  <P class="bullet bullet-disc indent-level-1">Nested item</P>
  <P class="bullet bullet-circle indent-level-2">Deeper nested</P>
</TextBox>

<!-- Numbered list -->
<TextBox class="...">
  <P class="bullet bullet-digit">First item</P>
  <P class="bullet bullet-digit">Second item</P>
  <P class="bullet bullet-alpha indent-level-1">Sub-item a</P>
</TextBox>

<!-- Bullet presets -->
<TextBox class="list-disc-circle-square">        <!-- ● ○ ■ -->
<TextBox class="list-arrow-diamond-disc">        <!-- ➤ ◆ ● -->
<TextBox class="list-checkbox">                  <!-- ☐ -->
<TextBox class="list-star-circle-square">        <!-- ★ ○ ■ -->
<TextBox class="list-digit-alpha-roman">         <!-- 1. a. i. -->
<TextBox class="list-digit-alpha-roman-parens">  <!-- 1) a) i) -->
<TextBox class="list-upper-alpha-roman">         <!-- A. I. 1. -->
```

---

## Image Elements

### Basic Image

```html
<Image id="img1"
       class="x-100 y-100 w-300 h-200"
       src="https://..."/>
```

### Image Properties

```html
<!-- Transparency -->
<Image class="opacity-100"/>        <!-- Fully opaque -->
<Image class="opacity-50"/>         <!-- 50% transparent -->

<!-- Brightness (-100 to 100, 0 is normal) -->
<Image class="brightness-0"/>       <!-- Normal -->
<Image class="brightness-50"/>      <!-- Brighter -->
<Image class="brightness--50"/>     <!-- Darker -->

<!-- Contrast (-100 to 100, 0 is normal) -->
<Image class="contrast-0"/>         <!-- Normal -->
<Image class="contrast-50"/>        <!-- Higher contrast -->
<Image class="contrast--50"/>       <!-- Lower contrast -->
```

### Image Cropping

```html
<!-- Crop offsets (percentage 0-100) -->
<Image class="crop-l-10 crop-r-10 crop-t-5 crop-b-5"/>
<Image class="crop-l-0 crop-r-0 crop-t-0 crop-b-0"/>  <!-- No crop -->
```

### Image Recolor

Recolor applies color transformations to images based on predefined presets or theme colors.

```html
<!-- Standard recolor presets -->
<Image class="recolor-none"/>           <!-- No recolor (default) -->
<Image class="recolor-grayscale"/>      <!-- Convert to grayscale -->
<Image class="recolor-sepia"/>          <!-- Apply sepia tone -->
<Image class="recolor-negative"/>       <!-- Invert colors -->

<!-- Theme-based light recolors (LIGHT1-10) -->
<Image class="recolor-light1"/>         <!-- Theme light variant 1 -->
<Image class="recolor-light2"/>
<Image class="recolor-light3"/>
<!-- ... through recolor-light10 -->

<!-- Theme-based dark recolors (DARK1-10) -->
<Image class="recolor-dark1"/>          <!-- Theme dark variant 1 -->
<Image class="recolor-dark2"/>
<Image class="recolor-dark3"/>
<!-- ... through recolor-dark10 -->

<!-- Custom recolor (advanced) -->
<Image class="recolor-custom" recolor-stops="..."/>
```

| Class | API Recolor Name | Description |
|-------|------------------|-------------|
| `recolor-none` | `NONE` | No recolor effect |
| `recolor-grayscale` | `GRAYSCALE` | Convert to grayscale |
| `recolor-sepia` | `SEPIA` | Apply sepia/brown tone |
| `recolor-negative` | `NEGATIVE` | Invert all colors |
| `recolor-light1` through `recolor-light10` | `LIGHT1`-`LIGHT10` | Theme-based light variants |
| `recolor-dark1` through `recolor-dark10` | `DARK1`-`DARK10` | Theme-based dark variants |
| `recolor-custom` | `CUSTOM` | Custom recolor with color stops |

**Note:** Recolor is read-only in the API. These classes are provided for representing existing presentations; modifying recolor values via the API has no effect.

### Image Outline & Shadow

```html
<Image class="stroke-#d1d5db stroke-w-2 shadow-md"/>
```

---

## Line Elements

### Line Category & Type

Lines can be straight, bent (elbow), or curved connectors.

```html
<!-- Straight lines -->
<Line id="line1" class="line-straight x1-100 y1-100 x2-300 y2-200"/>
<Line id="line2" class="line-straight-1"/>  <!-- Straight connector -->

<!-- Bent connectors (2-5 segments) -->
<Line id="line3" class="line-bent-2"/>
<Line id="line4" class="line-bent-3"/>
<Line id="line5" class="line-bent-4"/>
<Line id="line6" class="line-bent-5"/>

<!-- Curved connectors (2-5 segments) -->
<Line id="line7" class="line-curved-2"/>
<Line id="line8" class="line-curved-3"/>
<Line id="line9" class="line-curved-4"/>
<Line id="line10" class="line-curved-5"/>
```

| Class | API Line Type | Description |
|-------|---------------|-------------|
| `line-straight` | `STRAIGHT_LINE` | Simple straight line |
| `line-straight-1` | `STRAIGHT_CONNECTOR_1` | Straight connector |
| `line-bent-2` | `BENT_CONNECTOR_2` | Bent with 2 segments |
| `line-bent-3` | `BENT_CONNECTOR_3` | Bent with 3 segments |
| `line-bent-4` | `BENT_CONNECTOR_4` | Bent with 4 segments |
| `line-bent-5` | `BENT_CONNECTOR_5` | Bent with 5 segments |
| `line-curved-2` | `CURVED_CONNECTOR_2` | Curved with 2 segments |
| `line-curved-3` | `CURVED_CONNECTOR_3` | Curved with 3 segments |
| `line-curved-4` | `CURVED_CONNECTOR_4` | Curved with 4 segments |
| `line-curved-5` | `CURVED_CONNECTOR_5` | Curved with 5 segments |

### Line Position

```html
<!-- Start and end points -->
<Line class="x1-100 y1-100 x2-400 y2-300"/>
```

### Line Styling

```html
<Line class="stroke-#3b82f6 stroke-w-2 stroke-dash"/>
```

### Arrow Heads

```html
<!-- Start arrow -->
<Line class="arrow-start-none"/>
<Line class="arrow-start-fill"/>        <!-- Filled arrow (FILL_ARROW) -->
<Line class="arrow-start-stealth"/>     <!-- Stealth arrow (STEALTH_ARROW) -->
<Line class="arrow-start-open"/>        <!-- Open arrow (OPEN_ARROW) -->
<Line class="arrow-start-fill-circle"/> <!-- Filled circle (FILL_CIRCLE) -->
<Line class="arrow-start-open-circle"/> <!-- Open circle (OPEN_CIRCLE) -->
<Line class="arrow-start-fill-square"/> <!-- Filled square (FILL_SQUARE) -->
<Line class="arrow-start-open-square"/> <!-- Open square (OPEN_SQUARE) -->
<Line class="arrow-start-fill-diamond"/><!-- Filled diamond (FILL_DIAMOND) -->
<Line class="arrow-start-open-diamond"/><!-- Open diamond (OPEN_DIAMOND) -->

<!-- End arrow (same options) -->
<Line class="arrow-end-fill"/>
<Line class="arrow-end-none"/>
```

| Class Pattern | API Arrow Style | Description |
|---------------|-----------------|-------------|
| `arrow-{pos}-none` | `NONE` | No arrow |
| `arrow-{pos}-fill` | `FILL_ARROW` | Standard filled arrow |
| `arrow-{pos}-stealth` | `STEALTH_ARROW` | Stealth/pointed arrow |
| `arrow-{pos}-open` | `OPEN_ARROW` | Open/outline arrow |
| `arrow-{pos}-fill-circle` | `FILL_CIRCLE` | Filled circle |
| `arrow-{pos}-open-circle` | `OPEN_CIRCLE` | Open circle |
| `arrow-{pos}-fill-square` | `FILL_SQUARE` | Filled square |
| `arrow-{pos}-open-square` | `OPEN_SQUARE` | Open square |
| `arrow-{pos}-fill-diamond` | `FILL_DIAMOND` | Filled diamond |
| `arrow-{pos}-open-diamond` | `OPEN_DIAMOND` | Open diamond |

*Where `{pos}` is `start` or `end`.*

### Line Connections

```html
<!-- Connected to shapes -->
<Line class="..." connect-start="shape_id:2" connect-end="shape_id:5"/>
<!-- :N refers to connection site index -->
```

---

## Table Elements

### Basic Table

Tables use **explicit row and column indices** on each cell for unambiguous addressing. This maps directly to the Google Slides API's `TableRange` structure.

```html
<Table id="table1" class="x-72 y-200 w-600 h-300" rows="3" cols="4">
  <Row r="0" class="h-50">
    <Cell id="table1_r0c0" r="0" c="0" class="fill-#3b82f6 text-color-#ffffff font-weight-bold text-align-center">Header 1</Cell>
    <Cell id="table1_r0c1" r="0" c="1" class="fill-#3b82f6 text-color-#ffffff font-weight-bold text-align-center">Header 2</Cell>
    <Cell id="table1_r0c2" r="0" c="2" class="fill-#3b82f6 text-color-#ffffff font-weight-bold text-align-center">Header 3</Cell>
    <Cell id="table1_r0c3" r="0" c="3" class="fill-#3b82f6 text-color-#ffffff font-weight-bold text-align-center">Header 4</Cell>
  </Row>
  <Row r="1">
    <Cell id="table1_r1c0" r="1" c="0">Data 1</Cell>
    <Cell id="table1_r1c1" r="1" c="1">Data 2</Cell>
    <Cell id="table1_r1c2" r="1" c="2">Data 3</Cell>
    <Cell id="table1_r1c3" r="1" c="3">Data 4</Cell>
  </Row>
  <Row r="2" class="fill-#f9fafb">
    <Cell id="table1_r2c0" r="2" c="0">Data 5</Cell>
    <Cell id="table1_r2c1" r="2" c="1">Data 6</Cell>
    <Cell id="table1_r2c2" r="2" c="2">Data 7</Cell>
    <Cell id="table1_r2c3" r="2" c="3">Data 8</Cell>
  </Row>
</Table>
```

### Cell Addressing

| Attribute | Required | Description |
|-----------|----------|-------------|
| `r` | Yes | Row index (0-based) |
| `c` | Yes | Column index (0-based) |
| `id` | Recommended | Unique cell identifier for diffing (convention: `{tableId}_r{row}c{col}`) |

**Benefits of explicit addressing:**
- Cell matching by `(tableId, r, c)` is trivial during diffing
- Merged cells are clearly identified by their origin coordinates
- Maps directly to API's `tableRange.location.rowIndex` / `columnIndex`
- Sparse representation possible (only include non-default cells)

### Table Column Widths

```html
<Table class="..." cols="3">
  <ColGroup>
    <Col c="0" class="w-100"/>
    <Col c="1" class="w-200"/>
    <Col c="2" class="w-150"/>
  </ColGroup>
  ...
</Table>
```

### Cell Properties

```html
<!-- Cell spanning (origin cell specifies the span) -->
<Cell r="0" c="1" colspan="2">Spans columns 1-2</Cell>
<Cell r="1" c="0" rowspan="3">Spans rows 1-3</Cell>
<Cell r="2" c="2" colspan="2" rowspan="2">Spans 2x2</Cell>

<!-- Cell background -->
<Cell r="0" c="0" class="fill-#fef3c7">Highlighted cell</Cell>

<!-- Cell content alignment -->
<Cell r="0" c="0" class="content-top text-align-left">Top-left aligned</Cell>
<Cell r="0" c="1" class="content-middle text-align-center">Centered</Cell>
<Cell r="0" c="2" class="content-bottom text-align-right">Bottom-right</Cell>
```

### Merged Cells

When cells are merged, only the **origin cell** (top-left) is represented with `colspan`/`rowspan` attributes. Covered cells are omitted:

```html
<Table id="table2" rows="3" cols="3">
  <Row r="0">
    <Cell r="0" c="0" colspan="2" rowspan="2">Merged 2x2 cell</Cell>
    <!-- r="0" c="1" is covered by merge -->
    <Cell r="0" c="2">Normal cell</Cell>
  </Row>
  <Row r="1">
    <!-- r="1" c="0" and r="1" c="1" are covered by merge -->
    <Cell r="1" c="2">Normal cell</Cell>
  </Row>
  <Row r="2">
    <Cell r="2" c="0">Normal</Cell>
    <Cell r="2" c="1">Normal</Cell>
    <Cell r="2" c="2">Normal</Cell>
  </Row>
</Table>
```

### Table Borders

```html
<!-- Border on all cells -->
<Table class="border-#d1d5db border-w-1"/>

<!-- Specific borders (applied to Table or Cell) -->
<Cell r="0" c="0" class="border-t-#6b7280 border-t-w-2"/>  <!-- Top border -->
<Cell r="0" c="1" class="border-b-#6b7280 border-b-w-1"/>  <!-- Bottom border -->
<Cell r="0" c="2" class="border-l-#6b7280 border-l-w-1"/>  <!-- Left border -->
<Cell r="0" c="3" class="border-r-#6b7280 border-r-w-1"/>  <!-- Right border -->
```

---

## Video Elements

```html
<Video id="vid1"
       class="x-100 y-100 w-480 h-270"
       src="youtube:dQw4w9WgXcQ"
       autoplay
       muted
       start="30"
       end="120"/>

<Video id="vid2"
       class="x-100 y-400 w-480 h-270"
       src="drive:1abc2def3ghi"
       stroke-gray-300 stroke-w-1"/>
```

### Video Properties

| Attribute | Maps to | Description |
|-----------|---------|-------------|
| `src` | `source` + `id` | Video source: `youtube:{id}` or `drive:{id}` |
| `autoplay` | `autoPlay` | Auto-play in presentation mode |
| `muted` | `mute` | Mute audio during playback |
| `start` | `start` | Start time in seconds |
| `end` | `end` | End time in seconds |

---

## WordArt Elements

WordArt displays stylized text rendered as an image.

```html
<WordArt id="wordart_1"
         class="x-100 y-100 w-400 h-100">
  AWESOME
</WordArt>
```

**Note:** WordArt is rendered as an image by Google Slides. The text content is stored in `renderedText` and can be read but styling is limited. For new designs, prefer using styled `<TextBox>` elements instead.

---

## SheetsChart Elements

Embedded charts from Google Sheets.

```html
<Chart id="chart_1"
       class="x-72 y-150 w-500 h-300"
       spreadsheet="1abc2def3ghi4jkl"
       chart-id="123456789"/>
```

| Attribute | Maps to | Description |
|-----------|---------|-------------|
| `spreadsheet` | `spreadsheetId` | Source Google Sheets ID |
| `chart-id` | `chartId` | Chart ID within the spreadsheet |

### Chart Image Properties

Charts are rendered as images and support image properties:

```html
<Chart id="chart_1"
       class="x-72 y-150 w-500 h-300 stroke-#e5e7eb stroke-w-1"
       spreadsheet="1abc2def3ghi4jkl"
       chart-id="123456789"/>
```

**Note:** Chart content is managed in the linked Google Sheet. Updates to the sheet automatically update the chart in the presentation.

---

## Group Elements

Groups combine multiple elements that move and scale together.

```html
<!-- Group definition -->
<Group id="group_1" class="x-100 y-100 w-300 h-200">
  <!-- Child elements are nested inside -->
  <Rect id="rect_1" class="x-0 y-0 w-300 h-200 fill-#dbeafe"/>
  <TextBox id="label_1" class="x-10 y-80 w-280 h-40 text-center">
    Grouped Content
  </TextBox>
  <Circle id="icon_1" class="x-130 y-20 w-40 h-40 fill-#3b82f6"/>
</Group>
```

### Group Behavior

- Child element positions are **relative to the group**, not the slide
- Groups require **minimum 2 children**
- Groups can be nested (groups within groups)
- Transformations (rotation, scale) apply to the entire group

### Flat Representation Alternative

For serialization, groups can also be represented flat with references:

```html
<Group id="group_1" class="x-100 y-100 w-300 h-200"/>
<Rect id="rect_1" class="x-0 y-0 w-300 h-200 fill-#dbeafe" group="group_1"/>
<TextBox id="label_1" class="x-10 y-80 w-280 h-40" group="group_1">Grouped</TextBox>
<Circle id="icon_1" class="x-130 y-20 w-40 h-40 fill-#3b82f6" group="group_1"/>
```

---

## Element Duplication

Elements can be created as duplicates of existing elements using the `duplicate-of` attribute. This maps to the Google Slides API's `DuplicateObjectRequest`.

### Basic Duplication

```html
<!-- Original element -->
<TextBox id="card_template" class="x-50 y-100 w-200 h-150 fill-#dbeafe stroke-#3b82f6">
  <P><T>Template Card</T></P>
</TextBox>

<!-- Duplicate with new position (inherits all other properties) -->
<TextBox id="card_copy_1" duplicate-of="card_template" class="x-280 y-100"/>

<!-- Duplicate with position and style override -->
<TextBox id="card_copy_2" duplicate-of="card_template" class="x-510 y-100 fill-#dcfce7 stroke-#22c55e"/>
```

### How Duplication Works

1. **Source element** is identified by `duplicate-of="source_id"`
2. **New element** gets a unique `id` (must be different from source)
3. **Classes** on the duplicate specify only the **overrides** - all other properties are inherited from the source
4. **Content** is copied from the source unless explicitly provided

### Duplication with Content Override

```html
<!-- Original -->
<TextBox id="title_1" class="x-72 y-100 w-576 h-50 font-google-sans text-24">
  <P><T>Original Title</T></P>
</TextBox>

<!-- Duplicate with new content -->
<TextBox id="title_2" duplicate-of="title_1" class="y-200">
  <P><T>Different Title</T></P>
</TextBox>
```

### Duplicating Complex Elements

Groups, tables, and other complex elements can also be duplicated:

```html
<!-- Original group -->
<Group id="info_card" class="x-50 y-100 w-200 h-100">
  <Rect id="card_bg" class="x-0 y-0 w-200 h-100 fill-#ffffff"/>
  <TextBox id="card_label" class="x-10 y-40 w-180 h-30">
    <P><T>Info Card</T></P>
  </TextBox>
</Group>

<!-- Duplicate the entire group (children are duplicated automatically) -->
<Group id="info_card_2" duplicate-of="info_card" class="x-280 y-100"/>
```

**Note:** When duplicating a group, all child elements are duplicated with auto-generated IDs. If you need to reference specific child elements in the duplicate, you must specify explicit ID mappings (see reconciliation spec for details).

### Duplication Rules

| Rule | Description |
|------|-------------|
| New ID required | Duplicate must have a unique `id` different from source |
| Classes are overrides | Only specify classes that differ from the source |
| Content is optional | Omit content to copy from source; provide to override |
| Same page | Duplicate is created on the same page as the source |
| Immediate copy | Duplicate appears immediately after source in z-order |

---

## Speaker Spotlight

Speaker spotlight elements show the presenter's video feed during a presentation.

```html
<Spotlight id="spotlight_1"
           class="x-550 y-300 w-150 h-100
                  stroke-#d1d5db stroke-w-2 shadow-md"/>
```

### Spotlight Properties

```html
<!-- Outline styling -->
<Spotlight class="stroke-#3b82f6 stroke-w-3"/>

<!-- Shadow -->
<Spotlight class="shadow-lg"/>

<!-- Rounded corners (if supported) -->
<Spotlight class="corner-8"/>
```

**Note:** Speaker spotlight is only visible during presentation mode when the presenter's camera is active.

---

## Notes Pages

Every slide has an associated notes page for speaker notes.

### Notes Structure

```html
<Slide id="slide_1" layout="title_body">
  <!-- Slide content -->
  <TextBox id="title" class="...">Slide Title</TextBox>
</Slide>

<Notes for="slide_1">
  <!-- Notes page has a thumbnail of the slide and a text area -->
  <TextBox id="speaker_notes_1"
           class="x-72 y-400 w-576 h-200
                  font-roboto text-12 text-#111827">
    <P>Remember to mention the Q3 results here.</P>
    <P>Key points:</P>
    <P class="bullet bullet-disc indent-level-0">Revenue growth of 23%</P>
    <P class="bullet bullet-disc indent-level-0">Customer satisfaction up</P>
    <P>Transition to the next slide by asking a question.</P>
  </TextBox>
</Notes>
```

### Notes Master

The notes master defines the default layout for all notes pages:

```html
<NotesMaster id="notes_master_1">
  <!-- Slide image placeholder -->
  <Image id="slide_thumbnail" class="x-72 y-72 w-400 h-225"
         placeholder="slide-image"/>

  <!-- Speaker notes placeholder -->
  <TextBox id="notes_body" class="x-72 y-320 w-576 h-350"
           placeholder="body"
           class="font-roboto text-11 text-#1f2937"/>
</NotesMaster>
```

### Simplified Notes Syntax

For convenience, notes can be attached directly to slides:

```html
<Slide id="slide_1" layout="title_body">
  <TextBox id="title" class="...">Slide Title</TextBox>

  <!-- Inline notes using <SpeakerNotes> -->
  <SpeakerNotes>
    Remember to mention the Q3 results here.

    Key points:
    - Revenue growth of 23%
    - Customer satisfaction up

    Transition to the next slide by asking a question.
  </SpeakerNotes>
</Slide>
```

---

## Actions

Actions represent **imperative operations** that should be performed, as opposed to declarative state. Actions are collected in an `<Actions>` section within a slide or at the presentation level.

### Why Actions?

Some operations in the Google Slides API are inherently imperative:
- Z-order changes (`BRING_TO_FRONT`, `SEND_TO_BACK`) are relative operations
- Line rerouting recalculates connector paths
- Chart refreshing fetches updated data

These cannot be meaningfully represented as element state because:
1. They are not idempotent (applying twice has no additional effect)
2. They represent commands, not properties
3. They cannot be diffed in a meaningful way

### Action Syntax

```html
<Slide id="slide_1">
  <!-- Declarative elements (state) -->
  <Rect id="box1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
  <Rect id="box2" class="x-150 y-150 w-200 h-100 fill-#ef4444"/>
  <Line id="connector1" class="line-bent-2" connect-start="box1:2" connect-end="box2:0"/>
  <Chart id="chart1" spreadsheet="1abc2def" chart-id="123456"/>

  <!-- Imperative actions (operations to perform) -->
  <Actions>
    <BringToFront target="box1"/>
    <RerouteLine target="connector1"/>
    <RefreshChart target="chart1"/>
  </Actions>
</Slide>
```

### Available Actions

#### Z-Order Actions

Control the stacking order of elements:

```html
<Actions>
  <BringToFront target="element_id"/>    <!-- Move to top of stack -->
  <BringForward target="element_id"/>    <!-- Move up one level -->
  <SendBackward target="element_id"/>    <!-- Move down one level -->
  <SendToBack target="element_id"/>      <!-- Move to bottom of stack -->
</Actions>
```

| Action | API Request | Description |
|--------|-------------|-------------|
| `<BringToFront>` | `updatePageElementsZOrder` with `BRING_TO_FRONT` | Move element to front |
| `<BringForward>` | `updatePageElementsZOrder` with `BRING_FORWARD` | Move element forward one level |
| `<SendBackward>` | `updatePageElementsZOrder` with `SEND_BACKWARD` | Move element backward one level |
| `<SendToBack>` | `updatePageElementsZOrder` with `SEND_TO_BACK` | Move element to back |

**Multiple targets:** Z-order actions can target multiple elements:

```html
<BringToFront target="box1 box2 box3"/>
```

#### Line Actions

```html
<Actions>
  <RerouteLine target="connector_id"/>
</Actions>
```

| Action | API Request | Description |
|--------|-------------|-------------|
| `<RerouteLine>` | `rerouteLine` | Reroute connector to closest connection points |

**Note:** Only works on lines with a category indicating they are connectors (bent or curved connectors).

#### Chart Actions

```html
<Actions>
  <RefreshChart target="chart_id"/>
</Actions>
```

| Action | API Request | Description |
|--------|-------------|-------------|
| `<RefreshChart>` | `refreshSheetsChart` | Refresh embedded chart from Google Sheets |

**Note:** Requires appropriate OAuth scopes for Sheets/Drive access.

### Actions Processing

Actions are processed **after** all declarative changes have been applied:

1. Create/update/delete elements (declarative)
2. Apply text and style changes (declarative)
3. Execute actions in order (imperative)

Within the `<Actions>` section, actions are executed in document order.

---

## Placeholders

Placeholders are template elements that inherit properties from layouts and masters.

### Placeholder Types

| Type | Description |
|------|-------------|
| `title` | Slide title |
| `centered-title` | Centered title |
| `subtitle` | Subtitle text |
| `body` | Body text area |
| `header` | Header text |
| `footer` | Footer text |
| `slide-number` | Slide number |
| `date-time` | Date/time field |
| `picture` | Image placeholder |
| `chart` | Chart placeholder |
| `table` | Table placeholder |
| `diagram` | Diagram placeholder |
| `media` | Media (video) placeholder |
| `clip-art` | Clip art placeholder |
| `object` | Generic object placeholder |
| `slide-image` | Slide thumbnail (in notes) |

### Placeholder Attributes

```html
<TextBox id="title_1"
         class="x-72 y-180 w-576 h-80"
         placeholder="title"
         placeholder-index="0"
         placeholder-parent="layout_title_ph">
  Presentation Title
</TextBox>
```

| Attribute | Maps to | Description |
|-----------|---------|-------------|
| `placeholder` | `type` | Placeholder type (see table above) |
| `placeholder-index` | `index` | Index when multiple placeholders of same type |
| `placeholder-parent` | `parentObjectId` | Parent placeholder for inheritance |

### Placeholder Inheritance Chain

```
Master Placeholder → Layout Placeholder → Slide Element
```

Properties cascade down:
- Position and size can be overridden at each level
- Text styling inherits from parent if not specified
- Fill, stroke, shadow inherit if not specified

### Example: Title Placeholder Chain

```html
<!-- Master defines the base title style -->
<Master id="master_1">
  <TextBox id="master_title_ph"
           class="x-72 y-180 w-576 h-80
                  font-google-sans text-44 font-bold text-theme-dark1"
           placeholder="title"/>
</Master>

<!-- Layout can customize position/styling -->
<Layout id="layout_1" master="master_1">
  <TextBox id="layout_title_ph"
           class="x-72 y-50 w-576 h-60 text-36"
           placeholder="title"
           placeholder-parent="master_title_ph"/>
</Layout>

<!-- Slide inherits from layout, provides content -->
<Slide id="slide_1" layout="layout_1">
  <TextBox id="slide_title"
           placeholder="title"
           placeholder-parent="layout_title_ph">
    My Slide Title
  </TextBox>
</Slide>
```

---

## Links

Hyperlinks can be applied to shapes, images, or text runs.

### External URLs

```html
<!-- Shape-level link -->
<TextBox class="..." href="https://example.com">Click me</TextBox>
<Rect class="..." href="https://google.com"/>
<Image class="..." src="..." href="https://example.com"/>

<!-- Text run link -->
<TextBox>
  <P>Visit <T class="text-blue-600 underline" href="https://google.com">Google</T> for more.</P>
</TextBox>
```

### Internal Slide Links

```html
<!-- Link to specific slide by ID -->
<TextBox href="#slide_5">Go to slide 5</TextBox>

<!-- Link by slide index (0-based) -->
<TextBox href="#index:4">Go to 5th slide</TextBox>

<!-- Relative links -->
<TextBox href="#next">Next slide</TextBox>
<TextBox href="#prev">Previous slide</TextBox>
<TextBox href="#first">First slide</TextBox>
<TextBox href="#last">Last slide</TextBox>
```

### Link on Images and Shapes

```html
<Image class="..." src="..." href="https://example.com"
       title="Click to visit our website"/>

<Rect class="fill-#3b82f6" href="#next">
  <TextBox class="text-#ffffff text-center content-middle">
    Continue →
  </TextBox>
</Rect>
```

---

## Accessibility

Accessibility properties help screen readers describe content.

### Title and Description

```html
<!-- Image with alt text -->
<Image class="x-100 y-100 w-300 h-200"
       src="https://..."
       title="Company Logo"
       alt="Blue circular logo with white text reading 'Acme Corp'"/>

<!-- Shape with description -->
<Rect class="fill-#3b82f6"
      title="Call to Action Button"
      alt="Blue button that navigates to the pricing page when clicked"/>

<!-- Decorative image (no alt needed) -->
<Image class="..." src="..." alt=""/>
```

| Attribute | Maps to | Description |
|-----------|---------|-------------|
| `title` | `title` | Brief accessible name |
| `alt` | `description` | Detailed description for screen readers |

### Best Practices

1. **All meaningful images** should have `alt` text
2. **Decorative images** should have empty `alt=""`
3. **Interactive elements** should have `title` explaining the action
4. **Complex diagrams** should have detailed `alt` descriptions
5. **Charts** should describe the data trend in `alt`

```html
<!-- Good: Descriptive alt text -->
<Image src="chart.png"
       title="Q4 Revenue Chart"
       alt="Bar chart showing revenue growth from $2M in Q1 to $5M in Q4,
            with steady 25% quarter-over-quarter growth"/>

<!-- Good: Interactive element with clear title -->
<Rect class="fill-#22c55e" href="#contact"
      title="Contact Us"
      alt="Green button linking to the contact information slide"/>
```

---

## Style Inheritance

Elements can inherit styles from other elements by referencing their ID in the `class` attribute.

```html
<!-- Define a reusable style -->
<TextBox id="heading_style" class="font-family-google-sans text-size-24 font-weight-bold text-color-#2563eb"/>

<!-- Reference the style by ID -->
<TextBox id="heading_1" class="heading_style x-72 y-100 w-400 h-40">
  <P><T>First Heading</T></P>
</TextBox>

<TextBox id="heading_2" class="heading_style x-72 y-200 w-400 h-40">
  <P><T>Second Heading</T></P>
</TextBox>

<!-- Override specific properties -->
<TextBox id="heading_3" class="heading_style text-color-#dc2626 x-72 y-300 w-400 h-40">
  <P><T>Red Heading (overrides blue)</T></P>
</TextBox>
```

### Inheritance Rules

1. Referenced element's classes are applied first
2. Local classes override inherited ones
3. Multiple inheritance is allowed: `class="style_a style_b local-class"`
4. Later classes win in case of conflicts

---

## Complete Examples

### Example 1: Simple Title Slide

```html
<Slide id="slide_1" layout="title_layout" class="bg-#ffffff">

  <TextBox id="title"
           class="x-72 y-180 w-576 h-80
                  font-family-google-sans text-size-44 font-weight-bold text-color-#111827
                  text-align-center content-middle">
    <P><T>Quarterly Business Review</T></P>
  </TextBox>

  <TextBox id="subtitle"
           class="x-72 y-280 w-576 h-40
                  font-family-roboto text-size-24 text-color-#4b5563
                  text-align-center content-middle">
    <P><T>Q4 2024 Results</T></P>
  </TextBox>

  <TextBox id="date"
           class="x-72 y-360 w-576 h-24
                  font-family-roboto text-size-14 text-color-#9ca3af
                  text-align-center">
    <P><T>January 15, 2025</T></P>
  </TextBox>

</Slide>
```

### Example 2: Content Slide with Bullets

```html
<Slide id="slide_2" layout="title_body" class="bg-#ffffff">

  <TextBox id="slide_title"
           class="x-72 y-36 w-576 h-50
                  font-family-google-sans text-size-28 font-weight-medium text-color-#111827">
    <P><T>Key Highlights</T></P>
  </TextBox>

  <TextBox id="bullet_content"
           class="x-72 y-110 w-576 h-280
                  font-family-roboto text-size-18 text-color-#374151
                  list-disc-circle-square autofit-text">
    <P class="bullet bullet-disc leading-150 space-below-8"><T>Revenue grew 23% year-over-year</T></P>
    <P class="bullet bullet-disc leading-150 space-below-8"><T>Customer acquisition up 45%</T></P>
    <P class="bullet bullet-disc leading-150 space-below-8"><T>Net promoter score improved to 72</T></P>
    <P class="bullet bullet-circle indent-level-1 leading-150 space-below-4"><T>Enterprise segment: 78</T></P>
    <P class="bullet bullet-circle indent-level-1 leading-150 space-below-4"><T>SMB segment: 65</T></P>
    <P class="bullet bullet-disc leading-150"><T>New product launch exceeded targets</T></P>
  </TextBox>

  <TextBox id="slide_num"
           class="x-648 y-380 w-50 h-20
                  font-family-roboto text-size-10 text-color-#9ca3af text-align-right">
    <P><Auto type="slide-number"/></P>
  </TextBox>

</Slide>
```

### Example 3: Image with Caption

```html
<Slide id="slide_3" class="bg-#f9fafb">

  <TextBox id="title"
           class="x-72 y-30 w-576 h-40
                  font-family-google-sans text-size-24 font-weight-medium text-color-#111827">
    <P><T>Product Screenshot</T></P>
  </TextBox>

  <Rect id="image_frame"
        class="x-110 y-90 w-500 h-280
               fill-#ffffff stroke-#e5e7eb stroke-w-1 shadow-lg">
  </Rect>

  <Image id="screenshot"
         class="x-120 y-100 w-480 h-260"
         src="https://..."
         title="Dashboard Screenshot"
         alt="Main dashboard showing analytics overview"/>

  <TextBox id="caption"
           class="x-110 y-375 w-500 h-20
                  font-family-roboto text-size-12 italic text-color-#6b7280 text-align-center">
    <P><T>Figure 1: New analytics dashboard interface</T></P>
  </TextBox>

</Slide>
```

### Example 4: Comparison with Shapes

```html
<Slide id="slide_4" class="bg-#ffffff">

  <TextBox id="title"
           class="x-72 y-30 w-576 h-40
                  font-family-google-sans text-size-24 font-weight-medium text-color-#111827 text-align-center">
    <P><T>Before &amp; After</T></P>
  </TextBox>

  <!-- Left card -->
  <RoundRect id="card_left"
             class="x-50 y-90 w-300 h-290
                    fill-#fef2f2 stroke-#fecaca stroke-w-1 corner-8"/>

  <TextBox id="card_left_title"
           class="x-60 y-100 w-280 h-30
                  font-family-google-sans text-size-18 font-weight-bold text-color-#b91c1c text-align-center">
    <P><T>Before</T></P>
  </TextBox>

  <TextBox id="card_left_content"
           class="x-60 y-140 w-280 h-220
                  font-family-roboto text-size-14 text-color-#374151
                  list-disc-circle-square">
    <P class="bullet bullet-disc"><T>Manual processes</T></P>
    <P class="bullet bullet-disc"><T>3-day turnaround</T></P>
    <P class="bullet bullet-disc"><T>High error rate</T></P>
    <P class="bullet bullet-disc"><T>Limited visibility</T></P>
  </TextBox>

  <!-- Arrow -->
  <ArrowRight id="arrow"
              class="x-360 y-220 w-40 h-30
                     fill-#9ca3af"/>

  <!-- Right card -->
  <RoundRect id="card_right"
             class="x-410 y-90 w-300 h-290
                    fill-#f0fdf4 stroke-#bbf7d0 stroke-w-1 corner-8"/>

  <TextBox id="card_right_title"
           class="x-420 y-100 w-280 h-30
                  font-family-google-sans text-size-18 font-weight-bold text-color-#15803d text-align-center">
    <P><T>After</T></P>
  </TextBox>

  <TextBox id="card_right_content"
           class="x-420 y-140 w-280 h-220
                  font-family-roboto text-size-14 text-color-#374151
                  list-disc-circle-square">
    <P class="bullet bullet-disc"><T>Fully automated</T></P>
    <P class="bullet bullet-disc"><T>Real-time updates</T></P>
    <P class="bullet bullet-disc"><T>99.9% accuracy</T></P>
    <P class="bullet bullet-disc"><T>Complete dashboard</T></P>
  </TextBox>

</Slide>
```

### Example 5: Data Table

```html
<Slide id="slide_5" class="bg-#ffffff">

  <TextBox id="title"
           class="x-72 y-30 w-576 h-40
                  font-family-google-sans text-size-24 font-weight-medium text-color-#111827">
    <P><T>Regional Performance</T></P>
  </TextBox>

  <Table id="perf_table"
         class="x-72 y-90 w-576 h-280 border-#d1d5db border-w-1"
         rows="5" cols="4">
    <ColGroup>
      <Col c="0" class="w-144"/>
      <Col c="1" class="w-144"/>
      <Col c="2" class="w-144"/>
      <Col c="3" class="w-144"/>
    </ColGroup>
    <Row r="0" class="h-40">
      <Cell r="0" c="0" class="fill-#2563eb text-color-#ffffff font-weight-bold text-align-center content-middle"><T>Region</T></Cell>
      <Cell r="0" c="1" class="fill-#2563eb text-color-#ffffff font-weight-bold text-align-center content-middle"><T>Q3</T></Cell>
      <Cell r="0" c="2" class="fill-#2563eb text-color-#ffffff font-weight-bold text-align-center content-middle"><T>Q4</T></Cell>
      <Cell r="0" c="3" class="fill-#2563eb text-color-#ffffff font-weight-bold text-align-center content-middle"><T>Growth</T></Cell>
    </Row>
    <Row r="1" class="h-50">
      <Cell r="1" c="0" class="fill-#f9fafb font-weight-medium"><T>North America</T></Cell>
      <Cell r="1" c="1" class="text-align-right"><T>$4.2M</T></Cell>
      <Cell r="1" c="2" class="text-align-right"><T>$5.1M</T></Cell>
      <Cell r="1" c="3" class="text-align-right text-color-#16a34a font-weight-bold"><T>+21%</T></Cell>
    </Row>
    <Row r="2" class="h-50">
      <Cell r="2" c="0" class="font-weight-medium"><T>Europe</T></Cell>
      <Cell r="2" c="1" class="text-align-right"><T>$2.8M</T></Cell>
      <Cell r="2" c="2" class="text-align-right"><T>$3.4M</T></Cell>
      <Cell r="2" c="3" class="text-align-right text-color-#16a34a font-weight-bold"><T>+18%</T></Cell>
    </Row>
    <Row r="3" class="h-50">
      <Cell r="3" c="0" class="fill-#f9fafb font-weight-medium"><T>APAC</T></Cell>
      <Cell r="3" c="1" class="text-align-right"><T>$1.9M</T></Cell>
      <Cell r="3" c="2" class="text-align-right"><T>$2.6M</T></Cell>
      <Cell r="3" c="3" class="text-align-right text-color-#16a34a font-weight-bold"><T>+37%</T></Cell>
    </Row>
    <Row r="4" class="h-50">
      <Cell r="4" c="0" class="font-weight-medium"><T>LATAM</T></Cell>
      <Cell r="4" c="1" class="text-align-right"><T>$0.8M</T></Cell>
      <Cell r="4" c="2" class="text-align-right"><T>$1.1M</T></Cell>
      <Cell r="4" c="3" class="text-align-right text-color-#16a34a font-weight-bold"><T>+28%</T></Cell>
    </Row>
  </Table>

</Slide>
```

### Example 6: Complex Diagram

```html
<Slide id="slide_6" class="bg-#ffffff">

  <TextBox id="title"
           class="x-72 y-20 w-576 h-35
                  font-family-google-sans text-size-22 font-weight-medium text-color-#111827 text-align-center">
    <P><T>System Architecture</T></P>
  </TextBox>

  <!-- Client layer -->
  <RoundRect id="client_box"
             class="x-80 y-70 w-140 h-60
                    fill-#dbeafe stroke-#60a5fa stroke-w-2 corner-8"/>
  <TextBox id="client_label"
           class="x-80 y-80 w-140 h-40
                  font-family-roboto text-size-14 font-weight-medium text-color-#1e40af text-align-center content-middle">
    <P><T>Web Client</T></P>
  </TextBox>

  <RoundRect id="mobile_box"
             class="x-80 y-150 w-140 h-60
                    fill-#dbeafe stroke-#60a5fa stroke-w-2 corner-8"/>
  <TextBox id="mobile_label"
           class="x-80 y-160 w-140 h-40
                  font-family-roboto text-size-14 font-weight-medium text-color-#1e40af text-align-center content-middle">
    <P><T>Mobile App</T></P>
  </TextBox>

  <!-- API Gateway -->
  <RoundRect id="api_box"
             class="x-290 y-110 w-140 h-60
                    fill-#dcfce7 stroke-#22c55e stroke-w-2 corner-8"/>
  <TextBox id="api_label"
           class="x-290 y-120 w-140 h-40
                  font-family-roboto text-size-14 font-weight-medium text-color-#166534 text-align-center content-middle">
    <P><T>API Gateway</T></P>
  </TextBox>

  <!-- Services -->
  <RoundRect id="svc1"
             class="x-500 y-60 w-120 h-50
                    fill-#f3e8ff stroke-#a855f7 stroke-w-2 corner-8"/>
  <TextBox id="svc1_label"
           class="x-500 y-65 w-120 h-40
                  font-family-roboto text-size-12 font-weight-medium text-color-#6b21a8 text-align-center content-middle">
    <P><T>Auth Service</T></P>
  </TextBox>

  <RoundRect id="svc2"
             class="x-500 y-120 w-120 h-50
                    fill-#f3e8ff stroke-#a855f7 stroke-w-2 corner-8"/>
  <TextBox id="svc2_label"
           class="x-500 y-125 w-120 h-40
                  font-family-roboto text-size-12 font-weight-medium text-color-#6b21a8 text-align-center content-middle">
    <P><T>Data Service</T></P>
  </TextBox>

  <RoundRect id="svc3"
             class="x-500 y-180 w-120 h-50
                    fill-#f3e8ff stroke-#a855f7 stroke-w-2 corner-8"/>
  <TextBox id="svc3_label"
           class="x-500 y-185 w-120 h-40
                  font-family-roboto text-size-12 font-weight-medium text-color-#6b21a8 text-align-center content-middle">
    <P><T>ML Service</T></P>
  </TextBox>

  <!-- Database -->
  <Ellipse id="db"
           class="x-500 y-260 w-120 h-70
                  fill-#ffedd5 stroke-#f97316 stroke-w-2"/>
  <TextBox id="db_label"
           class="x-500 y-275 w-120 h-40
                  font-family-roboto text-size-12 font-weight-medium text-color-#9a3412 text-align-center content-middle">
    <P><T>PostgreSQL</T></P>
  </TextBox>

  <!-- Connectors -->
  <Line id="conn1" class="x1-220 y1-100 x2-290 y2-130 stroke-#9ca3af stroke-w-2 arrow-end-fill"/>
  <Line id="conn2" class="x1-220 y1-180 x2-290 y2-150 stroke-#9ca3af stroke-w-2 arrow-end-fill"/>
  <Line id="conn3" class="x1-430 y1-140 x2-500 y2-85 stroke-#9ca3af stroke-w-2 arrow-end-fill"/>
  <Line id="conn4" class="x1-430 y1-140 x2-500 y2-145 stroke-#9ca3af stroke-w-2 arrow-end-fill"/>
  <Line id="conn5" class="x1-430 y1-140 x2-500 y2-205 stroke-#9ca3af stroke-w-2 arrow-end-fill"/>
  <Line id="conn6" class="x1-560 y1-170 x2-560 y2-260 stroke-#9ca3af stroke-w-2 stroke-dash arrow-end-fill"/>

  <!-- Legend -->
  <TextBox id="legend"
           class="x-80 y-320 w-540 h-30
                  font-family-roboto text-size-10 text-color-#6b7280 text-align-center">
    <P><T>Solid lines = synchronous | Dashed lines = asynchronous</T></P>
  </TextBox>

</Slide>
```

---

## Class Reference

### Position & Transform

| Class | Description | Example |
|-------|-------------|---------|
| `x-{n}` | X position in points | `x-72`, `x-0` |
| `y-{n}` | Y position in points | `y-144`, `y-0` |
| `x-{n}/{d}` | X position as fraction | `x-1/2` (50%) |
| `y-{n}/{d}` | Y position as fraction | `y-1/3` (33%) |
| `w-{n}` | Width in points | `w-400`, `w-100` |
| `h-{n}` | Height in points | `h-50`, `h-200` |
| `w-full` | Full width | `w-full` |
| `h-full` | Full height | `h-full` |
| `w-{n}/{d}` | Width as fraction | `w-1/2` (50%) |
| `rotate-{deg}` | Rotation in degrees | `rotate-45`, `-rotate-90` |
| `scale-{n}` | Uniform scale (%) | `scale-100`, `scale-50` |
| `scale-x-{n}` | Horizontal scale | `scale-x-100` |
| `scale-y-{n}` | Vertical scale | `scale-y-150` |
| `-scale-x-100` | Horizontal flip | `-scale-x-100` |
| `-scale-y-100` | Vertical flip | `-scale-y-100` |
| `shear-x-{n}` | Horizontal shear | `shear-x-0` |
| `shear-y-{n}` | Vertical shear | `shear-y-0` |
| ~~`z-*`~~ | Z-order operations | Use `<Actions>` section instead |

### Fill

| Class | Description | Example |
|-------|-------------|---------|
| `fill-#rrggbb` | Solid hex color | `fill-#4285f4` |
| `fill-#rrggbb/{opacity}` | Hex color with opacity | `fill-#4285f4/80` |
| `fill-theme-{name}` | Theme color fill | `fill-theme-accent1` |
| `fill-none` | No fill (NOT_RENDERED) | `fill-none` |
| `fill-inherit` | Inherit from parent (INHERIT) | `fill-inherit` |
| `fill-gradient-{angle}` | Linear gradient | `fill-gradient-90` |
| `fill-radial` | Radial gradient | `fill-radial` |
| `from-{color}` | Gradient start | `from-#3b82f6` |
| `via-{color}` | Gradient middle | `via-#a855f7` |
| `to-{color}` | Gradient end | `to-#ef4444` |

### Stroke/Outline

| Class | Description | Example |
|-------|-------------|---------|
| `stroke-#rrggbb` | Hex stroke color | `stroke-#d1d5db` |
| `stroke-#rrggbb/{opacity}` | Stroke with opacity | `stroke-#000000/50` |
| `stroke-theme-{name}` | Theme stroke color | `stroke-theme-accent1` |
| `stroke-none` | No stroke (NOT_RENDERED) | `stroke-none` |
| `stroke-inherit` | Inherit from parent | `stroke-inherit` |
| `stroke-w-{n}` | Stroke weight (pt) | `stroke-w-2` |
| `stroke-solid` | Solid line | `stroke-solid` |
| `stroke-dot` | Dotted line | `stroke-dot` |
| `stroke-dash` | Dashed line | `stroke-dash` |
| `stroke-dash-dot` | Dash-dot pattern | `stroke-dash-dot` |
| `stroke-long-dash` | Long dashes | `stroke-long-dash` |
| `stroke-long-dash-dot` | Long dash-dot | `stroke-long-dash-dot` |

### Shadow

| Class | Description | Example |
|-------|-------------|---------|
| `shadow` | Default shadow | `shadow` |
| `shadow-none` | No shadow | `shadow-none` |
| `shadow-sm` | Small shadow | `shadow-sm` |
| `shadow-md` | Medium shadow | `shadow-md` |
| `shadow-lg` | Large shadow | `shadow-lg` |
| `shadow-xl` | Extra large | `shadow-xl` |
| `shadow-{color}` | Shadow color | `shadow-#000000` |
| `shadow-opacity-{n}` | Shadow opacity | `shadow-opacity-50` |
| `shadow-blur-{n}` | Blur radius (pt) | `shadow-blur-8` |
| `shadow-{pos}` | Shadow position | `shadow-br`, `shadow-tl` |

### Typography

| Class | Description | Example |
|-------|-------------|---------|
| `font-family-{family}` | Font family | `font-family-arial`, `font-family-roboto` |
| `font-family-[{name}]` | Font with spaces | `font-family-[Open Sans]` |
| `text-size-{n}` | Font size (pt) | `text-size-14`, `text-size-24` |
| `font-weight-{weight}` | Font weight | `font-weight-bold`, `font-weight-500` |
| `font-weight-light` | Light weight (300) | `font-weight-light` |
| `font-weight-normal` | Normal weight (400) | `font-weight-normal` |
| `font-weight-medium` | Medium weight (500) | `font-weight-medium` |
| `font-weight-semibold` | Semi-bold (600) | `font-weight-semibold` |
| `font-weight-bold` | Bold (700) | `font-weight-bold` |
| `italic` | Italic style | `italic` |
| `underline` | Underline | `underline` |
| `line-through` | Strikethrough | `line-through` |
| `small-caps` | Small caps | `small-caps` |
| `superscript` | Superscript | `superscript` |
| `subscript` | Subscript | `subscript` |

### Text Color & Alignment

| Class | Description | Example |
|-------|-------------|---------|
| `text-color-#rrggbb` | Hex text color | `text-color-#333333` |
| `text-color-theme-{name}` | Theme text color | `text-color-theme-text1` |
| `text-align-left` | Left align | `text-align-left` |
| `text-align-center` | Center align | `text-align-center` |
| `text-align-right` | Right align | `text-align-right` |
| `text-align-justify` | Justify | `text-align-justify` |
| `content-top` | Vertical top | `content-top` |
| `content-middle` | Vertical middle | `content-middle` |
| `content-bottom` | Vertical bottom | `content-bottom` |
| `dir-ltr` | Left to right | `dir-ltr` |
| `dir-rtl` | Right to left | `dir-rtl` |

### Paragraph

| Class | Description | Example |
|-------|-------------|---------|
| `leading-{n}` | Line spacing (%) | `leading-150` |
| `space-above-{n}` | Space above (pt) | `space-above-12` |
| `space-below-{n}` | Space below (pt) | `space-below-6` |
| `indent-start-{n}` | Start indent (pt) | `indent-start-18` |
| `indent-end-{n}` | End indent (pt) | `indent-end-18` |
| `indent-first-{n}` | First line indent | `indent-first-18` |
| `indent-level-{n}` | Nesting level | `indent-level-1` |
| `bullet` | Enable bullet | `bullet` |
| `bullet-disc` | Disc bullet | `bullet-disc` |
| `bullet-circle` | Circle bullet | `bullet-circle` |
| `bullet-square` | Square bullet | `bullet-square` |
| `bullet-digit` | Numbered (1, 2) | `bullet-digit` |
| `bullet-alpha` | Alpha (a, b) | `bullet-alpha` |
| `bullet-roman` | Roman (i, ii) | `bullet-roman` |
| `spacing-never-collapse` | Preserve spacing | `spacing-never-collapse` |
| `spacing-collapse-lists` | Collapse in lists | `spacing-collapse-lists` |

### Autofit

| Class | Description | Example |
|-------|-------------|---------|
| `autofit-none` | No autofit | `autofit-none` |
| `autofit-text` | Shrink text to fit | `autofit-text` |
| `autofit-shape` | Resize shape to fit | `autofit-shape` |

### Image

| Class | Description | Example |
|-------|-------------|---------|
| `opacity-{n}` | Image opacity (%) | `opacity-50` |
| `brightness-{n}` | Brightness (-100 to 100) | `brightness-0` |
| `contrast-{n}` | Contrast (-100 to 100) | `contrast-0` |
| `crop-l-{n}` | Crop left (%) | `crop-l-10` |
| `crop-r-{n}` | Crop right (%) | `crop-r-10` |
| `crop-t-{n}` | Crop top (%) | `crop-t-5` |
| `crop-b-{n}` | Crop bottom (%) | `crop-b-5` |
| `recolor-none` | No recolor | `recolor-none` |
| `recolor-grayscale` | Grayscale | `recolor-grayscale` |
| `recolor-sepia` | Sepia | `recolor-sepia` |
| `recolor-negative` | Negative | `recolor-negative` |
| `recolor-light{n}` | Theme light (1-10) | `recolor-light1` |
| `recolor-dark{n}` | Theme dark (1-10) | `recolor-dark1` |
| `recolor-custom` | Custom recolor | `recolor-custom` |

### Line

| Class | Description | Example |
|-------|-------------|---------|
| `line-straight` | Straight line | `line-straight` |
| `line-straight-1` | Straight connector | `line-straight-1` |
| `line-bent-{n}` | Bent connector (2-5) | `line-bent-2`, `line-bent-5` |
| `line-curved-{n}` | Curved connector (2-5) | `line-curved-3`, `line-curved-5` |
| `x1-{n}`, `y1-{n}` | Start point | `x1-100 y1-100` |
| `x2-{n}`, `y2-{n}` | End point | `x2-300 y2-200` |
| `arrow-start-{type}` | Start arrow | `arrow-start-fill` |
| `arrow-end-{type}` | End arrow | `arrow-end-fill-circle` |

**Arrow types:** `none`, `fill`, `stealth`, `open`, `fill-circle`, `open-circle`, `fill-square`, `open-square`, `fill-diamond`, `open-diamond`

### Corner Radius

| Class | Description | Example |
|-------|-------------|---------|
| `corner-{n}` | Corner radius (pt) | `corner-8`, `corner-16` |

### Background (Pages)

| Class | Description | Example |
|-------|-------------|---------|
| `bg-#rrggbb` | Hex background color | `bg-#ffffff`, `bg-#f0f0f0` |
| `bg-theme-{name}` | Theme background | `bg-theme-light1` |
| `bg-none` | No background (NOT_RENDERED) | `bg-none` |
| `bg-inherit` | Inherit background (INHERIT) | `bg-inherit` |

---

## Parsing & Serialization Notes

### General Rules

1. **Class order doesn't matter**: `fill-#3b82f6 w-400` = `w-400 fill-#3b82f6`
2. **Later classes override earlier**: `fill-#ef4444 fill-#3b82f6` → blue wins
3. **Inheritance**: Classes referencing an element ID apply that element's classes first

### Color Values

1. **Hex colors**: 6-digit with `#` prefix: `#4285f4`
2. **Theme colors**: `theme-{name}`: `theme-accent1`, `theme-dark1`, `theme-light2`
3. **Opacity modifier**: `/{percent}`: `fill-#4285f4/80`

**Note:** Named color palettes (e.g., `blue-500`) are **not supported**. Use hex colors or theme colors only.

### Numeric Values

1. **Points**: Default unit, no suffix needed: `x-72` = 72pt
2. **Fractions**: `{n}/{d}` for percentages: `w-1/2` = 50%
3. **Percentages**: For opacity, leading, etc.: `leading-150` = 150%
4. **Negative values**: Prefix with `-`: `-rotate-45`, `indent-first--18`

### Special Syntax

1. **Custom fonts**: Brackets for spaces: `font-[Open Sans]`
2. **Boolean attributes**: Present = true: `autoplay`, `muted`, `skipped`
3. **Connection references**: `connect-start="shape_id:site_index"`

### Element ID Rules

1. IDs should be unique within the presentation
2. IDs can be referenced in `class` for style inheritance
3. IDs are used in `href` for internal links: `href="#slide_id"`

### Text Content Rules

1. **All text** must be wrapped in explicit `<P>` and `<T>` elements
2. **No bare text** is allowed directly inside shapes or `<P>` elements
3. **No newlines** (`\n`) in text content - use separate `<P>` elements
4. **Whitespace** is preserved exactly as written within `<T>` elements

---

## Limitations

### Not Supported by Google Slides API

The following features exist in the Google Slides UI but are **not exposed through the API** and therefore cannot be represented in SML:

| Feature | Status | Notes |
|---------|--------|-------|
| **Animations** | ❌ Not supported | Cannot create, read, or modify element animations. [Feature request](https://issuetracker.google.com/issues/36761236) is open. |
| **Transitions** | ❌ Not supported | Slide transitions cannot be set via API |
| **Audio** | ❌ Not supported | Audio elements are not available in the API |
| **Themes** | ❌ Limited | Cannot create new themes; can only use existing masters/layouts |
| **Comments** | ❌ Not supported | Presentation comments are not accessible |

### Read-Only Properties

Some properties can be **read** from the API but **cannot be modified**:

| Property | Element | Notes |
|----------|---------|-------|
| `brightness` | Image | Read-only; use Google Slides UI to modify |
| `contrast` | Image | Read-only; use Google Slides UI to modify |
| `transparency` | Image | Read-only; use Google Slides UI to modify |
| `cropProperties` | Image | Read-only; use Google Slides UI to modify |
| `recolor` | Image | Read-only; use Google Slides UI to modify |
| `contentUrl` | Image, SheetsChart | Generated URL; output-only |
| `renderedText` | WordArt | Text is readable but styling is limited |
| Gradient fills | Shape | Limited write support; primarily read-only |

**Note:** While SML includes syntax for image properties like `brightness-*`, `contrast-*`, `crop-*`, and `recolor-*`, these are provided for **reading/representing** existing presentations. Attempts to modify these values via the API will have no effect.

### Partial Support

| Feature | Status | Notes |
|---------|--------|-------|
| **Gradient fills** | ⚠️ Partial | Can read gradients; write support is limited to page backgrounds |
| **WordArt styling** | ⚠️ Partial | Text content is accessible; visual styling is baked into the rendering |
| **SheetsChart** | ⚠️ Partial | Charts are linked to Google Sheets; content is managed there |
| **Custom fonts** | ⚠️ Partial | Font must be available in Google Fonts or already in the presentation |

### SML-Specific Limitations

| Limitation | Description |
|------------|-------------|
| **Unit conversion** | SML uses points (pt); API uses EMU. Conversion may introduce small rounding differences. |
| **Transform vs position** | `x-{n}` and `y-{n}` are translateX/translateY values, not visual positions when rotation/shear is applied. |
| **Nested groups** | While supported, deeply nested groups may complicate reconciliation. |
| **Text structure** | All text must be in explicit `<P><T>` structure - no bare text or newlines in content. |

---

## API Coverage Summary

| Google Slides API | SML Element/Class | Notes |
|-------------------|-------------------|-------|
| Presentation | `<Presentation>` | Full support |
| Page (SLIDE) | `<Slide>` | Full support |
| Page (MASTER) | `<Master>` | Full support |
| Page (LAYOUT) | `<Layout>` | Full support |
| Page (NOTES) | `<Notes>` | Full support |
| PageElement.Shape | `<TextBox>`, `<Rect>`, etc. | 143 shape types |
| PageElement.Image | `<Image>` | Full support |
| PageElement.Video | `<Video>` | Full support |
| PageElement.Line | `<Line>` | Full support |
| PageElement.Table | `<Table>` | Full support |
| PageElement.WordArt | `<WordArt>` | Read-only text |
| PageElement.SheetsChart | `<Chart>` | Full support |
| PageElement.Group | `<Group>` | Full support |
| PageElement.SpeakerSpotlight | `<Spotlight>` | Full support |
| AffineTransform | `x-`, `y-`, `rotate-`, `scale-` | Full support |
| ShapeBackgroundFill | `fill-` classes | Solid + limited gradient |
| Outline | `stroke-` classes | Full support |
| Shadow | `shadow-` classes | Full support |
| TextContent | `<P>`, `<T>`, content | Full support |
| TextStyle | Typography classes | Full support |
| ParagraphStyle | Paragraph classes | Full support |
| Placeholder | `placeholder` attribute | Full support |
| Link | `href` attribute | Full support |
| ColorScheme | `<ColorScheme>` | Full support |

---

*Version 1.0 - Draft Specification*
