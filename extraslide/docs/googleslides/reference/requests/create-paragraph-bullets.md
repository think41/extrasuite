# CreateParagraphBulletsRequest

Creates bullets for all of the paragraphs that overlap with the given text index range. The nesting level of each paragraph will be determined by counting leading tabs in front of each paragraph. To avoid excess space between the bullet and the corresponding paragraph, these leading tabs are removed by this request. This may change the indices of parts of the text. If the paragraph immediately before paragraphs being updated is in a list with a matching preset, the paragraphs being updated are added to that preceding list.

## Schema

```json
{
  "createParagraphBullets": {
    "objectId": string,
    "cellLocation": [TableCellLocation],
    "textRange": [Range],
    "bulletPreset": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the shape or table containing the text to add bullets to. |
| `cellLocation` | [TableCellLocation] | No | The optional table cell location if the text to be modified is in a table cell. If present, the o... |
| `textRange` | [Range] | No | The range of text to apply the bullet presets to, based on TextElement indexes. |
| `bulletPreset` | string | No | The kinds of bullet glyphs to be used. Defaults to the `BULLET_DISC_CIRCLE_SQUARE` preset. |

### bulletPreset Values

| Value | Description |
|-------|-------------|
| `BULLET_DISC_CIRCLE_SQUARE` | A bulleted list with a `DISC`, `CIRCLE` and `SQUARE` bullet glyph for the first 3 list nesting le... |
| `BULLET_DIAMONDX_ARROW3D_SQUARE` | A bulleted list with a `DIAMONDX`, `ARROW3D` and `SQUARE` bullet glyph for the first 3 list nesti... |
| `BULLET_CHECKBOX` | A bulleted list with `CHECKBOX` bullet glyphs for all list nesting levels. |
| `BULLET_ARROW_DIAMOND_DISC` | A bulleted list with a `ARROW`, `DIAMOND` and `DISC` bullet glyph for the first 3 list nesting le... |
| `BULLET_STAR_CIRCLE_SQUARE` | A bulleted list with a `STAR`, `CIRCLE` and `SQUARE` bullet glyph for the first 3 list nesting le... |
| `BULLET_ARROW3D_CIRCLE_SQUARE` | A bulleted list with a `ARROW3D`, `CIRCLE` and `SQUARE` bullet glyph for the first 3 list nesting... |
| `BULLET_LEFTTRIANGLE_DIAMOND_DISC` | A bulleted list with a `LEFTTRIANGLE`, `DIAMOND` and `DISC` bullet glyph for the first 3 list nes... |
| `BULLET_DIAMONDX_HOLLOWDIAMOND_SQUARE` | A bulleted list with a `DIAMONDX`, `HOLLOWDIAMOND` and `SQUARE` bullet glyph for the first 3 list... |
| `BULLET_DIAMOND_CIRCLE_SQUARE` | A bulleted list with a `DIAMOND`, `CIRCLE` and `SQUARE` bullet glyph for the first 3 list nesting... |
| `NUMBERED_DIGIT_ALPHA_ROMAN` | A numbered list with `DIGIT`, `ALPHA` and `ROMAN` numeric glyphs for the first 3 list nesting lev... |
| `NUMBERED_DIGIT_ALPHA_ROMAN_PARENS` | A numbered list with `DIGIT`, `ALPHA` and `ROMAN` numeric glyphs for the first 3 list nesting lev... |
| `NUMBERED_DIGIT_NESTED` | A numbered list with `DIGIT` numeric glyphs separated by periods, where each nesting level uses t... |
| `NUMBERED_UPPERALPHA_ALPHA_ROMAN` | A numbered list with `UPPERALPHA`, `ALPHA` and `ROMAN` numeric glyphs for the first 3 list nestin... |
| `NUMBERED_UPPERROMAN_UPPERALPHA_DIGIT` | A numbered list with `UPPERROMAN`, `UPPERALPHA` and `DIGIT` numeric glyphs for the first 3 list n... |
| `NUMBERED_ZERODIGIT_ALPHA_ROMAN` | A numbered list with `ZERODIGIT`, `ALPHA` and `ROMAN` numeric glyphs for the first 3 list nesting... |

## Example

```json
{
  "requests": [
    {
      "createParagraphBullets": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [Range](../objects/range.md)
- [TableCellLocation](../objects/table-cell-location.md)

