"""
Google Sheets API Types

Auto-generated from Google Sheets API v4 discovery document.
Do not edit manually - run scripts/generate_types.py instead.

These TypedDict classes provide static type checking for Google Sheets API
request and response objects without runtime overhead.
"""

from __future__ import annotations

from typing import Any, TypedDict

# =============================================================================
# Google Sheets API Types
# =============================================================================


# =============================================================================
# Core Objects
# =============================================================================


class GridRange(TypedDict, total=False):
    """A range on a sheet. All indexes are zero-based. Indexes are half open, i.e. the start index is inclusive and the end index is exclusive -- [start_index, end_index). Missing indexes indicate the range is unbounded on that side. For example, if `"Sheet1"` is sheet ID 123456, then: `Sheet1!A1:A1 == sheet_id: 123456, start_row_index: 0, end_row_index: 1, start_column_index: 0, end_column_index: 1` `Sheet1!A3:B4 == sheet_id: 123456, start_row_index: 2, end_row_index: 4, start_column_index: 0, end_column_index: 2` `Sheet1!A:B == sheet_id: 123456, start_column_index: 0, end_column_index: 2` `Sheet1!A5:B == sheet_id: 123456, start_row_index: 4, start_column_index: 0, end_column_index: 2` `Sheet1 == sheet_id: 123456` The start index must always be less than or equal to the end index. If the start index equals the end index, then the range is empty. Empty ranges are typically not meaningful and are usually rendered in the UI as `#REF!`."""

    # The end column (exclusive) of the range, or not set if unbounded.
    endColumnIndex: int

    # The end row (exclusive) of the range, or not set if unbounded.
    endRowIndex: int

    # The sheet this range is on.
    sheetId: int

    # The start column (inclusive) of the range, or not set if unbounded.
    startColumnIndex: int

    # The start row (inclusive) of the range, or not set if unbounded.
    startRowIndex: int


class GridCoordinate(TypedDict, total=False):
    """A coordinate in a sheet. All indexes are zero-based."""

    # The column index of the coordinate.
    columnIndex: int

    # The row index of the coordinate.
    rowIndex: int

    # The sheet this coordinate is on.
    sheetId: int


class CellFormat(TypedDict, total=False):
    """The format of a cell."""

    # The background color of the cell. Deprecated: Use background_color_style.
    # Deprecated
    backgroundColor: Color

    # The background color of the cell. If background_color is also set, this f...
    backgroundColorStyle: ColorStyle

    # The borders of the cell.
    borders: Borders

    # The horizontal alignment of the value in the cell.
    # Enum values:
    #   "HORIZONTAL_ALIGN_UNSPECIFIED": The horizontal alignment is not specified. Do not use this.
    #   "LEFT": The text is explicitly aligned to the left of the cell.
    #   "CENTER": The text is explicitly aligned to the center of the cell.
    #   "RIGHT": The text is explicitly aligned to the right of the cell.
    horizontalAlignment: str

    # If one exists, how a hyperlink should be displayed in the cell.
    # Enum values:
    #   "HYPERLINK_DISPLAY_TYPE_UNSPECIFIED": The default value: the hyperlink is rendered. Do not use ...
    #   "LINKED": A hyperlink should be explicitly rendered.
    #   "PLAIN_TEXT": A hyperlink should not be rendered.
    hyperlinkDisplayType: str

    # A format describing how number values should be represented to the user.
    numberFormat: NumberFormat

    # The padding of the cell.
    padding: Padding

    # The direction of the text in the cell.
    # Enum values:
    #   "TEXT_DIRECTION_UNSPECIFIED": The text direction is not specified. Do not use this.
    #   "LEFT_TO_RIGHT": The text direction of left-to-right was set by the user.
    #   "RIGHT_TO_LEFT": The text direction of right-to-left was set by the user.
    textDirection: str

    # The format of the text in the cell (unless overridden by a format run). S...
    textFormat: TextFormat

    # The rotation applied to text in the cell.
    textRotation: TextRotation

    # The vertical alignment of the value in the cell.
    # Enum values:
    #   "VERTICAL_ALIGN_UNSPECIFIED": The vertical alignment is not specified. Do not use this.
    #   "TOP": The text is explicitly aligned to the top of the cell.
    #   "MIDDLE": The text is explicitly aligned to the middle of the cell.
    #   "BOTTOM": The text is explicitly aligned to the bottom of the cell.
    verticalAlignment: str

    # The wrap strategy for the value in the cell.
    # Enum values:
    #   "WRAP_STRATEGY_UNSPECIFIED": The default value, do not use.
    #   "OVERFLOW_CELL": Lines that are longer than the cell width will be written...
    #   "LEGACY_WRAP": This wrap strategy represents the old Google Sheets wrap ...
    #   "CLIP": Lines that are longer than the cell width will be clipped...
    #   "WRAP": Words that are longer than a line are wrapped at the char...
    wrapStrategy: str


class DimensionRange(TypedDict, total=False):
    """A range along a single dimension on a sheet. All indexes are zero-based. Indexes are half open: the start index is inclusive and the end index is exclusive. Missing indexes indicate the range is unbounded on that side."""

    # The dimension of the span.
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    dimension: str

    # The end (exclusive) of the span, or not set if unbounded.
    endIndex: int

    # The sheet this span is on.
    sheetId: int

    # The start (inclusive) of the span, or not set if unbounded.
    startIndex: int


class DimensionGroup(TypedDict, total=False):
    """A group over an interval of rows or columns on a sheet, which can contain or be contained within other groups. A group can be collapsed or expanded as a unit on the sheet."""

    # This field is true if this group is collapsed. A collapsed group remains ...
    collapsed: bool

    # The depth of the group, representing how many groups have a range that wh...
    depth: int

    # The range over which this group exists.
    range: DimensionRange


class NamedRange(TypedDict, total=False):
    """A named range."""

    # The name of the named range.
    name: str

    # The ID of the named range.
    namedRangeId: str

    # The range this represents.
    range: GridRange


class GridProperties(TypedDict, total=False):
    """Properties of a grid."""

    # The number of columns in the grid.
    columnCount: int

    # True if the column grouping control toggle is shown after the group.
    columnGroupControlAfter: bool

    # The number of columns that are frozen in the grid.
    frozenColumnCount: int

    # The number of rows that are frozen in the grid.
    frozenRowCount: int

    # True if the grid isn't showing gridlines in the UI.
    hideGridlines: bool

    # The number of rows in the grid.
    rowCount: int

    # True if the row grouping control toggle is shown after the group.
    rowGroupControlAfter: bool


class SheetProperties(TypedDict, total=False):
    """Properties of a sheet."""

    # Output only. If present, the field contains DATA_SOURCE sheet specific pr...
    # Read-only field
    dataSourceSheetProperties: DataSourceSheetProperties

    # Additional properties of the sheet if this sheet is a grid. (If the sheet...
    gridProperties: GridProperties

    # True if the sheet is hidden in the UI, false if it's visible.
    hidden: bool

    # The index of the sheet within the spreadsheet. When adding or updating sh...
    index: int

    # True if the sheet is an RTL sheet instead of an LTR sheet.
    rightToLeft: bool

    # The ID of the sheet. Must be non-negative. This field cannot be changed o...
    sheetId: int

    # The type of sheet. Defaults to GRID. This field cannot be changed once set.
    # Enum values:
    #   "SHEET_TYPE_UNSPECIFIED": Default value, do not use.
    #   "GRID": The sheet is a grid.
    #   "OBJECT": The sheet has no grid and instead has an object like a ch...
    #   "DATA_SOURCE": The sheet connects with an external DataSource and shows ...
    sheetType: str

    # The color of the tab in the UI. Deprecated: Use tab_color_style.
    # Deprecated
    tabColor: Color

    # The color of the tab in the UI. If tab_color is also set, this field take...
    tabColorStyle: ColorStyle

    # The name of the sheet.
    title: str


class ErrorValue(TypedDict, total=False):
    """An error in a cell."""

    # A message with more information about the error (in the spreadsheet's loc...
    message: str

    # The type of error.
    # Enum values:
    #   "ERROR_TYPE_UNSPECIFIED": The default error type, do not use this.
    #   "ERROR": Corresponds to the `#ERROR!` error.
    #   "NULL_VALUE": Corresponds to the `#NULL!` error.
    #   "DIVIDE_BY_ZERO": Corresponds to the `#DIV/0` error.
    #   "VALUE": Corresponds to the `#VALUE!` error.
    #   "REF": Corresponds to the `#REF!` error.
    #   "NAME": Corresponds to the `#NAME?` error.
    #   "NUM": Corresponds to the `#NUM!` error.
    #   "N_A": Corresponds to the `#N/A` error.
    #   "LOADING": Corresponds to the `Loading...` state.
    type: str


class ExtendedValue(TypedDict, total=False):
    """The kinds of value that a cell in a spreadsheet can have."""

    # Represents a boolean value.
    boolValue: bool

    # Represents an error. This field is read-only.
    errorValue: ErrorValue

    # Represents a formula.
    formulaValue: str

    # Represents a double value. Note: Dates, Times and DateTimes are represent...
    numberValue: float

    # Represents a string value. Leading single quotes are not included. For ex...
    stringValue: str


class CellData(TypedDict, total=False):
    """Data about a specific cell."""

    # Optional. Runs of chips applied to subsections of the cell. Properties of...
    chipRuns: list[ChipRun]

    # Output only. Information about a data source formula on the cell. The fie...
    # Read-only field
    dataSourceFormula: DataSourceFormula

    # A data source table anchored at this cell. The size of data source table ...
    dataSourceTable: DataSourceTable

    # A data validation rule on the cell, if any. When writing, the new data va...
    dataValidation: DataValidationRule

    # The effective format being used by the cell. This includes the results of...
    effectiveFormat: CellFormat

    # The effective value of the cell. For cells with formulas, this is the cal...
    effectiveValue: ExtendedValue

    # The formatted value of the cell. This is the value as it's shown to the u...
    formattedValue: str

    # A hyperlink this cell points to, if any. If the cell contains multiple hy...
    hyperlink: str

    # Any note on the cell.
    note: str

    # A pivot table anchored at this cell. The size of pivot table itself is co...
    pivotTable: PivotTable

    # Runs of rich text applied to subsections of the cell. Runs are only valid...
    textFormatRuns: list[TextFormatRun]

    # The format the user entered for the cell. When writing, the new format wi...
    userEnteredFormat: CellFormat

    # The value the user entered in the cell. e.g., `1234`, `'Hello'`, or `=NOW...
    userEnteredValue: ExtendedValue


class RowData(TypedDict, total=False):
    """Data about each cell in a row."""

    # The values in the row, one per column.
    values: list[CellData]


class DimensionProperties(TypedDict, total=False):
    """Properties about a dimension."""

    # Output only. If set, this is a column in a data source sheet.
    # Read-only field
    dataSourceColumnReference: DataSourceColumnReference

    # The developer metadata associated with a single row or column.
    developerMetadata: list[DeveloperMetadata]

    # True if this dimension is being filtered. This field is read-only.
    hiddenByFilter: bool

    # True if this dimension is explicitly hidden.
    hiddenByUser: bool

    # The height (if a row) or width (if a column) of the dimension in pixels.
    pixelSize: int


class SpreadsheetProperties(TypedDict, total=False):
    """Properties of a spreadsheet."""

    # The amount of time to wait before volatile functions are recalculated.
    # Enum values:
    #   "RECALCULATION_INTERVAL_UNSPECIFIED": Default value. This value must not be used.
    #   "ON_CHANGE": Volatile functions are updated on every change.
    #   "MINUTE": Volatile functions are updated on every change and every ...
    #   "HOUR": Volatile functions are updated on every change and hourly.
    autoRecalc: str

    # The default format of all cells in the spreadsheet. CellData.effectiveFor...
    defaultFormat: CellFormat

    # Whether to allow external URL access for image and import functions. Read...
    importFunctionsExternalUrlAccessAllowed: bool

    # Determines whether and how circular references are resolved with iterativ...
    iterativeCalculationSettings: IterativeCalculationSettings

    # The locale of the spreadsheet in one of the following formats: * an ISO 6...
    locale: str

    # Theme applied to the spreadsheet.
    spreadsheetTheme: SpreadsheetTheme

    # The time zone of the spreadsheet, in CLDR format such as `America/New_Yor...
    timeZone: str

    # The title of the spreadsheet.
    title: str


class GridData(TypedDict, total=False):
    """Data in the grid, as well as metadata about the dimensions."""

    # Metadata about the requested columns in the grid, starting with the colum...
    columnMetadata: list[DimensionProperties]

    # The data in the grid, one entry per row, starting with the row in startRo...
    rowData: list[RowData]

    # Metadata about the requested rows in the grid, starting with the row in s...
    rowMetadata: list[DimensionProperties]

    # The first column this GridData refers to, zero-based.
    startColumn: int

    # The first row this GridData refers to, zero-based.
    startRow: int


class Sheet(TypedDict, total=False):
    """A sheet in a spreadsheet."""

    # The banded (alternating colors) ranges on this sheet.
    bandedRanges: list[BandedRange]

    # The filter on this sheet, if any.
    basicFilter: BasicFilter

    # The specifications of every chart on this sheet.
    charts: list[EmbeddedChart]

    # All column groups on this sheet, ordered by increasing range start index,...
    columnGroups: list[DimensionGroup]

    # The conditional format rules in this sheet.
    conditionalFormats: list[ConditionalFormatRule]

    # Data in the grid, if this is a grid sheet. The number of GridData objects...
    data: list[GridData]

    # The developer metadata associated with a sheet.
    developerMetadata: list[DeveloperMetadata]

    # The filter views in this sheet.
    filterViews: list[FilterView]

    # The ranges that are merged together.
    merges: list[GridRange]

    # The properties of the sheet.
    properties: SheetProperties

    # The protected ranges in this sheet.
    protectedRanges: list[ProtectedRange]

    # All row groups on this sheet, ordered by increasing range start index, th...
    rowGroups: list[DimensionGroup]

    # The slicers on this sheet.
    slicers: list[Slicer]

    # The tables on this sheet.
    tables: list[Table]


class Spreadsheet(TypedDict, total=False):
    """Resource that represents a spreadsheet."""

    # Output only. A list of data source refresh schedules.
    # Read-only field
    dataSourceSchedules: list[DataSourceRefreshSchedule]

    # A list of external data sources connected with the spreadsheet.
    dataSources: list[DataSource]

    # The developer metadata associated with a spreadsheet.
    developerMetadata: list[DeveloperMetadata]

    # The named ranges defined in a spreadsheet.
    namedRanges: list[NamedRange]

    # Overall properties of a spreadsheet.
    properties: SpreadsheetProperties

    # The sheets that are part of a spreadsheet.
    sheets: list[Sheet]

    # The ID of the spreadsheet. This field is read-only.
    spreadsheetId: str

    # The url of the spreadsheet. This field is read-only.
    spreadsheetUrl: str


# =============================================================================
# Formatting
# =============================================================================


class Color(TypedDict, total=False):
    """Represents a color in the RGBA color space. This representation is designed for simplicity of conversion to and from color representations in various languages over compactness. For example, the fields of this representation can be trivially provided to the constructor of `java.awt.Color` in Java; it can also be trivially provided to UIColor's `+colorWithRed:green:blue:alpha` method in iOS; and, with just a little work, it can be easily formatted into a CSS `rgba()` string in JavaScript. This reference page doesn't have information about the absolute color space that should be used to interpret the RGB value—for example, sRGB, Adobe RGB, DCI-P3, and BT.2020. By default, applications should assume the sRGB color space. When color equality needs to be decided, implementations, unless documented otherwise, treat two colors as equal if all their red, green, blue, and alpha values each differ by at most `1e-5`. Example (Java): import com.google.type.Color; // ... public static java.awt.Color fromProto(Color protocolor) { float alpha = protocolor.hasAlpha() ? protocolor.getAlpha().getValue() : 1.0; return new java.awt.Color( protocolor.getRed(), protocolor.getGreen(), protocolor.getBlue(), alpha); } public static Color toProto(java.awt.Color color) { float red = (float) color.getRed(); float green = (float) color.getGreen(); float blue = (float) color.getBlue(); float denominator = 255.0; Color.Builder resultBuilder = Color .newBuilder() .setRed(red / denominator) .setGreen(green / denominator) .setBlue(blue / denominator); int alpha = color.getAlpha(); if (alpha != 255) { result.setAlpha( FloatValue .newBuilder() .setValue(((float) alpha) / denominator) .build()); } return resultBuilder.build(); } // ... Example (iOS / Obj-C): // ... static UIColor* fromProto(Color* protocolor) { float red = [protocolor red]; float green = [protocolor green]; float blue = [protocolor blue]; FloatValue* alpha_wrapper = [protocolor alpha]; float alpha = 1.0; if (alpha_wrapper != nil) { alpha = [alpha_wrapper value]; } return [UIColor colorWithRed:red green:green blue:blue alpha:alpha]; } static Color* toProto(UIColor* color) { CGFloat red, green, blue, alpha; if (![color getRed:&red green:&green blue:&blue alpha:&alpha]) { return nil; } Color* result = [[Color alloc] init]; [result setRed:red]; [result setGreen:green]; [result setBlue:blue]; if (alpha <= 0.9999) { [result setAlpha:floatWrapperWithValue(alpha)]; } [result autorelease]; return result; } // ... Example (JavaScript): // ... var protoToCssColor = function(rgb_color) { var redFrac = rgb_color.red || 0.0; var greenFrac = rgb_color.green || 0.0; var blueFrac = rgb_color.blue || 0.0; var red = Math.floor(redFrac * 255); var green = Math.floor(greenFrac * 255); var blue = Math.floor(blueFrac * 255); if (!('alpha' in rgb_color)) { return rgbToCssColor(red, green, blue); } var alphaFrac = rgb_color.alpha.value || 0.0; var rgbParams = [red, green, blue].join(','); return ['rgba(', rgbParams, ',', alphaFrac, ')'].join(''); }; var rgbToCssColor = function(red, green, blue) { var rgbNumber = new Number((red << 16) | (green << 8) | blue); var hexString = rgbNumber.toString(16); var missingZeros = 6 - hexString.length; var resultBuilder = ['#']; for (var i = 0; i < missingZeros; i++) { resultBuilder.push('0'); } resultBuilder.push(hexString); return resultBuilder.join(''); }; // ..."""

    # The fraction of this color that should be applied to the pixel. That is, ...
    alpha: float

    # The amount of blue in the color as a value in the interval [0, 1].
    blue: float

    # The amount of green in the color as a value in the interval [0, 1].
    green: float

    # The amount of red in the color as a value in the interval [0, 1].
    red: float


class ColorStyle(TypedDict, total=False):
    """A color value."""

    # RGB color. The [`alpha`](https://developers.google.com/workspace/sheets/a...
    rgbColor: Color

    # Theme color.
    # Enum values:
    #   "THEME_COLOR_TYPE_UNSPECIFIED": Unspecified theme color
    #   "TEXT": Represents the primary text color
    #   "BACKGROUND": Represents the primary background color
    #   "ACCENT1": Represents the first accent color
    #   "ACCENT2": Represents the second accent color
    #   "ACCENT3": Represents the third accent color
    #   "ACCENT4": Represents the fourth accent color
    #   "ACCENT5": Represents the fifth accent color
    #   "ACCENT6": Represents the sixth accent color
    #   "LINK": Represents the color to use for hyperlinks
    themeColor: str


