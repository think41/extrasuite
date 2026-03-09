Google Apps Script - edit standalone and container-bound scripts via local JS/HTML files.

## Workflow

  extrasuite script pull <url> [output_dir]   Download script project
  # Edit .js and .html files in <output_dir>/<script_id>/
  extrasuite script push <folder>             Apply changes to Apps Script
  extrasuite script create <title>            Create a new standalone script

See `extrasuite script pull --help` for directory layout and flags (self-contained).

## Files to Edit

Edit .js and .html files directly. The file names match the script editor.
project.json contains the appsscript.json manifest - edit for time zones,
OAuth scopes, and add-on configuration.

## Commands

  extrasuite script pull --help     Pull flags and folder layout
  extrasuite script push --help     Push flags (includes lint)
  extrasuite script diff --help     Show changed files (no auth needed)
  extrasuite script create --help   Create a new script project
  extrasuite script lint --help     Lint without pushing
