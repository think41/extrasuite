Download a Google Apps Script project to a local folder.

## Usage

  extrasuite script pull <url> [output_dir]

## Arguments

  url           Script URL or ID (from script.google.com)
  output_dir    Output directory (default: current directory)

## Flags

  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

Creates <output_dir>/<script_id>/ with:

  project.json    Project metadata and appsscript.json manifest
  Code.js         Script source files (one per file in the project)
  *.html          HTML files (if any)
  .pristine/      Snapshot for diff/push comparison - do not edit
  .raw/           Raw API responses for debugging - do not edit

## Example

  extrasuite script pull https://script.google.com/d/abc123/edit
