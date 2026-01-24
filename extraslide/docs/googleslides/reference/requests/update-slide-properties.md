# UpdateSlidePropertiesRequest

Updates the properties of a Slide.

## Schema

```json
{
  "updateSlideProperties": {
    "objectId": string,
    "slideProperties": [SlideProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the slide the update is applied to. |
| `slideProperties` | [SlideProperties] | No | The slide properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root 'slidePropertie... |

## Example

```json
{
  "requests": [
    {
      "updateSlideProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [SlideProperties](../objects/slide-properties.md)

