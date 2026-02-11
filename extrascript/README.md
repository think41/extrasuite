# extrascript

Google Apps Script management for LLM agents. Part of [ExtraSuite](https://github.com/think41/extrasuite).

Pull, edit, push, and lint Google Apps Script projects. Supports both standalone and container-bound scripts.

## Install

```bash
pip install extrascript
# or
uvx extrascript
```

## Usage

```bash
# Pull a script project to local files
extrascript pull <script_id_or_url> [output_dir]

# Edit files locally, then check what changed
extrascript diff <folder>

# Lint before pushing
extrascript lint <folder>

# Push changes back to Google
extrascript push <folder>

# Create a new script (standalone)
extrascript create "My Script"

# Create a bound script (attached to a spreadsheet)
extrascript create "Sheet Script" --bind-to https://docs.google.com/spreadsheets/d/FILE_ID/edit
```
