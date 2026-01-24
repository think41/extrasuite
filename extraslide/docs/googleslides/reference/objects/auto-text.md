# AutoText

A TextElement kind that represents auto text.

## Schema

```json
{
  "type": string,
  "content": string,
  "style": [TextStyle]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `type` | string | The type of this auto text. |
| `content` | string | The rendered content of this auto text, if available. |
| `style` | [TextStyle] | The styling applied to this auto text. |

### type Values

| Value | Description |
|-------|-------------|
| `TYPE_UNSPECIFIED` | An unspecified autotext type. |
| `SLIDE_NUMBER` | Type for autotext that represents the current slide number. |

## Related Objects

- [TextStyle](./text-style.md)

