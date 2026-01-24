# LayoutReference

Slide layout reference. This may reference either: - A predefined layout - One of the layouts in the presentation.

## Schema

```json
{
  "predefinedLayout": string,
  "layoutId": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `predefinedLayout` | string | Predefined layout. |
| `layoutId` | string | Layout ID: the object ID of one of the layouts in the presentation. |

### predefinedLayout Values

| Value | Description |
|-------|-------------|
| `PREDEFINED_LAYOUT_UNSPECIFIED` | Unspecified layout. |
| `BLANK` | Blank layout, with no placeholders. |
| `CAPTION_ONLY` | Layout with a caption at the bottom. |
| `TITLE` | Layout with a title and a subtitle. |
| `TITLE_AND_BODY` | Layout with a title and body. |
| `TITLE_AND_TWO_COLUMNS` | Layout with a title and two columns. |
| `TITLE_ONLY` | Layout with only a title. |
| `SECTION_HEADER` | Layout with a section title. |
| `SECTION_TITLE_AND_DESCRIPTION` | Layout with a title and subtitle on one side and description on the other. |
| `ONE_COLUMN_TEXT` | Layout with one title and one body, arranged in a single column. |
| `MAIN_POINT` | Layout with a main point. |
| `BIG_NUMBER` | Layout with a big number heading. |

