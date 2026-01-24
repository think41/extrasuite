# ReplaceAllShapesWithImageRequest

Replaces all shapes that match the given criteria with the provided image. The images replacing the shapes are rectangular after being inserted into the presentation and do not take on the forms of the shapes.

## Schema

```json
{
  "replaceAllShapesWithImage": {
    "containsText": [SubstringMatchCriteria],
    "imageUrl": string,
    "replaceMethod": string,
    "imageReplaceMethod": string,
    "pageObjectIds": array of string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `containsText` | [SubstringMatchCriteria] | No | If set, this request will replace all of the shapes that contain the given text. |
| `imageUrl` | string | No | The image URL. The image is fetched once at insertion time and a copy is stored for display insid... |
| `replaceMethod` | string | No | The replace method. *Deprecated*: use `image_replace_method` instead. If you specify both a `repl... |
| `imageReplaceMethod` | string | No | The image replace method. If you specify both a `replace_method` and an `image_replace_method`, t... |
| `pageObjectIds` | array of string | No | If non-empty, limits the matches to page elements only on the given pages. Returns a 400 bad requ... |

### replaceMethod Values

| Value | Description |
|-------|-------------|
| `CENTER_INSIDE` | Scales and centers the image to fit within the bounds of the original shape and maintains the ima... |
| `CENTER_CROP` | Scales and centers the image to fill the bounds of the original shape. The image may be cropped i... |

### imageReplaceMethod Values

| Value | Description |
|-------|-------------|
| `IMAGE_REPLACE_METHOD_UNSPECIFIED` | Unspecified image replace method. This value must not be used. |
| `CENTER_INSIDE` | Scales and centers the image to fit within the bounds of the original shape and maintains the ima... |
| `CENTER_CROP` | Scales and centers the image to fill the bounds of the original shape. The image may be cropped i... |

## Example

```json
{
  "requests": [
    {
      "replaceAllShapesWithImage": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [SubstringMatchCriteria](../objects/substring-match-criteria.md)

