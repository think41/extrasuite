# UpdateVideoPropertiesRequest

Update the properties of a Video.

## Schema

```json
{
  "updateVideoProperties": {
    "objectId": string,
    "videoProperties": [VideoProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the video the updates are applied to. |
| `videoProperties` | [VideoProperties] | No | The video properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `videoPropertie... |

## Example

```json
{
  "requests": [
    {
      "updateVideoProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [VideoProperties](../objects/video-properties.md)

