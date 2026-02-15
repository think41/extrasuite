"""Google Docs API types - auto-generated from discovery.json.

Do not edit manually. Regenerate with:
    cd extradoc
    uv run python scripts/generate_api_types.py
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of StrEnum for Python 3.10."""

        pass


from pydantic import BaseModel, ConfigDict, Field


class AutoTextType(StrEnum):
    """The type of this auto text."""

    TYPE_UNSPECIFIED = "TYPE_UNSPECIFIED"
    PAGE_NUMBER = "PAGE_NUMBER"
    PAGE_COUNT = "PAGE_COUNT"


class CreateFooterRequestType(StrEnum):
    """The type of footer to create."""

    HEADER_FOOTER_TYPE_UNSPECIFIED = "HEADER_FOOTER_TYPE_UNSPECIFIED"
    DEFAULT = "DEFAULT"


class CreateParagraphBulletsRequestBulletPreset(StrEnum):
    """The kinds of bullet glyphs to be used."""

    BULLET_GLYPH_PRESET_UNSPECIFIED = "BULLET_GLYPH_PRESET_UNSPECIFIED"
    BULLET_DISC_CIRCLE_SQUARE = "BULLET_DISC_CIRCLE_SQUARE"
    BULLET_DIAMONDX_ARROW3D_SQUARE = "BULLET_DIAMONDX_ARROW3D_SQUARE"
    BULLET_CHECKBOX = "BULLET_CHECKBOX"
    BULLET_ARROW_DIAMOND_DISC = "BULLET_ARROW_DIAMOND_DISC"
    BULLET_STAR_CIRCLE_SQUARE = "BULLET_STAR_CIRCLE_SQUARE"
    BULLET_ARROW3D_CIRCLE_SQUARE = "BULLET_ARROW3D_CIRCLE_SQUARE"
    BULLET_LEFTTRIANGLE_DIAMOND_DISC = "BULLET_LEFTTRIANGLE_DIAMOND_DISC"
    BULLET_DIAMONDX_HOLLOWDIAMOND_SQUARE = "BULLET_DIAMONDX_HOLLOWDIAMOND_SQUARE"
    BULLET_DIAMOND_CIRCLE_SQUARE = "BULLET_DIAMOND_CIRCLE_SQUARE"
    NUMBERED_DECIMAL_ALPHA_ROMAN = "NUMBERED_DECIMAL_ALPHA_ROMAN"
    NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS = "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS"
    NUMBERED_DECIMAL_NESTED = "NUMBERED_DECIMAL_NESTED"
    NUMBERED_UPPERALPHA_ALPHA_ROMAN = "NUMBERED_UPPERALPHA_ALPHA_ROMAN"
    NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL = "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL"
    NUMBERED_ZERODECIMAL_ALPHA_ROMAN = "NUMBERED_ZERODECIMAL_ALPHA_ROMAN"


class DateElementPropertiesDateFormat(StrEnum):
    """Determines how the date part of the DateElement will be displayed in the docu..."""

    DATE_FORMAT_UNSPECIFIED = "DATE_FORMAT_UNSPECIFIED"
    DATE_FORMAT_CUSTOM = "DATE_FORMAT_CUSTOM"
    DATE_FORMAT_MONTH_DAY_ABBREVIATED = "DATE_FORMAT_MONTH_DAY_ABBREVIATED"
    DATE_FORMAT_MONTH_DAY_FULL = "DATE_FORMAT_MONTH_DAY_FULL"
    DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED = "DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"
    DATE_FORMAT_ISO8601 = "DATE_FORMAT_ISO8601"


class DateElementPropertiesTimeFormat(StrEnum):
    """Determines how the time part of the DateElement will be displayed in the docu..."""

    TIME_FORMAT_UNSPECIFIED = "TIME_FORMAT_UNSPECIFIED"
    TIME_FORMAT_DISABLED = "TIME_FORMAT_DISABLED"
    TIME_FORMAT_HOUR_MINUTE = "TIME_FORMAT_HOUR_MINUTE"
    TIME_FORMAT_HOUR_MINUTE_TIMEZONE = "TIME_FORMAT_HOUR_MINUTE_TIMEZONE"


class DimensionUnit(StrEnum):
    """The units for magnitude."""

    UNIT_UNSPECIFIED = "UNIT_UNSPECIFIED"
    PT = "PT"


class DocumentFormatDocumentMode(StrEnum):
    """Whether the document has pages or is pageless."""

    DOCUMENT_MODE_UNSPECIFIED = "DOCUMENT_MODE_UNSPECIFIED"
    PAGES = "PAGES"
    PAGELESS = "PAGELESS"


class DocumentSuggestionsViewMode(StrEnum):
    """Output only."""

    DEFAULT_FOR_CURRENT_ACCESS = "DEFAULT_FOR_CURRENT_ACCESS"
    SUGGESTIONS_INLINE = "SUGGESTIONS_INLINE"
    PREVIEW_SUGGESTIONS_ACCEPTED = "PREVIEW_SUGGESTIONS_ACCEPTED"
    PREVIEW_WITHOUT_SUGGESTIONS = "PREVIEW_WITHOUT_SUGGESTIONS"


class EmbeddedObjectBorderDashStyle(StrEnum):
    """The dash style of the border."""

    DASH_STYLE_UNSPECIFIED = "DASH_STYLE_UNSPECIFIED"
    SOLID = "SOLID"
    DOT = "DOT"
    DASH = "DASH"


class EmbeddedObjectBorderPropertyState(StrEnum):
    """The property state of the border property."""

    RENDERED = "RENDERED"
    NOT_RENDERED = "NOT_RENDERED"


class InsertSectionBreakRequestSectionType(StrEnum):
    """The type of section to insert."""

    SECTION_TYPE_UNSPECIFIED = "SECTION_TYPE_UNSPECIFIED"
    CONTINUOUS = "CONTINUOUS"
    NEXT_PAGE = "NEXT_PAGE"


class NestingLevelBulletAlignment(StrEnum):
    """The alignment of the bullet within the space allotted for rendering the bullet."""

    BULLET_ALIGNMENT_UNSPECIFIED = "BULLET_ALIGNMENT_UNSPECIFIED"
    START = "START"
    CENTER = "CENTER"
    END = "END"


class NestingLevelGlyphType(StrEnum):
    """The type of glyph used by bullets when paragraphs at this level of nesting is..."""

    GLYPH_TYPE_UNSPECIFIED = "GLYPH_TYPE_UNSPECIFIED"
    NONE = "NONE"
    DECIMAL = "DECIMAL"
    ZERO_DECIMAL = "ZERO_DECIMAL"
    UPPER_ALPHA = "UPPER_ALPHA"
    ALPHA = "ALPHA"
    UPPER_ROMAN = "UPPER_ROMAN"
    ROMAN = "ROMAN"


class ParagraphStyleAlignment(StrEnum):
    """The text alignment for this paragraph."""

    ALIGNMENT_UNSPECIFIED = "ALIGNMENT_UNSPECIFIED"
    START = "START"
    CENTER = "CENTER"
    END = "END"
    JUSTIFIED = "JUSTIFIED"


class ParagraphStyleDirection(StrEnum):
    """The text direction of this paragraph."""

    CONTENT_DIRECTION_UNSPECIFIED = "CONTENT_DIRECTION_UNSPECIFIED"
    LEFT_TO_RIGHT = "LEFT_TO_RIGHT"
    RIGHT_TO_LEFT = "RIGHT_TO_LEFT"


class ParagraphStyleNamedStyleType(StrEnum):
    """The named style type of the paragraph."""

    NAMED_STYLE_TYPE_UNSPECIFIED = "NAMED_STYLE_TYPE_UNSPECIFIED"
    NORMAL_TEXT = "NORMAL_TEXT"
    TITLE = "TITLE"
    SUBTITLE = "SUBTITLE"
    HEADING_1 = "HEADING_1"
    HEADING_2 = "HEADING_2"
    HEADING_3 = "HEADING_3"
    HEADING_4 = "HEADING_4"
    HEADING_5 = "HEADING_5"
    HEADING_6 = "HEADING_6"


class ParagraphStyleSpacingMode(StrEnum):
    """The spacing mode for the paragraph."""

    SPACING_MODE_UNSPECIFIED = "SPACING_MODE_UNSPECIFIED"
    NEVER_COLLAPSE = "NEVER_COLLAPSE"
    COLLAPSE_LISTS = "COLLAPSE_LISTS"


class PositionedObjectPositioningLayout(StrEnum):
    """The layout of this positioned object."""

    POSITIONED_OBJECT_LAYOUT_UNSPECIFIED = "POSITIONED_OBJECT_LAYOUT_UNSPECIFIED"
    WRAP_TEXT = "WRAP_TEXT"
    BREAK_LEFT = "BREAK_LEFT"
    BREAK_RIGHT = "BREAK_RIGHT"
    BREAK_LEFT_RIGHT = "BREAK_LEFT_RIGHT"
    IN_FRONT_OF_TEXT = "IN_FRONT_OF_TEXT"
    BEHIND_TEXT = "BEHIND_TEXT"


class ReplaceImageRequestImageReplaceMethod(StrEnum):
    """The replacement method."""

    IMAGE_REPLACE_METHOD_UNSPECIFIED = "IMAGE_REPLACE_METHOD_UNSPECIFIED"
    CENTER_CROP = "CENTER_CROP"


class SectionStyleColumnSeparatorStyle(StrEnum):
    """The style of column separators."""

    COLUMN_SEPARATOR_STYLE_UNSPECIFIED = "COLUMN_SEPARATOR_STYLE_UNSPECIFIED"
    NONE = "NONE"
    BETWEEN_EACH_COLUMN = "BETWEEN_EACH_COLUMN"


