# Creating Slides

> **Source**: [Google Slides API - Create Slide](https://developers.google.com/workspace/slides/api/guides/create-slide)

## Overview

The Google Slides API enables developers to add slides to existing presentations using the `batchUpdate()` method with a `CreateSlideRequest`.

## Basic Slide Creation

```json
{
  "requests": [
    {
      "createSlide": {
        "objectId": "my_slide_id",
        "insertionIndex": 1,
        "slideLayoutReference": {
          "predefinedLayout": "TITLE_AND_TWO_COLUMNS"
        }
      }
    }
  ]
}
```

## CreateSlideRequest Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `objectId` | string | No | Explicit identifier (must be unique across presentation) |
| `insertionIndex` | integer | No | Position where slide appears (0-based) |
| `slideLayoutReference` | object | No | Layout template selection |
| `placeholderIdMappings` | array | No | Custom IDs for placeholder elements |

## Slide Layouts

### Predefined Layouts

| Layout | Description |
|--------|-------------|
| `BLANK` | Empty slide |
| `CAPTION_ONLY` | Caption at bottom |
| `TITLE` | Title only |
| `TITLE_AND_BODY` | Title with content body |
| `TITLE_AND_TWO_COLUMNS` | Title with two content columns |
| `TITLE_ONLY` | Title at top |
| `SECTION_HEADER` | Section divider |
| `SECTION_TITLE_AND_DESCRIPTION` | Section with description |
| `ONE_COLUMN_TEXT` | Single column text |
| `MAIN_POINT` | Main point emphasis |
| `BIG_NUMBER` | Large number display |

### Using Layout Reference

```json
{
  "slideLayoutReference": {
    "predefinedLayout": "TITLE_AND_BODY"
  }
}
```

Or reference a specific layout by ID:

```json
{
  "slideLayoutReference": {
    "layoutId": "layout_object_id"
  }
}
```

## Placeholder Management

The `placeholderIdMappings` field enables custom IDs for placeholder elements:

```json
{
  "createSlide": {
    "objectId": "my_slide",
    "slideLayoutReference": {
      "predefinedLayout": "TITLE_AND_BODY"
    },
    "placeholderIdMappings": [
      {
        "layoutPlaceholder": {
          "type": "TITLE",
          "index": 0
        },
        "objectId": "my_title_id"
      },
      {
        "layoutPlaceholder": {
          "type": "BODY",
          "index": 0
        },
        "objectId": "my_body_id"
      }
    ]
  }
}
```

### Placeholder Types

| Type | Description |
|------|-------------|
| `TITLE` | Slide title |
| `SUBTITLE` | Slide subtitle |
| `BODY` | Body content |
| `HEADER` | Header |
| `FOOTER` | Footer |
| `SLIDE_NUMBER` | Slide number |
| `DATE_AND_TIME` | Date/time |
| `CENTERED_TITLE` | Centered title |
| `DIAGRAM` | Diagram placeholder |
| `CHART` | Chart placeholder |
| `TABLE` | Table placeholder |
| `MEDIA` | Media (image/video) |
| `OBJECT` | Generic object |
| `SLIDE_IMAGE` | Slide image |

## Response

```json
{
  "replies": [
    {
      "createSlide": {
        "objectId": "my_slide_id"
      }
    }
  ]
}
```

## Combining Operations

Create a slide and add content in a single batch:

```json
{
  "requests": [
    {
      "createSlide": {
        "objectId": "new_slide",
        "insertionIndex": 1,
        "slideLayoutReference": {
          "predefinedLayout": "BLANK"
        }
      }
    },
    {
      "createShape": {
        "objectId": "text_box",
        "shapeType": "TEXT_BOX",
        "elementProperties": {
          "pageObjectId": "new_slide",
          "size": {
            "width": {"magnitude": 3000000, "unit": "EMU"},
            "height": {"magnitude": 3000000, "unit": "EMU"}
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
      "insertText": {
        "objectId": "text_box",
        "text": "Hello, World!"
      }
    }
  ]
}
```

## Best Practices

1. **Use UUIDs for object IDs** rather than plain strings
2. **Omit objectId** to let the API generate unique identifiers
3. **Combine operations** in the same batch request for efficiency
4. **Fill placeholders simultaneously** with slide creation for optimal performance

## Related Documentation

- [Presentations](./presentations.md) - Managing presentations
- [Add Shape](./add-shape.md) - Creating shapes on slides
- [Batch Updates](./batch.md) - Efficient API usage
- [Page Elements](../concepts/page-elements.md) - Element types
