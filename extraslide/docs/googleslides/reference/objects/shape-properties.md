# ShapeProperties

The properties of a Shape. If the shape is a placeholder shape as determined by the placeholder field, then these properties may be inherited from a parent placeholder shape. Determining the rendered value of the property depends on the corresponding property_state field value. Any text autofit settings on the shape are automatically deactivated by requests that can impact how text fits in the shape.

## Schema

```json
{
  "shapeBackgroundFill": [ShapeBackgroundFill],
  "outline": [Outline],
  "shadow": [Shadow],
  "link": [Link],
  "contentAlignment": string,
  "autofit": [Autofit]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `shapeBackgroundFill` | [ShapeBackgroundFill] | The background fill of the shape. If unset, the background fill is inherited from a parent placeh... |
| `outline` | [Outline] | The outline of the shape. If unset, the outline is inherited from a parent placeholder if it exis... |
| `shadow` | [Shadow] | The shadow properties of the shape. If unset, the shadow is inherited from a parent placeholder i... |
| `link` | [Link] | The hyperlink destination of the shape. If unset, there is no link. Links are not inherited from ... |
| `contentAlignment` | string | The alignment of the content in the shape. If unspecified, the alignment is inherited from a pare... |
| `autofit` | [Autofit] | The autofit properties of the shape. This property is only set for shapes that allow text. |

### contentAlignment Values

| Value | Description |
|-------|-------------|
| `CONTENT_ALIGNMENT_UNSPECIFIED` | An unspecified content alignment. The content alignment is inherited from the parent if it exists. |
| `CONTENT_ALIGNMENT_UNSUPPORTED` | An unsupported content alignment. |
| `TOP` | An alignment that aligns the content to the top of the content holder. Corresponds to ECMA-376 ST... |
| `MIDDLE` | An alignment that aligns the content to the middle of the content holder. Corresponds to ECMA-376... |
| `BOTTOM` | An alignment that aligns the content to the bottom of the content holder. Corresponds to ECMA-376... |

## Related Objects

- [Autofit](./autofit.md)
- [Link](./link.md)
- [Outline](./outline.md)
- [Shadow](./shadow.md)
- [ShapeBackgroundFill](./shape-background-fill.md)

