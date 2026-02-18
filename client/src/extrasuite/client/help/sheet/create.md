Create a new Google Spreadsheet and share it with your service account.

## Usage

  extrasuite sheet create <title>

## Arguments

  title    Title for the new spreadsheet

## Output

Prints the spreadsheet URL and the service account email it was shared with.
Also prints the pull command to start editing immediately.

## Next Steps

After creating, pull the spreadsheet to start editing:

  extrasuite sheet pull <url>

## Notes

- The spreadsheet is owned by your Google account
- It is automatically shared with your service account (editor access)
- The service account email is printed so you can share additional files with it