class TabStopAlignment(StrEnum):
    """The alignment of this tab stop."""

    TAB_STOP_ALIGNMENT_UNSPECIFIED = "TAB_STOP_ALIGNMENT_UNSPECIFIED"
    START = "START"
    CENTER = "CENTER"
    END = "END"


class TableCellStyleContentAlignment(StrEnum):
    """The alignment of the content in the table cell."""

    CONTENT_ALIGNMENT_UNSPECIFIED = "CONTENT_ALIGNMENT_UNSPECIFIED"
    CONTENT_ALIGNMENT_UNSUPPORTED = "CONTENT_ALIGNMENT_UNSUPPORTED"
    TOP = "TOP"
    MIDDLE = "MIDDLE"
    BOTTOM = "BOTTOM"


class TableColumnPropertiesWidthType(StrEnum):
    """The width type of the column."""

    WIDTH_TYPE_UNSPECIFIED = "WIDTH_TYPE_UNSPECIFIED"
    EVENLY_DISTRIBUTED = "EVENLY_DISTRIBUTED"
    FIXED_WIDTH = "FIXED_WIDTH"


class TextStyleBaselineOffset(StrEnum):
    """The text's vertical offset from its normal position."""

    BASELINE_OFFSET_UNSPECIFIED = "BASELINE_OFFSET_UNSPECIFIED"
    NONE = "NONE"
    SUPERSCRIPT = "SUPERSCRIPT"
    SUBSCRIPT = "SUBSCRIPT"


class BackgroundSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base Background have been changed in this suggestion. For any field set to true, the Backgound has a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color_suggested: bool | None = Field(
        None, alias="backgroundColorSuggested"
    )


class BookmarkLink(BaseModel):
    """A reference to a bookmark in this document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str | None = Field(None)
    tab_id: str | None = Field(None, alias="tabId")


class CreateFooterResponse(BaseModel):
    """The result of creating a footer."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    footer_id: str | None = Field(None, alias="footerId")


class CreateFootnoteResponse(BaseModel):
    """The result of creating a footnote."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    footnote_id: str | None = Field(None, alias="footnoteId")


class CreateHeaderResponse(BaseModel):
    """The result of creating a header."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    header_id: str | None = Field(None, alias="headerId")


class CreateNamedRangeResponse(BaseModel):
    """The result of creating a named range."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    named_range_id: str | None = Field(None, alias="namedRangeId")


class CropProperties(BaseModel):
    """The crop properties of an image. The crop rectangle is represented using fractional offsets from the original content's 4 edges. - If the offset is in the interval (0, 1), the corresponding edge of crop rectangle is positioned inside of the image's original bounding rectangle. - If the offset is negative or greater than 1, the corresponding edge of crop rectangle is positioned outside of the image's original bounding rectangle. - If all offsets and rotation angles are 0, the image is not cropped."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    angle: float | None = Field(None)
    offset_bottom: float | None = Field(None, alias="offsetBottom")
    offset_left: float | None = Field(None, alias="offsetLeft")
    offset_right: float | None = Field(None, alias="offsetRight")
    offset_top: float | None = Field(None, alias="offsetTop")


class CropPropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base CropProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    angle_suggested: bool | None = Field(None, alias="angleSuggested")
    offset_bottom_suggested: bool | None = Field(None, alias="offsetBottomSuggested")
    offset_left_suggested: bool | None = Field(None, alias="offsetLeftSuggested")
    offset_right_suggested: bool | None = Field(None, alias="offsetRightSuggested")
    offset_top_suggested: bool | None = Field(None, alias="offsetTopSuggested")


class DateElementProperties(BaseModel):
    """Properties of a DateElement."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date_format: DateElementPropertiesDateFormat | None = Field(
        None, alias="dateFormat"
    )
    display_text: str | None = Field(None, alias="displayText")
    locale: str | None = Field(None)
    time_format: DateElementPropertiesTimeFormat | None = Field(
        None, alias="timeFormat"
    )
    time_zone_id: str | None = Field(None, alias="timeZoneId")
    timestamp: str | None = Field(None)


class DateElementPropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base DateElementProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date_format_suggested: bool | None = Field(None, alias="dateFormatSuggested")
    locale_suggested: bool | None = Field(None, alias="localeSuggested")
    time_format_suggested: bool | None = Field(None, alias="timeFormatSuggested")
    time_zone_id_suggested: bool | None = Field(None, alias="timeZoneIdSuggested")
    timestamp_suggested: bool | None = Field(None, alias="timestampSuggested")


class DeleteFooterRequest(BaseModel):
    """Deletes a Footer from the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    footer_id: str | None = Field(None, alias="footerId")
    tab_id: str | None = Field(None, alias="tabId")


class DeleteHeaderRequest(BaseModel):
    """Deletes a Header from the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    header_id: str | None = Field(None, alias="headerId")
    tab_id: str | None = Field(None, alias="tabId")


class DeletePositionedObjectRequest(BaseModel):
    """Deletes a PositionedObject from the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    object_id: str | None = Field(None, alias="objectId")
    tab_id: str | None = Field(None, alias="tabId")


class DeleteTabRequest(BaseModel):
    """Deletes a tab. If the tab has child tabs, they are deleted as well."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tab_id: str | None = Field(None, alias="tabId")


class Dimension(BaseModel):
    """A magnitude in a single direction in the specified units."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    magnitude: float | None = Field(None)
    unit: DimensionUnit | None = Field(None)


class DocumentFormat(BaseModel):
    """Represents document-level format settings."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    document_mode: DocumentFormatDocumentMode | None = Field(None, alias="documentMode")


class EmbeddedDrawingProperties(BaseModel):
    """The properties of an embedded drawing and used to differentiate the object type. An embedded drawing is one that's created and edited within a document. Note that extensive details are not supported."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    pass


class EmbeddedDrawingPropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base EmbeddedDrawingProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    pass


class EmbeddedObjectBorderSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base EmbeddedObjectBorder have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    color_suggested: bool | None = Field(None, alias="colorSuggested")
    dash_style_suggested: bool | None = Field(None, alias="dashStyleSuggested")
    property_state_suggested: bool | None = Field(None, alias="propertyStateSuggested")
    width_suggested: bool | None = Field(None, alias="widthSuggested")


class EndOfSegmentLocation(BaseModel):
    """Location at the end of a body, header, footer or footnote. The location is immediately before the last newline in the document segment."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    segment_id: str | None = Field(None, alias="segmentId")
    tab_id: str | None = Field(None, alias="tabId")


class Equation(BaseModel):
    """A ParagraphElement representing an equation."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )


class HeadingLink(BaseModel):
    """A reference to a heading in this document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str | None = Field(None)
    tab_id: str | None = Field(None, alias="tabId")


class InsertInlineImageResponse(BaseModel):
    """The result of inserting an inline image."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    object_id: str | None = Field(None, alias="objectId")


class InsertInlineSheetsChartResponse(BaseModel):
    """The result of inserting an embedded Google Sheets chart."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    object_id: str | None = Field(None, alias="objectId")


class Location(BaseModel):
    """A particular location in the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    index: int | None = Field(None)
    segment_id: str | None = Field(None, alias="segmentId")
    tab_id: str | None = Field(None, alias="tabId")


class ObjectReferences(BaseModel):
    """A collection of object IDs."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    object_ids: list[str] | None = Field(None, alias="objectIds")


class PersonProperties(BaseModel):
    """Properties specific to a linked Person."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    email: str | None = Field(None)
    name: str | None = Field(None)


class PositionedObjectPositioningSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base PositionedObjectPositioning have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    layout_suggested: bool | None = Field(None, alias="layoutSuggested")
    left_offset_suggested: bool | None = Field(None, alias="leftOffsetSuggested")
    top_offset_suggested: bool | None = Field(None, alias="topOffsetSuggested")


class Range(BaseModel):
    """Specifies a contiguous range of text."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_index: int | None = Field(None, alias="endIndex")
    segment_id: str | None = Field(None, alias="segmentId")
    start_index: int | None = Field(None, alias="startIndex")
    tab_id: str | None = Field(None, alias="tabId")


class ReplaceAllTextResponse(BaseModel):
    """The result of replacing text."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    occurrences_changed: int | None = Field(None, alias="occurrencesChanged")


class ReplaceImageRequest(BaseModel):
    """Replaces an existing image with a new image. Replacing an image removes some image effects from the existing image in order to mirror the behavior of the Docs editor."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    image_object_id: str | None = Field(None, alias="imageObjectId")
    image_replace_method: ReplaceImageRequestImageReplaceMethod | None = Field(
        None, alias="imageReplaceMethod"
    )
    tab_id: str | None = Field(None, alias="tabId")
    uri: str | None = Field(None)


class RgbColor(BaseModel):
    """An RGB color."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    blue: float | None = Field(None)
    green: float | None = Field(None)
    red: float | None = Field(None)


class RichLinkProperties(BaseModel):
    """Properties specific to a RichLink."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    mime_type: str | None = Field(None, alias="mimeType")
    title: str | None = Field(None)
    uri: str | None = Field(None)


class ShadingSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base Shading have been changed in this suggested change. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color_suggested: bool | None = Field(
        None, alias="backgroundColorSuggested"
    )


class SheetsChartReference(BaseModel):
    """A reference to a linked chart embedded from Google Sheets."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    chart_id: int | None = Field(None, alias="chartId")
    spreadsheet_id: str | None = Field(None, alias="spreadsheetId")


class SheetsChartReferenceSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base SheetsChartReference have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    chart_id_suggested: bool | None = Field(None, alias="chartIdSuggested")
    spreadsheet_id_suggested: bool | None = Field(None, alias="spreadsheetIdSuggested")


class SizeSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base Size have been changed in this suggestion. For any field set to true, the Size has a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    height_suggested: bool | None = Field(None, alias="heightSuggested")
    width_suggested: bool | None = Field(None, alias="widthSuggested")


class SubstringMatchCriteria(BaseModel):
    """A criteria that matches a specific string of text in the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    match_case: bool | None = Field(None, alias="matchCase")
    search_by_regex: bool | None = Field(None, alias="searchByRegex")
    text: str | None = Field(None)


class TabProperties(BaseModel):
    """Properties of a tab."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    icon_emoji: str | None = Field(None, alias="iconEmoji")
    index: int | None = Field(None)
    nesting_level: int | None = Field(None, alias="nestingLevel")
    parent_tab_id: str | None = Field(None, alias="parentTabId")
    tab_id: str | None = Field(None, alias="tabId")
    title: str | None = Field(None)


class TableCellStyleSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base TableCellStyle have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color_suggested: bool | None = Field(
        None, alias="backgroundColorSuggested"
    )
    border_bottom_suggested: bool | None = Field(None, alias="borderBottomSuggested")
    border_left_suggested: bool | None = Field(None, alias="borderLeftSuggested")
    border_right_suggested: bool | None = Field(None, alias="borderRightSuggested")
    border_top_suggested: bool | None = Field(None, alias="borderTopSuggested")
    column_span_suggested: bool | None = Field(None, alias="columnSpanSuggested")
    content_alignment_suggested: bool | None = Field(
        None, alias="contentAlignmentSuggested"
    )
    padding_bottom_suggested: bool | None = Field(None, alias="paddingBottomSuggested")
    padding_left_suggested: bool | None = Field(None, alias="paddingLeftSuggested")
    padding_right_suggested: bool | None = Field(None, alias="paddingRightSuggested")
    padding_top_suggested: bool | None = Field(None, alias="paddingTopSuggested")
    row_span_suggested: bool | None = Field(None, alias="rowSpanSuggested")


class TableRowStyleSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base TableRowStyle have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    min_row_height_suggested: bool | None = Field(None, alias="minRowHeightSuggested")


class TabsCriteria(BaseModel):
    """A criteria that specifies in which tabs a request executes."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tab_ids: list[str] | None = Field(None, alias="tabIds")


class TextStyleSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base TextStyle have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color_suggested: bool | None = Field(
        None, alias="backgroundColorSuggested"
    )
    baseline_offset_suggested: bool | None = Field(
        None, alias="baselineOffsetSuggested"
    )
    bold_suggested: bool | None = Field(None, alias="boldSuggested")
    font_size_suggested: bool | None = Field(None, alias="fontSizeSuggested")
    foreground_color_suggested: bool | None = Field(
        None, alias="foregroundColorSuggested"
    )
    italic_suggested: bool | None = Field(None, alias="italicSuggested")
    link_suggested: bool | None = Field(None, alias="linkSuggested")
    small_caps_suggested: bool | None = Field(None, alias="smallCapsSuggested")
    strikethrough_suggested: bool | None = Field(None, alias="strikethroughSuggested")
    underline_suggested: bool | None = Field(None, alias="underlineSuggested")
    weighted_font_family_suggested: bool | None = Field(
        None, alias="weightedFontFamilySuggested"
    )


class WeightedFontFamily(BaseModel):
    """Represents a font family and weight of text."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    font_family: str | None = Field(None, alias="fontFamily")
    weight: int | None = Field(None)


class WriteControl(BaseModel):
    """Provides control over how write requests are executed."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    required_revision_id: str | None = Field(None, alias="requiredRevisionId")
    target_revision_id: str | None = Field(None, alias="targetRevisionId")


class ImageProperties(BaseModel):
    """The properties of an image."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    angle: float | None = Field(None)
    brightness: float | None = Field(None)
    content_uri: str | None = Field(None, alias="contentUri")
    contrast: float | None = Field(None)
    crop_properties: CropProperties | None = Field(None, alias="cropProperties")
    source_uri: str | None = Field(None, alias="sourceUri")
    transparency: float | None = Field(None)


class ImagePropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base ImageProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    angle_suggested: bool | None = Field(None, alias="angleSuggested")
    brightness_suggested: bool | None = Field(None, alias="brightnessSuggested")
    content_uri_suggested: bool | None = Field(None, alias="contentUriSuggested")
    contrast_suggested: bool | None = Field(None, alias="contrastSuggested")
    crop_properties_suggestion_state: CropPropertiesSuggestionState | None = Field(
        None, alias="cropPropertiesSuggestionState"
    )
    source_uri_suggested: bool | None = Field(None, alias="sourceUriSuggested")
    transparency_suggested: bool | None = Field(None, alias="transparencySuggested")


class SuggestedDateElementProperties(BaseModel):
    """A suggested change to a DateElementProperties."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date_element_properties: DateElementProperties | None = Field(
        None, alias="dateElementProperties"
    )
    date_element_properties_suggestion_state: (
        DateElementPropertiesSuggestionState | None
    ) = Field(None, alias="dateElementPropertiesSuggestionState")


class PositionedObjectPositioning(BaseModel):
    """The positioning of a PositionedObject. The positioned object is positioned relative to the beginning of the Paragraph it's tethered to."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    layout: PositionedObjectPositioningLayout | None = Field(None)
    left_offset: Dimension | None = Field(None, alias="leftOffset")
    top_offset: Dimension | None = Field(None, alias="topOffset")


class SectionColumnProperties(BaseModel):
    """Properties that apply to a section's column."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    padding_end: Dimension | None = Field(None, alias="paddingEnd")
    width: Dimension | None = Field(None)


class Size(BaseModel):
    """A width and height."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    height: Dimension | None = Field(None)
    width: Dimension | None = Field(None)


class TabStop(BaseModel):
    """A tab stop within a paragraph."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    alignment: TabStopAlignment | None = Field(None)
    offset: Dimension | None = Field(None)


class TableColumnProperties(BaseModel):
    """The properties of a column in a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    width: Dimension | None = Field(None)
    width_type: TableColumnPropertiesWidthType | None = Field(None, alias="widthType")


class TableRowStyle(BaseModel):
    """Styles that apply to a table row."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    min_row_height: Dimension | None = Field(None, alias="minRowHeight")
    prevent_overflow: bool | None = Field(None, alias="preventOverflow")
    table_header: bool | None = Field(None, alias="tableHeader")


class Link(BaseModel):
    """A reference to another portion of a document or an external URL resource."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bookmark: BookmarkLink | None = Field(None)
    bookmark_id: str | None = Field(None, alias="bookmarkId")
    heading: HeadingLink | None = Field(None)
    heading_id: str | None = Field(None, alias="headingId")
    tab_id: str | None = Field(None, alias="tabId")
    url: str | None = Field(None)


class CreateFooterRequest(BaseModel):
    """Creates a Footer. The new footer is applied to the SectionStyle at the location of the SectionBreak if specified, otherwise it is applied to the DocumentStyle. If a footer of the specified type already exists, a 400 bad request error is returned."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    section_break_location: Location | None = Field(None, alias="sectionBreakLocation")
    type: CreateFooterRequestType | None = Field(None)


class CreateFootnoteRequest(BaseModel):
    """Creates a Footnote segment and inserts a new FootnoteReference to it at the given location. The new Footnote segment will contain a space followed by a newline character."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)


class CreateHeaderRequest(BaseModel):
    """Creates a Header. The new header is applied to the SectionStyle at the location of the SectionBreak if specified, otherwise it is applied to the DocumentStyle. If a header of the specified type already exists, a 400 bad request error is returned."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    section_break_location: Location | None = Field(None, alias="sectionBreakLocation")
    type: CreateFooterRequestType | None = Field(None)


class InsertDateRequest(BaseModel):
    """Inserts a date at the specified location."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date_element_properties: DateElementProperties | None = Field(
        None, alias="dateElementProperties"
    )
    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)


class InsertPageBreakRequest(BaseModel):
    """Inserts a page break followed by a newline at the specified location."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)


class InsertSectionBreakRequest(BaseModel):
    """Inserts a section break at the given location. A newline character will be inserted before the section break."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)
    section_type: InsertSectionBreakRequestSectionType | None = Field(
        None, alias="sectionType"
    )


class InsertTableRequest(BaseModel):
    """Inserts a table at the specified location. A newline character will be inserted before the inserted table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    columns: int | None = Field(None)
    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)
    rows: int | None = Field(None)


class InsertTextRequest(BaseModel):
    """Inserts text at the specified location."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)
    text: str | None = Field(None)


class PinTableHeaderRowsRequest(BaseModel):
    """Updates the number of pinned table header rows in a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    pinned_header_rows_count: int | None = Field(None, alias="pinnedHeaderRowsCount")
    table_start_location: Location | None = Field(None, alias="tableStartLocation")


class TableCellLocation(BaseModel):
    """Location of a single cell within a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    column_index: int | None = Field(None, alias="columnIndex")
    row_index: int | None = Field(None, alias="rowIndex")
    table_start_location: Location | None = Field(None, alias="tableStartLocation")


class InsertPersonRequest(BaseModel):
    """Inserts a person mention."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)
    person_properties: PersonProperties | None = Field(None, alias="personProperties")


class CreateNamedRangeRequest(BaseModel):
    """Creates a NamedRange referencing the given range."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str | None = Field(None)
    range: Range | None = Field(None)


