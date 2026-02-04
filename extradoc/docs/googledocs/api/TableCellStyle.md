# TableCellStyle

The style of a TableCell. Inherited table cell styles are represented as unset fields in this message. A table cell style can inherit from the table's style.

**Type:** object

## Properties

- **rowSpan** (integer): The row span of the cell. This property is read-only.
- **columnSpan** (integer): The column span of the cell. This property is read-only.
- **backgroundColor** ([OptionalColor](optionalcolor.md)): The background color of the cell.
- **borderLeft** ([TableCellBorder](tablecellborder.md)): The left border of the cell.
- **borderRight** ([TableCellBorder](tablecellborder.md)): The right border of the cell.
- **borderTop** ([TableCellBorder](tablecellborder.md)): The top border of the cell.
- **borderBottom** ([TableCellBorder](tablecellborder.md)): The bottom border of the cell.
- **paddingLeft** ([Dimension](dimension.md)): The left padding of the cell.
- **paddingRight** ([Dimension](dimension.md)): The right padding of the cell.
- **paddingTop** ([Dimension](dimension.md)): The top padding of the cell.
- **paddingBottom** ([Dimension](dimension.md)): The bottom padding of the cell.
- **contentAlignment** (enum): The alignment of the content in the table cell. The default alignment matches the alignment for newly created table cells in the Docs editor.
