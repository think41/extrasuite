# LineProperties

The properties of the Line. When unset, these fields default to values that match the appearance of new lines created in the Slides editor.

## Schema

```json
{
  "lineFill": [LineFill],
  "weight": [Dimension],
  "dashStyle": string,
  "startArrow": string,
  "endArrow": string,
  "link": [Link],
  "startConnection": [LineConnection],
  "endConnection": [LineConnection]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `lineFill` | [LineFill] | The fill of the line. The default line fill matches the defaults for new lines created in the Sli... |
| `weight` | [Dimension] | The thickness of the line. |
| `dashStyle` | string | The dash style of the line. |
| `startArrow` | string | The style of the arrow at the beginning of the line. |
| `endArrow` | string | The style of the arrow at the end of the line. |
| `link` | [Link] | The hyperlink destination of the line. If unset, there is no link. |
| `startConnection` | [LineConnection] | The connection at the beginning of the line. If unset, there is no connection. Only lines with a ... |
| `endConnection` | [LineConnection] | The connection at the end of the line. If unset, there is no connection. Only lines with a Type i... |

### dashStyle Values

| Value | Description |
|-------|-------------|
| `DASH_STYLE_UNSPECIFIED` | Unspecified dash style. |
| `SOLID` | Solid line. Corresponds to ECMA-376 ST_PresetLineDashVal value 'solid'. This is the default dash ... |
| `DOT` | Dotted line. Corresponds to ECMA-376 ST_PresetLineDashVal value 'dot'. |
| `DASH` | Dashed line. Corresponds to ECMA-376 ST_PresetLineDashVal value 'dash'. |
| `DASH_DOT` | Alternating dashes and dots. Corresponds to ECMA-376 ST_PresetLineDashVal value 'dashDot'. |
| `LONG_DASH` | Line with large dashes. Corresponds to ECMA-376 ST_PresetLineDashVal value 'lgDash'. |
| `LONG_DASH_DOT` | Alternating large dashes and dots. Corresponds to ECMA-376 ST_PresetLineDashVal value 'lgDashDot'. |

### startArrow Values

| Value | Description |
|-------|-------------|
| `ARROW_STYLE_UNSPECIFIED` | An unspecified arrow style. |
| `NONE` | No arrow. |
| `STEALTH_ARROW` | Arrow with notched back. Corresponds to ECMA-376 ST_LineEndType value 'stealth'. |
| `FILL_ARROW` | Filled arrow. Corresponds to ECMA-376 ST_LineEndType value 'triangle'. |
| `FILL_CIRCLE` | Filled circle. Corresponds to ECMA-376 ST_LineEndType value 'oval'. |
| `FILL_SQUARE` | Filled square. |
| `FILL_DIAMOND` | Filled diamond. Corresponds to ECMA-376 ST_LineEndType value 'diamond'. |
| `OPEN_ARROW` | Hollow arrow. |
| `OPEN_CIRCLE` | Hollow circle. |
| `OPEN_SQUARE` | Hollow square. |
| `OPEN_DIAMOND` | Hollow diamond. |

### endArrow Values

| Value | Description |
|-------|-------------|
| `ARROW_STYLE_UNSPECIFIED` | An unspecified arrow style. |
| `NONE` | No arrow. |
| `STEALTH_ARROW` | Arrow with notched back. Corresponds to ECMA-376 ST_LineEndType value 'stealth'. |
| `FILL_ARROW` | Filled arrow. Corresponds to ECMA-376 ST_LineEndType value 'triangle'. |
| `FILL_CIRCLE` | Filled circle. Corresponds to ECMA-376 ST_LineEndType value 'oval'. |
| `FILL_SQUARE` | Filled square. |
| `FILL_DIAMOND` | Filled diamond. Corresponds to ECMA-376 ST_LineEndType value 'diamond'. |
| `OPEN_ARROW` | Hollow arrow. |
| `OPEN_CIRCLE` | Hollow circle. |
| `OPEN_SQUARE` | Hollow square. |
| `OPEN_DIAMOND` | Hollow diamond. |

## Related Objects

- [Dimension](./dimension.md)
- [LineConnection](./line-connection.md)
- [LineFill](./line-fill.md)
- [Link](./link.md)