class CreateParagraphBulletsRequest(BaseModel):
    """Creates bullets for all of the paragraphs that overlap with the given range. The nesting level of each paragraph will be determined by counting leading tabs in front of each paragraph. To avoid excess space between the bullet and the corresponding paragraph, these leading tabs are removed by this request. This may change the indices of parts of the text. If the paragraph immediately before paragraphs being updated is in a list with a matching preset, the paragraphs being updated are added to that preceding list."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bullet_preset: CreateParagraphBulletsRequestBulletPreset | None = Field(
        None, alias="bulletPreset"
    )
    range: Range | None = Field(None)


class DeleteContentRangeRequest(BaseModel):
    """Deletes content from the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    range: Range | None = Field(None)


class DeleteParagraphBulletsRequest(BaseModel):
    """Deletes bullets from all of the paragraphs that overlap with the given range. The nesting level of each paragraph will be visually preserved by adding indent to the start of the corresponding paragraph."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    range: Range | None = Field(None)


class NamedRange(BaseModel):
    """A collection of Ranges with the same named range ID. Named ranges allow developers to associate parts of a document with an arbitrary user-defined label so their contents can be programmatically read or edited later. A document can contain multiple named ranges with the same name, but every named range has a unique ID. A named range is created with a single Range, and content inserted inside a named range generally expands that range. However, certain document changes can cause the range to be split into multiple ranges. Named ranges are not private. All applications and collaborators that have access to the document can see its named ranges."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str | None = Field(None)
    named_range_id: str | None = Field(None, alias="namedRangeId")
    ranges: list[Range] | None = Field(None)


class Color(BaseModel):
    """A solid color."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    rgb_color: RgbColor | None = Field(None, alias="rgbColor")


class ParagraphStyleSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base ParagraphStyle have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    alignment_suggested: bool | None = Field(None, alias="alignmentSuggested")
    avoid_widow_and_orphan_suggested: bool | None = Field(
        None, alias="avoidWidowAndOrphanSuggested"
    )
    border_between_suggested: bool | None = Field(None, alias="borderBetweenSuggested")
    border_bottom_suggested: bool | None = Field(None, alias="borderBottomSuggested")
    border_left_suggested: bool | None = Field(None, alias="borderLeftSuggested")
    border_right_suggested: bool | None = Field(None, alias="borderRightSuggested")
    border_top_suggested: bool | None = Field(None, alias="borderTopSuggested")
    direction_suggested: bool | None = Field(None, alias="directionSuggested")
    heading_id_suggested: bool | None = Field(None, alias="headingIdSuggested")
    indent_end_suggested: bool | None = Field(None, alias="indentEndSuggested")
    indent_first_line_suggested: bool | None = Field(
        None, alias="indentFirstLineSuggested"
    )
    indent_start_suggested: bool | None = Field(None, alias="indentStartSuggested")
    keep_lines_together_suggested: bool | None = Field(
        None, alias="keepLinesTogetherSuggested"
    )
    keep_with_next_suggested: bool | None = Field(None, alias="keepWithNextSuggested")
    line_spacing_suggested: bool | None = Field(None, alias="lineSpacingSuggested")
    named_style_type_suggested: bool | None = Field(
        None, alias="namedStyleTypeSuggested"
    )
    page_break_before_suggested: bool | None = Field(
        None, alias="pageBreakBeforeSuggested"
    )
    shading_suggestion_state: ShadingSuggestionState | None = Field(
        None, alias="shadingSuggestionState"
    )
    space_above_suggested: bool | None = Field(None, alias="spaceAboveSuggested")
    space_below_suggested: bool | None = Field(None, alias="spaceBelowSuggested")
    spacing_mode_suggested: bool | None = Field(None, alias="spacingModeSuggested")


class LinkedContentReference(BaseModel):
    """A reference to the external linked source content."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    sheets_chart_reference: SheetsChartReference | None = Field(
        None, alias="sheetsChartReference"
    )


class LinkedContentReferenceSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base LinkedContentReference have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    sheets_chart_reference_suggestion_state: (
        SheetsChartReferenceSuggestionState | None
    ) = Field(None, alias="sheetsChartReferenceSuggestionState")


class DocumentStyleSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base DocumentStyle have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_suggestion_state: BackgroundSuggestionState | None = Field(
        None, alias="backgroundSuggestionState"
    )
    default_footer_id_suggested: bool | None = Field(
        None, alias="defaultFooterIdSuggested"
    )
    default_header_id_suggested: bool | None = Field(
        None, alias="defaultHeaderIdSuggested"
    )
    even_page_footer_id_suggested: bool | None = Field(
        None, alias="evenPageFooterIdSuggested"
    )
    even_page_header_id_suggested: bool | None = Field(
        None, alias="evenPageHeaderIdSuggested"
    )
    first_page_footer_id_suggested: bool | None = Field(
        None, alias="firstPageFooterIdSuggested"
    )
    first_page_header_id_suggested: bool | None = Field(
        None, alias="firstPageHeaderIdSuggested"
    )
    flip_page_orientation_suggested: bool | None = Field(
        None, alias="flipPageOrientationSuggested"
    )
    margin_bottom_suggested: bool | None = Field(None, alias="marginBottomSuggested")
    margin_footer_suggested: bool | None = Field(None, alias="marginFooterSuggested")
    margin_header_suggested: bool | None = Field(None, alias="marginHeaderSuggested")
    margin_left_suggested: bool | None = Field(None, alias="marginLeftSuggested")
    margin_right_suggested: bool | None = Field(None, alias="marginRightSuggested")
    margin_top_suggested: bool | None = Field(None, alias="marginTopSuggested")
    page_number_start_suggested: bool | None = Field(
        None, alias="pageNumberStartSuggested"
    )
    page_size_suggestion_state: SizeSuggestionState | None = Field(
        None, alias="pageSizeSuggestionState"
    )
    use_custom_header_footer_margins_suggested: bool | None = Field(
        None, alias="useCustomHeaderFooterMarginsSuggested"
    )
    use_even_page_header_footer_suggested: bool | None = Field(
        None, alias="useEvenPageHeaderFooterSuggested"
    )
    use_first_page_header_footer_suggested: bool | None = Field(
        None, alias="useFirstPageHeaderFooterSuggested"
    )


class AddDocumentTabRequest(BaseModel):
    """Adds a document tab. When a tab is added at a given index, all subsequent tabs' indexes are incremented."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tab_properties: TabProperties | None = Field(None, alias="tabProperties")


class AddDocumentTabResponse(BaseModel):
    """The result of adding a document tab."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    tab_properties: TabProperties | None = Field(None, alias="tabProperties")


class UpdateDocumentTabPropertiesRequest(BaseModel):
    """Update the properties of a document tab."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fields: str | None = Field(None)
    tab_properties: TabProperties | None = Field(None, alias="tabProperties")


class DeleteNamedRangeRequest(BaseModel):
    """Deletes a NamedRange."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str | None = Field(None)
    named_range_id: str | None = Field(None, alias="namedRangeId")
    tabs_criteria: TabsCriteria | None = Field(None, alias="tabsCriteria")


class ReplaceAllTextRequest(BaseModel):
    """Replaces all instances of text matching a criteria with replace text."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    contains_text: SubstringMatchCriteria | None = Field(None, alias="containsText")
    replace_text: str | None = Field(None, alias="replaceText")
    tabs_criteria: TabsCriteria | None = Field(None, alias="tabsCriteria")


class ReplaceNamedRangeContentRequest(BaseModel):
    """Replaces the contents of the specified NamedRange or NamedRanges with the given replacement content. Note that an individual NamedRange may consist of multiple discontinuous ranges. In this case, only the content in the first range will be replaced. The other ranges and their content will be deleted. In cases where replacing or deleting any ranges would result in an invalid document structure, a 400 bad request error is returned."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    named_range_id: str | None = Field(None, alias="namedRangeId")
    named_range_name: str | None = Field(None, alias="namedRangeName")
    tabs_criteria: TabsCriteria | None = Field(None, alias="tabsCriteria")
    text: str | None = Field(None)


class BulletSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base Bullet have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    list_id_suggested: bool | None = Field(None, alias="listIdSuggested")
    nesting_level_suggested: bool | None = Field(None, alias="nestingLevelSuggested")
    text_style_suggestion_state: TextStyleSuggestionState | None = Field(
        None, alias="textStyleSuggestionState"
    )


class NestingLevelSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base NestingLevel have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bullet_alignment_suggested: bool | None = Field(
        None, alias="bulletAlignmentSuggested"
    )
    glyph_format_suggested: bool | None = Field(None, alias="glyphFormatSuggested")
    glyph_symbol_suggested: bool | None = Field(None, alias="glyphSymbolSuggested")
    glyph_type_suggested: bool | None = Field(None, alias="glyphTypeSuggested")
    indent_first_line_suggested: bool | None = Field(
        None, alias="indentFirstLineSuggested"
    )
    indent_start_suggested: bool | None = Field(None, alias="indentStartSuggested")
    start_number_suggested: bool | None = Field(None, alias="startNumberSuggested")
    text_style_suggestion_state: TextStyleSuggestionState | None = Field(
        None, alias="textStyleSuggestionState"
    )


