Create a new Google Spreadsheet, share it with your service account, and pull it locally.

## Usage

  extrasuite sheets create <title> [output_dir]

## Arguments

  title       Title for the new spreadsheet
  output_dir  Directory to pull the file into after creation (optional).
              If omitted, creates <spreadsheet_id>/ in the current directory.

## Output

Prints the spreadsheet URL and the service account email it was shared with.
Then automatically pulls the spreadsheet into output_dir (or <spreadsheet_id>/).

## Notes

- The spreadsheet is owned by your Google account
- It is automatically shared with your service account (editor access)
- The service account email is printed so you can share additional files with it
