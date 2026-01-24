# TextStyle

Represents the styling that can be applied to a TextRun. If this text is contained in a shape with a parent placeholder, then these text styles may be inherited from the parent. Which text styles are inherited depend on the nesting level of lists: * A text run in a paragraph that is not in a list will inherit its text style from the the newline character in the paragraph at the 0 nesting level of the list inside the parent placeholder. * A text run in a paragraph that is in a list will inherit its text style from the newline character in the paragraph at its corresponding nesting level of the list inside the parent placeholder. Inherited text styles are represented as unset fields in this message. If text is contained in a shape without a parent placeholder, unsetting these fields will revert the style to a value matching the defaults in the Slides editor.

## Schema

```json
{
  "backgroundColor": [OptionalColor],
  "foregroundColor": [OptionalColor],
  "bold": boolean,
  "italic": boolean,
  "fontFamily": string,
  "fontSize": [Dimension],
  "link": [Link],
  "baselineOffset": string,
  "smallCaps": boolean,
  "strikethrough": boolean,
  "underline": boolean,
  "weightedFontFamily": [WeightedFontFamily]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `backgroundColor` | [OptionalColor] | The background color of the text. If set, the color is either opaque or transparent, depending on... |
| `foregroundColor` | [OptionalColor] | The color of the text itself. If set, the color is either opaque or transparent, depending on if ... |
| `bold` | boolean | Whether or not the text is rendered as bold. |
| `italic` | boolean | Whether or not the text is italicized. |
| `fontFamily` | string | The font family of the text. The font family can be any font from the Font menu in Slides or from... |
| `fontSize` | [Dimension] | The size of the text's font. When read, the `font_size` will specified in points. |
| `link` | [Link] | The hyperlink destination of the text. If unset, there is no link. Links are not inherited from p... |
| `baselineOffset` | string | The text's vertical offset from its normal position. Text with `SUPERSCRIPT` or `SUBSCRIPT` basel... |
| `smallCaps` | boolean | Whether or not the text is in small capital letters. |
| `strikethrough` | boolean | Whether or not the text is struck through. |
| `underline` | boolean | Whether or not the text is underlined. |
| `weightedFontFamily` | [WeightedFontFamily] | The font family and rendered weight of the text. This field is an extension of `font_family` mean... |

### baselineOffset Values

| Value | Description |
|-------|-------------|
| `BASELINE_OFFSET_UNSPECIFIED` | The text's baseline offset is inherited from the parent. |
| `NONE` | The text is not vertically offset. |
| `SUPERSCRIPT` | The text is vertically offset upwards (superscript). |
| `SUBSCRIPT` | The text is vertically offset downwards (subscript). |

## Related Objects

- [Dimension](./dimension.md)
- [Link](./link.md)
- [OptionalColor](./optional-color.md)
- [WeightedFontFamily](./weighted-font-family.md)