class SectionStyle(BaseModel):
    """The styling that applies to a section."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    column_properties: list[SectionColumnProperties] | None = Field(
        None, alias="columnProperties"
    )
    column_separator_style: SectionStyleColumnSeparatorStyle | None = Field(
        None, alias="columnSeparatorStyle"
    )
    content_direction: ParagraphStyleDirection | None = Field(
        None, alias="contentDirection"
    )
    default_footer_id: str | None = Field(None, alias="defaultFooterId")
    default_header_id: str | None = Field(None, alias="defaultHeaderId")
    even_page_footer_id: str | None = Field(None, alias="evenPageFooterId")
    even_page_header_id: str | None = Field(None, alias="evenPageHeaderId")
    first_page_footer_id: str | None = Field(None, alias="firstPageFooterId")
    first_page_header_id: str | None = Field(None, alias="firstPageHeaderId")
    flip_page_orientation: bool | None = Field(None, alias="flipPageOrientation")
    margin_bottom: Dimension | None = Field(None, alias="marginBottom")
    margin_footer: Dimension | None = Field(None, alias="marginFooter")
    margin_header: Dimension | None = Field(None, alias="marginHeader")
    margin_left: Dimension | None = Field(None, alias="marginLeft")
    margin_right: Dimension | None = Field(None, alias="marginRight")
    margin_top: Dimension | None = Field(None, alias="marginTop")
    page_number_start: int | None = Field(None, alias="pageNumberStart")
    section_type: InsertSectionBreakRequestSectionType | None = Field(
        None, alias="sectionType"
    )
    use_first_page_header_footer: bool | None = Field(
        None, alias="useFirstPageHeaderFooter"
    )


class InsertInlineImageRequest(BaseModel):
    """Inserts an InlineObject containing an image at the given location."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_of_segment_location: EndOfSegmentLocation | None = Field(
        None, alias="endOfSegmentLocation"
    )
    location: Location | None = Field(None)
    object_size: Size | None = Field(None, alias="objectSize")
    uri: str | None = Field(None)


class TableStyle(BaseModel):
    """Styles that apply to a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_column_properties: list[TableColumnProperties] | None = Field(
        None, alias="tableColumnProperties"
    )


class UpdateTableColumnPropertiesRequest(BaseModel):
    """Updates the TableColumnProperties of columns in a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    column_indices: list[int] | None = Field(None, alias="columnIndices")
    fields: str | None = Field(None)
    table_column_properties: TableColumnProperties | None = Field(
        None, alias="tableColumnProperties"
    )
    table_start_location: Location | None = Field(None, alias="tableStartLocation")


class SuggestedTableRowStyle(BaseModel):
    """A suggested change to a TableRowStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_row_style: TableRowStyle | None = Field(None, alias="tableRowStyle")
    table_row_style_suggestion_state: TableRowStyleSuggestionState | None = Field(
        None, alias="tableRowStyleSuggestionState"
    )


class UpdateTableRowStyleRequest(BaseModel):
    """Updates the TableRowStyle of rows in a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fields: str | None = Field(None)
    row_indices: list[int] | None = Field(None, alias="rowIndices")
    table_row_style: TableRowStyle | None = Field(None, alias="tableRowStyle")
    table_start_location: Location | None = Field(None, alias="tableStartLocation")


class DeleteTableColumnRequest(BaseModel):
    """Deletes a column from a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_cell_location: TableCellLocation | None = Field(
        None, alias="tableCellLocation"
    )


class DeleteTableRowRequest(BaseModel):
    """Deletes a row from a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_cell_location: TableCellLocation | None = Field(
        None, alias="tableCellLocation"
    )


class InsertTableColumnRequest(BaseModel):
    """Inserts an empty column into a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    insert_right: bool | None = Field(None, alias="insertRight")
    table_cell_location: TableCellLocation | None = Field(
        None, alias="tableCellLocation"
    )


class InsertTableRowRequest(BaseModel):
    """Inserts an empty row into a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    insert_below: bool | None = Field(None, alias="insertBelow")
    table_cell_location: TableCellLocation | None = Field(
        None, alias="tableCellLocation"
    )


class TableRange(BaseModel):
    """A table range represents a reference to a subset of a table. It's important to note that the cells specified by a table range do not necessarily form a rectangle. For example, let's say we have a 3 x 3 table where all the cells of the last row are merged together. The table looks like this: [ ] A table range with table cell location = (table_start_location, row = 0, column = 0), row span = 3 and column span = 2 specifies the following cells: x x [ x x x ]"""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    column_span: int | None = Field(None, alias="columnSpan")
    row_span: int | None = Field(None, alias="rowSpan")
    table_cell_location: TableCellLocation | None = Field(
        None, alias="tableCellLocation"
    )


class NamedRanges(BaseModel):
    """A collection of all the NamedRanges in the document that share a given name."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str | None = Field(None)
    named_ranges: list[NamedRange] | None = Field(None, alias="namedRanges")


class OptionalColor(BaseModel):
    """A color that can either be fully opaque or fully transparent."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    color: Color | None = Field(None)


class NamedStyleSuggestionState(BaseModel):
    """A suggestion state of a NamedStyle message."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    named_style_type: ParagraphStyleNamedStyleType | None = Field(
        None, alias="namedStyleType"
    )
    paragraph_style_suggestion_state: ParagraphStyleSuggestionState | None = Field(
        None, alias="paragraphStyleSuggestionState"
    )
    text_style_suggestion_state: TextStyleSuggestionState | None = Field(
        None, alias="textStyleSuggestionState"
    )


class EmbeddedObjectSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base EmbeddedObject have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    description_suggested: bool | None = Field(None, alias="descriptionSuggested")
    embedded_drawing_properties_suggestion_state: (
        EmbeddedDrawingPropertiesSuggestionState | None
    ) = Field(None, alias="embeddedDrawingPropertiesSuggestionState")
    embedded_object_border_suggestion_state: (
        EmbeddedObjectBorderSuggestionState | None
    ) = Field(None, alias="embeddedObjectBorderSuggestionState")
    image_properties_suggestion_state: ImagePropertiesSuggestionState | None = Field(
        None, alias="imagePropertiesSuggestionState"
    )
    linked_content_reference_suggestion_state: (
        LinkedContentReferenceSuggestionState | None
    ) = Field(None, alias="linkedContentReferenceSuggestionState")
    margin_bottom_suggested: bool | None = Field(None, alias="marginBottomSuggested")
    margin_left_suggested: bool | None = Field(None, alias="marginLeftSuggested")
    margin_right_suggested: bool | None = Field(None, alias="marginRightSuggested")
    margin_top_suggested: bool | None = Field(None, alias="marginTopSuggested")
    size_suggestion_state: SizeSuggestionState | None = Field(
        None, alias="sizeSuggestionState"
    )
    title_suggested: bool | None = Field(None, alias="titleSuggested")


class Response(BaseModel):
    """A single response from an update."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    add_document_tab: AddDocumentTabResponse | None = Field(
        None, alias="addDocumentTab"
    )
    create_footer: CreateFooterResponse | None = Field(None, alias="createFooter")
    create_footnote: CreateFootnoteResponse | None = Field(None, alias="createFootnote")
    create_header: CreateHeaderResponse | None = Field(None, alias="createHeader")
    create_named_range: CreateNamedRangeResponse | None = Field(
        None, alias="createNamedRange"
    )
    insert_inline_image: InsertInlineImageResponse | None = Field(
        None, alias="insertInlineImage"
    )
    insert_inline_sheets_chart: InsertInlineSheetsChartResponse | None = Field(
        None, alias="insertInlineSheetsChart"
    )
    replace_all_text: ReplaceAllTextResponse | None = Field(
        None, alias="replaceAllText"
    )


class ListPropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base ListProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    nesting_levels_suggestion_states: list[NestingLevelSuggestionState] | None = Field(
        None, alias="nestingLevelsSuggestionStates"
    )


class SectionBreak(BaseModel):
    """A StructuralElement representing a section break. A section is a range of content that has the same SectionStyle. A section break represents the start of a new section, and the section style applies to the section after the section break. The document body always begins with a section break."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    section_style: SectionStyle | None = Field(None, alias="sectionStyle")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )


class UpdateSectionStyleRequest(BaseModel):
    """Updates the SectionStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fields: str | None = Field(None)
    range: Range | None = Field(None)
    section_style: SectionStyle | None = Field(None, alias="sectionStyle")


class MergeTableCellsRequest(BaseModel):
    """Merges cells in a Table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_range: TableRange | None = Field(None, alias="tableRange")


class UnmergeTableCellsRequest(BaseModel):
    """Unmerges cells in a Table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_range: TableRange | None = Field(None, alias="tableRange")


class Background(BaseModel):
    """Represents the background of a document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    color: OptionalColor | None = Field(None)


class EmbeddedObjectBorder(BaseModel):
    """A border around an EmbeddedObject."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    color: OptionalColor | None = Field(None)
    dash_style: EmbeddedObjectBorderDashStyle | None = Field(None, alias="dashStyle")
    property_state: EmbeddedObjectBorderPropertyState | None = Field(
        None, alias="propertyState"
    )
    width: Dimension | None = Field(None)


class ParagraphBorder(BaseModel):
    """A border around a paragraph."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    color: OptionalColor | None = Field(None)
    dash_style: EmbeddedObjectBorderDashStyle | None = Field(None, alias="dashStyle")
    padding: Dimension | None = Field(None)
    width: Dimension | None = Field(None)


class Shading(BaseModel):
    """The shading of a paragraph."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color: OptionalColor | None = Field(None, alias="backgroundColor")


class TableCellBorder(BaseModel):
    """A border around a table cell. Table cell borders cannot be transparent. To hide a table cell border, make its width 0."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    color: OptionalColor | None = Field(None)
    dash_style: EmbeddedObjectBorderDashStyle | None = Field(None, alias="dashStyle")
    width: Dimension | None = Field(None)


class TextStyle(BaseModel):
    """Represents the styling that can be applied to text. Inherited text styles are represented as unset fields in this message. A text style's parent depends on where the text style is defined: * The TextStyle of text in a Paragraph inherits from the paragraph's corresponding named style type. * The TextStyle on a named style inherits from the normal text named style. * The TextStyle of the normal text named style inherits from the default text style in the Docs editor. * The TextStyle on a Paragraph element that's contained in a table may inherit its text style from the table style. If the text style does not inherit from a parent, unsetting fields will revert the style to a value matching the defaults in the Docs editor."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color: OptionalColor | None = Field(None, alias="backgroundColor")
    baseline_offset: TextStyleBaselineOffset | None = Field(
        None, alias="baselineOffset"
    )
    bold: bool | None = Field(None)
    font_size: Dimension | None = Field(None, alias="fontSize")
    foreground_color: OptionalColor | None = Field(None, alias="foregroundColor")
    italic: bool | None = Field(None)
    link: Link | None = Field(None)
    small_caps: bool | None = Field(None, alias="smallCaps")
    strikethrough: bool | None = Field(None)
    underline: bool | None = Field(None)
    weighted_font_family: WeightedFontFamily | None = Field(
        None, alias="weightedFontFamily"
    )


