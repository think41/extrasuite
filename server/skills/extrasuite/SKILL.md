---
name: extrasuite
description: CRUD on google workspace files - Sheets, Slides, Docs, Forms. Compose drafts in Gmail. Fuzzy search through Contacts. Manage Google Calendar and App Script projects. 
---

ExtraSuite is a CLI for Google Workspace. Auth is automatic — a browser window opens on first use, tokens are cached after. Files must be shared with the user's service account before the agent can access them.

The `extrasuite` command is available via `uvx`. Discover commands using `--help`.

```bash
uvx extrasuite@latest --help
uvx extrasuite <module> --help           # Module overview. Skip @latest for subsequent commands
uvx extrasuite <module> <cmd> --help     # Command flags and format reference
```

## Workflow for Sheets, Slides, Docs, Forms, and App Script

Use the `create` command to create a new file.

```bash
uvx extrasuite sheet create "Financial Model for Q2"
uvx extrasuite doc create "Project Proposal"
```

`pull` downloads the file as editable local files. Edit them, then `push` to sync changes back.

```bash
uvx extrasuite sheet pull "https://docs.google.com/spreadsheets/..." <basefolder>
uvx extrasuite sheet push <basefolder>/<document-id>
```

The same workflow applies for `slide`, `doc`, `form`, and `script`.

## Gmail, Calendar, and Contacts

```bash
uvx extrasuite gmail compose <file>     # Save draft from markdown file
uvx extrasuite calendar view            # View today's events
uvx extrasuite contacts search "alice" "acme corp"  # Multiple queries, fuzzy match
```
