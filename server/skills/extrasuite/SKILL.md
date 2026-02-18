---
name: extrasuite
description: Read, write, and edit Google Workspace files (Sheets, Slides, Docs, Forms, Apps Script, Gmail, Calendar). Use when the user asks to work with any Google Workspace file or shares a docs.google.com URL.
---

# ExtraSuite

Edit Google Workspace files locally using a pull-edit-push workflow.

## Getting Started

```bash
uvx extrasuite --help
```

No installation needed. `uvx` downloads and runs the latest version automatically.
If `uvx` is not available, install it with: `pip install uv`

## Discovering Commands

```bash
uvx extrasuite --help                    # All modules and core workflow
uvx extrasuite <module> --help           # Module overview: workflow, file format, key rules
uvx extrasuite <module> <cmd> --help     # Command flags and format reference
```

Run `--help` at each level before starting. The help output is the documentation.

## Workflow (Sheets, Slides, Docs, Forms, Apps Script)

```bash
uvx extrasuite <module> pull <url>    # Download file to local folder
# Edit local files
uvx extrasuite <module> push <folder> # Apply changes to Google
# Re-pull before making further changes
```

## Auth

Fully automatic. A browser window opens on first use; tokens are cached and
reused on subsequent runs. Never read token files or make direct API calls —
use the CLI only. The CLI is the authentication boundary.

## diff is a Debugging Tool

`diff` shows the API requests that `push` would send. Skip it in normal
workflow — go directly from editing to push. Only use diff when a push
produces unexpected results and you need to inspect the generated requests.

## Gmail and Calendar

```bash
uvx extrasuite gmail compose <file>   # Save draft from markdown file
uvx extrasuite calendar view          # View today's events
```

---

## Team-Specific Guidance

<!-- Add your team's conventions below. Examples:
- Color palette: primary #1a73e8, secondary #34a853, accent #ea4335
- Document templates: all docs start with a summary section
- Sheet conventions: header row always row 1, bold + background #e8f0fe
- Slide conventions: 16:9, Roboto font, company theme colors
- Naming conventions: file names use kebab-case
-->
