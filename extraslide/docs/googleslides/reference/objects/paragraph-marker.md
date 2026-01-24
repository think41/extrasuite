# ParagraphMarker

A TextElement kind that represents the beginning of a new paragraph.

## Schema

```json
{
  "style": [ParagraphStyle],
  "bullet": [Bullet]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `style` | [ParagraphStyle] | The paragraph's style |
| `bullet` | [Bullet] | The bullet for this paragraph. If not present, the paragraph does not belong to a list. |

## Related Objects

- [Bullet](./bullet.md)
- [ParagraphStyle](./paragraph-style.md)

