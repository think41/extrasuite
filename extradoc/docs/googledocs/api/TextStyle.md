# TextStyle

Represents the styling that can be applied to text. Inherited text styles are represented as unset fields in this message. A text style's parent depends on where the text style is defined: * The TextStyle of text in a Paragraph inherits from the paragraph's corresponding named style type. * The TextStyle on a named style inherits from the normal text named style. * The TextStyle of the normal text named style inherits from the default text style in the Docs editor. * The TextStyle on a Paragraph element that's contained in a table may inherit its text style from the table style. If the text style does not inherit from a parent, unsetting fields will revert the style to a value matching the defaults in the Docs editor.

**Type:** object

## Properties

- **bold** (boolean): Whether or not the text is rendered as bold.
- **italic** (boolean): Whether or not the text is italicized.
- **underline** (boolean): Whether or not the text is underlined.
- **strikethrough** (boolean): Whether or not the text is struck through.
- **smallCaps** (boolean): Whether or not the text is in small capital letters.
- **backgroundColor** ([OptionalColor](optionalcolor.md)): The background color of the text. If set, the color is either an RGB color or transparent, depending on the `color` field.
- **foregroundColor** ([OptionalColor](optionalcolor.md)): The foreground color of the text. If set, the color is either an RGB color or transparent, depending on the `color` field.
- **fontSize** ([Dimension](dimension.md)): The size of the text's font.
- **weightedFontFamily** ([WeightedFontFamily](weightedfontfamily.md)): The font family and rendered weight of the text. If an update request specifies values for both `weighted_font_family` and `bold`, the `weighted_font_family` is applied first, then `bold`. If `weighted_font_family#weight` is not set, it defaults to `400`. If `weighted_font_family` is set, then `weighted_font_family#font_family` must also be set with a non-empty value. Otherwise, a 400 bad request error is returned.
- **baselineOffset** (enum): The text's vertical offset from its normal position. Text with `SUPERSCRIPT` or `SUBSCRIPT` baseline offsets is automatically rendered in a smaller font size, computed based on the `font_size` field. Changes in this field don't affect the `font_size`.
- **link** ([Link](link.md)): The hyperlink destination of the text. If unset, there's no link. Links are not inherited from parent text. Changing the link in an update request causes some other changes to the text style of the range: * When setting a link, the text foreground color will be updated to the default link color and the text will be underlined. If these fields are modified in the same request, those values will be used instead of the link defaults. * Setting a link on a text range that overlaps with an existing link will also update the existing link to point to the new URL. * Links are not settable on newline characters. As a result, setting a link on a text range that crosses a paragraph boundary, such as `"ABC\n123"`, will separate the newline character(s) into their own text runs. The link will be applied separately to the runs before and after the newline. * Removing a link will update the text style of the range to match the style of the preceding text (or the default text styles if the preceding text is another link) unless different styles are being set in the same request.