class EmbeddedObjectBorder(TypedDict, total=False):
    """A border along an embedded object."""

    # The color of the border. Deprecated: Use color_style.
    # Deprecated
    color: Color

    # The color of the border. If color is also set, this field takes precedence.
    colorStyle: ColorStyle


class LineStyle(TypedDict, total=False):
    """Properties that describe the style of a line."""

    # The dash type of the line.
    # Enum values:
    #   "LINE_DASH_TYPE_UNSPECIFIED": Default value, do not use.
    #   "INVISIBLE": No dash type, which is equivalent to a non-visible line.
    #   "CUSTOM": A custom dash for a line. Modifying the exact custom dash...
    #   "SOLID": A solid line.
    #   "DOTTED": A dotted line.
    #   "MEDIUM_DASHED": A dashed line where the dashes have "medium" length.
    #   "MEDIUM_DASHED_DOTTED": A line that alternates between a "medium" dash and a dot.
    #   "LONG_DASHED": A dashed line where the dashes have "long" length.
    #   "LONG_DASHED_DOTTED": A line that alternates between a "long" dash and a dot.
    type: str

    # The thickness of the line, in px.
    width: int


class TextFormat(TypedDict, total=False):
    """The format of a run of text in a cell. Absent values indicate that the field isn't specified."""

    # True if the text is bold.
    bold: bool

    # The font family.
    fontFamily: str

    # The size of the font.
    fontSize: int

    # The foreground color of the text. Deprecated: Use foreground_color_style.
    # Deprecated
    foregroundColor: Color

    # The foreground color of the text. If foreground_color is also set, this f...
    foregroundColorStyle: ColorStyle

    # True if the text is italicized.
    italic: bool

    # The link destination of the text, if any. Setting the link field in a Tex...
    link: Link

    # True if the text has a strikethrough.
    strikethrough: bool

    # True if the text is underlined.
    underline: bool


class PointStyle(TypedDict, total=False):
    """The style of a point on the chart."""

    # The point shape. If empty or unspecified, a default shape is used.
    # Enum values:
    #   "POINT_SHAPE_UNSPECIFIED": Default value.
    #   "CIRCLE": A circle shape.
    #   "DIAMOND": A diamond shape.
    #   "HEXAGON": A hexagon shape.
    #   "PENTAGON": A pentagon shape.
    #   "SQUARE": A square shape.
    #   "STAR": A star shape.
    #   "TRIANGLE": A triangle shape.
    #   "X_MARK": An x-mark shape.
    shape: str

    # The point size. If empty, a default size is used.
    size: float


class KeyValueFormat(TypedDict, total=False):
    """Formatting options for key value."""

    # Specifies the horizontal text positioning of key value. This field is opt...
    position: TextPosition

    # Text formatting options for key value. The link field is not supported.
    textFormat: TextFormat


class BaselineValueFormat(TypedDict, total=False):
    """Formatting options for baseline value."""

    # The comparison type of key value with baseline value.
    # Enum values:
    #   "COMPARISON_TYPE_UNDEFINED": Default value, do not use.
    #   "ABSOLUTE_DIFFERENCE": Use absolute difference between key and baseline value.
    #   "PERCENTAGE_DIFFERENCE": Use percentage difference between key and baseline value.
    comparisonType: str

    # Description which is appended after the baseline value. This field is opt...
    description: str

    # Color to be used, in case baseline value represents a negative change for...
    # Deprecated
    negativeColor: Color

    # Color to be used, in case baseline value represents a negative change for...
    negativeColorStyle: ColorStyle

    # Specifies the horizontal text positioning of baseline value. This field i...
    position: TextPosition

    # Color to be used, in case baseline value represents a positive change for...
    # Deprecated
    positiveColor: Color

    # Color to be used, in case baseline value represents a positive change for...
    positiveColorStyle: ColorStyle

    # Text formatting options for baseline value. The link field is not supported.
    textFormat: TextFormat


class Padding(TypedDict, total=False):
    """The amount of padding around the cell, in pixels. When updating padding, every field must be specified."""

    # The bottom padding of the cell.
    bottom: int

    # The left padding of the cell.
    left: int

    # The right padding of the cell.
    right: int

    # The top padding of the cell.
    top: int


class Border(TypedDict, total=False):
    """A border along a cell."""

    # The color of the border. Deprecated: Use color_style.
    # Deprecated
    color: Color

    # The color of the border. If color is also set, this field takes precedence.
    colorStyle: ColorStyle

    # The style of the border.
    # Enum values:
    #   "STYLE_UNSPECIFIED": The style is not specified. Do not use this.
    #   "DOTTED": The border is dotted.
    #   "DASHED": The border is dashed.
    #   "SOLID": The border is a thin solid line.
    #   "SOLID_MEDIUM": The border is a medium solid line.
    #   "SOLID_THICK": The border is a thick solid line.
    #   "NONE": No border. Used only when updating a border in order to e...
    #   "DOUBLE": The border is two solid lines.
    style: str

    # The width of the border, in pixels. Deprecated; the width is determined b...
    # Deprecated
    width: int


class Borders(TypedDict, total=False):
    """The borders of the cell."""

    # The bottom border of the cell.
    bottom: Border

    # The left border of the cell.
    left: Border

    # The right border of the cell.
    right: Border

    # The top border of the cell.
    top: Border


class NumberFormat(TypedDict, total=False):
    """The number format of a cell."""

    # Pattern string used for formatting. If not set, a default pattern based o...
    pattern: str

    # The type of the number format. When writing, this field must be set.
    # Enum values:
    #   "NUMBER_FORMAT_TYPE_UNSPECIFIED": The number format is not specified and is based on the co...
    #   "TEXT": Text formatting, e.g `1000.12`
    #   "NUMBER": Number formatting, e.g, `1,000.12`
    #   "PERCENT": Percent formatting, e.g `10.12%`
    #   "CURRENCY": Currency formatting, e.g `$1,000.12`
    #   "DATE": Date formatting, e.g `9/26/2008`
    #   "TIME": Time formatting, e.g `3:59:00 PM`
    #   "DATE_TIME": Date+Time formatting, e.g `9/26/08 15:59:00`
    #   "SCIENTIFIC": Scientific number formatting, e.g `1.01E+03`
    type: str


class ConditionalFormatRule(TypedDict, total=False):
    """A rule describing a conditional format."""

    # The formatting is either "on" or "off" according to the rule.
    booleanRule: BooleanRule

    # The formatting will vary based on the gradients in the rule.
    gradientRule: GradientRule

    # The ranges that are formatted if the condition is true. All the ranges mu...
    ranges: list[GridRange]


class TextFormatRun(TypedDict, total=False):
    """A run of a text format. The format of this run continues until the start index of the next run. When updating, all fields must be set."""

    # The format of this run. Absent values inherit the cell's format.
    format: TextFormat

    # The zero-based character index where this run starts, in UTF-16 code units.
    startIndex: int


class ThemeColorPair(TypedDict, total=False):
    """A pair mapping a spreadsheet theme color type to the concrete color it represents."""

    # The concrete color corresponding to the theme color type.
    color: ColorStyle

    # The type of the spreadsheet theme color.
    # Enum values:
    #   "THEME_COLOR_TYPE_UNSPECIFIED": Unspecified theme color
    #   "TEXT": Represents the primary text color
    #   "BACKGROUND": Represents the primary background color
    #   "ACCENT1": Represents the first accent color
    #   "ACCENT2": Represents the second accent color
    #   "ACCENT3": Represents the third accent color
    #   "ACCENT4": Represents the fourth accent color
    #   "ACCENT5": Represents the fifth accent color
    #   "ACCENT6": Represents the sixth accent color
    #   "LINK": Represents the color to use for hyperlinks
    colorType: str


# =============================================================================
# Charts
# =============================================================================


class ChartSourceRange(TypedDict, total=False):
    """Source ranges for a chart."""

    # The ranges of data for a series or domain. Exactly one dimension must hav...
    sources: list[GridRange]


class ChartDateTimeRule(TypedDict, total=False):
    """Allows you to organize the date-time values in a source data column into buckets based on selected parts of their date or time values."""

    # The type of date-time grouping to apply.
    # Enum values:
    #   "CHART_DATE_TIME_RULE_TYPE_UNSPECIFIED": The default type, do not use.
    #   "SECOND": Group dates by second, from 0 to 59.
    #   "MINUTE": Group dates by minute, from 0 to 59.
    #   "HOUR": Group dates by hour using a 24-hour system, from 0 to 23.
    #   "HOUR_MINUTE": Group dates by hour and minute using a 24-hour system, fo...
    #   "HOUR_MINUTE_AMPM": Group dates by hour and minute using a 12-hour system, fo...
    #   "DAY_OF_WEEK": Group dates by day of week, for example Sunday. The days ...
    #   "DAY_OF_YEAR": Group dates by day of year, from 1 to 366. Note that date...
    #   "DAY_OF_MONTH": Group dates by day of month, from 1 to 31.
    #   "DAY_MONTH": Group dates by day and month, for example 22-Nov. The mon...
    #   "MONTH": Group dates by month, for example Nov. The month is trans...
    #   "QUARTER": Group dates by quarter, for example Q1 (which represents ...
    #   "YEAR": Group dates by year, for example 2008.
    #   "YEAR_MONTH": Group dates by year and month, for example 2008-Nov. The ...
    #   "YEAR_QUARTER": Group dates by year and quarter, for example 2008 Q4.
    #   "YEAR_MONTH_DAY": Group dates by year, month, and day, for example 2008-11-22.
    type: str


class ChartHistogramRule(TypedDict, total=False):
    """Allows you to organize numeric values in a source data column into buckets of constant size."""

    # The size of the buckets that are created. Must be positive.
    intervalSize: float

    # The maximum value at which items are placed into buckets. Values greater ...
    maxValue: float

    # The minimum value at which items are placed into buckets. Values that are...
    minValue: float


class ChartGroupRule(TypedDict, total=False):
    """An optional setting on the ChartData of the domain of a data source chart that defines buckets for the values in the domain rather than breaking out each individual value. For example, when plotting a data source chart, you can specify a histogram rule on the domain (it should only contain numeric values), grouping its values into buckets. Any values of a chart series that fall into the same bucket are aggregated based on the aggregate_type."""

    # A ChartDateTimeRule.
    dateTimeRule: ChartDateTimeRule

    # A ChartHistogramRule
    histogramRule: ChartHistogramRule


class ChartData(TypedDict, total=False):
    """The data included in a domain or series."""

    # The aggregation type for the series of a data source chart. Only supporte...
    # Enum values:
    #   "CHART_AGGREGATE_TYPE_UNSPECIFIED": Default value, do not use.
    #   "AVERAGE": Average aggregate function.
    #   "COUNT": Count aggregate function.
    #   "MAX": Maximum aggregate function.
    #   "MEDIAN": Median aggregate function.
    #   "MIN": Minimum aggregate function.
    #   "SUM": Sum aggregate function.
    aggregateType: str

    # The reference to the data source column that the data reads from.
    columnReference: DataSourceColumnReference

    # The rule to group the data by if the ChartData backs the domain of a data...
    groupRule: ChartGroupRule

    # The source ranges of the data.
    sourceRange: ChartSourceRange


class CandlestickDomain(TypedDict, total=False):
    """The domain of a CandlestickChart."""

    # The data of the CandlestickDomain.
    data: ChartData

    # True to reverse the order of the domain values (horizontal axis).
    reversed: bool


class CandlestickSeries(TypedDict, total=False):
    """The series of a CandlestickData."""

    # The data of the CandlestickSeries.
    data: ChartData


class CandlestickData(TypedDict, total=False):
    """The Candlestick chart data, each containing the low, open, close, and high values for a series."""

    # The range data (vertical axis) for the close/final value for each candle....
    closeSeries: CandlestickSeries

    # The range data (vertical axis) for the high/maximum value for each candle...
    highSeries: CandlestickSeries

    # The range data (vertical axis) for the low/minimum value for each candle....
    lowSeries: CandlestickSeries

    # The range data (vertical axis) for the open/initial value for each candle...
    openSeries: CandlestickSeries


class CandlestickChartSpec(TypedDict, total=False):
    """A candlestick chart."""

    # The Candlestick chart data. Only one CandlestickData is supported.
    data: list[CandlestickData]

    # The domain data (horizontal axis) for the candlestick chart. String data ...
    domain: CandlestickDomain


class WaterfallChartDomain(TypedDict, total=False):
    """The domain of a waterfall chart."""

    # The data of the WaterfallChartDomain.
    data: ChartData

    # True to reverse the order of the domain values (horizontal axis).
    reversed: bool


class WaterfallChartCustomSubtotal(TypedDict, total=False):
    """A custom subtotal column for a waterfall chart series."""

    # True if the data point at subtotal_index is the subtotal. If false, the s...
    dataIsSubtotal: bool

    # A label for the subtotal column.
    label: str

    # The zero-based index of a data point within the series. If data_is_subtot...
    subtotalIndex: int


class WaterfallChartColumnStyle(TypedDict, total=False):
    """Styles for a waterfall chart column."""

    # The color of the column. Deprecated: Use color_style.
    # Deprecated
    color: Color

    # The color of the column. If color is also set, this field takes precedence.
    colorStyle: ColorStyle

    # The label of the column's legend.
    label: str


class WaterfallChartSeries(TypedDict, total=False):
    """A single series of data for a waterfall chart."""

    # Custom subtotal columns appearing in this series. The order in which subt...
    customSubtotals: list[WaterfallChartCustomSubtotal]

    # The data being visualized in this series.
    data: ChartData

    # Information about the data labels for this series.
    dataLabel: DataLabel

    # True to hide the subtotal column from the end of the series. By default, ...
    hideTrailingSubtotal: bool

    # Styles for all columns in this series with negative values.
    negativeColumnsStyle: WaterfallChartColumnStyle

    # Styles for all columns in this series with positive values.
    positiveColumnsStyle: WaterfallChartColumnStyle

    # Styles for all subtotal columns in this series.
    subtotalColumnsStyle: WaterfallChartColumnStyle


class WaterfallChartSpec(TypedDict, total=False):
    """A waterfall chart."""

    # The line style for the connector lines.
    connectorLineStyle: LineStyle

    # The domain data (horizontal axis) for the waterfall chart.
    domain: WaterfallChartDomain

    # True to interpret the first value as a total.
    firstValueIsTotal: bool

    # True to hide connector lines between columns.
    hideConnectorLines: bool

    # The data this waterfall chart is visualizing.
    series: list[WaterfallChartSeries]

    # The stacked type.
    # Enum values:
    #   "WATERFALL_STACKED_TYPE_UNSPECIFIED": Default value, do not use.
    #   "STACKED": Values corresponding to the same domain (horizontal axis)...
    #   "SEQUENTIAL": Series will spread out along the horizontal axis.
    stackedType: str

    # Controls whether to display additional data labels on stacked charts whic...
    totalDataLabel: DataLabel


class TreemapChartColorScale(TypedDict, total=False):
    """A color scale for a treemap chart."""

    # The background color for cells with a color value greater than or equal t...
    # Deprecated
    maxValueColor: Color

    # The background color for cells with a color value greater than or equal t...
    maxValueColorStyle: ColorStyle

    # The background color for cells with a color value at the midpoint between...
    # Deprecated
    midValueColor: Color

    # The background color for cells with a color value at the midpoint between...
    midValueColorStyle: ColorStyle

    # The background color for cells with a color value less than or equal to m...
    # Deprecated
    minValueColor: Color

    # The background color for cells with a color value less than or equal to m...
    minValueColorStyle: ColorStyle

    # The background color for cells that have no color data associated with th...
    # Deprecated
    noDataColor: Color

    # The background color for cells that have no color data associated with th...
    noDataColorStyle: ColorStyle


class TreemapChartSpec(TypedDict, total=False):
    """A Treemap chart."""

    # The data that determines the background color of each treemap data cell. ...
    colorData: ChartData

    # The color scale for data cells in the treemap chart. Data cells are assig...
    colorScale: TreemapChartColorScale

    # The background color for header cells. Deprecated: Use header_color_style.
    # Deprecated
    headerColor: Color

    # The background color for header cells. If header_color is also set, this ...
    headerColorStyle: ColorStyle

    # True to hide tooltips.
    hideTooltips: bool

    # The number of additional data levels beyond the labeled levels to be show...
    hintedLevels: int

    # The data that contains the treemap cell labels.
    labels: ChartData

    # The number of data levels to show on the treemap chart. These levels are ...
    levels: int

    # The maximum possible data value. Cells with values greater than this will...
    maxValue: float

    # The minimum possible data value. Cells with values less than this will ha...
    minValue: float

    # The data the contains the treemap cells' parent labels.
    parentLabels: ChartData

    # The data that determines the size of each treemap data cell. This data is...
    sizeData: ChartData

    # The text format for all labels on the chart. The link field is not suppor...
    textFormat: TextFormat


class BubbleChartSpec(TypedDict, total=False):
    """A bubble chart."""

    # The bubble border color. Deprecated: Use bubble_border_color_style.
    # Deprecated
    bubbleBorderColor: Color

    # The bubble border color. If bubble_border_color is also set, this field t...
    bubbleBorderColorStyle: ColorStyle

    # The data containing the bubble labels. These do not need to be unique.
    bubbleLabels: ChartData

    # The max radius size of the bubbles, in pixels. If specified, the field mu...
    bubbleMaxRadiusSize: int

    # The minimum radius size of the bubbles, in pixels. If specific, the field...
    bubbleMinRadiusSize: int

    # The opacity of the bubbles between 0 and 1.0. 0 is fully transparent and ...
    bubbleOpacity: float

    # The data containing the bubble sizes. Bubble sizes are used to draw the b...
    bubbleSizes: ChartData

    # The format of the text inside the bubbles. Strikethrough, underline, and ...
    bubbleTextStyle: TextFormat

    # The data containing the bubble x-values. These values locate the bubbles ...
    domain: ChartData

    # The data containing the bubble group IDs. All bubbles with the same group...
    groupIds: ChartData

    # Where the legend of the chart should be drawn.
    # Enum values:
    #   "BUBBLE_CHART_LEGEND_POSITION_UNSPECIFIED": Default value, do not use.
    #   "BOTTOM_LEGEND": The legend is rendered on the bottom of the chart.
    #   "LEFT_LEGEND": The legend is rendered on the left of the chart.
    #   "RIGHT_LEGEND": The legend is rendered on the right of the chart.
    #   "TOP_LEGEND": The legend is rendered on the top of the chart.
    #   "NO_LEGEND": No legend is rendered.
    #   "INSIDE_LEGEND": The legend is rendered inside the chart area.
    legendPosition: str

    # The data containing the bubble y-values. These values locate the bubbles ...
    series: ChartData


