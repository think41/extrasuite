# ParagraphStyle

Styles that apply to a whole paragraph. If this text is contained in a shape with a parent placeholder, then these paragraph styles may be inherited from the parent. Which paragraph styles are inherited depend on the nesting level of lists: * A paragraph not in a list will inherit its paragraph style from the paragraph at the 0 nesting level of the list inside the parent placeholder. * A paragraph in a list will inherit its paragraph style from the paragraph at its corresponding nesting level of the list inside the parent placeholder. Inherited paragraph styles are represented as unset fields in this message.

## Schema

```json
{
  "lineSpacing": number,
  "alignment": string,
  "indentStart": [Dimension],
  "indentEnd": [Dimension],
  "spaceAbove": [Dimension],
  "spaceBelow": [Dimension],
  "indentFirstLine": [Dimension],
  "direction": string,
  "spacingMode": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `lineSpacing` | number | The amount of space between lines, as a percentage of normal, where normal is represented as 100.... |
| `alignment` | string | The text alignment for this paragraph. |
| `indentStart` | [Dimension] | The amount indentation for the paragraph on the side that corresponds to the start of the text, b... |
| `indentEnd` | [Dimension] | The amount indentation for the paragraph on the side that corresponds to the end of the text, bas... |
| `spaceAbove` | [Dimension] | The amount of extra space above the paragraph. If unset, the value is inherited from the parent. |
| `spaceBelow` | [Dimension] | The amount of extra space below the paragraph. If unset, the value is inherited from the parent. |
| `indentFirstLine` | [Dimension] | The amount of indentation for the start of the first line of the paragraph. If unset, the value i... |
| `direction` | string | The text direction of this paragraph. If unset, the value defaults to LEFT_TO_RIGHT since text di... |
| `spacingMode` | string | The spacing mode for the paragraph. |

### alignment Values

| Value | Description |
|-------|-------------|
| `ALIGNMENT_UNSPECIFIED` | The paragraph alignment is inherited from the parent. |
| `START` | The paragraph is aligned to the start of the line. Left-aligned for LTR text, right-aligned other... |
| `CENTER` | The paragraph is centered. |
| `END` | The paragraph is aligned to the end of the line. Right-aligned for LTR text, left-aligned otherwise. |
| `JUSTIFIED` | The paragraph is justified. |

### direction Values

| Value | Description |
|-------|-------------|
| `TEXT_DIRECTION_UNSPECIFIED` | The text direction is inherited from the parent. |
| `LEFT_TO_RIGHT` | The text goes from left to right. |
| `RIGHT_TO_LEFT` | The text goes from right to left. |

### spacingMode Values

| Value | Description |
|-------|-------------|
| `SPACING_MODE_UNSPECIFIED` | The spacing mode is inherited from the parent. |
| `NEVER_COLLAPSE` | Paragraph spacing is always rendered. |
| `COLLAPSE_LISTS` | Paragraph spacing is skipped between list elements. |

## Related Objects

- [Dimension](./dimension.md)

