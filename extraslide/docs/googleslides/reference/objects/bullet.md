# Bullet

Describes the bullet of a paragraph.

## Schema

```json
{
  "listId": string,
  "nestingLevel": integer,
  "glyph": string,
  "bulletStyle": [TextStyle]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `listId` | string | The ID of the list this paragraph belongs to. |
| `nestingLevel` | integer | The nesting level of this paragraph in the list. |
| `glyph` | string | The rendered bullet glyph for this paragraph. |
| `bulletStyle` | [TextStyle] | The paragraph specific text style applied to this bullet. |

## Related Objects

- [TextStyle](./text-style.md)

