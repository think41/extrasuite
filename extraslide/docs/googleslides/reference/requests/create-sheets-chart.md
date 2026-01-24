# CreateSheetsChartRequest

Creates an embedded Google Sheets chart. NOTE: Chart creation requires at least one of the spreadsheets.readonly, spreadsheets, drive.readonly, drive.file, or drive OAuth scopes.

## Schema

```json
{
  "createSheetsChart": {
    "objectId": string,
    "elementProperties": [PageElementProperties],
    "spreadsheetId": string,
    "chartId": integer,
    "linkingMode": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | A user-supplied object ID. If specified, the ID must be unique among all pages and page elements ... |
| `elementProperties` | [PageElementProperties] | No | The element properties for the chart. When the aspect ratio of the provided size does not match t... |
| `spreadsheetId` | string | No | The ID of the Google Sheets spreadsheet that contains the chart. You might need to add a resource... |
| `chartId` | integer | No | The ID of the specific chart in the Google Sheets spreadsheet. |
| `linkingMode` | string | No | The mode with which the chart is linked to the source spreadsheet. When not specified, the chart ... |

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
      "createSheetsChart": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [PageElementProperties](../objects/page-element-properties.md)

