ExtraSuite - edit Google Workspace files with AI agents using a local pull-edit-push workflow.

## Modules

  sheet      Google Sheets (spreadsheets, formulas, charts)
  slide      Google Slides (presentations, SML markup)
  doc        Google Docs (documents, XML markup)
  form       Google Forms (surveys, quizzes)
  script     Google Apps Script (standalone and bound scripts)
  gmail      Gmail (compose drafts from markdown files)
  calendar   Google Calendar (view events)

## Core Workflow (sheet, slide, doc, form, script)

  extrasuite <module> pull <url>     Download file to local folder
  # Edit local files
  extrasuite <module> push <folder>  Apply changes to Google

After push, always re-pull before making more changes.

## Auth

Automatic. On first use, a browser window opens for Google login.
Tokens are cached in ~/.config/extrasuite/. No manual setup needed.

## Discovery

  extrasuite <module> --help           Module overview: workflow, files, key rules
  extrasuite <module> <cmd> --help     Command flags and format reference
