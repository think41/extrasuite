# Field Masks

> **Source**: [Google Slides API - Field Masks](https://developers.google.com/workspace/slides/api/guides/field-masks)

## Overview

Field masks allow developers to specify which fields should be returned or updated in API requests. Using field masks improves performance by avoiding unnecessary data transfer and processing.

## Reading with Field Masks

When retrieving presentation data, the `fields` URL parameter limits response content.

### Basic Syntax

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}?fields=slides
```

### Syntax Rules

| Rule | Example |
|------|---------|
| Multiple fields | `field1,field2,field3` |
| Subfields (dot notation) | `slides.pageElements` |
| Field names (camelCase) | `pageElements` |
| Field names (underscore) | `page_elements` |
| Grouped subfields | `slides(objectId,pageElements)` |

### Examples

**Get only slide IDs:**
```http
GET .../presentations/{id}?fields=slides.objectId
```

**Get page elements with specific properties:**
```http
GET .../presentations/{id}?fields=slides.pageElements(objectId,size,transform)
```

**Get multiple top-level fields:**
```http
GET .../presentations/{id}?fields=presentationId,title,slides.objectId
```

### Response with Field Mask

Request:
```http
GET .../presentations/{id}?fields=slides.pageElements(objectId,size)
```

Response:
```json
{
  "slides": [
    {
      "pageElements": [
        {
          "objectId": "element_1",
          "size": {
            "width": {"magnitude": 3000000, "unit": "EMU"},
            "height": {"magnitude": 3000000, "unit": "EMU"}
          }
        }
      ]
    }
  ]
}
```

## Updating with Field Masks

Within `batchUpdate` requests, field masks specify which object fields are being modified.

### Basic Structure

```json
{
  "updateShapeProperties": {
    "objectId": "shape_id",
    "shapeProperties": {
      "shapeBackgroundFill": {
        "solidFill": {
          "color": {"themeColor": "DARK1"}
        }
      }
    },
    "fields": "shapeBackgroundFill.solidFill.color"
  }
}
```

### Field Mask Behavior

| Scenario | Result |
|----------|--------|
| Field in mask with value | Field is updated |
| Field in mask without value | Field is cleared/reset |
| Field not in mask | Field is preserved |

### Example: Update Color, Clear Outline

```json
{
  "updateShapeProperties": {
    "objectId": "shape_id",
    "shapeProperties": {
      "shapeBackgroundFill": {
        "solidFill": {
          "color": {"themeColor": "DARK1"}
        }
      }
    },
    "fields": "shapeBackgroundFill.solidFill.color,outline"
  }
}
```

This:
- Updates the background fill color to DARK1
- Clears the outline (no value provided but field is in mask)

## Common Field Masks

### Shape Properties

```
shapeBackgroundFill
shapeBackgroundFill.solidFill
shapeBackgroundFill.solidFill.color
outline
outline.outlineFill
outline.weight
outline.dashStyle
shadow
link
contentAlignment
```

### Text Style

```
bold
italic
underline
strikethrough
fontFamily
fontSize
foregroundColor
backgroundColor
link
baselineOffset
smallCaps
weightedFontFamily
```

### Paragraph Style

```
alignment
lineSpacing
indentStart
indentEnd
indentFirstLine
spaceAbove
spaceBelow
direction
```

### Image Properties

```
cropProperties
transparency
brightness
contrast
recolor
outline
shadow
link
```

## Wildcard Field Masks

You can use `*` to update all fields:

```json
{
  "updateShapeProperties": {
    "objectId": "shape_id",
    "shapeProperties": {...},
    "fields": "*"
  }
}
```

**Warning**: Avoid wildcards in production code. Always explicitly list target fields because:
- Future API updates might introduce new fields
- Unintended field modifications may occur
- Performance impact from unnecessary data transfer

## Best Practices

1. **Be explicit**: Always list specific fields you need
2. **Minimize data**: Request only necessary fields for reads
3. **Preserve values**: Omit fields you don't want to change
4. **Test thoroughly**: Verify field masks produce expected results
5. **Avoid wildcards**: Use `*` only during development

## Performance Impact

| Approach | Read Performance | Update Performance |
|----------|------------------|-------------------|
| No field mask | Slower (full data) | N/A |
| Wildcard `*` | N/A | Risk of errors |
| Specific fields | Optimal | Optimal |

## Related Documentation

- [Batch Updates](./batch.md) - Combining requests
- [Performance](./performance.md) - Optimization tips
- [Page Elements](../concepts/page-elements.md) - Available properties
