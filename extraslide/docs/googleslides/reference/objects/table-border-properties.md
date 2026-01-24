# TableBorderProperties

The border styling properties of the TableBorderCell.

## Schema

```json
{
  "tableBorderFill": [TableBorderFill],
  "weight": [Dimension],
  "dashStyle": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `tableBorderFill` | [TableBorderFill] | The fill of the table border. |
| `weight` | [Dimension] | The thickness of the border. |
| `dashStyle` | string | The dash style of the border. |

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

## Related Objects

- [Dimension](./dimension.md)
- [TableBorderFill](./table-border-fill.md)

