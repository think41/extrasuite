# UpdatePageElementAltTextRequest

Updates the alt text title and/or description of a page element.

## Schema

```json
{
  "updatePageElementAltText": {
    "objectId": string,
    "title": string,
    "description": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the page element the updates are applied to. |
| `title` | string | No | The updated alt text title of the page element. If unset the existing value will be maintained. T... |
| `description` | string | No | The updated alt text description of the page element. If unset the existing value will be maintai... |

## Example

```json
{
  "requests": [
    {
      "updatePageElementAltText": {
        // Properties here
      }
    }
  ]
}
```

