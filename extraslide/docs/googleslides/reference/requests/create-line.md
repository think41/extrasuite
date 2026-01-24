# CreateLineRequest

Creates a line.

## Schema

```json
{
  "createLine": {
    "objectId": string,
    "elementProperties": [PageElementProperties],
    "lineCategory": string,
    "category": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | A user-supplied object ID. If you specify an ID, it must be unique among all pages and page eleme... |
| `elementProperties` | [PageElementProperties] | No | The element properties for the line. |
| `lineCategory` | string | No | The category of the line to be created. *Deprecated*: use `category` instead. The exact line type... |
| `category` | string | No | The category of the line to be created. The exact line type created is determined based on the ca... |

### lineCategory Values

| Value | Description |
|-------|-------------|
| `STRAIGHT` | Straight connectors, including straight connector 1. The is the default category when one is not ... |
| `BENT` | Bent connectors, including bent connector 2 to 5. |
| `CURVED` | Curved connectors, including curved connector 2 to 5. |

### category Values

| Value | Description |
|-------|-------------|
| `LINE_CATEGORY_UNSPECIFIED` | Unspecified line category. |
| `STRAIGHT` | Straight connectors, including straight connector 1. |
| `BENT` | Bent connectors, including bent connector 2 to 5. |
| `CURVED` | Curved connectors, including curved connector 2 to 5. |

## Example

```json
{
  "requests": [
    {
      "createLine": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [PageElementProperties](../objects/page-element-properties.md)

