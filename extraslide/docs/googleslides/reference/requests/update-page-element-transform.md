# UpdatePageElementTransformRequest

Updates the transform of a page element. Updating the transform of a group will change the absolute transform of the page elements in that group, which can change their visual appearance. See the documentation for PageElement.transform for more details.

## Schema

```json
{
  "updatePageElementTransform": {
    "objectId": string,
    "transform": [AffineTransform],
    "applyMode": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the page element to update. |
| `transform` | [AffineTransform] | No | The input transform matrix used to update the page element. |
| `applyMode` | string | No | The apply mode of the transform update. |

### applyMode Values

| Value | Description |
|-------|-------------|
| `APPLY_MODE_UNSPECIFIED` | Unspecified mode. |
| `RELATIVE` | Applies the new AffineTransform matrix to the existing one, and replaces the existing one with th... |
| `ABSOLUTE` | Replaces the existing AffineTransform matrix with the new one. |

## Example

```json
{
  "requests": [
    {
      "updatePageElementTransform": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [AffineTransform](../objects/affine-transform.md)

