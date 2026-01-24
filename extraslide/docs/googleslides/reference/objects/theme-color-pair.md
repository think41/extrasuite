# ThemeColorPair

A pair mapping a theme color type to the concrete color it represents.

## Schema

```json
{
  "type": string,
  "color": [RgbColor]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `type` | string | The type of the theme color. |
| `color` | [RgbColor] | The concrete color corresponding to the theme color type above. |

### type Values

| Value | Description |
|-------|-------------|
| `THEME_COLOR_TYPE_UNSPECIFIED` | Unspecified theme color. This value should not be used. |
| `DARK1` | Represents the first dark color. |
| `LIGHT1` | Represents the first light color. |
| `DARK2` | Represents the second dark color. |
| `LIGHT2` | Represents the second light color. |
| `ACCENT1` | Represents the first accent color. |
| `ACCENT2` | Represents the second accent color. |
| `ACCENT3` | Represents the third accent color. |
| `ACCENT4` | Represents the fourth accent color. |
| `ACCENT5` | Represents the fifth accent color. |
| `ACCENT6` | Represents the sixth accent color. |
| `HYPERLINK` | Represents the color to use for hyperlinks. |
| `FOLLOWED_HYPERLINK` | Represents the color to use for visited hyperlinks. |
| `TEXT1` | Represents the first text color. |
| `BACKGROUND1` | Represents the first background color. |
| `TEXT2` | Represents the second text color. |
| `BACKGROUND2` | Represents the second background color. |

## Related Objects

- [RgbColor](./rgb-color.md)