class NamedStylesSuggestionState(BaseModel):
    """The suggestion state of a NamedStyles message."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    styles_suggestion_states: list[NamedStyleSuggestionState] | None = Field(
        None, alias="stylesSuggestionStates"
    )


class InlineObjectPropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base InlineObjectProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    embedded_object_suggestion_state: EmbeddedObjectSuggestionState | None = Field(
        None, alias="embeddedObjectSuggestionState"
    )


class PositionedObjectPropertiesSuggestionState(BaseModel):
    """A mask that indicates which of the fields on the base PositionedObjectProperties have been changed in this suggestion. For any field set to true, there's a new suggested value."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    embedded_object_suggestion_state: EmbeddedObjectSuggestionState | None = Field(
        None, alias="embeddedObjectSuggestionState"
    )
    positioning_suggestion_state: PositionedObjectPositioningSuggestionState | None = (
        Field(None, alias="positioningSuggestionState")
    )


class BatchUpdateDocumentResponse(BaseModel):
    """Response message from a BatchUpdateDocument request."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    document_id: str | None = Field(None, alias="documentId")
    replies: list[Response] | None = Field(None)
    write_control: WriteControl | None = Field(None, alias="writeControl")


class DocumentStyle(BaseModel):
    """The style of the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background: Background | None = Field(None)
    default_footer_id: str | None = Field(None, alias="defaultFooterId")
    default_header_id: str | None = Field(None, alias="defaultHeaderId")
    document_format: DocumentFormat | None = Field(None, alias="documentFormat")
    even_page_footer_id: str | None = Field(None, alias="evenPageFooterId")
    even_page_header_id: str | None = Field(None, alias="evenPageHeaderId")
    first_page_footer_id: str | None = Field(None, alias="firstPageFooterId")
    first_page_header_id: str | None = Field(None, alias="firstPageHeaderId")
    flip_page_orientation: bool | None = Field(None, alias="flipPageOrientation")
    margin_bottom: Dimension | None = Field(None, alias="marginBottom")
    margin_footer: Dimension | None = Field(None, alias="marginFooter")
    margin_header: Dimension | None = Field(None, alias="marginHeader")
    margin_left: Dimension | None = Field(None, alias="marginLeft")
    margin_right: Dimension | None = Field(None, alias="marginRight")
    margin_top: Dimension | None = Field(None, alias="marginTop")
    page_number_start: int | None = Field(None, alias="pageNumberStart")
    page_size: Size | None = Field(None, alias="pageSize")
    use_custom_header_footer_margins: bool | None = Field(
        None, alias="useCustomHeaderFooterMargins"
    )
    use_even_page_header_footer: bool | None = Field(
        None, alias="useEvenPageHeaderFooter"
    )
    use_first_page_header_footer: bool | None = Field(
        None, alias="useFirstPageHeaderFooter"
    )


class EmbeddedObject(BaseModel):
    """An embedded object in the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    description: str | None = Field(None)
    embedded_drawing_properties: EmbeddedDrawingProperties | None = Field(
        None, alias="embeddedDrawingProperties"
    )
    embedded_object_border: EmbeddedObjectBorder | None = Field(
        None, alias="embeddedObjectBorder"
    )
    image_properties: ImageProperties | None = Field(None, alias="imageProperties")
    linked_content_reference: LinkedContentReference | None = Field(
        None, alias="linkedContentReference"
    )
    margin_bottom: Dimension | None = Field(None, alias="marginBottom")
    margin_left: Dimension | None = Field(None, alias="marginLeft")
    margin_right: Dimension | None = Field(None, alias="marginRight")
    margin_top: Dimension | None = Field(None, alias="marginTop")
    size: Size | None = Field(None)
    title: str | None = Field(None)


class ParagraphStyle(BaseModel):
    """Styles that apply to a whole paragraph. Inherited paragraph styles are represented as unset fields in this message. A paragraph style's parent depends on where the paragraph style is defined: * The ParagraphStyle on a Paragraph inherits from the paragraph's corresponding named style type. * The ParagraphStyle on a named style inherits from the normal text named style. * The ParagraphStyle of the normal text named style inherits from the default paragraph style in the Docs editor. * The ParagraphStyle on a Paragraph element that's contained in a table may inherit its paragraph style from the table style. If the paragraph style does not inherit from a parent, unsetting fields will revert the style to a value matching the defaults in the Docs editor."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    alignment: ParagraphStyleAlignment | None = Field(None)
    avoid_widow_and_orphan: bool | None = Field(None, alias="avoidWidowAndOrphan")
    border_between: ParagraphBorder | None = Field(None, alias="borderBetween")
    border_bottom: ParagraphBorder | None = Field(None, alias="borderBottom")
    border_left: ParagraphBorder | None = Field(None, alias="borderLeft")
    border_right: ParagraphBorder | None = Field(None, alias="borderRight")
    border_top: ParagraphBorder | None = Field(None, alias="borderTop")
    direction: ParagraphStyleDirection | None = Field(None)
    heading_id: str | None = Field(None, alias="headingId")
    indent_end: Dimension | None = Field(None, alias="indentEnd")
    indent_first_line: Dimension | None = Field(None, alias="indentFirstLine")
    indent_start: Dimension | None = Field(None, alias="indentStart")
    keep_lines_together: bool | None = Field(None, alias="keepLinesTogether")
    keep_with_next: bool | None = Field(None, alias="keepWithNext")
    line_spacing: float | None = Field(None, alias="lineSpacing")
    named_style_type: ParagraphStyleNamedStyleType | None = Field(
        None, alias="namedStyleType"
    )
    page_break_before: bool | None = Field(None, alias="pageBreakBefore")
    shading: Shading | None = Field(None)
    space_above: Dimension | None = Field(None, alias="spaceAbove")
    space_below: Dimension | None = Field(None, alias="spaceBelow")
    spacing_mode: ParagraphStyleSpacingMode | None = Field(None, alias="spacingMode")
    tab_stops: list[TabStop] | None = Field(None, alias="tabStops")


class TableCellStyle(BaseModel):
    """The style of a TableCell. Inherited table cell styles are represented as unset fields in this message. A table cell style can inherit from the table's style."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    background_color: OptionalColor | None = Field(None, alias="backgroundColor")
    border_bottom: TableCellBorder | None = Field(None, alias="borderBottom")
    border_left: TableCellBorder | None = Field(None, alias="borderLeft")
    border_right: TableCellBorder | None = Field(None, alias="borderRight")
    border_top: TableCellBorder | None = Field(None, alias="borderTop")
    column_span: int | None = Field(None, alias="columnSpan")
    content_alignment: TableCellStyleContentAlignment | None = Field(
        None, alias="contentAlignment"
    )
    padding_bottom: Dimension | None = Field(None, alias="paddingBottom")
    padding_left: Dimension | None = Field(None, alias="paddingLeft")
    padding_right: Dimension | None = Field(None, alias="paddingRight")
    padding_top: Dimension | None = Field(None, alias="paddingTop")
    row_span: int | None = Field(None, alias="rowSpan")


class Bullet(BaseModel):
    """Describes the bullet of a paragraph."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    list_id: str | None = Field(None, alias="listId")
    nesting_level: int | None = Field(None, alias="nestingLevel")
    text_style: TextStyle | None = Field(None, alias="textStyle")


class NestingLevel(BaseModel):
    """Contains properties describing the look and feel of a list bullet at a given level of nesting."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bullet_alignment: NestingLevelBulletAlignment | None = Field(
        None, alias="bulletAlignment"
    )
    glyph_format: str | None = Field(None, alias="glyphFormat")
    glyph_symbol: str | None = Field(None, alias="glyphSymbol")
    glyph_type: NestingLevelGlyphType | None = Field(None, alias="glyphType")
    indent_first_line: Dimension | None = Field(None, alias="indentFirstLine")
    indent_start: Dimension | None = Field(None, alias="indentStart")
    start_number: int | None = Field(None, alias="startNumber")
    text_style: TextStyle | None = Field(None, alias="textStyle")


class SuggestedTextStyle(BaseModel):
    """A suggested change to a TextStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    text_style: TextStyle | None = Field(None, alias="textStyle")
    text_style_suggestion_state: TextStyleSuggestionState | None = Field(
        None, alias="textStyleSuggestionState"
    )


class UpdateTextStyleRequest(BaseModel):
    """Update the styling of text."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fields: str | None = Field(None)
    range: Range | None = Field(None)
    text_style: TextStyle | None = Field(None, alias="textStyle")


class SuggestedDocumentStyle(BaseModel):
    """A suggested change to the DocumentStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    document_style: DocumentStyle | None = Field(None, alias="documentStyle")
    document_style_suggestion_state: DocumentStyleSuggestionState | None = Field(
        None, alias="documentStyleSuggestionState"
    )


class UpdateDocumentStyleRequest(BaseModel):
    """Updates the DocumentStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    document_style: DocumentStyle | None = Field(None, alias="documentStyle")
    fields: str | None = Field(None)
    tab_id: str | None = Field(None, alias="tabId")


class InlineObjectProperties(BaseModel):
    """Properties of an InlineObject."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    embedded_object: EmbeddedObject | None = Field(None, alias="embeddedObject")


