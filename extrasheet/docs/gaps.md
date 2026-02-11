# ExtraSheet: Push Gaps

Remaining properties that are extracted and stored on pull but not supported during push.

## Data Source Tables (data-source-tables.json)

| Operation | Supported? |
|-----------|-----------|
| Refresh | Yes |
| Add | **No** |
| Delete | **No** |

Low priority — these are rarely used and typically managed through the Google Sheets UI.

## Resolved Gaps

The following gaps have been fixed:

- **Format properties:** `wrapStrategy`, `padding`, `textDirection`, `textRotation` — added to `_convert_to_cell_format()` and `_get_format_fields()`
- **Borders:** Uses `updateBorders` request via `_build_update_borders_request()`
- **Dimension hidden:** `hidden` property diffed and pushed as `hiddenByUser`
- **Dimension deletion:** Resets to default pixelSize (21px rows, 100px columns)
- **Format rule deletion:** Clears formatting via `repeatCell` with empty format + `updateBorders` with `NONE` style
- **tabColor/tabColorStyle:** Diffed and pushed via `updateSheetProperties` with `tabColorStyle`
- **rightToLeft:** Diffed and pushed via `updateSheetProperties`
