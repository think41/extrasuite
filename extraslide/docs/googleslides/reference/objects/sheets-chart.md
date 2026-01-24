# SheetsChart

A PageElement kind representing a linked chart embedded from Google Sheets.

## Schema

```json
{
  "spreadsheetId": string,
  "chartId": integer,
  "contentUrl": string,
  "sheetsChartProperties": [SheetsChartProperties]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `spreadsheetId` | string | The ID of the Google Sheets spreadsheet that contains the source chart. |
| `chartId` | integer | The ID of the specific chart in the Google Sheets spreadsheet that is embedded. |
| `contentUrl` | string | The URL of an image of the embedded chart, with a default lifetime of 30 minutes. This URL is tag... |
| `sheetsChartProperties` | [SheetsChartProperties] | The properties of the Sheets chart. |

## Related Objects

- [SheetsChartProperties](./sheets-chart-properties.md)

