# ParagraphStyle

Styles that apply to a whole paragraph. Inherited paragraph styles are represented as unset fields in this message. A paragraph style's parent depends on where the paragraph style is defined: * The ParagraphStyle on a Paragraph inherits from the paragraph's corresponding named style type. * The ParagraphStyle on a named style inherits from the normal text named style. * The ParagraphStyle of the normal text named style inherits from the default paragraph style in the Docs editor. * The ParagraphStyle on a Paragraph element that's contained in a table may inherit its paragraph style from the table style. If the paragraph style does not inherit from a parent, unsetting fields will revert the style to a value matching the defaults in the Docs editor.

**Type:** object

## Properties

- **headingId** (string): The heading ID of the paragraph. If empty, then this paragraph is not a heading. This property is read-only.
- **namedStyleType** (enum): The named style type of the paragraph. Since updating the named style type affects other properties within ParagraphStyle, the named style type is applied before the other properties are updated.
- **alignment** (enum): The text alignment for this paragraph.
- **lineSpacing** (number): The amount of space between lines, as a percentage of normal, where normal is represented as 100.0. If unset, the value is inherited from the parent.
- **direction** (enum): The text direction of this paragraph. If unset, the value defaults to LEFT_TO_RIGHT since paragraph direction is not inherited.
- **spacingMode** (enum): The spacing mode for the paragraph.
- **spaceAbove** ([Dimension](dimension.md)): The amount of extra space above the paragraph. If unset, the value is inherited from the parent.
- **spaceBelow** ([Dimension](dimension.md)): The amount of extra space below the paragraph. If unset, the value is inherited from the parent.
- **borderBetween** ([ParagraphBorder](paragraphborder.md)): The border between this paragraph and the next and previous paragraphs. If unset, the value is inherited from the parent. The between border is rendered when the adjacent paragraph has the same border and indent properties. Paragraph borders cannot be partially updated. When changing a paragraph border, the new border must be specified in its entirety.
- **borderTop** ([ParagraphBorder](paragraphborder.md)): The border at the top of this paragraph. If unset, the value is inherited from the parent. The top border is rendered when the paragraph above has different border and indent properties. Paragraph borders cannot be partially updated. When changing a paragraph border, the new border must be specified in its entirety.
- **borderBottom** ([ParagraphBorder](paragraphborder.md)): The border at the bottom of this paragraph. If unset, the value is inherited from the parent. The bottom border is rendered when the paragraph below has different border and indent properties. Paragraph borders cannot be partially updated. When changing a paragraph border, the new border must be specified in its entirety.
- **borderLeft** ([ParagraphBorder](paragraphborder.md)): The border to the left of this paragraph. If unset, the value is inherited from the parent. Paragraph borders cannot be partially updated. When changing a paragraph border, the new border must be specified in its entirety.
- **borderRight** ([ParagraphBorder](paragraphborder.md)): The border to the right of this paragraph. If unset, the value is inherited from the parent. Paragraph borders cannot be partially updated. When changing a paragraph border, the new border must be specified in its entirety.
- **indentFirstLine** ([Dimension](dimension.md)): The amount of indentation for the first line of the paragraph. If unset, the value is inherited from the parent.
- **indentStart** ([Dimension](dimension.md)): The amount of indentation for the paragraph on the side that corresponds to the start of the text, based on the current paragraph direction. If unset, the value is inherited from the parent.
- **indentEnd** ([Dimension](dimension.md)): The amount of indentation for the paragraph on the side that corresponds to the end of the text, based on the current paragraph direction. If unset, the value is inherited from the parent.
- **tabStops** (array of [TabStop](tabstop.md)): A list of the tab stops for this paragraph. The list of tab stops is not inherited. This property is read-only.
- **keepLinesTogether** (boolean): Whether all lines of the paragraph should be laid out on the same page or column if possible. If unset, the value is inherited from the parent.
- **keepWithNext** (boolean): Whether at least a part of this paragraph should be laid out on the same page or column as the next paragraph if possible. If unset, the value is inherited from the parent.
- **avoidWidowAndOrphan** (boolean): Whether to avoid widows and orphans for the paragraph. If unset, the value is inherited from the parent.
- **shading** ([Shading](shading.md)): The shading of the paragraph. If unset, the value is inherited from the parent.
- **pageBreakBefore** (boolean): Whether the current paragraph should always start at the beginning of a page. If unset, the value is inherited from the parent. Attempting to update page_break_before for paragraphs in unsupported regions, including Table, Header, Footer and Footnote, can result in an invalid document state that returns a 400 bad request error.