class DataSourceChartProperties(TypedDict, total=False):
    """Properties of a data source chart."""

    # Output only. The data execution status.
    # Read-only field
    dataExecutionStatus: DataExecutionStatus

    # ID of the data source that the chart is associated with.
    dataSourceId: str


class OrgChartSpec(TypedDict, total=False):
    """An org chart. Org charts require a unique set of labels in labels and may optionally include parent_labels and tooltips. parent_labels contain, for each node, the label identifying the parent node. tooltips contain, for each node, an optional tooltip. For example, to describe an OrgChart with Alice as the CEO, Bob as the President (reporting to Alice) and Cathy as VP of Sales (also reporting to Alice), have labels contain "Alice", "Bob", "Cathy", parent_labels contain "", "Alice", "Alice" and tooltips contain "CEO", "President", "VP Sales"."""

    # The data containing the labels for all the nodes in the chart. Labels mus...
    labels: ChartData

    # The color of the org chart nodes. Deprecated: Use node_color_style.
    # Deprecated
    nodeColor: Color

    # The color of the org chart nodes. If node_color is also set, this field t...
    nodeColorStyle: ColorStyle

    # The size of the org chart nodes.
    # Enum values:
    #   "ORG_CHART_LABEL_SIZE_UNSPECIFIED": Default value, do not use.
    #   "SMALL": The small org chart node size.
    #   "MEDIUM": The medium org chart node size.
    #   "LARGE": The large org chart node size.
    nodeSize: str

    # The data containing the label of the parent for the corresponding node. A...
    parentLabels: ChartData

    # The color of the selected org chart nodes. Deprecated: Use selected_node_...
    # Deprecated
    selectedNodeColor: Color

    # The color of the selected org chart nodes. If selected_node_color is also...
    selectedNodeColorStyle: ColorStyle

    # The data containing the tooltip for the corresponding node. A blank value...
    tooltips: ChartData


class HistogramSeries(TypedDict, total=False):
    """A histogram series containing the series color and data."""

    # The color of the column representing this series in each bucket. This fie...
    # Deprecated
    barColor: Color

    # The color of the column representing this series in each bucket. This fie...
    barColorStyle: ColorStyle

    # The data for this histogram series.
    data: ChartData


class HistogramChartSpec(TypedDict, total=False):
    """A histogram chart. A histogram chart groups data items into bins, displaying each bin as a column of stacked items. Histograms are used to display the distribution of a dataset. Each column of items represents a range into which those items fall. The number of bins can be chosen automatically or specified explicitly."""

    # By default the bucket size (the range of values stacked in a single colum...
    bucketSize: float

    # The position of the chart legend.
    # Enum values:
    #   "HISTOGRAM_CHART_LEGEND_POSITION_UNSPECIFIED": Default value, do not use.
    #   "BOTTOM_LEGEND": The legend is rendered on the bottom of the chart.
    #   "LEFT_LEGEND": The legend is rendered on the left of the chart.
    #   "RIGHT_LEGEND": The legend is rendered on the right of the chart.
    #   "TOP_LEGEND": The legend is rendered on the top of the chart.
    #   "NO_LEGEND": No legend is rendered.
    #   "INSIDE_LEGEND": The legend is rendered inside the chart area.
    legendPosition: str

    # The outlier percentile is used to ensure that outliers do not adversely a...
    outlierPercentile: float

    # The series for a histogram may be either a single series of values to be ...
    series: list[HistogramSeries]

    # Whether horizontal divider lines should be displayed between items in eac...
    showItemDividers: bool


class ChartAxisViewWindowOptions(TypedDict, total=False):
    """The options that define a "view window" for a chart (such as the visible values in an axis)."""

    # The maximum numeric value to be shown in this view window. If unset, will...
    viewWindowMax: float

    # The minimum numeric value to be shown in this view window. If unset, will...
    viewWindowMin: float

    # The view window's mode.
    # Enum values:
    #   "DEFAULT_VIEW_WINDOW_MODE": The default view window mode used in the Sheets editor fo...
    #   "VIEW_WINDOW_MODE_UNSUPPORTED": Do not use. Represents that the currently set mode is not...
    #   "EXPLICIT": Follows the min and max exactly if specified. If a value ...
    #   "PRETTY": Chooses a min and max that make the chart look good. Both...
    viewWindowMode: str


class BasicChartAxis(TypedDict, total=False):
    """An axis of the chart. A chart may not have more than one axis per axis position."""

    # The format of the title. Only valid if the axis is not associated with th...
    format: TextFormat

    # The position of this axis.
    # Enum values:
    #   "BASIC_CHART_AXIS_POSITION_UNSPECIFIED": Default value, do not use.
    #   "BOTTOM_AXIS": The axis rendered at the bottom of a chart. For most char...
    #   "LEFT_AXIS": The axis rendered at the left of a chart. For most charts...
    #   "RIGHT_AXIS": The axis rendered at the right of a chart. For most chart...
    position: str

    # The title of this axis. If set, this overrides any title inferred from he...
    title: str

    # The axis title text position.
    titleTextPosition: TextPosition

    # The view window options for this axis.
    viewWindowOptions: ChartAxisViewWindowOptions


class BasicChartDomain(TypedDict, total=False):
    """The domain of a chart. For example, if charting stock prices over time, this would be the date."""

    # The data of the domain. For example, if charting stock prices over time, ...
    domain: ChartData

    # True to reverse the order of the domain values (horizontal axis).
    reversed: bool


class BasicSeriesDataPointStyleOverride(TypedDict, total=False):
    """Style override settings for a single series data point."""

    # Color of the series data point. If empty, the series default is used. Dep...
    # Deprecated
    color: Color

    # Color of the series data point. If empty, the series default is used. If ...
    colorStyle: ColorStyle

    # The zero-based index of the series data point.
    index: int

    # Point style of the series data point. Valid only if the chartType is AREA...
    pointStyle: PointStyle


class BasicChartSeries(TypedDict, total=False):
    """A single series of data in a chart. For example, if charting stock prices over time, multiple series may exist, one for the "Open Price", "High Price", "Low Price" and "Close Price"."""

    # The color for elements (such as bars, lines, and points) associated with ...
    # Deprecated
    color: Color

    # The color for elements (such as bars, lines, and points) associated with ...
    colorStyle: ColorStyle

    # Information about the data labels for this series.
    dataLabel: DataLabel

    # The line style of this series. Valid only if the chartType is AREA, LINE,...
    lineStyle: LineStyle

    # The style for points associated with this series. Valid only if the chart...
    pointStyle: PointStyle

    # The data being visualized in this chart series.
    series: ChartData

    # Style override settings for series data points.
    styleOverrides: list[BasicSeriesDataPointStyleOverride]

    # The minor axis that will specify the range of values for this series. For...
    # Enum values:
    #   "BASIC_CHART_AXIS_POSITION_UNSPECIFIED": Default value, do not use.
    #   "BOTTOM_AXIS": The axis rendered at the bottom of a chart. For most char...
    #   "LEFT_AXIS": The axis rendered at the left of a chart. For most charts...
    #   "RIGHT_AXIS": The axis rendered at the right of a chart. For most chart...
    targetAxis: str

    # The type of this series. Valid only if the chartType is COMBO. Different ...
    # Enum values:
    #   "BASIC_CHART_TYPE_UNSPECIFIED": Default value, do not use.
    #   "BAR": A bar chart.
    #   "LINE": A line chart.
    #   "AREA": An area chart.
    #   "COLUMN": A column chart.
    #   "SCATTER": A scatter chart.
    #   "COMBO": A combo chart.
    #   "STEPPED_AREA": A stepped area chart.
    type: str


class BasicChartSpec(TypedDict, total=False):
    """The specification for a basic chart. See BasicChartType for the list of charts this supports."""

    # The axis on the chart.
    axis: list[BasicChartAxis]

    # The type of the chart.
    # Enum values:
    #   "BASIC_CHART_TYPE_UNSPECIFIED": Default value, do not use.
    #   "BAR": A bar chart.
    #   "LINE": A line chart.
    #   "AREA": An area chart.
    #   "COLUMN": A column chart.
    #   "SCATTER": A scatter chart.
    #   "COMBO": A combo chart.
    #   "STEPPED_AREA": A stepped area chart.
    chartType: str

    # The behavior of tooltips and data highlighting when hovering on data and ...
    # Enum values:
    #   "BASIC_CHART_COMPARE_MODE_UNSPECIFIED": Default value, do not use.
    #   "DATUM": Only the focused data element is highlighted and shown in...
    #   "CATEGORY": All data elements with the same category (e.g., domain va...
    compareMode: str

    # The domain of data this is charting. Only a single domain is supported.
    domains: list[BasicChartDomain]

    # The number of rows or columns in the data that are "headers". If not set,...
    headerCount: int

    # If some values in a series are missing, gaps may appear in the chart (e.g...
    interpolateNulls: bool

    # The position of the chart legend.
    # Enum values:
    #   "BASIC_CHART_LEGEND_POSITION_UNSPECIFIED": Default value, do not use.
    #   "BOTTOM_LEGEND": The legend is rendered on the bottom of the chart.
    #   "LEFT_LEGEND": The legend is rendered on the left of the chart.
    #   "RIGHT_LEGEND": The legend is rendered on the right of the chart.
    #   "TOP_LEGEND": The legend is rendered on the top of the chart.
    #   "NO_LEGEND": No legend is rendered.
    legendPosition: str

    # Gets whether all lines should be rendered smooth or straight by default. ...
    lineSmoothing: bool

    # The data this chart is visualizing.
    series: list[BasicChartSeries]

    # The stacked type for charts that support vertical stacking. Applies to Ar...
    # Enum values:
    #   "BASIC_CHART_STACKED_TYPE_UNSPECIFIED": Default value, do not use.
    #   "NOT_STACKED": Series are not stacked.
    #   "STACKED": Series values are stacked, each value is rendered vertica...
    #   "PERCENT_STACKED": Vertical stacks are stretched to reach the top of the cha...
    stackedType: str

    # True to make the chart 3D. Applies to Bar and Column charts.
    threeDimensional: bool

    # Controls whether to display additional data labels on stacked charts whic...
    totalDataLabel: DataLabel


class PieChartSpec(TypedDict, total=False):
    """A pie chart."""

    # The data that covers the domain of the pie chart.
    domain: ChartData

    # Where the legend of the pie chart should be drawn.
    # Enum values:
    #   "PIE_CHART_LEGEND_POSITION_UNSPECIFIED": Default value, do not use.
    #   "BOTTOM_LEGEND": The legend is rendered on the bottom of the chart.
    #   "LEFT_LEGEND": The legend is rendered on the left of the chart.
    #   "RIGHT_LEGEND": The legend is rendered on the right of the chart.
    #   "TOP_LEGEND": The legend is rendered on the top of the chart.
    #   "NO_LEGEND": No legend is rendered.
    #   "LABELED_LEGEND": Each pie slice has a label attached to it.
    legendPosition: str

    # The size of the hole in the pie chart.
    pieHole: float

    # The data that covers the one and only series of the pie chart.
    series: ChartData

    # True if the pie is three dimensional.
    threeDimensional: bool


class ChartCustomNumberFormatOptions(TypedDict, total=False):
    """Custom number formatting options for chart attributes."""

    # Custom prefix to be prepended to the chart attribute. This field is optio...
    prefix: str

    # Custom suffix to be appended to the chart attribute. This field is optional.
    suffix: str


class ScorecardChartSpec(TypedDict, total=False):
    """A scorecard chart. Scorecard charts are used to highlight key performance indicators, known as KPIs, on the spreadsheet. A scorecard chart can represent things like total sales, average cost, or a top selling item. You can specify a single data value, or aggregate over a range of data. Percentage or absolute difference from a baseline value can be highlighted, like changes over time."""

    # The aggregation type for key and baseline chart data in scorecard chart. ...
    # Enum values:
    #   "CHART_AGGREGATE_TYPE_UNSPECIFIED": Default value, do not use.
    #   "AVERAGE": Average aggregate function.
    #   "COUNT": Count aggregate function.
    #   "MAX": Maximum aggregate function.
    #   "MEDIAN": Median aggregate function.
    #   "MIN": Minimum aggregate function.
    #   "SUM": Sum aggregate function.
    aggregateType: str

    # The data for scorecard baseline value. This field is optional.
    baselineValueData: ChartData

    # Formatting options for baseline value. This field is needed only if basel...
    baselineValueFormat: BaselineValueFormat

    # Custom formatting options for numeric key/baseline values in scorecard ch...
    customFormatOptions: ChartCustomNumberFormatOptions

    # The data for scorecard key value.
    keyValueData: ChartData

    # Formatting options for key value.
    keyValueFormat: KeyValueFormat

    # The number format source used in the scorecard chart. This field is optio...
    # Enum values:
    #   "CHART_NUMBER_FORMAT_SOURCE_UNDEFINED": Default value, do not use.
    #   "FROM_DATA": Inherit number formatting from data.
    #   "CUSTOM": Apply custom formatting as specified by ChartCustomNumber...
    numberFormatSource: str

    # Value to scale scorecard key and baseline value. For example, a factor of...
    scaleFactor: float


class ChartSpec(TypedDict, total=False):
    """The specifications of a chart."""

    # The alternative text that describes the chart. This is often used for acc...
    altText: str

    # The background color of the entire chart. Not applicable to Org charts. D...
    # Deprecated
    backgroundColor: Color

    # The background color of the entire chart. Not applicable to Org charts. I...
    backgroundColorStyle: ColorStyle

    # A basic chart specification, can be one of many kinds of charts. See Basi...
    basicChart: BasicChartSpec

    # A bubble chart specification.
    bubbleChart: BubbleChartSpec

    # A candlestick chart specification.
    candlestickChart: CandlestickChartSpec

    # If present, the field contains data source chart specific properties.
    dataSourceChartProperties: DataSourceChartProperties

    # The filters applied to the source data of the chart. Only supported for d...
    filterSpecs: list[FilterSpec]

    # The name of the font to use by default for all chart text (e.g. title, ax...
    fontName: str

    # Determines how the charts will use hidden rows or columns.
    # Enum values:
    #   "CHART_HIDDEN_DIMENSION_STRATEGY_UNSPECIFIED": Default value, do not use.
    #   "SKIP_HIDDEN_ROWS_AND_COLUMNS": Charts will skip hidden rows and columns.
    #   "SKIP_HIDDEN_ROWS": Charts will skip hidden rows only.
    #   "SKIP_HIDDEN_COLUMNS": Charts will skip hidden columns only.
    #   "SHOW_ALL": Charts will not skip any hidden rows or columns.
    hiddenDimensionStrategy: str

    # A histogram chart specification.
    histogramChart: HistogramChartSpec

    # True to make a chart fill the entire space in which it's rendered with mi...
    maximized: bool

    # An org chart specification.
    orgChart: OrgChartSpec

    # A pie chart specification.
    pieChart: PieChartSpec

    # A scorecard chart specification.
    scorecardChart: ScorecardChartSpec

    # The order to sort the chart data by. Only a single sort spec is supported...
    sortSpecs: list[SortSpec]

    # The subtitle of the chart.
    subtitle: str

    # The subtitle text format. Strikethrough, underline, and link are not supp...
    subtitleTextFormat: TextFormat

    # The subtitle text position. This field is optional.
    subtitleTextPosition: TextPosition

    # The title of the chart.
    title: str

    # The title text format. Strikethrough, underline, and link are not supported.
    titleTextFormat: TextFormat

    # The title text position. This field is optional.
    titleTextPosition: TextPosition

    # A treemap chart specification.
    treemapChart: TreemapChartSpec

    # A waterfall chart specification.
    waterfallChart: WaterfallChartSpec


class EmbeddedChart(TypedDict, total=False):
    """A chart embedded in a sheet."""

    # The border of the chart.
    border: EmbeddedObjectBorder

    # The ID of the chart.
    chartId: int

    # The position of the chart.
    position: EmbeddedObjectPosition

    # The specification of the chart.
    spec: ChartSpec


class HistogramRule(TypedDict, total=False):
    """Allows you to organize the numeric values in a source data column into buckets of a constant size. All values from HistogramRule.start to HistogramRule.end are placed into groups of size HistogramRule.interval. In addition, all values below HistogramRule.start are placed in one group, and all values above HistogramRule.end are placed in another. Only HistogramRule.interval is required, though if HistogramRule.start and HistogramRule.end are both provided, HistogramRule.start must be less than HistogramRule.end. For example, a pivot table showing average purchase amount by age that has 50+ rows: +-----+-------------------+ | Age | AVERAGE of Amount | +-----+-------------------+ | 16 | $27.13 | | 17 | $5.24 | | 18 | $20.15 | ... +-----+-------------------+ could be turned into a pivot table that looks like the one below by applying a histogram group rule with a HistogramRule.start of 25, an HistogramRule.interval of 20, and an HistogramRule.end of 65. +-------------+-------------------+ | Grouped Age | AVERAGE of Amount | +-------------+-------------------+ | < 25 | $19.34 | | 25-45 | $31.43 | | 45-65 | $35.87 | | > 65 | $27.55 | +-------------+-------------------+ | Grand Total | $29.12 | +-------------+-------------------+"""

    # The maximum value at which items are placed into buckets of constant size...
    end: float

    # The size of the buckets that are created. Must be positive.
    interval: float

    # The minimum value at which items are placed into buckets of constant size...
    start: float


# =============================================================================
# Features (Pivot Tables, Filters, etc.)
# =============================================================================


class BandedRange(TypedDict, total=False):
    """A banded (alternating colors) range in a sheet."""

    # The ID of the banded range. If unset, refer to banded_range_reference.
    bandedRangeId: int

    # Output only. The reference of the banded range, used to identify the ID t...
    # Read-only field
    bandedRangeReference: str

    # Properties for column bands. These properties are applied on a column- by...
    columnProperties: BandingProperties

    # The range over which these properties are applied.
    range: GridRange

    # Properties for row bands. These properties are applied on a row-by-row ba...
    rowProperties: BandingProperties


class FilterCriteria(TypedDict, total=False):
    """Criteria for showing/hiding rows in a filter or filter view."""

    # A condition that must be true for values to be shown. (This does not over...
    condition: BooleanCondition

    # Values that should be hidden.
    hiddenValues: list[str]

    # The background fill color to filter by; only cells with this fill color a...
    # Deprecated
    visibleBackgroundColor: Color

    # The background fill color to filter by; only cells with this fill color a...
    visibleBackgroundColorStyle: ColorStyle

    # The foreground color to filter by; only cells with this foreground color ...
    # Deprecated
    visibleForegroundColor: Color

    # The foreground color to filter by; only cells with this foreground color ...
    visibleForegroundColorStyle: ColorStyle


class FilterSpec(TypedDict, total=False):
    """The filter criteria associated with a specific column."""

    # The zero-based column index.
    columnIndex: int

    # Reference to a data source column.
    dataSourceColumnReference: DataSourceColumnReference

    # The criteria for the column.
    filterCriteria: FilterCriteria


class BigQueryTableSpec(TypedDict, total=False):
    """Specifies a BigQuery table definition. Only [native tables](https://cloud.google.com/bigquery/docs/tables-intro) are allowed."""

    # The BigQuery dataset id.
    datasetId: str

    # The BigQuery table id.
    tableId: str

    # The ID of a BigQuery project the table belongs to. If not specified, the ...
    tableProjectId: str


