# UpdatePagePropertiesRequest

Updates the properties of a Page.

## Schema

```json
{
  "updatePageProperties": {
    "objectId": string,
    "pageProperties": [PageProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the page the update is applied to. |
| `pageProperties` | [PageProperties] | No | The page properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `pageProperties... |

## Example

```json
{
  "requests": [
    {
      "updatePageProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [PageProperties](../objects/page-properties.md)

