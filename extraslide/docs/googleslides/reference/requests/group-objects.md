# GroupObjectsRequest

Groups objects to create an object group. For example, groups PageElements to create a Group on the same page as all the children.

## Schema

```json
{
  "groupObjects": {
    "groupObjectId": string,
    "childrenObjectIds": array of string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `groupObjectId` | string | No | A user-supplied object ID for the group to be created. If you specify an ID, it must be unique am... |
| `childrenObjectIds` | array of string | No | The object IDs of the objects to group. Only page elements can be grouped. There should be at lea... |

## Example

```json
{
  "requests": [
    {
      "groupObjects": {
        // Properties here
      }
    }
  ]
}
```