class FilterView(TypedDict, total=False):
    """A filter view."""

    # The criteria for showing/hiding values per column. The map's key is the c...
    # Deprecated
    criteria: dict[str, FilterCriteria]

    # The filter criteria for showing/hiding values per column. Both criteria a...
    filterSpecs: list[FilterSpec]

    # The ID of the filter view.
    filterViewId: int

    # The named range this filter view is backed by, if any. When writing, only...
    namedRangeId: str

    # The range this filter view covers. When writing, only one of range or nam...
    range: GridRange

    # The sort order per column. Later specifications are used when values are ...
    sortSpecs: list[SortSpec]

    # The table this filter view is backed by, if any. When writing, only one o...
    tableId: str

    # The name of the filter view.
    title: str


class ProtectedRange(TypedDict, total=False):
    """A protected range."""

    # The description of this protected range.
    description: str

    # The users and groups with edit access to the protected range. This field ...
    editors: Editors

    # The named range this protected range is backed by, if any. When writing, ...
    namedRangeId: str

    # The ID of the protected range. This field is read-only.
    protectedRangeId: int

    # The range that is being protected. The range may be fully unbounded, in w...
    range: GridRange

    # True if the user who requested this protected range can edit the protecte...
    requestingUserCanEdit: bool

    # The table this protected range is backed by, if any. When writing, only o...
    tableId: str

    # The list of unprotected ranges within a protected sheet. Unprotected rang...
    unprotectedRanges: list[GridRange]

    # True if this protected range will show a warning when editing. Warning-ba...
    warningOnly: bool


class SlicerSpec(TypedDict, total=False):
    """The specifications of a slicer."""

    # True if the filter should apply to pivot tables. If not set, default to `...
    applyToPivotTables: bool

    # The background color of the slicer. Deprecated: Use background_color_style.
    # Deprecated
    backgroundColor: Color

    # The background color of the slicer. If background_color is also set, this...
    backgroundColorStyle: ColorStyle

    # The zero-based column index in the data table on which the filter is appl...
    columnIndex: int

    # The data range of the slicer.
    dataRange: GridRange

    # The filtering criteria of the slicer.
    filterCriteria: FilterCriteria

    # The horizontal alignment of title in the slicer. If unspecified, defaults...
    # Enum values:
    #   "HORIZONTAL_ALIGN_UNSPECIFIED": The horizontal alignment is not specified. Do not use this.
    #   "LEFT": The text is explicitly aligned to the left of the cell.
    #   "CENTER": The text is explicitly aligned to the center of the cell.
    #   "RIGHT": The text is explicitly aligned to the right of the cell.
    horizontalAlignment: str

    # The text format of title in the slicer. The link field is not supported.
    textFormat: TextFormat

    # The title of the slicer.
    title: str


class Slicer(TypedDict, total=False):
    """A slicer in a sheet."""

    # The position of the slicer. Note that slicer can be positioned only on ex...
    position: EmbeddedObjectPosition

    # The ID of the slicer.
    slicerId: int

    # The specification of the slicer.
    spec: SlicerSpec


class TableColumnDataValidationRule(TypedDict, total=False):
    """A data validation rule for a column in a table."""

    # The condition that data in the cell must match. Valid only if the [Boolea...
    condition: BooleanCondition


class TableColumnProperties(TypedDict, total=False):
    """The table column."""

    # The 0-based column index. This index is relative to its position in the t...
    columnIndex: int

    # The column name.
    columnName: str

    # The column type.
    # Enum values:
    #   "COLUMN_TYPE_UNSPECIFIED": An unspecified column type.
    #   "DOUBLE": The number column type.
    #   "CURRENCY": The currency column type.
    #   "PERCENT": The percent column type.
    #   "DATE": The date column type.
    #   "TIME": The time column type.
    #   "DATE_TIME": The date and time column type.
    #   "TEXT": The text column type.
    #   "BOOLEAN": The boolean column type.
    #   "DROPDOWN": The dropdown column type.
    #   "FILES_CHIP": The files chip column type
    #   "PEOPLE_CHIP": The people chip column type
    #   "FINANCE_CHIP": The finance chip column type
    #   "PLACE_CHIP": The place chip column type
    #   "RATINGS_CHIP": The ratings chip column type
    columnType: str

    # The column data validation rule. Only set for dropdown column type.
    dataValidationRule: TableColumnDataValidationRule


class TableRowsProperties(TypedDict, total=False):
    """The table row properties."""

    # The first color that is alternating. If this field is set, the first band...
    firstBandColorStyle: ColorStyle

    # The color of the last row. If this field is not set a footer is not added...
    footerColorStyle: ColorStyle

    # The color of the header row. If this field is set, the header row is fill...
    headerColorStyle: ColorStyle

    # The second color that is alternating. If this field is set, the second ba...
    secondBandColorStyle: ColorStyle


class Table(TypedDict, total=False):
    """A table."""

    # The table column properties.
    columnProperties: list[TableColumnProperties]

    # The table name. This is unique to all tables in the same spreadsheet.
    name: str

    # The table range.
    range: GridRange

    # The table rows properties.
    rowsProperties: TableRowsProperties

    # The id of the table.
    tableId: str


class PivotFilterCriteria(TypedDict, total=False):
    """Criteria for showing/hiding rows in a pivot table."""

    # A condition that must be true for values to be shown. (`visibleValues` do...
    condition: BooleanCondition

    # Whether values are visible by default. If true, the visible_values are ig...
    visibleByDefault: bool

    # Values that should be included. Values not listed here are excluded.
    visibleValues: list[str]


class PivotFilterSpec(TypedDict, total=False):
    """The pivot table filter criteria associated with a specific source column offset."""

    # The zero-based column offset of the source range.
    columnOffsetIndex: int

    # The reference to the data source column.
    dataSourceColumnReference: DataSourceColumnReference

    # The criteria for the column.
    filterCriteria: PivotFilterCriteria


class PivotValue(TypedDict, total=False):
    """The definition of how a value in a pivot table should be calculated."""

    # If specified, indicates that pivot values should be displayed as the resu...
    # Enum values:
    #   "PIVOT_VALUE_CALCULATED_DISPLAY_TYPE_UNSPECIFIED": Default value, do not use.
    #   "PERCENT_OF_ROW_TOTAL": Shows the pivot values as percentage of the row total val...
    #   "PERCENT_OF_COLUMN_TOTAL": Shows the pivot values as percentage of the column total ...
    #   "PERCENT_OF_GRAND_TOTAL": Shows the pivot values as percentage of the grand total v...
    calculatedDisplayType: str

    # The reference to the data source column that this value reads from.
    dataSourceColumnReference: DataSourceColumnReference

    # A custom formula to calculate the value. The formula must start with an `...
    formula: str

    # A name to use for the value.
    name: str

    # The column offset of the source range that this value reads from. For exa...
    sourceColumnOffset: int

    # A function to summarize the value. If formula is set, the only supported ...
    # Enum values:
    #   "PIVOT_STANDARD_VALUE_FUNCTION_UNSPECIFIED": The default, do not use.
    #   "SUM": Corresponds to the `SUM` function.
    #   "COUNTA": Corresponds to the `COUNTA` function.
    #   "COUNT": Corresponds to the `COUNT` function.
    #   "COUNTUNIQUE": Corresponds to the `COUNTUNIQUE` function.
    #   "AVERAGE": Corresponds to the `AVERAGE` function.
    #   "MAX": Corresponds to the `MAX` function.
    #   "MIN": Corresponds to the `MIN` function.
    #   "MEDIAN": Corresponds to the `MEDIAN` function.
    #   "PRODUCT": Corresponds to the `PRODUCT` function.
    #   "STDEV": Corresponds to the `STDEV` function.
    #   "STDEVP": Corresponds to the `STDEVP` function.
    #   "VAR": Corresponds to the `VAR` function.
    #   "VARP": Corresponds to the `VARP` function.
    #   "CUSTOM": Indicates the formula should be used as-is. Only valid if...
    #   "NONE": Indicates that the value is already summarized, and the s...
    summarizeFunction: str


class PivotGroupValueMetadata(TypedDict, total=False):
    """Metadata about a value in a pivot grouping."""

    # True if the data corresponding to the value is collapsed.
    collapsed: bool

    # The calculated value the metadata corresponds to. (Note that formulaValue...
    value: ExtendedValue


class PivotGroupSortValueBucket(TypedDict, total=False):
    """Information about which values in a pivot group should be used for sorting."""

    # Determines the bucket from which values are chosen to sort. For example, ...
    buckets: list[ExtendedValue]

    # The offset in the PivotTable.values list which the values in this groupin...
    valuesIndex: int


class PivotGroupLimit(TypedDict, total=False):
    """The count limit on rows or columns in the pivot group."""

    # The order in which the group limit is applied to the pivot table. Pivot g...
    applyOrder: int

    # The count limit.
    countLimit: int


class PivotGroupRule(TypedDict, total=False):
    """An optional setting on a PivotGroup that defines buckets for the values in the source data column rather than breaking out each individual value. Only one PivotGroup with a group rule may be added for each column in the source data, though on any given column you may add both a PivotGroup that has a rule and a PivotGroup that does not."""

    # A DateTimeRule.
    dateTimeRule: DateTimeRule

    # A HistogramRule.
    histogramRule: HistogramRule

    # A ManualRule.
    manualRule: ManualRule


class PivotGroup(TypedDict, total=False):
    """A single grouping (either row or column) in a pivot table."""

    # The reference to the data source column this grouping is based on.
    dataSourceColumnReference: DataSourceColumnReference

    # The count limit on rows or columns to apply to this pivot group.
    groupLimit: PivotGroupLimit

    # The group rule to apply to this row/column group.
    groupRule: PivotGroupRule

    # The labels to use for the row/column groups which can be customized. For ...
    label: str

    # True if the headings in this pivot group should be repeated. This is only...
    repeatHeadings: bool

    # True if the pivot table should include the totals for this grouping.
    showTotals: bool

    # The order the values in this group should be sorted.
    # Enum values:
    #   "SORT_ORDER_UNSPECIFIED": Default value, do not use this.
    #   "ASCENDING": Sort ascending.
    #   "DESCENDING": Sort descending.
    sortOrder: str

    # The column offset of the source range that this grouping is based on. For...
    sourceColumnOffset: int

    # The bucket of the opposite pivot group to sort by. If not specified, sort...
    valueBucket: PivotGroupSortValueBucket

    # Metadata about values in the grouping.
    valueMetadata: list[PivotGroupValueMetadata]


class PivotTable(TypedDict, total=False):
    """A pivot table."""

    # Each column grouping in the pivot table.
    columns: list[PivotGroup]

    # An optional mapping of filters per source column offset. The filters are ...
    # Deprecated
    criteria: dict[str, PivotFilterCriteria]

    # Output only. The data execution status for data source pivot tables.
    # Read-only field
    dataExecutionStatus: DataExecutionStatus

    # The ID of the data source the pivot table is reading data from.
    dataSourceId: str

    # The filters applied to the source columns before aggregating data for the...
    filterSpecs: list[PivotFilterSpec]

    # Each row grouping in the pivot table.
    rows: list[PivotGroup]

    # The range the pivot table is reading data from.
    source: GridRange

    # Whether values should be listed horizontally (as columns) or vertically (...
    # Enum values:
    #   "HORIZONTAL": Values are laid out horizontally (as columns).
    #   "VERTICAL": Values are laid out vertically (as rows).
    valueLayout: str

    # A list of values to include in the pivot table.
    values: list[PivotValue]


class DataSourceTable(TypedDict, total=False):
    """A data source table, which allows the user to import a static table of data from the DataSource into Sheets. This is also known as "Extract" in the Sheets editor."""

    # The type to select columns for the data source table. Defaults to SELECTED.
    # Enum values:
    #   "DATA_SOURCE_TABLE_COLUMN_SELECTION_TYPE_UNSPECIFIED": The default column selection type, do not use.
    #   "SELECTED": Select columns specified by columns field.
    #   "SYNC_ALL": Sync all current and future columns in the data source. I...
    columnSelectionType: str

    # Columns selected for the data source table. The column_selection_type mus...
    columns: list[DataSourceColumnReference]

    # Output only. The data execution status.
    # Read-only field
    dataExecutionStatus: DataExecutionStatus

    # The ID of the data source the data source table is associated with.
    dataSourceId: str

    # Filter specifications in the data source table.
    filterSpecs: list[FilterSpec]

    # The limit of rows to return. If not set, a default limit is applied. Plea...
    rowLimit: int

    # Sort specifications in the data source table. The result of the data sour...
    sortSpecs: list[SortSpec]


class DataValidationRule(TypedDict, total=False):
    """A data validation rule."""

    # The condition that data in the cell must match.
    condition: BooleanCondition

    # A message to show the user when adding data to the cell.
    inputMessage: str

    # True if the UI should be customized based on the kind of condition. If tr...
    showCustomUi: bool

    # True if invalid data should be rejected.
    strict: bool


class BasicFilter(TypedDict, total=False):
    """The default filter associated with a sheet."""

    # The criteria for showing/hiding values per column. The map's key is the c...
    # Deprecated
    criteria: dict[str, FilterCriteria]

    # The filter criteria per column. Both criteria and filter_specs are popula...
    filterSpecs: list[FilterSpec]

    # The range the filter covers.
    range: GridRange

    # The sort order per column. Later specifications are used when values are ...
    sortSpecs: list[SortSpec]

    # The table this filter is backed by, if any. When writing, only one of ran...
    tableId: str


class DataFilter(TypedDict, total=False):
    """Filter that describes what data should be selected or returned from a request."""

    # Selects data that matches the specified A1 range.
    a1Range: str

    # Selects data associated with the developer metadata matching the criteria...
    developerMetadataLookup: DeveloperMetadataLookup

    # Selects data that matches the range described by the GridRange.
    gridRange: GridRange


class DataFilterValueRange(TypedDict, total=False):
    """A range of values whose location is specified by a DataFilter."""

    # The data filter describing the location of the values in the spreadsheet.
    dataFilter: DataFilter

    # The major dimension of the values.
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    majorDimension: str

    # The data to be written. If the provided values exceed any of the ranges m...
    values: list[list[Any]]


# =============================================================================
# Data Sources
# =============================================================================


class DataSourceColumnReference(TypedDict, total=False):
    """An unique identifier that references a data source column."""

    # The display name of the column. It should be unique within a data source.
    name: str


class DataSourceColumn(TypedDict, total=False):
    """A column in a data source."""

    # The formula of the calculated column.
    formula: str

    # The column reference.
    reference: DataSourceColumnReference


class BigQueryQuerySpec(TypedDict, total=False):
    """Specifies a custom BigQuery query."""

    # The raw query string.
    rawQuery: str


class BigQueryDataSourceSpec(TypedDict, total=False):
    """The specification of a BigQuery data source that's connected to a sheet."""

    # The ID of a BigQuery enabled Google Cloud project with a billing account ...
    projectId: str

    # A BigQueryQuerySpec.
    querySpec: BigQueryQuerySpec

    # A BigQueryTableSpec.
    tableSpec: BigQueryTableSpec


class LookerDataSourceSpec(TypedDict, total=False):
    """The specification of a Looker data source."""

    # Name of a Looker model explore.
    explore: str

    # A Looker instance URL.
    instanceUri: str

    # Name of a Looker model.
    model: str


class DataSourceParameter(TypedDict, total=False):
    """A parameter in a data source's query. The parameter allows the user to pass in values from the spreadsheet into a query."""

    # Named parameter. Must be a legitimate identifier for the DataSource that ...
    name: str

    # ID of a NamedRange. Its size must be 1x1.
    namedRangeId: str

    # A range that contains the value of the parameter. Its size must be 1x1.
    range: GridRange


class DataSourceSpec(TypedDict, total=False):
    """This specifies the details of the data source. For example, for BigQuery, this specifies information about the BigQuery source."""

    # A BigQueryDataSourceSpec.
    bigQuery: BigQueryDataSourceSpec

    # A LookerDatasourceSpec.
    looker: LookerDataSourceSpec

    # The parameters of the data source, used when querying the data source.
    parameters: list[DataSourceParameter]


class DataSource(TypedDict, total=False):
    """Information about an external data source in the spreadsheet."""

    # All calculated columns in the data source.
    calculatedColumns: list[DataSourceColumn]

    # The spreadsheet-scoped unique ID that identifies the data source. Example...
    dataSourceId: str

    # The ID of the Sheet connected with the data source. The field cannot be c...
    sheetId: int

    # The DataSourceSpec for the data source connected with this spreadsheet.
    spec: DataSourceSpec


class DataSourceSheetProperties(TypedDict, total=False):
    """Additional properties of a DATA_SOURCE sheet."""

    # The columns displayed on the sheet, corresponding to the values in RowData.
    columns: list[DataSourceColumn]

    # The data execution status.
    dataExecutionStatus: DataExecutionStatus

    # ID of the DataSource the sheet is connected to.
    dataSourceId: str


class DataSourceFormula(TypedDict, total=False):
    """A data source formula."""

    # Output only. The data execution status.
    # Read-only field
    dataExecutionStatus: DataExecutionStatus

    # The ID of the data source the formula is associated with.
    dataSourceId: str


class DataSourceSheetDimensionRange(TypedDict, total=False):
    """A range along a single dimension on a DATA_SOURCE sheet."""

    # The columns on the data source sheet.
    columnReferences: list[DataSourceColumnReference]

    # The ID of the data source sheet the range is on.
    sheetId: int


class DataSourceObjectReference(TypedDict, total=False):
    """Reference to a data source object."""

    # References to a data source chart.
    chartId: int

    # References to a cell containing DataSourceFormula.
    dataSourceFormulaCell: GridCoordinate

    # References to a data source PivotTable anchored at the cell.
    dataSourcePivotTableAnchorCell: GridCoordinate

    # References to a DataSourceTable anchored at the cell.
    dataSourceTableAnchorCell: GridCoordinate

    # References to a DATA_SOURCE sheet.
    sheetId: str


class DataSourceObjectReferences(TypedDict, total=False):
    """A list of references to data source objects."""

    # The references.
    references: list[DataSourceObjectReference]


class DataSourceRefreshMonthlySchedule(TypedDict, total=False):
    """A monthly schedule for data to refresh on specific days in the month in a given time interval."""

    # Days of the month to refresh. Only 1-28 are supported, mapping to the 1st...
    daysOfMonth: list[int]

    # The start time of a time interval in which a data source refresh is sched...
    startTime: TimeOfDay


class DataSourceRefreshDailySchedule(TypedDict, total=False):
    """A schedule for data to refresh every day in a given time interval."""

    # The start time of a time interval in which a data source refresh is sched...
    startTime: TimeOfDay


class DataSourceRefreshWeeklySchedule(TypedDict, total=False):
    """A weekly schedule for data to refresh on specific days in a given time interval."""

    # Days of the week to refresh. At least one day must be specified.
    daysOfWeek: list[str]

    # The start time of a time interval in which a data source refresh is sched...
    startTime: TimeOfDay