class PositionedObjectProperties(BaseModel):
    """Properties of a PositionedObject."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    embedded_object: EmbeddedObject | None = Field(None, alias="embeddedObject")
    positioning: PositionedObjectPositioning | None = Field(None)


class NamedStyle(BaseModel):
    """A named style. Paragraphs in the document can inherit their TextStyle and ParagraphStyle from this named style when they have the same named style type."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    named_style_type: ParagraphStyleNamedStyleType | None = Field(
        None, alias="namedStyleType"
    )
    paragraph_style: ParagraphStyle | None = Field(None, alias="paragraphStyle")
    text_style: TextStyle | None = Field(None, alias="textStyle")


class SuggestedParagraphStyle(BaseModel):
    """A suggested change to a ParagraphStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    paragraph_style: ParagraphStyle | None = Field(None, alias="paragraphStyle")
    paragraph_style_suggestion_state: ParagraphStyleSuggestionState | None = Field(
        None, alias="paragraphStyleSuggestionState"
    )


class UpdateParagraphStyleRequest(BaseModel):
    """Update the styling of all paragraphs that overlap with the given range."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fields: str | None = Field(None)
    paragraph_style: ParagraphStyle | None = Field(None, alias="paragraphStyle")
    range: Range | None = Field(None)


class SuggestedTableCellStyle(BaseModel):
    """A suggested change to a TableCellStyle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    table_cell_style: TableCellStyle | None = Field(None, alias="tableCellStyle")
    table_cell_style_suggestion_state: TableCellStyleSuggestionState | None = Field(
        None, alias="tableCellStyleSuggestionState"
    )


class UpdateTableCellStyleRequest(BaseModel):
    """Updates the style of a range of table cells."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    fields: str | None = Field(None)
    table_cell_style: TableCellStyle | None = Field(None, alias="tableCellStyle")
    table_range: TableRange | None = Field(None, alias="tableRange")
    table_start_location: Location | None = Field(None, alias="tableStartLocation")


class SuggestedBullet(BaseModel):
    """A suggested change to a Bullet."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bullet: Bullet | None = Field(None)
    bullet_suggestion_state: BulletSuggestionState | None = Field(
        None, alias="bulletSuggestionState"
    )


class ListProperties(BaseModel):
    """The properties of a list that describe the look and feel of bullets belonging to paragraphs associated with a list."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    nesting_levels: list[NestingLevel] | None = Field(None, alias="nestingLevels")


class AutoText(BaseModel):
    """A ParagraphElement representing a spot in the text that's dynamically replaced with content that can change over time, like a page number."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")
    type: AutoTextType | None = Field(None)


class ColumnBreak(BaseModel):
    """A ParagraphElement representing a column break. A column break makes the subsequent text start at the top of the next column."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class DateElement(BaseModel):
    """A date instance mentioned in a document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    date_element_properties: DateElementProperties | None = Field(
        None, alias="dateElementProperties"
    )
    date_id: str | None = Field(None, alias="dateId")
    suggested_date_element_properties_changes: (
        dict[str, SuggestedDateElementProperties] | None
    ) = Field(None, alias="suggestedDateElementPropertiesChanges")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class FootnoteReference(BaseModel):
    """A ParagraphElement representing a footnote reference. A footnote reference is the inline content rendered with a number and is used to identify the footnote."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    footnote_id: str | None = Field(None, alias="footnoteId")
    footnote_number: str | None = Field(None, alias="footnoteNumber")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class HorizontalRule(BaseModel):
    """A ParagraphElement representing a horizontal line."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class InlineObjectElement(BaseModel):
    """A ParagraphElement that contains an InlineObject."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    inline_object_id: str | None = Field(None, alias="inlineObjectId")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class PageBreak(BaseModel):
    """A ParagraphElement representing a page break. A page break makes the subsequent text start at the top of the next page."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class Person(BaseModel):
    """A person or email address mentioned in a document. These mentions behave as a single, immutable element containing the person's name or email address."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    person_id: str | None = Field(None, alias="personId")
    person_properties: PersonProperties | None = Field(None, alias="personProperties")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class RichLink(BaseModel):
    """A link to a Google resource (such as a file in Drive, a YouTube video, or a Calendar event)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    rich_link_id: str | None = Field(None, alias="richLinkId")
    rich_link_properties: RichLinkProperties | None = Field(
        None, alias="richLinkProperties"
    )
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class TextRun(BaseModel):
    """A ParagraphElement that represents a run of text that all has the same styling."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: str | None = Field(None)
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_text_style_changes: dict[str, SuggestedTextStyle] | None = Field(
        None, alias="suggestedTextStyleChanges"
    )
    text_style: TextStyle | None = Field(None, alias="textStyle")


class SuggestedInlineObjectProperties(BaseModel):
    """A suggested change to InlineObjectProperties."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    inline_object_properties: InlineObjectProperties | None = Field(
        None, alias="inlineObjectProperties"
    )
    inline_object_properties_suggestion_state: (
        InlineObjectPropertiesSuggestionState | None
    ) = Field(None, alias="inlineObjectPropertiesSuggestionState")


class SuggestedPositionedObjectProperties(BaseModel):
    """A suggested change to PositionedObjectProperties."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    positioned_object_properties: PositionedObjectProperties | None = Field(
        None, alias="positionedObjectProperties"
    )
    positioned_object_properties_suggestion_state: (
        PositionedObjectPropertiesSuggestionState | None
    ) = Field(None, alias="positionedObjectPropertiesSuggestionState")


class NamedStyles(BaseModel):
    """The named styles. Paragraphs in the document can inherit their TextStyle and ParagraphStyle from these named styles."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    styles: list[NamedStyle] | None = Field(None)


class Request(BaseModel):
    """A single update to apply to a document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    add_document_tab: AddDocumentTabRequest | None = Field(None, alias="addDocumentTab")
    create_footer: CreateFooterRequest | None = Field(None, alias="createFooter")
    create_footnote: CreateFootnoteRequest | None = Field(None, alias="createFootnote")
    create_header: CreateHeaderRequest | None = Field(None, alias="createHeader")
    create_named_range: CreateNamedRangeRequest | None = Field(
        None, alias="createNamedRange"
    )
    create_paragraph_bullets: CreateParagraphBulletsRequest | None = Field(
        None, alias="createParagraphBullets"
    )
    delete_content_range: DeleteContentRangeRequest | None = Field(
        None, alias="deleteContentRange"
    )
    delete_footer: DeleteFooterRequest | None = Field(None, alias="deleteFooter")
    delete_header: DeleteHeaderRequest | None = Field(None, alias="deleteHeader")
    delete_named_range: DeleteNamedRangeRequest | None = Field(
        None, alias="deleteNamedRange"
    )
    delete_paragraph_bullets: DeleteParagraphBulletsRequest | None = Field(
        None, alias="deleteParagraphBullets"
    )
    delete_positioned_object: DeletePositionedObjectRequest | None = Field(
        None, alias="deletePositionedObject"
    )
    delete_tab: DeleteTabRequest | None = Field(None, alias="deleteTab")
    delete_table_column: DeleteTableColumnRequest | None = Field(
        None, alias="deleteTableColumn"
    )
    delete_table_row: DeleteTableRowRequest | None = Field(None, alias="deleteTableRow")
    insert_date: InsertDateRequest | None = Field(None, alias="insertDate")
    insert_inline_image: InsertInlineImageRequest | None = Field(
        None, alias="insertInlineImage"
    )
    insert_page_break: InsertPageBreakRequest | None = Field(
        None, alias="insertPageBreak"
    )
    insert_person: InsertPersonRequest | None = Field(None, alias="insertPerson")
    insert_section_break: InsertSectionBreakRequest | None = Field(
        None, alias="insertSectionBreak"
    )
    insert_table: InsertTableRequest | None = Field(None, alias="insertTable")
    insert_table_column: InsertTableColumnRequest | None = Field(
        None, alias="insertTableColumn"
    )
    insert_table_row: InsertTableRowRequest | None = Field(None, alias="insertTableRow")
    insert_text: InsertTextRequest | None = Field(None, alias="insertText")
    merge_table_cells: MergeTableCellsRequest | None = Field(
        None, alias="mergeTableCells"
    )
    pin_table_header_rows: PinTableHeaderRowsRequest | None = Field(
        None, alias="pinTableHeaderRows"
    )
    replace_all_text: ReplaceAllTextRequest | None = Field(None, alias="replaceAllText")
    replace_image: ReplaceImageRequest | None = Field(None, alias="replaceImage")
    replace_named_range_content: ReplaceNamedRangeContentRequest | None = Field(
        None, alias="replaceNamedRangeContent"
    )
    unmerge_table_cells: UnmergeTableCellsRequest | None = Field(
        None, alias="unmergeTableCells"
    )
    update_document_style: UpdateDocumentStyleRequest | None = Field(
        None, alias="updateDocumentStyle"
    )
    update_document_tab_properties: UpdateDocumentTabPropertiesRequest | None = Field(
        None, alias="updateDocumentTabProperties"
    )
    update_paragraph_style: UpdateParagraphStyleRequest | None = Field(
        None, alias="updateParagraphStyle"
    )
    update_section_style: UpdateSectionStyleRequest | None = Field(
        None, alias="updateSectionStyle"
    )
    update_table_cell_style: UpdateTableCellStyleRequest | None = Field(
        None, alias="updateTableCellStyle"
    )
    update_table_column_properties: UpdateTableColumnPropertiesRequest | None = Field(
        None, alias="updateTableColumnProperties"
    )
    update_table_row_style: UpdateTableRowStyleRequest | None = Field(
        None, alias="updateTableRowStyle"
    )
    update_text_style: UpdateTextStyleRequest | None = Field(
        None, alias="updateTextStyle"
    )


