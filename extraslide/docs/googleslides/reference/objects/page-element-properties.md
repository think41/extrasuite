# PageElementProperties

Common properties for a page element. Note: When you initially create a PageElement, the API may modify the values of both `size` and `transform`, but the visual size will be unchanged.

## Schema

```json
{
  "pageObjectId": string,
  "size": [Size],
  "transform": [AffineTransform]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `pageObjectId` | string | The object ID of the page where the element is located. |
| `size` | [Size] | The size of the element. |
| `transform` | [AffineTransform] | The transform for the element. |

## Related Objects

- [AffineTransform](./affine-transform.md)
- [Size](./size.md)

