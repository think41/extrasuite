# ExtraSheet: Current Gaps

This file tracks the parts of the pulled representation that are still read-only
or only partially supported during diff/push.

## Pull-Only Root Files

These files are emitted on pull but ignored on push:

- `theme.json`
- `developer_metadata.json`
- `data_sources.json`

## Pull-Only Sheet Files Or Sections

- `protection.json`
- `dimension.json.rowGroups`
- `dimension.json.columnGroups`
- `dimension.json.developerMetadata`
- `dimension.json` row/column `developerMetadata`

Row/column `pixelSize` and `hidden` are supported. The grouping and metadata
sections are not.

## Spreadsheet Properties Not Pushed

`spreadsheet.json.properties` currently supports only:

- `title`

These are informational only:

- `locale`
- `autoRecalc`
- `timeZone`

## Comments Limits

`comments.json` supports:

- new replies
- resolving existing comments

It does not support:

- creating new top-level comments
- relocating comments by cell reference

## Data Source Tables

`data-source-tables.json` is only partially supported:

- Refresh/modify style updates are supported
- Add/delete is not

## Not Extracted

These still are not represented in the local file model:

- smart chips
- embedded images as editable artifacts
- version history