class SuggestedListProperties(BaseModel):
    """A suggested change to ListProperties."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    list_properties: ListProperties | None = Field(None, alias="listProperties")
    list_properties_suggestion_state: ListPropertiesSuggestionState | None = Field(
        None, alias="listPropertiesSuggestionState"
    )


class ParagraphElement(BaseModel):
    """A ParagraphElement describes content within a Paragraph."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    auto_text: AutoText | None = Field(None, alias="autoText")
    column_break: ColumnBreak | None = Field(None, alias="columnBreak")
    date_element: DateElement | None = Field(None, alias="dateElement")
    end_index: int | None = Field(None, alias="endIndex")
    equation: Equation | None = Field(None)
    footnote_reference: FootnoteReference | None = Field(
        None, alias="footnoteReference"
    )
    horizontal_rule: HorizontalRule | None = Field(None, alias="horizontalRule")
    inline_object_element: InlineObjectElement | None = Field(
        None, alias="inlineObjectElement"
    )
    page_break: PageBreak | None = Field(None, alias="pageBreak")
    person: Person | None = Field(None)
    rich_link: RichLink | None = Field(None, alias="richLink")
    start_index: int | None = Field(None, alias="startIndex")
    text_run: TextRun | None = Field(None, alias="textRun")


class InlineObject(BaseModel):
    """An object that appears inline with text. An InlineObject contains an EmbeddedObject such as an image."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    inline_object_properties: InlineObjectProperties | None = Field(
        None, alias="inlineObjectProperties"
    )
    object_id: str | None = Field(None, alias="objectId")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_inline_object_properties_changes: (
        dict[str, SuggestedInlineObjectProperties] | None
    ) = Field(None, alias="suggestedInlineObjectPropertiesChanges")
    suggested_insertion_id: str | None = Field(None, alias="suggestedInsertionId")


class PositionedObject(BaseModel):
    """An object that's tethered to a Paragraph and positioned relative to the beginning of the paragraph. A PositionedObject contains an EmbeddedObject such as an image."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    object_id: str | None = Field(None, alias="objectId")
    positioned_object_properties: PositionedObjectProperties | None = Field(
        None, alias="positionedObjectProperties"
    )
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_id: str | None = Field(None, alias="suggestedInsertionId")
    suggested_positioned_object_properties_changes: (
        dict[str, SuggestedPositionedObjectProperties] | None
    ) = Field(None, alias="suggestedPositionedObjectPropertiesChanges")


class SuggestedNamedStyles(BaseModel):
    """A suggested change to the NamedStyles."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    named_styles: NamedStyles | None = Field(None, alias="namedStyles")
    named_styles_suggestion_state: NamedStylesSuggestionState | None = Field(
        None, alias="namedStylesSuggestionState"
    )


class BatchUpdateDocumentRequest(BaseModel):
    """Request message for BatchUpdateDocument."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    requests: list[Request] | None = Field(None)
    write_control: WriteControl | None = Field(None, alias="writeControl")


class List(BaseModel):
    """A List represents the list attributes for a group of paragraphs that all belong to the same list. A paragraph that's part of a list has a reference to the list's ID in its bullet."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    list_properties: ListProperties | None = Field(None, alias="listProperties")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_id: str | None = Field(None, alias="suggestedInsertionId")
    suggested_list_properties_changes: dict[str, SuggestedListProperties] | None = (
        Field(None, alias="suggestedListPropertiesChanges")
    )


class Paragraph(BaseModel):
    """A StructuralElement representing a paragraph. A paragraph is a range of content that's terminated with a newline character."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bullet: Bullet | None = Field(None)
    elements: list[ParagraphElement] | None = Field(None)
    paragraph_style: ParagraphStyle | None = Field(None, alias="paragraphStyle")
    positioned_object_ids: list[str] | None = Field(None, alias="positionedObjectIds")
    suggested_bullet_changes: dict[str, SuggestedBullet] | None = Field(
        None, alias="suggestedBulletChanges"
    )
    suggested_paragraph_style_changes: dict[str, SuggestedParagraphStyle] | None = (
        Field(None, alias="suggestedParagraphStyleChanges")
    )
    suggested_positioned_object_ids: dict[str, ObjectReferences] | None = Field(
        None, alias="suggestedPositionedObjectIds"
    )


class Body(BaseModel):
    """The document body. The body typically contains the full document contents except for headers, footers, and footnotes."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[StructuralElement] | None = Field(None)


class Document(BaseModel):
    """A Google Docs document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    body: Body | None = Field(None)
    document_id: str | None = Field(None, alias="documentId")
    document_style: DocumentStyle | None = Field(None, alias="documentStyle")
    footers: dict[str, Footer] | None = Field(None)
    footnotes: dict[str, Footnote] | None = Field(None)
    headers: dict[str, Header] | None = Field(None)
    inline_objects: dict[str, InlineObject] | None = Field(None, alias="inlineObjects")
    lists: dict[str, List] | None = Field(None)
    named_ranges: dict[str, NamedRanges] | None = Field(None, alias="namedRanges")
    named_styles: NamedStyles | None = Field(None, alias="namedStyles")
    positioned_objects: dict[str, PositionedObject] | None = Field(
        None, alias="positionedObjects"
    )
    revision_id: str | None = Field(None, alias="revisionId")
    suggested_document_style_changes: dict[str, SuggestedDocumentStyle] | None = Field(
        None, alias="suggestedDocumentStyleChanges"
    )
    suggested_named_styles_changes: dict[str, SuggestedNamedStyles] | None = Field(
        None, alias="suggestedNamedStylesChanges"
    )
    suggestions_view_mode: DocumentSuggestionsViewMode | None = Field(
        None, alias="suggestionsViewMode"
    )
    tabs: list[Tab] | None = Field(None)
    title: str | None = Field(None)


class DocumentTab(BaseModel):
    """A tab with document contents."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    body: Body | None = Field(None)
    document_style: DocumentStyle | None = Field(None, alias="documentStyle")
    footers: dict[str, Footer] | None = Field(None)
    footnotes: dict[str, Footnote] | None = Field(None)
    headers: dict[str, Header] | None = Field(None)
    inline_objects: dict[str, InlineObject] | None = Field(None, alias="inlineObjects")
    lists: dict[str, List] | None = Field(None)
    named_ranges: dict[str, NamedRanges] | None = Field(None, alias="namedRanges")
    named_styles: NamedStyles | None = Field(None, alias="namedStyles")
    positioned_objects: dict[str, PositionedObject] | None = Field(
        None, alias="positionedObjects"
    )
    suggested_document_style_changes: dict[str, SuggestedDocumentStyle] | None = Field(
        None, alias="suggestedDocumentStyleChanges"
    )
    suggested_named_styles_changes: dict[str, SuggestedNamedStyles] | None = Field(
        None, alias="suggestedNamedStylesChanges"
    )


class Footer(BaseModel):
    """A document footer."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[StructuralElement] | None = Field(None)
    footer_id: str | None = Field(None, alias="footerId")


class Footnote(BaseModel):
    """A document footnote."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[StructuralElement] | None = Field(None)
    footnote_id: str | None = Field(None, alias="footnoteId")


class Header(BaseModel):
    """A document header."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[StructuralElement] | None = Field(None)
    header_id: str | None = Field(None, alias="headerId")


class StructuralElement(BaseModel):
    """A StructuralElement describes content that provides structure to the document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_index: int | None = Field(None, alias="endIndex")
    paragraph: Paragraph | None = Field(None)
    section_break: SectionBreak | None = Field(None, alias="sectionBreak")
    start_index: int | None = Field(None, alias="startIndex")
    table: Table | None = Field(None)
    table_of_contents: TableOfContents | None = Field(None, alias="tableOfContents")


class Tab(BaseModel):
    """A tab in a document."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    child_tabs: list[Tab] | None = Field(None, alias="childTabs")
    document_tab: DocumentTab | None = Field(None, alias="documentTab")
    tab_properties: TabProperties | None = Field(None, alias="tabProperties")


class Table(BaseModel):
    """A StructuralElement representing a table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    columns: int | None = Field(None)
    rows: int | None = Field(None)
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    table_rows: list[TableRow] | None = Field(None, alias="tableRows")
    table_style: TableStyle | None = Field(None, alias="tableStyle")


class TableCell(BaseModel):
    """The contents and style of a cell in a Table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[StructuralElement] | None = Field(None)
    end_index: int | None = Field(None, alias="endIndex")
    start_index: int | None = Field(None, alias="startIndex")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_table_cell_style_changes: dict[str, SuggestedTableCellStyle] | None = (
        Field(None, alias="suggestedTableCellStyleChanges")
    )
    table_cell_style: TableCellStyle | None = Field(None, alias="tableCellStyle")


class TableOfContents(BaseModel):
    """A StructuralElement representing a table of contents."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[StructuralElement] | None = Field(None)
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )


class TableRow(BaseModel):
    """The contents and style of a row in a Table."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    end_index: int | None = Field(None, alias="endIndex")
    start_index: int | None = Field(None, alias="startIndex")
    suggested_deletion_ids: list[str] | None = Field(None, alias="suggestedDeletionIds")
    suggested_insertion_ids: list[str] | None = Field(
        None, alias="suggestedInsertionIds"
    )
    suggested_table_row_style_changes: dict[str, SuggestedTableRowStyle] | None = Field(
        None, alias="suggestedTableRowStyleChanges"
    )
    table_cells: list[TableCell] | None = Field(None, alias="tableCells")
    table_row_style: TableRowStyle | None = Field(None, alias="tableRowStyle")
