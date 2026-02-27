List files in Google Drive that are visible to the service account.

## Usage

  extrasuite drive ls [--folder URL] [--max N] [--page TOKEN]

## Options

  --folder URL    Limit listing to files inside this folder (URL or folder ID)
  --max N         Maximum number of files to return (default: 20)
  --page TOKEN    Page token for pagination (printed at the end of previous output)

## Output

Prints a table with columns: NAME, TYPE, MODIFIED, URL.

## Examples

  extrasuite drive ls
  extrasuite drive ls --folder https://drive.google.com/drive/folders/FOLDER_ID
  extrasuite drive ls --max 50

## Notes

- Files are ordered by last modified time (most recent first).
- Only files shared with your service account are shown.
- Use `drive search` for full-text or metadata queries.
