Create a new Google Apps Script project.

## Usage

  extrasuite script create <title> [output_dir]

## Arguments

  title       Project title
  output_dir  Output directory (default: current directory)

## Flags

  --bind-to <url>   Bind to an existing Google Drive file (Sheet, Doc, etc.)

## Output

Prints the script URL and creates the initial project folder locally.

## Notes

Without --bind-to, creates a standalone script.
With --bind-to, creates a container-bound script attached to the specified file.

## Next Steps

After creating, edit the .js files and push:

  extrasuite script push <folder>
