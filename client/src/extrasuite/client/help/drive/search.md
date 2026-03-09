Search Google Drive files visible to the service account using a query string.

## Usage

  extrasuite drive search <query> [--max N] [--page TOKEN]

## Arguments

  query    Drive query string (see Google Drive query syntax below)

## Options

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  --max N         Maximum number of files to return (default: 20)
  --page TOKEN    Page token for pagination (printed at the end of previous output)

## Output

Prints a table with columns: NAME, TYPE, MODIFIED, URL.

## Query Syntax Examples

  name contains 'budget'
  mimeType = 'application/vnd.google-apps.spreadsheet'
  modifiedTime > '2025-01-01T00:00:00'
  name contains 'report' and mimeType = 'application/vnd.google-apps.document'

## Examples

  extrasuite drive search "name contains 'budget'" --reason "state the user's intent that led to this command"
  extrasuite drive search "mimeType = 'application/vnd.google-apps.spreadsheet'"

## Notes

- Results are limited to files shared with your service account.
- See https://developers.google.com/drive/api/guides/search-files for full query syntax.
