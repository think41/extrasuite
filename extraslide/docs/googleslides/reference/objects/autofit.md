# Autofit

The autofit properties of a Shape. This property is only set for shapes that allow text.

## Schema

```json
{
  "autofitType": string,
  "fontScale": number,
  "lineSpacingReduction": number
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `autofitType` | string | The autofit type of the shape. If the autofit type is AUTOFIT_TYPE_UNSPECIFIED, the autofit type ... |
| `fontScale` | number | The font scale applied to the shape. For shapes with autofit_type NONE or SHAPE_AUTOFIT, this val... |
| `lineSpacingReduction` | number | The line spacing reduction applied to the shape. For shapes with autofit_type NONE or SHAPE_AUTOF... |

### autofitType Values

| Value | Description |
|-------|-------------|
| `AUTOFIT_TYPE_UNSPECIFIED` | The autofit type is unspecified. |
| `NONE` | Do not autofit. |
| `TEXT_AUTOFIT` | Shrink text on overflow to fit the shape. |
| `SHAPE_AUTOFIT` | Resize the shape to fit the text. |

