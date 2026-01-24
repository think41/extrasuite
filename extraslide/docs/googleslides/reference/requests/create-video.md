# CreateVideoRequest

Creates a video. NOTE: Creating a video from Google Drive requires that the requesting app have at least one of the drive, drive.readonly, or drive.file OAuth scopes.

## Schema

```json
{
  "createVideo": {
    "objectId": string,
    "elementProperties": [PageElementProperties],
    "source": string,
    "id": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | A user-supplied object ID. If you specify an ID, it must be unique among all pages and page eleme... |
| `elementProperties` | [PageElementProperties] | No | The element properties for the video. The PageElementProperties.size property is optional. If you... |
| `source` | string | No | The video source. |
| `id` | string | No | The video source's unique identifier for this video. e.g. For YouTube video https://www.youtube.c... |

### source Values

| Value | Description |
|-------|-------------|
| `SOURCE_UNSPECIFIED` | The video source is unspecified. |
| `YOUTUBE` | The video source is YouTube. |
| `DRIVE` | The video source is Google Drive. |

## Example

```json
{
  "requests": [
    {
      "createVideo": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [PageElementProperties](../objects/page-element-properties.md)

