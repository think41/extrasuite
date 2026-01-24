# PageProperties

The properties of the Page. The page will inherit properties from the parent page. Depending on the page type the hierarchy is defined in either SlideProperties or LayoutProperties.

## Schema

```json
{
  "pageBackgroundFill": [PageBackgroundFill],
  "colorScheme": [ColorScheme]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `pageBackgroundFill` | [PageBackgroundFill] | The background fill of the page. If unset, the background fill is inherited from a parent page if... |
| `colorScheme` | [ColorScheme] | The color scheme of the page. If unset, the color scheme is inherited from a parent page. If the ... |

## Related Objects

- [ColorScheme](./color-scheme.md)
- [PageBackgroundFill](./page-background-fill.md)

