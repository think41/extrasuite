# DuplicateObjectRequest

Duplicates a slide or page element. When duplicating a slide, the duplicate slide will be created immediately following the specified slide. When duplicating a page element, the duplicate will be placed on the same page at the same position as the original.

## Schema

```json
{
  "duplicateObject": {
    "objectId": string,
    "objectIds": map<string, string>
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The ID of the object to duplicate. |
| `objectIds` | map<string, string> | No | The object being duplicated may contain other objects, for example when duplicating a slide or a ... |

## Example

```json
{
  "requests": [
    {
      "duplicateObject": {
        // Properties here
      }
    }
  ]
}
```

