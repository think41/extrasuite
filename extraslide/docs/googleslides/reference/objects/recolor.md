# Recolor

A recolor effect applied on an image.

## Schema

```json
{
  "recolorStops": array of [ColorStop],
  "name": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `recolorStops` | array of [ColorStop] | The recolor effect is represented by a gradient, which is a list of color stops. The colors in th... |
| `name` | string | The name of the recolor effect. The name is determined from the `recolor_stops` by matching the g... |

### name Values

| Value | Description |
|-------|-------------|
| `NONE` | No recolor effect. The default value. |
| `LIGHT1` | A recolor effect that lightens the image using the page's first available color from its color sc... |
| `LIGHT2` | A recolor effect that lightens the image using the page's second available color from its color s... |
| `LIGHT3` | A recolor effect that lightens the image using the page's third available color from its color sc... |
| `LIGHT4` | A recolor effect that lightens the image using the page's fourth available color from its color s... |
| `LIGHT5` | A recolor effect that lightens the image using the page's fifth available color from its color sc... |
| `LIGHT6` | A recolor effect that lightens the image using the page's sixth available color from its color sc... |
| `LIGHT7` | A recolor effect that lightens the image using the page's seventh available color from its color ... |
| `LIGHT8` | A recolor effect that lightens the image using the page's eighth available color from its color s... |
| `LIGHT9` | A recolor effect that lightens the image using the page's ninth available color from its color sc... |
| `LIGHT10` | A recolor effect that lightens the image using the page's tenth available color from its color sc... |
| `DARK1` | A recolor effect that darkens the image using the page's first available color from its color sch... |
| `DARK2` | A recolor effect that darkens the image using the page's second available color from its color sc... |
| `DARK3` | A recolor effect that darkens the image using the page's third available color from its color sch... |
| `DARK4` | A recolor effect that darkens the image using the page's fourth available color from its color sc... |
| `DARK5` | A recolor effect that darkens the image using the page's fifth available color from its color sch... |
| `DARK6` | A recolor effect that darkens the image using the page's sixth available color from its color sch... |
| `DARK7` | A recolor effect that darkens the image using the page's seventh available color from its color s... |
| `DARK8` | A recolor effect that darkens the image using the page's eighth available color from its color sc... |
| `DARK9` | A recolor effect that darkens the image using the page's ninth available color from its color sch... |
| `DARK10` | A recolor effect that darkens the image using the page's tenth available color from its color sch... |
| `GRAYSCALE` | A recolor effect that recolors the image to grayscale. |
| `NEGATIVE` | A recolor effect that recolors the image to negative grayscale. |
| `SEPIA` | A recolor effect that recolors the image using the sepia color. |
| `CUSTOM` | Custom recolor effect. Refer to `recolor_stops` for the concrete gradient. |

## Related Objects

- [ColorStop](./color-stop.md)