class DataSourceRefreshSchedule(TypedDict, total=False):
    """Schedule for refreshing the data source. Data sources in the spreadsheet are refreshed within a time interval. You can specify the start time by clicking the Scheduled Refresh button in the Sheets editor, but the interval is fixed at 4 hours. For example, if you specify a start time of 8 AM , the refresh will take place between 8 AM and 12 PM every day."""

    # Daily refresh schedule.
    dailySchedule: DataSourceRefreshDailySchedule

    # True if the refresh schedule is enabled, or false otherwise.
    enabled: bool

    # Monthly refresh schedule.
    monthlySchedule: DataSourceRefreshMonthlySchedule

    # Output only. The time interval of the next run.
    # Read-only field
    nextRun: Interval

    # The scope of the refresh. Must be ALL_DATA_SOURCES.
    # Enum values:
    #   "DATA_SOURCE_REFRESH_SCOPE_UNSPECIFIED": Default value, do not use.
    #   "ALL_DATA_SOURCES": Refreshes all data sources and their associated data sour...
    refreshScope: str

    # Weekly refresh schedule.
    weeklySchedule: DataSourceRefreshWeeklySchedule


class RefreshDataSourceObjectExecutionStatus(TypedDict, total=False):
    """The execution status of refreshing one data source object."""

    # The data execution status.
    dataExecutionStatus: DataExecutionStatus

    # Reference to a data source object being refreshed.
    reference: DataSourceObjectReference


class CancelDataSourceRefreshStatus(TypedDict, total=False):
    """The status of cancelling a single data source object refresh."""

    # Reference to the data source object whose refresh is being cancelled.
    reference: DataSourceObjectReference

    # The cancellation status.
    refreshCancellationStatus: RefreshCancellationStatus


# =============================================================================
# Other Objects
# =============================================================================


class BandingProperties(TypedDict, total=False):
    """Properties referring a single dimension (either row or column). If both BandedRange.row_properties and BandedRange.column_properties are set, the fill colors are applied to cells according to the following rules: * header_color and footer_color take priority over band colors. * first_band_color takes priority over second_band_color. * row_properties takes priority over column_properties. For example, the first row color takes priority over the first column color, but the first column color takes priority over the second row color. Similarly, the row header takes priority over the column header in the top left cell, but the column header takes priority over the first row color if the row header is not set."""

    # The first color that is alternating. (Required) Deprecated: Use first_ban...
    # Deprecated
    firstBandColor: Color

    # The first color that is alternating. (Required) If first_band_color is al...
    firstBandColorStyle: ColorStyle

    # The color of the last row or column. If this field is not set, the last r...
    # Deprecated
    footerColor: Color

    # The color of the last row or column. If this field is not set, the last r...
    footerColorStyle: ColorStyle

    # The color of the first row or column. If this field is set, the first row...
    # Deprecated
    headerColor: Color

    # The color of the first row or column. If this field is set, the first row...
    headerColorStyle: ColorStyle

    # The second color that is alternating. (Required) Deprecated: Use second_b...
    # Deprecated
    secondBandColor: Color

    # The second color that is alternating. (Required) If second_band_color is ...
    secondBandColorStyle: ColorStyle


class SortSpec(TypedDict, total=False):
    """A sort order associated with a specific column or row."""

    # The background fill color to sort by; cells with this fill color are sort...
    # Deprecated
    backgroundColor: Color

    # The background fill color to sort by; cells with this fill color are sort...
    backgroundColorStyle: ColorStyle

    # Reference to a data source column.
    dataSourceColumnReference: DataSourceColumnReference

    # The dimension the sort should be applied to.
    dimensionIndex: int

    # The foreground color to sort by; cells with this foreground color are sor...
    # Deprecated
    foregroundColor: Color

    # The foreground color to sort by; cells with this foreground color are sor...
    foregroundColorStyle: ColorStyle

    # The order data should be sorted.
    # Enum values:
    #   "SORT_ORDER_UNSPECIFIED": Default value, do not use this.
    #   "ASCENDING": Sort ascending.
    #   "DESCENDING": Sort descending.
    sortOrder: str


class ConditionValue(TypedDict, total=False):
    """The value of the condition."""

    # A relative date (based on the current date). Valid only if the type is DA...
    # Enum values:
    #   "RELATIVE_DATE_UNSPECIFIED": Default value, do not use.
    #   "PAST_YEAR": The value is one year before today.
    #   "PAST_MONTH": The value is one month before today.
    #   "PAST_WEEK": The value is one week before today.
    #   "YESTERDAY": The value is yesterday.
    #   "TODAY": The value is today.
    #   "TOMORROW": The value is tomorrow.
    relativeDate: str

    # A value the condition is based on. The value is parsed as if the user typ...
    userEnteredValue: str


class BooleanCondition(TypedDict, total=False):
    """A condition that can evaluate to true or false. BooleanConditions are used by conditional formatting, data validation, and the criteria in filters."""

    # The type of condition.
    # Enum values:
    #   "CONDITION_TYPE_UNSPECIFIED": The default value, do not use.
    #   "NUMBER_GREATER": The cell's value must be greater than the condition's val...
    #   "NUMBER_GREATER_THAN_EQ": The cell's value must be greater than or equal to the con...
    #   "NUMBER_LESS": The cell's value must be less than the condition's value....
    #   "NUMBER_LESS_THAN_EQ": The cell's value must be less than or equal to the condit...
    #   "NUMBER_EQ": The cell's value must be equal to the condition's value. ...
    #   "NUMBER_NOT_EQ": The cell's value must be not equal to the condition's val...
    #   "NUMBER_BETWEEN": The cell's value must be between the two condition values...
    #   "NUMBER_NOT_BETWEEN": The cell's value must not be between the two condition va...
    #   "TEXT_CONTAINS": The cell's value must contain the condition's value. Supp...
    #   "TEXT_NOT_CONTAINS": The cell's value must not contain the condition's value. ...
    #   "TEXT_STARTS_WITH": The cell's value must start with the condition's value. S...
    #   "TEXT_ENDS_WITH": The cell's value must end with the condition's value. Sup...
    #   "TEXT_EQ": The cell's value must be exactly the condition's value. S...
    #   "TEXT_IS_EMAIL": The cell's value must be a valid email address. Supported...
    #   "TEXT_IS_URL": The cell's value must be a valid URL. Supported by data v...
    #   "DATE_EQ": The cell's value must be the same date as the condition's...
    #   "DATE_BEFORE": The cell's value must be before the date of the condition...
    #   "DATE_AFTER": The cell's value must be after the date of the condition'...
    #   "DATE_ON_OR_BEFORE": The cell's value must be on or before the date of the con...
    #   "DATE_ON_OR_AFTER": The cell's value must be on or after the date of the cond...
    #   "DATE_BETWEEN": The cell's value must be between the dates of the two con...
    #   "DATE_NOT_BETWEEN": The cell's value must be outside the dates of the two con...
    #   "DATE_IS_VALID": The cell's value must be a date. Supported by data valida...
    #   "ONE_OF_RANGE": The cell's value must be listed in the grid in condition ...
    #   "ONE_OF_LIST": The cell's value must be in the list of condition values....
    #   "BLANK": The cell's value must be empty. Supported by conditional ...
    #   "NOT_BLANK": The cell's value must not be empty. Supported by conditio...
    #   "CUSTOM_FORMULA": The condition's formula must evaluate to true. Supported ...
    #   "BOOLEAN": The cell's value must be TRUE/FALSE or in the list of con...
    #   "TEXT_NOT_EQ": The cell's value must be exactly not the condition's valu...
    #   "DATE_NOT_EQ": The cell's value must be exactly not the condition's valu...
    #   "FILTER_EXPRESSION": The cell's value must follow the pattern specified. Requi...
    type: str

    # The values of the condition. The number of supported values depends on th...
    values: list[ConditionValue]


class Link(TypedDict, total=False):
    """An external or local reference."""

    # The link identifier.
    uri: str


class DataLabel(TypedDict, total=False):
    """Settings for one set of data labels. Data labels are annotations that appear next to a set of data, such as the points on a line chart, and provide additional information about what the data represents, such as a text representation of the value behind that point on the graph."""

    # Data to use for custom labels. Only used if type is set to CUSTOM. This d...
    customLabelData: ChartData

    # The placement of the data label relative to the labeled data.
    # Enum values:
    #   "DATA_LABEL_PLACEMENT_UNSPECIFIED": The positioning is determined automatically by the renderer.
    #   "CENTER": Center within a bar or column, both horizontally and vert...
    #   "LEFT": To the left of a data point.
    #   "RIGHT": To the right of a data point.
    #   "ABOVE": Above a data point.
    #   "BELOW": Below a data point.
    #   "INSIDE_END": Inside a bar or column at the end (top if positive, botto...
    #   "INSIDE_BASE": Inside a bar or column at the base.
    #   "OUTSIDE_END": Outside a bar or column at the end.
    placement: str

    # The text format used for the data label. The link field is not supported.
    textFormat: TextFormat

    # The type of the data label.
    # Enum values:
    #   "DATA_LABEL_TYPE_UNSPECIFIED": The data label type is not specified and will be interpre...
    #   "NONE": The data label is not displayed.
    #   "DATA": The data label is displayed using values from the series ...
    #   "CUSTOM": The data label is displayed using values from a custom da...
    type: str


class DataExecutionStatus(TypedDict, total=False):
    """The data execution status. A data execution is created to sync a data source object with the latest data from a DataSource. It is usually scheduled to run at background, you can check its state to tell if an execution completes There are several scenarios where a data execution is triggered to run: * Adding a data source creates an associated data source sheet as well as a data execution to sync the data from the data source to the sheet. * Updating a data source creates a data execution to refresh the associated data source sheet similarly. * You can send refresh request to explicitly refresh one or multiple data source objects."""

    # The error code.
    # Enum values:
    #   "DATA_EXECUTION_ERROR_CODE_UNSPECIFIED": Default value, do not use.
    #   "TIMED_OUT": The data execution timed out.
    #   "TOO_MANY_ROWS": The data execution returns more rows than the limit.
    #   "TOO_MANY_COLUMNS": The data execution returns more columns than the limit.
    #   "TOO_MANY_CELLS": The data execution returns more cells than the limit.
    #   "ENGINE": Error is received from the backend data execution engine ...
    #   "PARAMETER_INVALID": One or some of the provided data source parameters are in...
    #   "UNSUPPORTED_DATA_TYPE": The data execution returns an unsupported data type.
    #   "DUPLICATE_COLUMN_NAMES": The data execution returns duplicate column names or alia...
    #   "INTERRUPTED": The data execution is interrupted. Please refresh later.
    #   "CONCURRENT_QUERY": The data execution is currently in progress, can not be r...
    #   "OTHER": Other errors.
    #   "TOO_MANY_CHARS_PER_CELL": The data execution returns values that exceed the maximum...
    #   "DATA_NOT_FOUND": The database referenced by the data source is not found. */
    #   "PERMISSION_DENIED": The user does not have access to the database referenced ...
    #   "MISSING_COLUMN_ALIAS": The data execution returns columns with missing aliases.
    #   "OBJECT_NOT_FOUND": The data source object does not exist.
    #   "OBJECT_IN_ERROR_STATE": The data source object is currently in error state. To fo...
    #   "OBJECT_SPEC_INVALID": The data source object specification is invalid.
    #   "DATA_EXECUTION_CANCELLED": The data execution has been cancelled.
    errorCode: str

    # The error message, which may be empty.
    errorMessage: str

    # Gets the time the data last successfully refreshed.
    lastRefreshTime: str

    # The state of the data execution.
    # Enum values:
    #   "DATA_EXECUTION_STATE_UNSPECIFIED": Default value, do not use.
    #   "NOT_STARTED": The data execution has not started.
    #   "RUNNING": The data execution has started and is running.
    #   "CANCELLING": The data execution is currently being cancelled.
    #   "SUCCEEDED": The data execution has completed successfully.
    #   "FAILED": The data execution has completed with errors.
    state: str


class TextPosition(TypedDict, total=False):
    """Position settings for text."""

    # Horizontal alignment setting for the piece of text.
    # Enum values:
    #   "HORIZONTAL_ALIGN_UNSPECIFIED": The horizontal alignment is not specified. Do not use this.
    #   "LEFT": The text is explicitly aligned to the left of the cell.
    #   "CENTER": The text is explicitly aligned to the center of the cell.
    #   "RIGHT": The text is explicitly aligned to the right of the cell.
    horizontalAlignment: str


class OverlayPosition(TypedDict, total=False):
    """The location an object is overlaid on top of a grid."""

    # The cell the object is anchored to.
    anchorCell: GridCoordinate

    # The height of the object, in pixels. Defaults to 371.
    heightPixels: int

    # The horizontal offset, in pixels, that the object is offset from the anch...
    offsetXPixels: int

    # The vertical offset, in pixels, that the object is offset from the anchor...
    offsetYPixels: int

    # The width of the object, in pixels. Defaults to 600.
    widthPixels: int


class EmbeddedObjectPosition(TypedDict, total=False):
    """The position of an embedded object such as a chart."""

    # If true, the embedded object is put on a new sheet whose ID is chosen for...
    newSheet: bool

    # The position at which the object is overlaid on top of a grid.
    overlayPosition: OverlayPosition

    # The sheet this is on. Set only if the embedded object is on its own sheet...
    sheetId: int


class InterpolationPoint(TypedDict, total=False):
    """A single interpolation point on a gradient conditional format. These pin the gradient color scale according to the color, type and value chosen."""

    # The color this interpolation point should use. Deprecated: Use color_style.
    # Deprecated
    color: Color

    # The color this interpolation point should use. If color is also set, this...
    colorStyle: ColorStyle

    # How the value should be interpreted.
    # Enum values:
    #   "INTERPOLATION_POINT_TYPE_UNSPECIFIED": The default value, do not use.
    #   "MIN": The interpolation point uses the minimum value in the cel...
    #   "MAX": The interpolation point uses the maximum value in the cel...
    #   "NUMBER": The interpolation point uses exactly the value in Interpo...
    #   "PERCENT": The interpolation point is the given percentage over all ...
    #   "PERCENTILE": The interpolation point is the given percentile over all ...
    type: str

    # The value this interpolation point uses. May be a formula. Unused if type...
    value: str


class GradientRule(TypedDict, total=False):
    """A rule that applies a gradient color scale format, based on the interpolation points listed. The format of a cell will vary based on its contents as compared to the values of the interpolation points."""

    # The final interpolation point.
    maxpoint: InterpolationPoint

    # An optional midway interpolation point.
    midpoint: InterpolationPoint

    # The starting interpolation point.
    minpoint: InterpolationPoint


class TextRotation(TypedDict, total=False):
    """The rotation applied to text in a cell."""

    # The angle between the standard orientation and the desired orientation. M...
    angle: int

    # If true, text reads top to bottom, but the orientation of individual char...
    vertical: bool


class BooleanRule(TypedDict, total=False):
    """A rule that may or may not match, depending on the condition."""

    # The condition of the rule. If the condition evaluates to true, the format...
    condition: BooleanCondition

    # The format to apply. Conditional formatting can only apply a subset of fo...
    format: CellFormat


class Editors(TypedDict, total=False):
    """The editors of a protected range."""

    # True if anyone in the document's domain has edit access to the protected ...
    domainUsersCanEdit: bool

    # The email addresses of groups with edit access to the protected range.
    groups: list[str]

    # The email addresses of users with edit access to the protected range.
    users: list[str]


class ManualRuleGroup(TypedDict, total=False):
    """A group name and a list of items from the source data that should be placed in the group with this name."""

    # The group name, which must be a string. Each group in a given ManualRule ...
    groupName: ExtendedValue

    # The items in the source data that should be placed into this group. Each ...
    items: list[ExtendedValue]


class ManualRule(TypedDict, total=False):
    """Allows you to manually organize the values in a source data column into buckets with names of your choosing. For example, a pivot table that aggregates population by state: +-------+-------------------+ | State | SUM of Population | +-------+-------------------+ | AK | 0.7 | | AL | 4.8 | | AR | 2.9 | ... +-------+-------------------+ could be turned into a pivot table that aggregates population by time zone by providing a list of groups (for example, groupName = 'Central', items = ['AL', 'AR', 'IA', ...]) to a manual group rule. Note that a similar effect could be achieved by adding a time zone column to the source data and adjusting the pivot table. +-----------+-------------------+ | Time Zone | SUM of Population | +-----------+-------------------+ | Central | 106.3 | | Eastern | 151.9 | | Mountain | 17.4 | ... +-----------+-------------------+"""

    # The list of group names and the corresponding items from the source data ...
    groups: list[ManualRuleGroup]


class DateTimeRule(TypedDict, total=False):
    """Allows you to organize the date-time values in a source data column into buckets based on selected parts of their date or time values. For example, consider a pivot table showing sales transactions by date: +----------+--------------+ | Date | SUM of Sales | +----------+--------------+ | 1/1/2017 | $621.14 | | 2/3/2017 | $708.84 | | 5/8/2017 | $326.84 | ... +----------+--------------+ Applying a date-time group rule with a DateTimeRuleType of YEAR_MONTH results in the following pivot table. +--------------+--------------+ | Grouped Date | SUM of Sales | +--------------+--------------+ | 2017-Jan | $53,731.78 | | 2017-Feb | $83,475.32 | | 2017-Mar | $94,385.05 | ... +--------------+--------------+"""

    # The type of date-time grouping to apply.
    # Enum values:
    #   "DATE_TIME_RULE_TYPE_UNSPECIFIED": The default type, do not use.
    #   "SECOND": Group dates by second, from 0 to 59.
    #   "MINUTE": Group dates by minute, from 0 to 59.
    #   "HOUR": Group dates by hour using a 24-hour system, from 0 to 23.
    #   "HOUR_MINUTE": Group dates by hour and minute using a 24-hour system, fo...
    #   "HOUR_MINUTE_AMPM": Group dates by hour and minute using a 12-hour system, fo...
    #   "DAY_OF_WEEK": Group dates by day of week, for example Sunday. The days ...
    #   "DAY_OF_YEAR": Group dates by day of year, from 1 to 366. Note that date...
    #   "DAY_OF_MONTH": Group dates by day of month, from 1 to 31.
    #   "DAY_MONTH": Group dates by day and month, for example 22-Nov. The mon...
    #   "MONTH": Group dates by month, for example Nov. The month is trans...
    #   "QUARTER": Group dates by quarter, for example Q1 (which represents ...
    #   "YEAR": Group dates by year, for example 2008.
    #   "YEAR_MONTH": Group dates by year and month, for example 2008-Nov. The ...
    #   "YEAR_QUARTER": Group dates by year and quarter, for example 2008 Q4.
    #   "YEAR_MONTH_DAY": Group dates by year, month, and day, for example 2008-11-22.
    type: str


class PersonProperties(TypedDict, total=False):
    """Properties specific to a linked person."""

    # Optional. The display format of the person chip. If not set, the default ...
    # Enum values:
    #   "DISPLAY_FORMAT_UNSPECIFIED": Default value, do not use.
    #   "DEFAULT": Default display format.
    #   "LAST_NAME_COMMA_FIRST_NAME": Last name, first name display format.
    #   "EMAIL": Email display format.
    displayFormat: str

    # Required. The email address linked to this person. This field is always p...
    email: str


