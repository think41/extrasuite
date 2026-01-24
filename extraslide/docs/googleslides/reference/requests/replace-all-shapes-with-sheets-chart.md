# ReplaceAllShapesWithSheetsChartRequest

Replaces all shapes that match the given criteria with the provided Google Sheets chart. The chart will be scaled and centered to fit within the bounds of the original shape. NOTE: Replacing shapes with a chart requires at least one of the spreadsheets.readonly, spreadsheets, drive.readonly, or drive OAuth scopes.

## Schema

```json
{
  "replaceAllShapesWithSheetsChart": {
    "containsText": [SubstringMatchCriteria],
    "spreadsheetId": string,
    "chartId": integer,
    "linkingMode": string,
    "pageObjectIds": array of string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `containsText` | [SubstringMatchCriteria] | No | The criteria that the shapes must match in order to be replaced. The request will replace all of ... |
| `spreadsheetId` | string | No | The ID of the Google Sheets spreadsheet that contains the chart. |
| `chartId` | integer | No | The ID of the specific chart in the Google Sheets spreadsheet. |
| `linkingMode` | string | No | The mode with which the chart is linked to the source spreadsheet. When not specified, the chart ... |
| `pageObjectIds` | array of string | No | If non-empty, limits the matches to page elements only on the given pages. Returns a 400 bad requ... |

### linkingMode Values

| Value | Description |
|-------|-------------|
| `NOT_LINKED_IMAGE` | The chart is not associated with the source spreadsheet and cannot be updated. A chart that is no... |
| `LINKED` | Linking the chart allows it to be updated, and other collaborators will see a link to the spreads... |

## Example

```json
{
  "requests": [
    {
      "replaceAllShapesWithSheetsChart": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [SubstringMatchCriteria](../objects/substring-match-criteria.md)

