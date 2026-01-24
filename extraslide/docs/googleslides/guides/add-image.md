# Adding Images

> **Source**: [Google Slides API - Add Image](https://developers.google.com/workspace/slides/api/guides/add-image)

## Overview

The Google Slides API allows developers to insert images into presentations programmatically. Images are treated as page elements with configurable size and position properties.

## Image Requirements

| Requirement | Limit |
|-------------|-------|
| Maximum file size | 50 MB |
| Maximum resolution | 25 megapixels |
| Supported formats | PNG, JPEG, GIF |
| Source | Publicly accessible URL required |

## CreateImageRequest

```json
{
  "createImage": {
    "objectId": "my_image_id",
    "url": "https://example.com/image.png",
    "elementProperties": {
      "pageObjectId": "slide_id",
      "size": {
        "width": {"magnitude": 4000000, "unit": "EMU"},
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
}
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `objectId` | string | No | Unique identifier for the image |
| `url` | string | Yes | Publicly accessible image URL |
| `elementProperties` | object | No | Size and position properties |

### ElementProperties

| Property | Description |
|----------|-------------|
| `pageObjectId` | Target slide ID |
| `size` | Dimensions in EMU |
| `transform` | Position and scaling |

## Units

Images use **EMU (English Metric Units)**:
- 1 inch = 914400 EMU
- 1 point = 12700 EMU
- Standard image size: ~4000000 EMU = ~4.37 inches

## Complete Example

```json
{
  "requests": [
    {
      "createImage": {
        "objectId": "company_logo",
        "url": "https://example.com/logo.png",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": {
            "width": {"magnitude": 4000000, "unit": "EMU"},
            "height": {"magnitude": 4000000, "unit": "EMU"}
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
    }
  ]
}
```

## Response

```json
{
  "replies": [
    {
      "createImage": {
        "objectId": "company_logo"
      }
    }
  ]
}
```

## Handling Private Images

For private or local images:

1. Upload to Google Cloud Storage
2. Generate a signed URL with 15-minute expiration
3. Use the signed URL in `CreateImageRequest`

**Important**: Uploaded images are automatically deleted after 15 minutes.

### Using Google Cloud Storage

```python
from google.cloud import storage

def get_signed_url(bucket_name, blob_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="GET"
    )
    return url
```

## Updating Image Properties

Use `UpdateImagePropertiesRequest`:

```json
{
  "updateImageProperties": {
    "objectId": "image_id",
    "imageProperties": {
      "transparency": 0.5,
      "brightness": 0.1,
      "contrast": 0.2
    },
    "fields": "transparency,brightness,contrast"
  }
}
```

### Available Properties

| Property | Description |
|----------|-------------|
| `cropProperties` | Crop the image |
| `transparency` | 0.0 (opaque) to 1.0 (transparent) |
| `brightness` | -1.0 to 1.0 |
| `contrast` | -1.0 to 1.0 |
| `recolor` | Apply recolor effect |
| `outline` | Image border |
| `shadow` | Drop shadow (read-only) |
| `link` | Hyperlink |

## Replacing Images

Use `ReplaceImageRequest`:

```json
{
  "replaceImage": {
    "imageObjectId": "existing_image_id",
    "url": "https://example.com/new-image.png",
    "imageReplaceMethod": "CENTER_INSIDE"
  }
}
```

### Replace Methods

| Method | Description |
|--------|-------------|
| `CENTER_INSIDE` | Scale image to fit within bounds, centered |
| `CENTER_CROP` | Scale to fill bounds, crop excess |

## Related Documentation

- [Add Shape](./add-shape.md) - Creating shapes
- [Transform Guide](./transform.md) - Positioning elements
- [Merge Guide](./merge.md) - Replacing shapes with images
- [Page Elements](../concepts/page-elements.md) - Element types
