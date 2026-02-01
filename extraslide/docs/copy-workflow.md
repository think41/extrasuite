# Copy-Based Workflow

This document describes how to copy elements between slides in extraslide.

## Overview

The copy workflow allows duplicating elements (shapes, groups, images, text boxes) to new positions. The copy operation:
- Preserves all styling (fill, stroke, shadow, text formatting)
- Translates all children to maintain relative positions
- Uses styles from `styles.json` for accurate recreation

## How to Copy Elements

To copy an element, duplicate its XML entry in `content.sml` with:
1. The **same element ID**
2. Only **x and y** position (omit w and h to signal this is a copy)
3. Children unchanged from original

```xml
<!-- Original element (has x, y, w, h) -->
<Group id="g96" x="31.0" y="68.1" w="109.4" h="49.9">
  <RoundRect id="e1203" x="31.0" y="68.1" w="50.0" h="30.0" />
  <TextBox id="e1204" x="85.0" y="68.1" w="55.0" h="30.0">
    <P>Hello</P>
  </TextBox>
</Group>

<!-- Copy - same IDs, new position (x, y only, NO w, h) -->
<Group id="g96" x="200.0" y="100.0">
  <RoundRect id="e1203" x="31.0" y="68.1" w="50.0" h="30.0" />
  <TextBox id="e1204" x="85.0" y="68.1" w="55.0" h="30.0">
    <P>Hello</P>
  </TextBox>
</Group>
```

**Key convention**: The root element of a copy has only `x` and `y` attributes (no `w` and `h`). This signals to the diff algorithm that this is a copy operation. Children retain their original positions from the source.

The diff algorithm detects this pattern and calculates the translation needed to position all elements correctly.

## How Copy Detection Works

The diff algorithm identifies copies using a simple rule:

**Missing dimensions = copy**: If an element has `x` and `y` but no `w` and `h`, it's a copy.

The algorithm then:
1. Finds the source element by ID in the pristine data
2. Calculates translation: `dx = copy.x - source.x`, `dy = copy.y - source.y`
3. Applies translation to all children: `child_new_pos = child_orig_pos + (dx, dy)`
4. Retrieves styles from `styles.json` for accurate recreation

This means you can:
- Copy an element from any slide to any other slide
- Copy an element within the same slide to a different position
- Copy entire groups with nested children

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

1. **Position**: The new position is calculated from copy's `x`, `y` plus translation applied to all children
2. **Dimensions**: Width and height are read from `styles.json` using the source element ID
3. **Styles**: Fill, stroke, shadow are read from `styles.json`
4. **Children**: For groups, all children are recreated with translated positions
5. **Text**: Text content from the SML and text styling from `styles.json`
6. **Images**: Dimensions from `styles.json` for accurate sizing

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

For copies, all positions are calculated using translation:

```
translation = (copy.x - source.x, copy.y - source.y)
child_new_position = child_original_position + translation
```

Example:
- Source group at (31.0, 68.1)
- Copy placed at (200.0, 100.0)
- Translation: dx=169.0, dy=31.9
- Child originally at (85.0, 68.1) → created at (254.0, 100.0)

## Styles

The copy operation uses the element ID to look up styles in `styles.json`. This ensures:
- Consistent styling across copies (fill, stroke, shadow, text formatting)
- Efficient diff/push (styles are retrieved from source, not duplicated)
- Accurate recreation of visual appearance

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

3. **Copy convention**: To mark an element as a copy, include only `x` and `y` attributes (omit `w` and `h`). Keep all children unchanged from the source.

## Testing

To verify a copy is pixel-perfect:
1. Run `extraslide push`
2. Run `extraslide pull` to get updated content
3. Compare positions and styles in `styles.json`

Expected results:
- Positions match exactly (or within 0.01 pt)
- Colors match (or within 1-bit per channel)
- All children present with correct relative positions
