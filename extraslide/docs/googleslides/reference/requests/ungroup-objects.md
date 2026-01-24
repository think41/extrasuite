# UngroupObjectsRequest

Ungroups objects, such as groups.

## Schema

```json
{
  "ungroupObjects": {
    "objectIds": array of string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectIds` | array of string | No | The object IDs of the objects to ungroup. Only groups that are not inside other groups can be ung... |

## Example

```json
{
  "requests": [
    {
      "ungroupObjects": {
        // Properties here
      }
    }
  ]
}
```

