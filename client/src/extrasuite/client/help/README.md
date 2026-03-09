ExtraSuite - edit Google Workspace files with AI agents using a local pull-edit-push workflow.

## Modules

  sheet      Google Sheets (spreadsheets, formulas, charts)
  slide      Google Slides (presentations, SML markup)
  doc        Google Docs (documents, XML markup)
  form       Google Forms (surveys, quizzes)
  script     Google Apps Script (standalone and bound scripts)
  gmail      Gmail (compose drafts, read and reply to emails)
  calendar   Google Calendar (view, search, create, and manage events)
  drive      Google Drive (browse and search files)
  contacts   Google Contacts (sync and search for email addresses)

## Core Workflow (sheet, slide, doc, form, script)

  extrasuite <module> pull <url> [output_dir]    # Convert google workspace file to local files inside <output_dir>/<file-id>
  # Edit files inside <output_dir>/<file-id>
  extrasuite <module> push <folder>  # Identify changes made and apply them to the google workspace file

Make all changes locally and push once when done. Always re-pull before making further changes.

## Discovery

  extrasuite <module> --help           Module overview: workflow, files, key rules
  extrasuite <module> <cmd> --help     Command flags and format reference (self-contained, no need to read module --help first)
