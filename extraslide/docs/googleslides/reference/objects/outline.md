# Outline

The outline of a PageElement. If these fields are unset, they may be inherited from a parent placeholder if it exists. If there is no parent, the fields will default to the value used for new page elements created in the Slides editor, which may depend on the page element kind.

## Schema

```json
{
  "outlineFill": [OutlineFill],
  "weight": [Dimension],
  "dashStyle": string,
  "propertyState": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `outlineFill` | [OutlineFill] | The fill of the outline. |
| `weight` | [Dimension] | The thickness of the outline. |
| `dashStyle` | string | The dash style of the outline. |
| `propertyState` | string | The outline property state. Updating the outline on a page element will implicitly update this fi... |

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

### propertyState Values

| Value | Description |
|-------|-------------|
| `RENDERED` | If a property's state is RENDERED, then the element has the corresponding property when rendered ... |
| `NOT_RENDERED` | If a property's state is NOT_RENDERED, then the element does not have the corresponding property ... |
| `INHERIT` | If a property's state is INHERIT, then the property state uses the value of corresponding `proper... |

## Related Objects

- [Dimension](./dimension.md)
- [OutlineFill](./outline-fill.md)

