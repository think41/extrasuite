ExtraSuite - edit Google Workspace files with AI agents using a local pull-edit-push workflow.

## Modules

  sheets     Google Sheets (spreadsheets, formulas, charts)
  slides     Google Slides (presentations, SML markup)
  docs       Google Docs (documents, markdown)
  forms      Google Forms (surveys, quizzes)
  script     Google Apps Script (standalone and bound scripts)
  gmail      Gmail (compose drafts, read and reply to emails)
  calendar   Google Calendar (view, search, create, and manage events)
  drive      Google Drive (browse and search files)
  contacts   Google Contacts (sync and search for email addresses)

## Core Workflow (sheets, slides, docs, forms, script)

  extrasuite <module> pull <url> [output_dir]    # Download to a local folder
  # Edit the local files
  extrasuite <module> push <folder>              # Apply changes to Google

Make all changes locally and push once when done. Always re-pull before making further changes.

## Discovery

  extrasuite <module> --help    Workflow, file format, and editing rules for that module