class RichLinkProperties(TypedDict, total=False):
    """Properties of a link to a Google resource (such as a file in Drive, a YouTube video, a Maps address, or a Calendar event). Only Drive files can be written as chips. All other rich link types are read only. URIs cannot exceed 2000 bytes when writing. NOTE: Writing Drive file chips requires at least one of the `drive.file`, `drive.readonly`, or `drive` OAuth scopes."""

    # Output only. The [MIME type](https://developers.google.com/drive/api/v3/m...
    # Read-only field
    mimeType: str

    # Required. The URI to the link. This is always present.
    uri: str


class Chip(TypedDict, total=False):
    """The Smart Chip."""

    # Properties of a linked person.
    personProperties: PersonProperties

    # Properties of a rich link.
    richLinkProperties: RichLinkProperties


class ChipRun(TypedDict, total=False):
    """The run of a chip. The chip continues until the start index of the next run."""

    # Optional. The chip of this run.
    chip: Chip

    # Required. The zero-based character index where this run starts, in UTF-16...
    startIndex: int


class ValueRange(TypedDict, total=False):
    """Data within a range of the spreadsheet."""

    # The major dimension of the values. For output, if the spreadsheet data is...
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    majorDimension: str

    # The range the values cover, in [A1 notation](https://developers.google.co...
    range: str

    # The data that was read or to be written. This is an array of arrays, the ...
    values: list[list[Any]]


class SourceAndDestination(TypedDict, total=False):
    """A combination of a source range and how to extend that source."""

    # The dimension that data should be filled into.
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    dimension: str

    # The number of rows or columns that data should be filled into. Positive n...
    fillLength: int

    # The location of the data to use as the source of the autofill.
    source: GridRange


class DeveloperMetadataLocation(TypedDict, total=False):
    """A location where metadata may be associated in a spreadsheet."""

    # Represents the row or column when metadata is associated with a dimension...
    dimensionRange: DimensionRange

    # The type of location this object represents. This field is read-only.
    # Enum values:
    #   "DEVELOPER_METADATA_LOCATION_TYPE_UNSPECIFIED": Default value.
    #   "ROW": Developer metadata associated on an entire row dimension.
    #   "COLUMN": Developer metadata associated on an entire column dimension.
    #   "SHEET": Developer metadata associated on an entire sheet.
    #   "SPREADSHEET": Developer metadata associated on the entire spreadsheet.
    locationType: str

    # The ID of the sheet when metadata is associated with an entire sheet.
    sheetId: int

    # True when metadata is associated with an entire spreadsheet.
    spreadsheet: bool


class DeveloperMetadataLookup(TypedDict, total=False):
    """Selects DeveloperMetadata that matches all of the specified fields. For example, if only a metadata ID is specified this considers the DeveloperMetadata with that particular unique ID. If a metadata key is specified, this considers all developer metadata with that key. If a key, visibility, and location type are all specified, this considers all developer metadata with that key and visibility that are associated with a location of that type. In general, this selects all DeveloperMetadata that matches the intersection of all the specified fields; any field or combination of fields may be specified."""

    # Determines how this lookup matches the location. If this field is specifi...
    # Enum values:
    #   "DEVELOPER_METADATA_LOCATION_MATCHING_STRATEGY_UNSPECIFIED": Default value. This value must not be used.
    #   "EXACT_LOCATION": Indicates that a specified location should be matched exa...
    #   "INTERSECTING_LOCATION": Indicates that a specified location should match that exa...
    locationMatchingStrategy: str

    # Limits the selected developer metadata to those entries which are associa...
    # Enum values:
    #   "DEVELOPER_METADATA_LOCATION_TYPE_UNSPECIFIED": Default value.
    #   "ROW": Developer metadata associated on an entire row dimension.
    #   "COLUMN": Developer metadata associated on an entire column dimension.
    #   "SHEET": Developer metadata associated on an entire sheet.
    #   "SPREADSHEET": Developer metadata associated on the entire spreadsheet.
    locationType: str

    # Limits the selected developer metadata to that which has a matching Devel...
    metadataId: int

    # Limits the selected developer metadata to that which has a matching Devel...
    metadataKey: str

    # Limits the selected developer metadata to those entries associated with t...
    metadataLocation: DeveloperMetadataLocation

    # Limits the selected developer metadata to that which has a matching Devel...
    metadataValue: str

    # Limits the selected developer metadata to that which has a matching Devel...
    # Enum values:
    #   "DEVELOPER_METADATA_VISIBILITY_UNSPECIFIED": Default value.
    #   "DOCUMENT": Document-visible metadata is accessible from any develope...
    #   "PROJECT": Project-visible metadata is only visible to and accessibl...
    visibility: str


class MatchedValueRange(TypedDict, total=False):
    """A value range that was matched by one or more data filers."""

    # The DataFilters from the request that matched the range of values.
    dataFilters: list[DataFilter]

    # The values matched by the DataFilter.
    valueRange: ValueRange


class DeveloperMetadata(TypedDict, total=False):
    """Developer metadata associated with a location or object in a spreadsheet. Developer metadata may be used to associate arbitrary data with various parts of a spreadsheet and will remain associated at those locations as they move around and the spreadsheet is edited. For example, if developer metadata is associated with row 5 and another row is then subsequently inserted above row 5, that original metadata will still be associated with the row it was first associated with (what is now row 6). If the associated object is deleted its metadata is deleted too."""

    # The location where the metadata is associated.
    location: DeveloperMetadataLocation

    # The spreadsheet-scoped unique ID that identifies the metadata. IDs may be...
    metadataId: int

    # The metadata key. There may be multiple metadata in a spreadsheet with th...
    metadataKey: str

    # Data associated with the metadata's key.
    metadataValue: str

    # The metadata visibility. Developer metadata must always have a visibility...
    # Enum values:
    #   "DEVELOPER_METADATA_VISIBILITY_UNSPECIFIED": Default value.
    #   "DOCUMENT": Document-visible metadata is accessible from any develope...
    #   "PROJECT": Project-visible metadata is only visible to and accessibl...
    visibility: str


class IterativeCalculationSettings(TypedDict, total=False):
    """Settings to control how circular dependencies are resolved with iterative calculation."""

    # When iterative calculation is enabled and successive results differ by le...
    convergenceThreshold: float

    # When iterative calculation is enabled, the maximum number of calculation ...
    maxIterations: int


class SpreadsheetTheme(TypedDict, total=False):
    """Represents spreadsheet theme"""

    # Name of the primary font family.
    primaryFontFamily: str

    # The spreadsheet theme color pairs. To update you must provide all theme c...
    themeColors: list[ThemeColorPair]


class TimeOfDay(TypedDict, total=False):
    """Represents a time of day. The date and time zone are either not significant or are specified elsewhere. An API may choose to allow leap seconds. Related types are google.type.Date and `google.protobuf.Timestamp`."""

    # Hours of a day in 24 hour format. Must be greater than or equal to 0 and ...
    hours: int

    # Minutes of an hour. Must be greater than or equal to 0 and less than or e...
    minutes: int

    # Fractions of seconds, in nanoseconds. Must be greater than or equal to 0 ...
    nanos: int

    # Seconds of a minute. Must be greater than or equal to 0 and typically mus...
    seconds: int


class Interval(TypedDict, total=False):
    """Represents a time interval, encoded as a Timestamp start (inclusive) and a Timestamp end (exclusive). The start must be less than or equal to the end. When the start equals the end, the interval is empty (matches no time). When both start and end are unspecified, the interval matches any time."""

    # Optional. Exclusive end of the interval. If specified, a Timestamp matchi...
    endTime: str

    # Optional. Inclusive start of the interval. If specified, a Timestamp matc...
    startTime: str


class RefreshCancellationStatus(TypedDict, total=False):
    """The status of a refresh cancellation. You can send a cancel request to explicitly cancel one or multiple data source object refreshes."""

    # The error code.
    # Enum values:
    #   "REFRESH_CANCELLATION_ERROR_CODE_UNSPECIFIED": Default value, do not use.
    #   "EXECUTION_NOT_FOUND": Execution to be cancelled not found in the query engine o...
    #   "CANCEL_PERMISSION_DENIED": The user does not have permission to cancel the query.
    #   "QUERY_EXECUTION_COMPLETED": The query execution has already completed and thus could ...
    #   "CONCURRENT_CANCELLATION": There is already another cancellation in process.
    #   "CANCEL_OTHER_ERROR": All other errors.
    errorCode: str

    # The state of a call to cancel a refresh in Sheets.
    # Enum values:
    #   "REFRESH_CANCELLATION_STATE_UNSPECIFIED": Default value, do not use.
    #   "CANCEL_SUCCEEDED": The API call to Sheets to cancel a refresh has succeeded....
    #   "CANCEL_FAILED": The API call to Sheets to cancel a refresh has failed.
    state: str


class MatchedDeveloperMetadata(TypedDict, total=False):
    """A developer metadata entry and the data filters specified in the original request that matched it."""

    # All filters matching the returned developer metadata.
    dataFilters: list[DataFilter]

    # The developer metadata matching the specified filters.
    developerMetadata: DeveloperMetadata


# =============================================================================
# Requests
# =============================================================================


class AddBandingRequest(TypedDict, total=False):
    """Adds a new banded range to the spreadsheet."""

    # The banded range to add. The bandedRangeId field is optional; if one is n...
    bandedRange: BandedRange


class AddChartRequest(TypedDict, total=False):
    """Adds a chart to a sheet in the spreadsheet."""

    # The chart that should be added to the spreadsheet, including the position...
    chart: EmbeddedChart


class AddConditionalFormatRuleRequest(TypedDict, total=False):
    """Adds a new conditional format rule at the given index. All subsequent rules' indexes are incremented."""

    # The zero-based index where the rule should be inserted.
    index: int

    # The rule to add.
    rule: ConditionalFormatRule


class AddDataSourceRequest(TypedDict, total=False):
    """Adds a data source. After the data source is added successfully, an associated DATA_SOURCE sheet is created and an execution is triggered to refresh the sheet to read data from the data source. The request requires an additional `bigquery.readonly` OAuth scope if you are adding a BigQuery data source."""

    # The data source to add.
    dataSource: DataSource


class AddDimensionGroupRequest(TypedDict, total=False):
    """Creates a group over the specified range. If the requested range is a superset of the range of an existing group G, then the depth of G is incremented and this new group G' has the depth of that group. For example, a group [C:D, depth 1] + [B:E] results in groups [B:E, depth 1] and [C:D, depth 2]. If the requested range is a subset of the range of an existing group G, then the depth of the new group G' becomes one greater than the depth of G. For example, a group [B:E, depth 1] + [C:D] results in groups [B:E, depth 1] and [C:D, depth 2]. If the requested range starts before and ends within, or starts within and ends after, the range of an existing group G, then the range of the existing group G becomes the union of the ranges, and the new group G' has depth one greater than the depth of G and range as the intersection of the ranges. For example, a group [B:D, depth 1] + [C:E] results in groups [B:E, depth 1] and [C:D, depth 2]."""

    # The range over which to create a group.
    range: DimensionRange


class AddFilterViewRequest(TypedDict, total=False):
    """Adds a filter view."""

    # The filter to add. The filterViewId field is optional; if one is not set,...
    filter: FilterView


class AddNamedRangeRequest(TypedDict, total=False):
    """Adds a named range to the spreadsheet."""

    # The named range to add. The namedRangeId field is optional; if one is not...
    namedRange: NamedRange


class AddProtectedRangeRequest(TypedDict, total=False):
    """Adds a new protected range."""

    # The protected range to be added. The protectedRangeId field is optional; ...
    protectedRange: ProtectedRange


class AddSheetRequest(TypedDict, total=False):
    """Adds a new sheet. When a sheet is added at a given index, all subsequent sheets' indexes are incremented. To add an object sheet, use AddChartRequest instead and specify EmbeddedObjectPosition.sheetId or EmbeddedObjectPosition.newSheet."""

    # The properties the new sheet should have. All properties are optional. Th...
    properties: SheetProperties


class AddSlicerRequest(TypedDict, total=False):
    """Adds a slicer to a sheet in the spreadsheet."""

    # The slicer that should be added to the spreadsheet, including the positio...
    slicer: Slicer


class AddTableRequest(TypedDict, total=False):
    """Adds a new table to the spreadsheet."""

    # Required. The table to add.
    table: Table


class AppendCellsRequest(TypedDict, total=False):
    """Adds new cells after the last row with data in a sheet, inserting new rows into the sheet if necessary."""

    # The fields of CellData that should be updated. At least one field must be...
    fields: str

    # The data to append.
    rows: list[RowData]

    # The sheet ID to append the data to.
    sheetId: int

    # The ID of the table to append data to. The data will be only appended to ...
    tableId: str


class AppendDimensionRequest(TypedDict, total=False):
    """Appends rows or columns to the end of a sheet."""

    # Whether rows or columns should be appended.
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    dimension: str

    # The number of rows or columns to append.
    length: int

    # The sheet to append rows or columns to.
    sheetId: int


class AutoFillRequest(TypedDict, total=False):
    """Fills in more data based on existing data."""

    # The range to autofill. This will examine the range and detect the locatio...
    range: GridRange

    # The source and destination areas to autofill. This explicitly lists the s...
    sourceAndDestination: SourceAndDestination

    # True if we should generate data with the "alternate" series. This differs...
    useAlternateSeries: bool


class AutoResizeDimensionsRequest(TypedDict, total=False):
    """Automatically resizes one or more dimensions based on the contents of the cells in that dimension."""

    # The dimensions on a data source sheet to automatically resize.
    dataSourceSheetDimensions: DataSourceSheetDimensionRange

    # The dimensions to automatically resize.
    dimensions: DimensionRange


class BatchClearValuesByDataFilterRequest(TypedDict, total=False):
    """The request for clearing more than one range selected by a DataFilter in a spreadsheet."""

    # The DataFilters used to determine which ranges to clear.
    dataFilters: list[DataFilter]


class BatchClearValuesRequest(TypedDict, total=False):
    """The request for clearing more than one range of values in a spreadsheet."""

    # The ranges to clear, in [A1 notation or R1C1 notation](https://developers...
    ranges: list[str]


class BatchGetValuesByDataFilterRequest(TypedDict, total=False):
    """The request for retrieving a range of values in a spreadsheet selected by a set of DataFilters."""

    # The data filters used to match the ranges of values to retrieve. Ranges t...
    dataFilters: list[DataFilter]

    # How dates, times, and durations should be represented in the output. This...
    # Enum values:
    #   "SERIAL_NUMBER": Instructs date, time, datetime, and duration fields to be...
    #   "FORMATTED_STRING": Instructs date, time, datetime, and duration fields to be...
    dateTimeRenderOption: str

    # The major dimension that results should use. For example, if the spreadsh...
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    majorDimension: str

    # How values should be represented in the output. The default render option...
    # Enum values:
    #   "FORMATTED_VALUE": Values will be calculated & formatted in the response acc...
    #   "UNFORMATTED_VALUE": Values will be calculated, but not formatted in the reply...
    #   "FORMULA": Values will not be calculated. The reply will include the...
    valueRenderOption: str


class UpdateDataSourceRequest(TypedDict, total=False):
    """Updates a data source. After the data source is updated successfully, an execution is triggered to refresh the associated DATA_SOURCE sheet to read data from the updated data source. The request requires an additional `bigquery.readonly` OAuth scope if you are updating a BigQuery data source."""

    # The data source to update.
    dataSource: DataSource

    # The fields that should be updated. At least one field must be specified. ...
    fields: str


class InsertRangeRequest(TypedDict, total=False):
    """Inserts cells into a range, shifting the existing cells over or down."""

    # The range to insert new cells into. The range is constrained to the curre...
    range: GridRange

    # The dimension which will be shifted when inserting cells. If ROWS, existi...
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    shiftDimension: str


class UpdateEmbeddedObjectBorderRequest(TypedDict, total=False):
    """Updates an embedded object's border property."""

    # The border that applies to the embedded object.
    border: EmbeddedObjectBorder

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The ID of the embedded object to update.
    objectId: int


class UpdateProtectedRangeRequest(TypedDict, total=False):
    """Updates an existing protected range with the specified protectedRangeId."""

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The protected range to update with the new properties.
    protectedRange: ProtectedRange


class CopyPasteRequest(TypedDict, total=False):
    """Copies data from the source to the destination."""

    # The location to paste to. If the range covers a span that's a multiple of...
    destination: GridRange

    # How that data should be oriented when pasting.
    # Enum values:
    #   "NORMAL": Paste normally.
    #   "TRANSPOSE": Paste transposed, where all rows become columns and vice ...
    pasteOrientation: str

    # What kind of data to paste.
    # Enum values:
    #   "PASTE_NORMAL": Paste values, formulas, formats, and merges.
    #   "PASTE_VALUES": Paste the values ONLY without formats, formulas, or merges.
    #   "PASTE_FORMAT": Paste the format and data validation only.
    #   "PASTE_NO_BORDERS": Like `PASTE_NORMAL` but without borders.
    #   "PASTE_FORMULA": Paste the formulas only.
    #   "PASTE_DATA_VALIDATION": Paste the data validation only.
    #   "PASTE_CONDITIONAL_FORMATTING": Paste the conditional formatting rules only.
    pasteType: str

    # The source range to copy.
    source: GridRange


class UpdateBandingRequest(TypedDict, total=False):
    """Updates properties of the supplied banded range."""

    # The banded range to update with the new properties.
    bandedRange: BandedRange

    # The fields that should be updated. At least one field must be specified. ...
    fields: str


class SortRangeRequest(TypedDict, total=False):
    """Sorts data in rows based on a sort order per column."""

    # The range to sort.
    range: GridRange

    # The sort order per column. Later specifications are used when values are ...
    sortSpecs: list[SortSpec]


class ClearBasicFilterRequest(TypedDict, total=False):
    """Clears the basic filter, if any exists on the sheet."""

    # The sheet ID on which the basic filter should be cleared.
    sheetId: int


class DeleteDimensionGroupRequest(TypedDict, total=False):
    """Deletes a group over the specified range by decrementing the depth of the dimensions in the range. For example, assume the sheet has a depth-1 group over B:E and a depth-2 group over C:D. Deleting a group over D:E leaves the sheet with a depth-1 group over B:D and a depth-2 group over C:C."""

    # The range of the group to be deleted.
    range: DimensionRange


class UpdateDimensionPropertiesRequest(TypedDict, total=False):
    """Updates properties of dimensions within the specified range."""

    # The columns on a data source sheet to update.
    dataSourceSheetRange: DataSourceSheetDimensionRange

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # Properties to update.
    properties: DimensionProperties

    # The rows or columns to update.
    range: DimensionRange


class UpdateTableRequest(TypedDict, total=False):
    """Updates a table in the spreadsheet."""

    # Required. The fields that should be updated. At least one field must be s...
    fields: str

    # Required. The table to update.
    table: Table


class DeleteEmbeddedObjectRequest(TypedDict, total=False):
    """Deletes the embedded object with the given ID."""

    # The ID of the embedded object to delete.
    objectId: int


