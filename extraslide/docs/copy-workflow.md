# Copy-Based Workflow

This document describes how to copy elements between slides in extraslide.

## Overview

The copy workflow allows duplicating elements (shapes, groups, images, text boxes) to new positions. The copy operation:
- Preserves all styling (fill, stroke, shadow, text formatting)
- Correctly positions children relative to the parent
- Applies native image dimensions for accurate sizing

## How to Copy Elements

To copy an element, duplicate its XML entry in `content.sml` with the **same element ID** but a different position:

```xml
<!-- Original element -->
<Group id="g96" x="31.0" y="68.1" w="109.4" h="49.9" pattern="p31">
  <RoundRect id="e1203" pattern="p32" />
  <Image id="e1204" pattern="p6" />
</Group>

<!-- Copy - same IDs, different position -->
<Group id="g96" x="200.0" y="68.1" w="109.4" h="49.9" pattern="p31">
  <RoundRect id="e1203" pattern="p32" />
  <Image id="e1204" pattern="p6" />
</Group>
```

The diff algorithm detects duplicate IDs and treats occurrences on different slides (or at different positions on the same slide) as copy operations.

## How Copy Detection Works

The diff algorithm identifies originals vs copies using these rules:

1. **Cross-slide copies**: If an element ID appears on multiple slides, the instance on the same slide as in pristine (the original pull) is the original. Instances on other slides are copies.

2. **Same-slide copies**: If an element ID appears multiple times on the same slide, the instance at the original position (matching pristine x, y coordinates) is the original. Instances at different positions are copies.

This means you can:
- Copy an element from slide 16 to slide 118 by using the same element ID
- Copy an element within the same slide by duplicating it with a different position

## Supported Shape Types

The following shape types can be copied:

| Shape Type | SML Tag | Description |
|------------|---------|-------------|
| RECTANGLE | `Rect` | Standard rectangle |
| TEXT_BOX | `TextBox` | Text container |
| ROUND_RECTANGLE | `RoundRect` | Rounded corner rectangle |
| ELLIPSE | `Ellipse` | Circle or oval |
| HOME_PLATE | `HOME_PLATE` | Chevron/arrow shape |
| CHEVRON | `CHEVRON` | Chevron shape |
| TRIANGLE | `TRIANGLE` | Triangle shape |
| LINE | `Line` | Line connector |
| IMAGE | `Image` | Image element |
| GROUP | `Group` | Group of elements |

## What Gets Copied

When copying an element:

1. **Position**: The new position is taken from the copy's `x`, `y`, `w`, `h` attributes
2. **Styles**: Fill, stroke, shadow are read from `styles.json` (referenced by pattern or ID)
3. **Children**: For groups, all children are recreated with correct relative positions
4. **Text**: Text content and styling (font, color, bold, etc.) are preserved
5. **Images**: Native dimensions are used for accurate sizing

## Known Limitations

### 1. Autofit (Read-Only)

The Google Slides API does not support setting `autofit.autofitType` via `updateShapeProperties`. Text boxes created via API default to `autofitType: NONE`, while manually created text boxes often use `SHAPE_AUTOFIT` which auto-sizes text to fit.

**Impact**: Text in copied text boxes may appear truncated or differently wrapped than the original if the original used `SHAPE_AUTOFIT`.

**Workaround**: After copying, manually adjust text box autofit settings in Google Slides UI (Format > Format Options > Text Fitting).

### 2. Theme-Inherited Fonts

Text elements that don't explicitly specify a font (relying on theme/master slide inheritance) will get Google's default font (Arial) when copied, not the theme font.

**Impact**: Title text boxes that inherit "Roboto Bold" from the theme may appear as "Arial Regular" after copying.

**Workaround**: After copying, manually set the font in Google Slides to match the original, or ensure source elements have explicit font settings.

### 3. Crop Properties (Read-Only)

The Google Slides API does not support setting crop properties via `updateImageProperties`. If the original image has cropping applied, the copy will show the full uncropped image.

**Workaround**: For cropped images, manually crop in Google Slides UI after the copy operation.

### 4. Minor Color Precision Loss

Colors may have 1-bit differences in RGB channels (e.g., #c6dbfd becoming #c6dbfc) due to float-to-integer conversion when going through the API.

**Impact**: Imperceptible to human eye, affects ~0.4% of color precision.

### 5. Size Rounding

Element sizes may differ by ~0.01 pt due to EMU (English Metric Units) to points conversion rounding.

**Impact**: Sub-pixel, not visible.

### 6. Image Transparency and Effects

Image properties like transparency, brightness, and contrast are read-only in the Google Slides API. These cannot be replicated via copy operations.

## Position Calculation

For copied groups, children positions are calculated as:
- Parent position: from the copy's x, y attributes
- Child offset: from `styles.json` relative positions
- Child absolute position = parent position + child offset

Example:
- Parent copy at (200, 100)
- Child has relative position (10, 20) in styles.json
- Child created at absolute position (210, 120)

## Styles and Patterns

The copy operation uses the pattern reference to look up styles in `styles.json`. This ensures:
- Consistent styling across copies
- Efficient diff/push (only position changes, not style definitions)
- Pattern reuse for repeated elements

## Cross-Slide Copy Implementation

The Google Slides API's `duplicateObject` only works for copying elements within the same slide. For cross-slide copies, extraslide uses a different approach:

1. **Create new shape**: Uses `createShape` with the same shape type as the source
2. **Apply styles**: Copies fill, stroke, shadow properties from the source element's style
3. **Insert text**: Adds text content with formatting from the source
4. **Handle children**: For groups, recursively creates all child elements

This means cross-slide copies are "deep copies" that recreate the element from scratch using the source's style definitions.

## Important Notes

1. **Pristine synchronization**: After a `push`, always `pull` again before making more edits. The `.pristine/` folder must reflect the current state of the presentation.

2. **Element IDs are local**: After push, Google assigns new IDs to created elements. The next pull will show different IDs than what you wrote.

3. **Pattern references**: Use pattern references (`pattern="p21"`) rather than inline styles. This ensures copies inherit styles correctly from `styles.json`.

## Testing

To verify a copy is pixel-perfect:
1. Run `extraslide push`
2. Run `extraslide pull` to get updated content
3. Compare positions and styles in `styles.json`

Expected results:
- Positions match exactly (or within 0.01 pt)
- Colors match (or within 1-bit per channel)
- All children present with correct relative positions
