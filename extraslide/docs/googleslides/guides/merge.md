# Merging Data into Presentations

> **Source**: [Google Slides API - Merge](https://developers.google.com/workspace/slides/api/guides/merge)

## Overview

The Google Slides API enables developers to implement mail merge functionality by combining external data with templated presentations. This separates content from design, allowing designers to refine layouts independently.

## Basic Workflow

1. **Create a template** with placeholder content for design purposes
2. **Replace placeholders with tags** - unique text strings (e.g., `{{account-holder-name}}`)
3. **Copy the template** using the Google Drive API
4. **Execute replacements** via `batchUpdate` with `replaceAllText` and `replaceAllShapesWithImage`

**Important**: Always work with copies of templates, never modify the primary template directly.

## Text Merging

### ReplaceAllTextRequest

```json
{
  "replaceAllText": {
    "containsText": {
      "text": "{{customer-name}}",
      "matchCase": true
    },
    "replaceText": "John Doe"
  }
}
```

This replaces ALL instances of `{{customer-name}}` throughout the presentation.

### Multiple Replacements

```json
{
  "requests": [
    {
      "replaceAllText": {
        "containsText": {"text": "{{customer-name}}", "matchCase": true},
        "replaceText": "John Doe"
      }
    },
    {
      "replaceAllText": {
        "containsText": {"text": "{{company}}", "matchCase": true},
        "replaceText": "Acme Corp"
      }
    },
    {
      "replaceAllText": {
        "containsText": {"text": "{{date}}", "matchCase": true},
        "replaceText": "January 15, 2024"
      }
    }
  ]
}
```

### Response

```json
{
  "replies": [
    {
      "replaceAllText": {
        "occurrencesChanged": 3
      }
    }
  ]
}
```

## Image Merging

### ReplaceAllShapesWithImageRequest

```json
{
  "replaceAllShapesWithImage": {
    "imageUrl": "https://example.com/logo.png",
    "replaceMethod": "CENTER_INSIDE",
    "containsText": {
      "text": "{{company-logo}}",
      "matchCase": true
    }
  }
}
```

The API automatically positions and scales images to fit within the tag shape's bounds while preserving aspect ratio.

### Replace Methods

| Method | Description |
|--------|-------------|
| `CENTER_INSIDE` | Scale to fit inside bounds, preserve aspect ratio |
| `CENTER_CROP` | Scale to fill bounds, crop excess |

## Complete Merge Example

```json
{
  "requests": [
    {
      "replaceAllText": {
        "containsText": {"text": "{{customer-name}}", "matchCase": true},
        "replaceText": "John Doe"
      }
    },
    {
      "replaceAllText": {
        "containsText": {"text": "{{account-number}}", "matchCase": true},
        "replaceText": "ACC-12345"
      }
    },
    {
      "replaceAllShapesWithImage": {
        "imageUrl": "https://example.com/company-logo.png",
        "replaceMethod": "CENTER_INSIDE",
        "containsText": {"text": "{{company-logo}}", "matchCase": true}
      }
    },
    {
      "replaceAllShapesWithImage": {
        "imageUrl": "https://example.com/profile-photo.jpg",
        "replaceMethod": "CENTER_CROP",
        "containsText": {"text": "{{profile-photo}}", "matchCase": true}
      }
    }
  ]
}
```

## Specific Element Replacement

For replacing only certain text boxes or images (e.g., on specific slides), you need to target by element ID.

### Text Replacement by ID

```json
{
  "requests": [
    {
      "deleteText": {
        "objectId": "shape_id",
        "textRange": {"type": "ALL"}
      }
    },
    {
      "insertText": {
        "objectId": "shape_id",
        "text": "New text content"
      }
    }
  ]
}
```

### Image Replacement by ID

1. Get the tag shape's ID
2. Copy size and transform information
3. Add image using that sizing data
4. Delete the tag shape

```json
{
  "requests": [
    {
      "createImage": {
        "objectId": "new_image_id",
        "url": "https://example.com/image.png",
        "elementProperties": {
          "pageObjectId": "slide_id",
          "size": {
            "width": {"magnitude": 3000000, "unit": "EMU"},
            "height": {"magnitude": 2000000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 100000,
            "translateY": 100000,
            "unit": "EMU"
          }
        }
      }
    },
    {
      "deleteObject": {
        "objectId": "tag_shape_id"
      }
    }
  ]
}
```

## Preserving Aspect Ratio

When replacing tags with images, calculate proper dimensions:

```python
# Original tag shape
tag_width = tag_size.width * tag_transform.scaleX
tag_height = tag_size.height * tag_transform.scaleY

# For new image, use the visual size
image_element_properties = {
    "size": {
        "width": {"magnitude": tag_width, "unit": "EMU"},
        "height": {"magnitude": tag_height, "unit": "EMU"}
    },
    "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": tag_transform.translateX,
        "translateY": tag_transform.translateY,
        "unit": "EMU"
    }
}
```

This prevents double-scaling and ensures the image's aspect ratio is preserved.

## Replacing with Charts

### ReplaceAllShapesWithSheetsChartRequest

```json
{
  "replaceAllShapesWithSheetsChart": {
    "spreadsheetId": "spreadsheet_id",
    "chartId": 12345,
    "linkingMode": "LINKED",
    "containsText": {
      "text": "{{sales-chart}}",
      "matchCase": true
    }
  }
}
```

## Template Management

### Application-Owned Templates

Use a service account to create and maintain the template, then grant read/write permissions appropriately.

### User Instances

Always use end-user credentials when creating presentation copies. This:
- Gives users full control over the resulting presentation
- Prevents scaling issues related to per-user limits in Google Drive

## Best Practices

1. **Use unique tag names** with delimiters like `{{tag-name}}`
2. **Match case** for reliable replacements
3. **Copy before merging** to preserve templates
4. **Batch replacements** for efficiency
5. **Handle missing tags** gracefully

## Related Documentation

- [Add Image](./add-image.md) - Inserting images
- [Add Chart](./add-chart.md) - Embedding charts
- [Batch Updates](./batch.md) - Efficient API usage
- [Presentations](./presentations.md) - Copying presentations