class RefreshDataSourceRequest(TypedDict, total=False):
    """Refreshes one or multiple data source objects in the spreadsheet by the specified references. The request requires an additional `bigquery.readonly` OAuth scope if you are refreshing a BigQuery data source. If there are multiple refresh requests referencing the same data source objects in one batch, only the last refresh request is processed, and all those requests will have the same response accordingly."""

    # Reference to a DataSource. If specified, refreshes all associated data so...
    dataSourceId: str

    # Refreshes the data source objects regardless of the current state. If not...
    force: bool

    # Refreshes all existing data source objects in the spreadsheet.
    isAll: bool

    # References to data source objects to refresh.
    references: DataSourceObjectReferences


class UpdateEmbeddedObjectPositionRequest(TypedDict, total=False):
    """Update an embedded object's position (such as a moving or resizing a chart or image)."""

    # The fields of OverlayPosition that should be updated when setting a new p...
    fields: str

    # An explicit position to move the embedded object to. If newPosition.sheet...
    newPosition: EmbeddedObjectPosition

    # The ID of the object to moved.
    objectId: int


class DeleteTableRequest(TypedDict, total=False):
    """Removes the table with the given ID from the spreadsheet."""

    # The ID of the table to delete.
    tableId: str


class DeleteBandingRequest(TypedDict, total=False):
    """Removes the banded range with the given ID from the spreadsheet."""

    # The ID of the banded range to delete.
    bandedRangeId: int


class MoveDimensionRequest(TypedDict, total=False):
    """Moves one or more rows or columns."""

    # The zero-based start index of where to move the source data to, based on ...
    destinationIndex: int

    # The source dimensions to move.
    source: DimensionRange


class UpdateDeveloperMetadataRequest(TypedDict, total=False):
    """A request to update properties of developer metadata. Updates the properties of the developer metadata selected by the filters to the values provided in the DeveloperMetadata resource. Callers must specify the properties they wish to update in the fields parameter, as well as specify at least one DataFilter matching the metadata they wish to update."""

    # The filters matching the developer metadata entries to update.
    dataFilters: list[DataFilter]

    # The value that all metadata matched by the data filters will be updated to.
    developerMetadata: DeveloperMetadata

    # The fields that should be updated. At least one field must be specified. ...
    fields: str


class DeleteDataSourceRequest(TypedDict, total=False):
    """Deletes a data source. The request also deletes the associated data source sheet, and unlinks all associated data source objects."""

    # The ID of the data source to delete.
    dataSourceId: str


class SetBasicFilterRequest(TypedDict, total=False):
    """Sets the basic filter associated with a sheet."""

    # The filter to set.
    filter: BasicFilter


class UpdateDimensionGroupRequest(TypedDict, total=False):
    """Updates the state of the specified group."""

    # The group whose state should be updated. The range and depth of the group...
    dimensionGroup: DimensionGroup

    # The fields that should be updated. At least one field must be specified. ...
    fields: str


class MergeCellsRequest(TypedDict, total=False):
    """Merges all cells in the range."""

    # How the cells should be merged.
    # Enum values:
    #   "MERGE_ALL": Create a single merge from the range
    #   "MERGE_COLUMNS": Create a merge for each column in the range
    #   "MERGE_ROWS": Create a merge for each row in the range
    mergeType: str

    # The range of cells to merge.
    range: GridRange


class UpdateSheetPropertiesRequest(TypedDict, total=False):
    """Updates properties of the sheet with the specified sheetId."""

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The properties to update.
    properties: SheetProperties


class PasteDataRequest(TypedDict, total=False):
    """Inserts data into the spreadsheet starting at the specified coordinate."""

    # The coordinate at which the data should start being inserted.
    coordinate: GridCoordinate

    # The data to insert.
    data: str

    # The delimiter in the data.
    delimiter: str

    # True if the data is HTML.
    html: bool

    # How the data should be pasted.
    # Enum values:
    #   "PASTE_NORMAL": Paste values, formulas, formats, and merges.
    #   "PASTE_VALUES": Paste the values ONLY without formats, formulas, or merges.
    #   "PASTE_FORMAT": Paste the format and data validation only.
    #   "PASTE_NO_BORDERS": Like `PASTE_NORMAL` but without borders.
    #   "PASTE_FORMULA": Paste the formulas only.
    #   "PASTE_DATA_VALIDATION": Paste the data validation only.
    #   "PASTE_CONDITIONAL_FORMATTING": Paste the conditional formatting rules only.
    type: str


class UpdateNamedRangeRequest(TypedDict, total=False):
    """Updates properties of the named range with the specified namedRangeId."""

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The named range to update with the new properties.
    namedRange: NamedRange


class DeleteDuplicatesRequest(TypedDict, total=False):
    """Removes rows within this range that contain values in the specified columns that are duplicates of values in any previous row. Rows with identical values but different letter cases, formatting, or formulas are considered to be duplicates. This request also removes duplicate rows hidden from view (for example, due to a filter). When removing duplicates, the first instance of each duplicate row scanning from the top downwards is kept in the resulting range. Content outside of the specified range isn't removed, and rows considered duplicates do not have to be adjacent to each other in the range."""

    # The columns in the range to analyze for duplicate values. If no columns a...
    comparisonColumns: list[DimensionRange]

    # The range to remove duplicates rows from.
    range: GridRange


class UpdateCellsRequest(TypedDict, total=False):
    """Updates all cells in a range with new data."""

    # The fields of CellData that should be updated. At least one field must be...
    fields: str

    # The range to write data to. If the data in rows does not cover the entire...
    range: GridRange

    # The data to write.
    rows: list[RowData]

    # The coordinate to start writing data at. Any number of rows and columns (...
    start: GridCoordinate


class DeleteConditionalFormatRuleRequest(TypedDict, total=False):
    """Deletes a conditional format rule at the given index. All subsequent rules' indexes are decremented."""

    # The zero-based index of the rule to be deleted.
    index: int

    # The sheet the rule is being deleted from.
    sheetId: int


class SetDataValidationRequest(TypedDict, total=False):
    """Sets a data validation rule to every cell in the range. To clear validation in a range, call this with no rule specified."""

    # Optional. If true, the data validation rule will be applied to the filter...
    filteredRowsIncluded: bool

    # The range the data validation rule should apply to.
    range: GridRange

    # The data validation rule to set on each cell in the range, or empty to cl...
    rule: DataValidationRule


class UpdateBordersRequest(TypedDict, total=False):
    """Updates the borders of a range. If a field is not set in the request, that means the border remains as-is. For example, with two subsequent UpdateBordersRequest: 1. range: A1:A5 `{ top: RED, bottom: WHITE }` 2. range: A1:A5 `{ left: BLUE }` That would result in A1:A5 having a borders of `{ top: RED, bottom: WHITE, left: BLUE }`. If you want to clear a border, explicitly set the style to NONE."""

    # The border to put at the bottom of the range.
    bottom: Border

    # The horizontal border to put within the range.
    innerHorizontal: Border

    # The vertical border to put within the range.
    innerVertical: Border

    # The border to put at the left of the range.
    left: Border

    # The range whose borders should be updated.
    range: GridRange

    # The border to put at the right of the range.
    right: Border

    # The border to put at the top of the range.
    top: Border


class CreateDeveloperMetadataRequest(TypedDict, total=False):
    """A request to create developer metadata."""

    # The developer metadata to create.
    developerMetadata: DeveloperMetadata


class TextToColumnsRequest(TypedDict, total=False):
    """Splits a column of text into multiple columns, based on a delimiter in each cell."""

    # The delimiter to use. Used only if delimiterType is CUSTOM.
    delimiter: str

    # The delimiter type to use.
    # Enum values:
    #   "DELIMITER_TYPE_UNSPECIFIED": Default value. This value must not be used.
    #   "COMMA": ","
    #   "SEMICOLON": ";"
    #   "PERIOD": "."
    #   "SPACE": " "
    #   "CUSTOM": A custom value as defined in delimiter.
    #   "AUTODETECT": Automatically detect columns.
    delimiterType: str

    # The source data range. This must span exactly one column.
    source: GridRange


class UpdateChartSpecRequest(TypedDict, total=False):
    """Updates a chart's specifications. (This does not move or resize a chart. To move or resize a chart, use UpdateEmbeddedObjectPositionRequest.)"""

    # The ID of the chart to update.
    chartId: int

    # The specification to apply to the chart.
    spec: ChartSpec


class DeleteDeveloperMetadataRequest(TypedDict, total=False):
    """A request to delete developer metadata."""

    # The data filter describing the criteria used to select which developer me...
    dataFilter: DataFilter


class InsertDimensionRequest(TypedDict, total=False):
    """Inserts rows or columns in a sheet at a particular index."""

    # Whether dimension properties should be extended from the dimensions befor...
    inheritFromBefore: bool

    # The dimensions to insert. Both the start and end indexes must be bounded.
    range: DimensionRange


class UnmergeCellsRequest(TypedDict, total=False):
    """Unmerges cells in the given range."""

    # The range within which all cells should be unmerged. If the range spans m...
    range: GridRange


class CutPasteRequest(TypedDict, total=False):
    """Moves data from the source to the destination."""

    # The top-left coordinate where the data should be pasted.
    destination: GridCoordinate

    # What kind of data to paste. All the source data will be cut, regardless o...
    # Enum values:
    #   "PASTE_NORMAL": Paste values, formulas, formats, and merges.
    #   "PASTE_VALUES": Paste the values ONLY without formats, formulas, or merges.
    #   "PASTE_FORMAT": Paste the format and data validation only.
    #   "PASTE_NO_BORDERS": Like `PASTE_NORMAL` but without borders.
    #   "PASTE_FORMULA": Paste the formulas only.
    #   "PASTE_DATA_VALIDATION": Paste the data validation only.
    #   "PASTE_CONDITIONAL_FORMATTING": Paste the conditional formatting rules only.
    pasteType: str

    # The source data to cut.
    source: GridRange


class DeleteProtectedRangeRequest(TypedDict, total=False):
    """Deletes the protected range with the given ID."""

    # The ID of the protected range to delete.
    protectedRangeId: int


class UpdateFilterViewRequest(TypedDict, total=False):
    """Updates properties of the filter view."""

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The new properties of the filter view.
    filter: FilterView


class DeleteNamedRangeRequest(TypedDict, total=False):
    """Removes the named range with the given ID from the spreadsheet."""

    # The ID of the named range to delete.
    namedRangeId: str


class RandomizeRangeRequest(TypedDict, total=False):
    """Randomizes the order of the rows in a range."""

    # The range to randomize.
    range: GridRange


class UpdateSpreadsheetPropertiesRequest(TypedDict, total=False):
    """Updates properties of a spreadsheet."""

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The properties to update.
    properties: SpreadsheetProperties


class DeleteFilterViewRequest(TypedDict, total=False):
    """Deletes a particular filter view."""

    # The ID of the filter to delete.
    filterId: int


class RepeatCellRequest(TypedDict, total=False):
    """Updates all cells in the range to the values in the given Cell object. Only the fields listed in the fields field are updated; others are unchanged. If writing a cell with a formula, the formula's ranges will automatically increment for each field in the range. For example, if writing a cell with formula `=A1` into range B2:C4, B2 would be `=A1`, B3 would be `=A2`, B4 would be `=A3`, C2 would be `=B1`, C3 would be `=B2`, C4 would be `=B3`. To keep the formula's ranges static, use the `$` indicator. For example, use the formula `=$A$1` to prevent both the row and the column from incrementing."""

    # The data to write.
    cell: CellData

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The range to repeat the cell in.
    range: GridRange


class TrimWhitespaceRequest(TypedDict, total=False):
    """Trims the whitespace (such as spaces, tabs, or new lines) in every cell in the specified range. This request removes all whitespace from the start and end of each cell's text, and reduces any subsequence of remaining whitespace characters to a single space. If the resulting trimmed text starts with a '+' or '=' character, the text remains as a string value and isn't interpreted as a formula."""

    # The range whose cells to trim.
    range: GridRange


class UpdateConditionalFormatRuleRequest(TypedDict, total=False):
    """Updates a conditional format rule at the given index, or moves a conditional format rule to another index."""

    # The zero-based index of the rule that should be replaced or moved.
    index: int

    # The zero-based new index the rule should end up at.
    newIndex: int

    # The rule that should replace the rule at the given index.
    rule: ConditionalFormatRule

    # The sheet of the rule to move. Required if new_index is set, unused other...
    sheetId: int


class CancelDataSourceRefreshRequest(TypedDict, total=False):
    """Cancels one or multiple refreshes of data source objects in the spreadsheet by the specified references. The request requires an additional `bigquery.readonly` OAuth scope if you are cancelling a refresh on a BigQuery data source."""

    # Reference to a DataSource. If specified, cancels all associated data sour...
    dataSourceId: str

    # Cancels all existing data source object refreshes for all data sources in...
    isAll: bool

    # References to data source objects whose refreshes are to be cancelled.
    references: DataSourceObjectReferences


class DeleteSheetRequest(TypedDict, total=False):
    """Deletes the requested sheet."""

    # The ID of the sheet to delete. If the sheet is of DATA_SOURCE type, the a...
    sheetId: int


class DeleteDimensionRequest(TypedDict, total=False):
    """Deletes the dimensions from the sheet."""

    # The dimensions to delete from the sheet.
    range: DimensionRange


class DeleteRangeRequest(TypedDict, total=False):
    """Deletes a range of cells, shifting other cells into the deleted area."""

    # The range of cells to delete.
    range: GridRange

    # The dimension from which deleted cells will be replaced with. If ROWS, ex...
    # Enum values:
    #   "DIMENSION_UNSPECIFIED": The default value, do not use.
    #   "ROWS": Operates on the rows of a sheet.
    #   "COLUMNS": Operates on the columns of a sheet.
    shiftDimension: str


class DuplicateFilterViewRequest(TypedDict, total=False):
    """Duplicates a particular filter view."""

    # The ID of the filter being duplicated.
    filterId: int


class DuplicateSheetRequest(TypedDict, total=False):
    """Duplicates the contents of a sheet."""

    # The zero-based index where the new sheet should be inserted. The index of...
    insertSheetIndex: int

    # If set, the ID of the new sheet. If not set, an ID is chosen. If set, the...
    newSheetId: int

    # The name of the new sheet. If empty, a new name is chosen for you.
    newSheetName: str

    # The sheet to duplicate. If the source sheet is of DATA_SOURCE type, its b...
    sourceSheetId: int


class UpdateSlicerSpecRequest(TypedDict, total=False):
    """Updates a slicer's specifications. (This does not move or resize a slicer. To move or resize a slicer use UpdateEmbeddedObjectPositionRequest."""

    # The fields that should be updated. At least one field must be specified. ...
    fields: str

    # The id of the slicer to update.
    slicerId: int

    # The specification to apply to the slicer.
    spec: SlicerSpec


class FindReplaceRequest(TypedDict, total=False):
    """Finds and replaces data in cells over a range, sheet, or all sheets."""

    # True to find/replace over all sheets.
    allSheets: bool

    # The value to search.
    find: str

    # True if the search should include cells with formulas. False to skip cell...
    includeFormulas: bool

    # True if the search is case sensitive.
    matchCase: bool

    # True if the find value should match the entire cell.
    matchEntireCell: bool

    # The range to find/replace over.
    range: GridRange

    # The value to use as the replacement.
    replacement: str

    # True if the find value is a regex. The regular expression and replacement...
    searchByRegex: bool

    # The sheet to find/replace over.
    sheetId: int


class Request(TypedDict, total=False):
    """A single kind of update to apply to a spreadsheet."""

    # Adds a new banded range
    addBanding: AddBandingRequest

    # Adds a chart.
    addChart: AddChartRequest

    # Adds a new conditional format rule.
    addConditionalFormatRule: AddConditionalFormatRuleRequest

    # Adds a data source.
    addDataSource: AddDataSourceRequest

    # Creates a group over the specified range.
    addDimensionGroup: AddDimensionGroupRequest

    # Adds a filter view.
    addFilterView: AddFilterViewRequest

    # Adds a named range.
    addNamedRange: AddNamedRangeRequest

    # Adds a protected range.
    addProtectedRange: AddProtectedRangeRequest

    # Adds a sheet.
    addSheet: AddSheetRequest

    # Adds a slicer.
    addSlicer: AddSlicerRequest

    # Adds a table.
    addTable: AddTableRequest

    # Appends cells after the last row with data in a sheet.
    appendCells: AppendCellsRequest

    # Appends dimensions to the end of a sheet.
    appendDimension: AppendDimensionRequest

    # Automatically fills in more data based on existing data.
    autoFill: AutoFillRequest

    # Automatically resizes one or more dimensions based on the contents of the...
    autoResizeDimensions: AutoResizeDimensionsRequest

    # Cancels refreshes of one or multiple data sources and associated dbobjects.
    cancelDataSourceRefresh: CancelDataSourceRefreshRequest

    # Clears the basic filter on a sheet.
    clearBasicFilter: ClearBasicFilterRequest

    # Copies data from one area and pastes it to another.
    copyPaste: CopyPasteRequest

    # Creates new developer metadata
    createDeveloperMetadata: CreateDeveloperMetadataRequest

    # Cuts data from one area and pastes it to another.
    cutPaste: CutPasteRequest

    # Removes a banded range
    deleteBanding: DeleteBandingRequest

    # Deletes an existing conditional format rule.
    deleteConditionalFormatRule: DeleteConditionalFormatRuleRequest

    # Deletes a data source.
    deleteDataSource: DeleteDataSourceRequest

    # Deletes developer metadata
    deleteDeveloperMetadata: DeleteDeveloperMetadataRequest

    # Deletes rows or columns in a sheet.
    deleteDimension: DeleteDimensionRequest

    # Deletes a group over the specified range.
    deleteDimensionGroup: DeleteDimensionGroupRequest

    # Removes rows containing duplicate values in specified columns of a cell r...
    deleteDuplicates: DeleteDuplicatesRequest

    # Deletes an embedded object (e.g, chart, image) in a sheet.
    deleteEmbeddedObject: DeleteEmbeddedObjectRequest

    # Deletes a filter view from a sheet.
    deleteFilterView: DeleteFilterViewRequest

    # Deletes a named range.
    deleteNamedRange: DeleteNamedRangeRequest

    # Deletes a protected range.
    deleteProtectedRange: DeleteProtectedRangeRequest

    # Deletes a range of cells from a sheet, shifting the remaining cells.
    deleteRange: DeleteRangeRequest

    # Deletes a sheet.
    deleteSheet: DeleteSheetRequest

    # A request for deleting a table.
    deleteTable: DeleteTableRequest

    # Duplicates a filter view.
    duplicateFilterView: DuplicateFilterViewRequest

    # Duplicates a sheet.
    duplicateSheet: DuplicateSheetRequest

    # Finds and replaces occurrences of some text with other text.
    findReplace: FindReplaceRequest

    # Inserts new rows or columns in a sheet.
    insertDimension: InsertDimensionRequest

    # Inserts new cells in a sheet, shifting the existing cells.
    insertRange: InsertRangeRequest

    # Merges cells together.
    mergeCells: MergeCellsRequest

    # Moves rows or columns to another location in a sheet.
    moveDimension: MoveDimensionRequest

    # Pastes data (HTML or delimited) into a sheet.
    pasteData: PasteDataRequest

    # Randomizes the order of the rows in a range.
    randomizeRange: RandomizeRangeRequest

    # Refreshes one or multiple data sources and associated dbobjects.
    refreshDataSource: RefreshDataSourceRequest

    # Repeats a single cell across a range.
    repeatCell: RepeatCellRequest

    # Sets the basic filter on a sheet.
    setBasicFilter: SetBasicFilterRequest

    # Sets data validation for one or more cells.
    setDataValidation: SetDataValidationRequest

    # Sorts data in a range.
    sortRange: SortRangeRequest

    # Converts a column of text into many columns of text.
    textToColumns: TextToColumnsRequest

    # Trims cells of whitespace (such as spaces, tabs, or new lines).
    trimWhitespace: TrimWhitespaceRequest

    # Unmerges merged cells.
    unmergeCells: UnmergeCellsRequest

    # Updates a banded range
    updateBanding: UpdateBandingRequest

    # Updates the borders in a range of cells.
    updateBorders: UpdateBordersRequest

    # Updates many cells at once.
    updateCells: UpdateCellsRequest

    # Updates a chart's specifications.
    updateChartSpec: UpdateChartSpecRequest

    # Updates an existing conditional format rule.
    updateConditionalFormatRule: UpdateConditionalFormatRuleRequest

    # Updates a data source.
    updateDataSource: UpdateDataSourceRequest

    # Updates an existing developer metadata entry
    updateDeveloperMetadata: UpdateDeveloperMetadataRequest

    # Updates the state of the specified group.
    updateDimensionGroup: UpdateDimensionGroupRequest

    # Updates dimensions' properties.
    updateDimensionProperties: UpdateDimensionPropertiesRequest

    # Updates an embedded object's border.
    updateEmbeddedObjectBorder: UpdateEmbeddedObjectBorderRequest

    # Updates an embedded object's (e.g. chart, image) position.
    updateEmbeddedObjectPosition: UpdateEmbeddedObjectPositionRequest

    # Updates the properties of a filter view.
    updateFilterView: UpdateFilterViewRequest

    # Updates a named range.
    updateNamedRange: UpdateNamedRangeRequest

    # Updates a protected range.
    updateProtectedRange: UpdateProtectedRangeRequest

    # Updates a sheet's properties.
    updateSheetProperties: UpdateSheetPropertiesRequest

    # Updates a slicer's specifications.
    updateSlicerSpec: UpdateSlicerSpecRequest

    # Updates the spreadsheet's properties.
    updateSpreadsheetProperties: UpdateSpreadsheetPropertiesRequest

    # Updates a table.
    updateTable: UpdateTableRequest


