# RefreshSheetsChartRequest

Refreshes an embedded Google Sheets chart by replacing it with the latest version of the chart from Google Sheets. NOTE: Refreshing charts requires at least one of the spreadsheets.readonly, spreadsheets, drive.readonly, or drive OAuth scopes.

## Schema

```json
{
  "refreshSheetsChart": {
    "objectId": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the chart to refresh. |

## Example

```json
{
  "requests": [
    {
      "refreshSheetsChart": {
        // Properties here
      }
    }
  ]
}
```

