# LayoutPlaceholderIdMapping

The user-specified ID mapping for a placeholder that will be created on a slide from a specified layout.

## Schema

```json
{
  "layoutPlaceholder": [Placeholder],
  "layoutPlaceholderObjectId": string,
  "objectId": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `layoutPlaceholder` | [Placeholder] | The placeholder on a layout that will be applied to a slide. Only type and index are needed. For ... |
| `layoutPlaceholderObjectId` | string | The object ID of the placeholder on a layout that will be applied to a slide. |
| `objectId` | string | A user-supplied object ID for the placeholder identified above that to be created onto a slide. I... |

## Related Objects

- [Placeholder](./placeholder.md)