class BatchUpdateSpreadsheetRequest(TypedDict, total=False):
    """The request for updating any aspect of a spreadsheet."""

    # Determines if the update response should include the spreadsheet resource.
    includeSpreadsheetInResponse: bool

    # A list of updates to apply to the spreadsheet. Requests will be applied i...
    requests: list[Request]

    # True if grid data should be returned. Meaningful only if include_spreadsh...
    responseIncludeGridData: bool

    # Limits the ranges included in the response spreadsheet. Meaningful only i...
    responseRanges: list[str]


class BatchUpdateValuesByDataFilterRequest(TypedDict, total=False):
    """The request for updating more than one range of values in a spreadsheet."""

    # The new values to apply to the spreadsheet. If more than one range is mat...
    data: list[DataFilterValueRange]

    # Determines if the update response should include the values of the cells ...
    includeValuesInResponse: bool

    # Determines how dates, times, and durations in the response should be rend...
    # Enum values:
    #   "SERIAL_NUMBER": Instructs date, time, datetime, and duration fields to be...
    #   "FORMATTED_STRING": Instructs date, time, datetime, and duration fields to be...
    responseDateTimeRenderOption: str

    # Determines how values in the response should be rendered. The default ren...
    # Enum values:
    #   "FORMATTED_VALUE": Values will be calculated & formatted in the response acc...
    #   "UNFORMATTED_VALUE": Values will be calculated, but not formatted in the reply...
    #   "FORMULA": Values will not be calculated. The reply will include the...
    responseValueRenderOption: str

    # How the input data should be interpreted.
    # Enum values:
    #   "INPUT_VALUE_OPTION_UNSPECIFIED": Default input value. This value must not be used.
    #   "RAW": The values the user has entered will not be parsed and wi...
    #   "USER_ENTERED": The values will be parsed as if the user typed them into ...
    valueInputOption: str


class BatchUpdateValuesRequest(TypedDict, total=False):
    """The request for updating more than one range of values in a spreadsheet."""

    # The new values to apply to the spreadsheet.
    data: list[ValueRange]

    # Determines if the update response should include the values of the cells ...
    includeValuesInResponse: bool

    # Determines how dates, times, and durations in the response should be rend...
    # Enum values:
    #   "SERIAL_NUMBER": Instructs date, time, datetime, and duration fields to be...
    #   "FORMATTED_STRING": Instructs date, time, datetime, and duration fields to be...
    responseDateTimeRenderOption: str

    # Determines how values in the response should be rendered. The default ren...
    # Enum values:
    #   "FORMATTED_VALUE": Values will be calculated & formatted in the response acc...
    #   "UNFORMATTED_VALUE": Values will be calculated, but not formatted in the reply...
    #   "FORMULA": Values will not be calculated. The reply will include the...
    responseValueRenderOption: str

    # How the input data should be interpreted.
    # Enum values:
    #   "INPUT_VALUE_OPTION_UNSPECIFIED": Default input value. This value must not be used.
    #   "RAW": The values the user has entered will not be parsed and wi...
    #   "USER_ENTERED": The values will be parsed as if the user typed them into ...
    valueInputOption: str


class ClearValuesRequest(TypedDict, total=False):
    """The request for clearing a range of values in a spreadsheet."""

    pass


class CopySheetToAnotherSpreadsheetRequest(TypedDict, total=False):
    """The request to copy a sheet across spreadsheets."""

    # The ID of the spreadsheet to copy the sheet to.
    destinationSpreadsheetId: str


class GetSpreadsheetByDataFilterRequest(TypedDict, total=False):
    """The request for retrieving a Spreadsheet."""

    # The DataFilters used to select which ranges to retrieve from the spreadsh...
    dataFilters: list[DataFilter]

    # True if tables should be excluded in the banded ranges. False if not set.
    excludeTablesInBandedRanges: bool

    # True if grid data should be returned. This parameter is ignored if a fiel...
    includeGridData: bool


class SearchDeveloperMetadataRequest(TypedDict, total=False):
    """A request to retrieve all developer metadata matching the set of specified criteria."""

    # The data filters describing the criteria used to determine which Develope...
    dataFilters: list[DataFilter]


# =============================================================================
# Responses
# =============================================================================


class AddBandingResponse(TypedDict, total=False):
    """The result of adding a banded range."""

    # The banded range that was added.
    bandedRange: BandedRange


class AddChartResponse(TypedDict, total=False):
    """The result of adding a chart to a spreadsheet."""

    # The newly added chart.
    chart: EmbeddedChart


class AddDataSourceResponse(TypedDict, total=False):
    """The result of adding a data source."""

    # The data execution status.
    dataExecutionStatus: DataExecutionStatus

    # The data source that was created.
    dataSource: DataSource


class AddDimensionGroupResponse(TypedDict, total=False):
    """The result of adding a group."""

    # All groups of a dimension after adding a group to that dimension.
    dimensionGroups: list[DimensionGroup]


class AddFilterViewResponse(TypedDict, total=False):
    """The result of adding a filter view."""

    # The newly added filter view.
    filter: FilterView


class AddNamedRangeResponse(TypedDict, total=False):
    """The result of adding a named range."""

    # The named range to add.
    namedRange: NamedRange


class AddProtectedRangeResponse(TypedDict, total=False):
    """The result of adding a new protected range."""

    # The newly added protected range.
    protectedRange: ProtectedRange


class AddSheetResponse(TypedDict, total=False):
    """The result of adding a sheet."""

    # The properties of the newly added sheet.
    properties: SheetProperties


class AddSlicerResponse(TypedDict, total=False):
    """The result of adding a slicer to a spreadsheet."""

    # The newly added slicer.
    slicer: Slicer


class AddTableResponse(TypedDict, total=False):
    """The result of adding a table."""

    # Output only. The table that was added.
    # Read-only field
    table: Table


class UpdateValuesResponse(TypedDict, total=False):
    """The response when updating a range of values in a spreadsheet."""

    # The spreadsheet the updates were applied to.
    spreadsheetId: str

    # The number of cells updated.
    updatedCells: int

    # The number of columns where at least one cell in the column was updated.
    updatedColumns: int

    # The values of the cells after updates were applied. This is only included...
    updatedData: ValueRange

    # The range (in A1 notation) that updates were applied to.
    updatedRange: str

    # The number of rows where at least one cell in the row was updated.
    updatedRows: int


class AppendValuesResponse(TypedDict, total=False):
    """The response when updating a range of values in a spreadsheet."""

    # The spreadsheet the updates were applied to.
    spreadsheetId: str

    # The range (in A1 notation) of the table that values are being appended to...
    tableRange: str

    # Information about the updates that were applied.
    updates: UpdateValuesResponse


class BatchClearValuesByDataFilterResponse(TypedDict, total=False):
    """The response when clearing a range of values selected with DataFilters in a spreadsheet."""

    # The ranges that were cleared, in [A1 notation](https://developers.google....
    clearedRanges: list[str]

    # The spreadsheet the updates were applied to.
    spreadsheetId: str


class BatchClearValuesResponse(TypedDict, total=False):
    """The response when clearing a range of values in a spreadsheet."""

    # The ranges that were cleared, in A1 notation. If the requests are for an ...
    clearedRanges: list[str]

    # The spreadsheet the updates were applied to.
    spreadsheetId: str


class BatchGetValuesByDataFilterResponse(TypedDict, total=False):
    """The response when retrieving more than one range of values in a spreadsheet selected by DataFilters."""

    # The ID of the spreadsheet the data was retrieved from.
    spreadsheetId: str

    # The requested values with the list of data filters that matched them.
    valueRanges: list[MatchedValueRange]


class BatchGetValuesResponse(TypedDict, total=False):
    """The response when retrieving more than one range of values in a spreadsheet."""

    # The ID of the spreadsheet the data was retrieved from.
    spreadsheetId: str

    # The requested values. The order of the ValueRanges is the same as the ord...
    valueRanges: list[ValueRange]


class UpdateDeveloperMetadataResponse(TypedDict, total=False):
    """The response from updating developer metadata."""

    # The updated developer metadata.
    developerMetadata: list[DeveloperMetadata]


class UpdateEmbeddedObjectPositionResponse(TypedDict, total=False):
    """The result of updating an embedded object's position."""

    # The new position of the embedded object.
    position: EmbeddedObjectPosition


class CreateDeveloperMetadataResponse(TypedDict, total=False):
    """The response from creating developer metadata."""

    # The developer metadata that was created.
    developerMetadata: DeveloperMetadata


class FindReplaceResponse(TypedDict, total=False):
    """The result of the find/replace."""

    # The number of formula cells changed.
    formulasChanged: int

    # The number of occurrences (possibly multiple within a cell) changed. For ...
    occurrencesChanged: int

    # The number of rows changed.
    rowsChanged: int

    # The number of sheets changed.
    sheetsChanged: int

    # The number of non-formula cells changed.
    valuesChanged: int


class UpdateConditionalFormatRuleResponse(TypedDict, total=False):
    """The result of updating a conditional format rule."""

    # The index of the new rule.
    newIndex: int

    # The new rule that replaced the old rule (if replacing), or the rule that ...
    newRule: ConditionalFormatRule

    # The old index of the rule. Not set if a rule was replaced (because it is ...
    oldIndex: int

    # The old (deleted) rule. Not set if a rule was moved (because it is the sa...
    oldRule: ConditionalFormatRule


class UpdateDataSourceResponse(TypedDict, total=False):
    """The response from updating data source."""

    # The data execution status.
    dataExecutionStatus: DataExecutionStatus

    # The updated data source.
    dataSource: DataSource


class DeleteConditionalFormatRuleResponse(TypedDict, total=False):
    """The result of deleting a conditional format rule."""

    # The rule that was deleted.
    rule: ConditionalFormatRule


class DeleteDuplicatesResponse(TypedDict, total=False):
    """The result of removing duplicates in a range."""

    # The number of duplicate rows removed.
    duplicatesRemovedCount: int


class DeleteDeveloperMetadataResponse(TypedDict, total=False):
    """The response from deleting developer metadata."""

    # The metadata that was deleted.
    deletedDeveloperMetadata: list[DeveloperMetadata]


class DuplicateSheetResponse(TypedDict, total=False):
    """The result of duplicating a sheet."""

    # The properties of the duplicate sheet.
    properties: SheetProperties


class RefreshDataSourceResponse(TypedDict, total=False):
    """The response from refreshing one or multiple data source objects."""

    # All the refresh status for the data source object references specified in...
    statuses: list[RefreshDataSourceObjectExecutionStatus]


class TrimWhitespaceResponse(TypedDict, total=False):
    """The result of trimming whitespace in cells."""

    # The number of cells that were trimmed of whitespace.
    cellsChangedCount: int


class DeleteDimensionGroupResponse(TypedDict, total=False):
    """The result of deleting a group."""

    # All groups of a dimension after deleting a group from that dimension.
    dimensionGroups: list[DimensionGroup]


class DuplicateFilterViewResponse(TypedDict, total=False):
    """The result of a filter view being duplicated."""

    # The newly created filter.
    filter: FilterView


class CancelDataSourceRefreshResponse(TypedDict, total=False):
    """The response from cancelling one or multiple data source object refreshes."""

    # The cancellation statuses of refreshes of all data source objects specifi...
    statuses: list[CancelDataSourceRefreshStatus]


class Response(TypedDict, total=False):
    """A single response from an update."""

    # A reply from adding a banded range.
    addBanding: AddBandingResponse

    # A reply from adding a chart.
    addChart: AddChartResponse

    # A reply from adding a data source.
    addDataSource: AddDataSourceResponse

    # A reply from adding a dimension group.
    addDimensionGroup: AddDimensionGroupResponse

    # A reply from adding a filter view.
    addFilterView: AddFilterViewResponse

    # A reply from adding a named range.
    addNamedRange: AddNamedRangeResponse

    # A reply from adding a protected range.
    addProtectedRange: AddProtectedRangeResponse

    # A reply from adding a sheet.
    addSheet: AddSheetResponse

    # A reply from adding a slicer.
    addSlicer: AddSlicerResponse

    # A reply from adding a table.
    addTable: AddTableResponse

    # A reply from cancelling data source object refreshes.
    cancelDataSourceRefresh: CancelDataSourceRefreshResponse

    # A reply from creating a developer metadata entry.
    createDeveloperMetadata: CreateDeveloperMetadataResponse

    # A reply from deleting a conditional format rule.
    deleteConditionalFormatRule: DeleteConditionalFormatRuleResponse

    # A reply from deleting a developer metadata entry.
    deleteDeveloperMetadata: DeleteDeveloperMetadataResponse

    # A reply from deleting a dimension group.
    deleteDimensionGroup: DeleteDimensionGroupResponse

    # A reply from removing rows containing duplicate values.
    deleteDuplicates: DeleteDuplicatesResponse

    # A reply from duplicating a filter view.
    duplicateFilterView: DuplicateFilterViewResponse

    # A reply from duplicating a sheet.
    duplicateSheet: DuplicateSheetResponse

    # A reply from doing a find/replace.
    findReplace: FindReplaceResponse

    # A reply from refreshing data source objects.
    refreshDataSource: RefreshDataSourceResponse

    # A reply from trimming whitespace.
    trimWhitespace: TrimWhitespaceResponse

    # A reply from updating a conditional format rule.
    updateConditionalFormatRule: UpdateConditionalFormatRuleResponse

    # A reply from updating a data source.
    updateDataSource: UpdateDataSourceResponse

    # A reply from updating a developer metadata entry.
    updateDeveloperMetadata: UpdateDeveloperMetadataResponse

    # A reply from updating an embedded object's position.
    updateEmbeddedObjectPosition: UpdateEmbeddedObjectPositionResponse


class BatchUpdateSpreadsheetResponse(TypedDict, total=False):
    """The reply for batch updating a spreadsheet."""

    # The reply of the updates. This maps 1:1 with the updates, although replie...
    replies: list[Response]

    # The spreadsheet the updates were applied to.
    spreadsheetId: str

    # The spreadsheet after updates were applied. This is only set if BatchUpda...
    updatedSpreadsheet: Spreadsheet


class UpdateValuesByDataFilterResponse(TypedDict, total=False):
    """The response when updating a range of values by a data filter in a spreadsheet."""

    # The data filter that selected the range that was updated.
    dataFilter: DataFilter

    # The number of cells updated.
    updatedCells: int

    # The number of columns where at least one cell in the column was updated.
    updatedColumns: int

    # The values of the cells in the range matched by the dataFilter after all ...
    updatedData: ValueRange

    # The range (in [A1 notation](https://developers.google.com/workspace/sheet...
    updatedRange: str

    # The number of rows where at least one cell in the row was updated.
    updatedRows: int


class BatchUpdateValuesByDataFilterResponse(TypedDict, total=False):
    """The response when updating a range of values in a spreadsheet."""

    # The response for each range updated.
    responses: list[UpdateValuesByDataFilterResponse]

    # The spreadsheet the updates were applied to.
    spreadsheetId: str

    # The total number of cells updated.
    totalUpdatedCells: int

    # The total number of columns where at least one cell in the column was upd...
    totalUpdatedColumns: int

    # The total number of rows where at least one cell in the row was updated.
    totalUpdatedRows: int

    # The total number of sheets where at least one cell in the sheet was updated.
    totalUpdatedSheets: int


class BatchUpdateValuesResponse(TypedDict, total=False):
    """The response when updating a range of values in a spreadsheet."""

    # One UpdateValuesResponse per requested range, in the same order as the re...
    responses: list[UpdateValuesResponse]

    # The spreadsheet the updates were applied to.
    spreadsheetId: str

    # The total number of cells updated.
    totalUpdatedCells: int

    # The total number of columns where at least one cell in the column was upd...
    totalUpdatedColumns: int

    # The total number of rows where at least one cell in the row was updated.
    totalUpdatedRows: int

    # The total number of sheets where at least one cell in the sheet was updated.
    totalUpdatedSheets: int


class ClearValuesResponse(TypedDict, total=False):
    """The response when clearing a range of values in a spreadsheet."""

    # The range (in A1 notation) that was cleared. (If the request was for an u...
    clearedRange: str

    # The spreadsheet the updates were applied to.
    spreadsheetId: str


class SearchDeveloperMetadataResponse(TypedDict, total=False):
    """A reply to a developer metadata search request."""

    # The metadata matching the criteria of the search request.
    matchedDeveloperMetadata: list[MatchedDeveloperMetadata]
