Google Apps Script - edit standalone and container-bound scripts via local JS/HTML files.

## Workflow

  extrasuite script pull <url> [output_dir]   Download script project
  # Edit .js and .html files in <output_dir>/<script_id>/
  extrasuite script push <folder>             Apply changes to Apps Script
  extrasuite script create <title>            Create a new standalone script

After push, always re-pull before making more changes.

## Directory Structure

  <script_id>/
    project.json    Project metadata and manifest (appsscript.json content)
    Code.js         Script files (one per file in the project)
    Utilities.js
    Page.html       HTML files (if any)
    .pristine/      Internal state - do not edit
    .raw/           Raw API responses - do not edit

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
