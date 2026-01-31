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

The diff algorithm detects duplicate IDs and treats the second occurrence as a copy operation.

## What Gets Copied

When copying an element:

1. **Position**: The new position is taken from the copy's `x`, `y`, `w`, `h` attributes
2. **Styles**: Fill, stroke, shadow are read from `styles.json` (referenced by pattern or ID)
3. **Children**: For groups, all children are recreated with correct relative positions
4. **Text**: Text content and styling (font, color, bold, etc.) are preserved
5. **Images**: Native dimensions are used for accurate sizing

## Known Limitations

### 1. Crop Properties (Read-Only)

The Google Slides API does not support setting crop properties via `updateImageProperties`. If the original image has cropping applied, the copy will show the full uncropped image.

**Workaround**: For cropped images, manually crop in Google Slides UI after the copy operation.

### 2. Minor Color Precision Loss

Colors may have 1-bit differences in RGB channels (e.g., #c6dbfd becoming #c6dbfc) due to float-to-integer conversion when going through the API.

**Impact**: Imperceptible to human eye, affects ~0.4% of color precision.

### 3. Size Rounding

Element sizes may differ by ~0.01 pt due to EMU (English Metric Units) to points conversion rounding.

**Impact**: Sub-pixel, not visible.

### 4. Image Transparency and Effects

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

## Testing

To verify a copy is pixel-perfect:
1. Run `extraslide push`
2. Run `extraslide pull` to get updated content
3. Compare positions and styles in `styles.json`

Expected results:
- Positions match exactly (or within 0.01 pt)
- Colors match (or within 1-bit per channel)
- All children present with correct relative positions
