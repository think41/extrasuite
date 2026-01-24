# UpdatePageElementsZOrderRequest

Updates the Z-order of page elements. Z-order is an ordering of the elements on the page from back to front. The page element in the front may cover the elements that are behind it.

## Schema

```json
{
  "updatePageElementsZOrder": {
    "pageElementObjectIds": array of string,
    "operation": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `pageElementObjectIds` | array of string | No | The object IDs of the page elements to update. All the page elements must be on the same page and... |
| `operation` | string | No | The Z-order operation to apply on the page elements. When applying the operation on multiple page... |

### operation Values

| Value | Description |
|-------|-------------|
| `Z_ORDER_OPERATION_UNSPECIFIED` | Unspecified operation. |
| `BRING_TO_FRONT` | Brings the page elements to the front of the page. |
| `BRING_FORWARD` | Brings the page elements forward on the page by one element relative to the forwardmost one in th... |
| `SEND_BACKWARD` | Sends the page elements backward on the page by one element relative to the furthest behind one i... |
| `SEND_TO_BACK` | Sends the page elements to the back of the page. |

## Example

```json
{
  "requests": [
    {
      "updatePageElementsZOrder": {
        // Properties here
      }
    }
  ]
}
```

