# Adding Charts

> **Source**: [Google Slides API - Add Chart](https://developers.google.com/workspace/slides/api/guides/add-chart)

## Overview

The Google Slides API enables developers to embed charts from Google Sheets into presentations, enhancing data visualization capabilities.

## Workflow

1. Create a chart in Google Sheets
2. Retrieve the chart ID using the Sheets API
3. Use `CreateSheetsChartRequest` to add it to a slide
4. Apply `RefreshSheetsChartRequest` when needed to sync changes

## CreateSheetsChartRequest

```json
{
  "createSheetsChart": {
    "objectId": "my_chart_id",
    "spreadsheetId": "spreadsheet_id_here",
    "chartId": 12345,
    "linkingMode": "LINKED",
    "elementProperties": {
      "pageObjectId": "slide_id",
      "size": {
        "width": {"magnitude": 6000000, "unit": "EMU"},
        "height": {"magnitude": 4000000, "unit": "EMU"}
      },
      "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": 100000,
        "translateY": 100000,
        "unit": "EMU"
      }
    }
  }
}
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `objectId` | string | No | Unique identifier for the embedded chart |
| `spreadsheetId` | string | Yes | Source spreadsheet ID |
| `chartId` | integer | Yes | Chart ID from Google Sheets |
| `linkingMode` | enum | No | LINKED or NOT_LINKED_IMAGE |
| `elementProperties` | object | No | Size and position |

## Linking Modes

### LINKED Mode

```json
{
  "linkingMode": "LINKED"
}
```

- Chart can be refreshed to reflect changes in underlying data
- Collaborators can access the source spreadsheet
- Enables future updates via refresh operations

### NOT_LINKED_IMAGE (Static) Mode

```json
{
  "linkingMode": "NOT_LINKED_IMAGE"
}
```

- Chart remains unchanged permanently
- Hides the source spreadsheet from collaborators
- Cannot be refreshed after embedding

## Getting Chart ID from Sheets

Use the Sheets API to retrieve chart information:

```http
GET https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}?fields=sheets.charts
```

Response:

```json
{
  "sheets": [
    {
      "charts": [
        {
          "chartId": 12345,
          "position": {...},
          "spec": {...}
        }
      ]
    }
  ]
}
```

## Refreshing Charts

### RefreshSheetsChartRequest

```json
{
  "refreshSheetsChart": {
    "objectId": "my_chart_id"
  }
}
```

This updates the chart to reflect current spreadsheet data. Only works for LINKED charts.

## Required OAuth Scopes

Adding charts requires one of these scopes:

| Scope | Access Level |
|-------|-------------|
| `https://www.googleapis.com/auth/spreadsheets.readonly` | Recommended - read-only |
| `https://www.googleapis.com/auth/spreadsheets` | Full spreadsheet access |
| `https://www.googleapis.com/auth/drive.readonly` | Read-only Drive access |
| `https://www.googleapis.com/auth/drive` | Full Drive access |

## Complete Example

```json
{
  "requests": [
    {
      "createSheetsChart": {
        "objectId": "sales_chart",
        "spreadsheetId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "chartId": 12345,
        "linkingMode": "LINKED",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": {
            "width": {"magnitude": 6000000, "unit": "EMU"},
            "height": {"magnitude": 4000000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 1500000,
            "translateY": 1000000,
            "unit": "EMU"
          }
        }
      }
    }
  ]
}
```

## Response

```json
{
  "replies": [
    {
      "createSheetsChart": {
        "objectId": "sales_chart"
      }
    }
  ]
}
```

## Supported Chart Types

The API supports any chart type available in Google Sheets:

- Bar charts
- Line charts
- Pie charts
- Area charts
- Scatter charts
- Column charts
- Combo charts
- And more...

## Related Documentation

- [Merge Guide](./merge.md) - Replacing shapes with charts
- [Add Image](./add-image.md) - Adding images
- [Batch Updates](./batch.md) - Efficient API usage
- [Page Elements](../concepts/page-elements.md) - Element types
