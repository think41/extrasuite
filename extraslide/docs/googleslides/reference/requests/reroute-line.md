# RerouteLineRequest

Reroutes a line such that it's connected at the two closest connection sites on the connected page elements.

## Schema

```json
{
  "rerouteLine": {
    "objectId": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the line to reroute. Only a line with a category indicating it is a "connector" ... |

## Example

```json
{
  "requests": [
    {
      "rerouteLine": {
        // Properties here
      }
    }
  ]
}
```

