Download a Google Apps Script project to a local folder.

## Usage

  extrasuite script pull <url> [output_dir]

## Arguments

  url           Script URL or ID (from script.google.com)
  output_dir    Output directory (optional)

## Flags

  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

If output_dir is given, files are created directly in output_dir.
Otherwise, creates <script_id>/ in the current directory.

The folder contains:

  project.json    Project metadata and appsscript.json manifest
  Code.js         Script source files (one per file in the project)
  *.html          HTML files (if any)
  .pristine/      Snapshot for diff/push comparison - do not edit
  .raw/           Raw API responses for debugging - do not edit

## Example

  extrasuite script pull https://script.google.com/d/abc123/edit
