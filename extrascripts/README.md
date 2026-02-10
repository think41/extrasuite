# extrascripts

Google Apps Script management for LLM agents. Part of [ExtraSuite](https://github.com/think41/extrasuite).

Pull, edit, push, run, and lint Google Apps Script projects. Supports both standalone and container-bound scripts.

## Install

```bash
pip install extrascripts
# or
uvx extrascripts
```

## Usage

```bash
# Pull a script project to local files
extrascripts pull <script_id_or_url> [output_dir]

# Edit files locally, then check what changed
extrascripts diff <folder>

# Lint before pushing
extrascripts lint <folder>

# Push changes back to Google
extrascripts push <folder>

# Create a new script (standalone)
extrascripts create "My Script"

# Create a bound script (attached to a spreadsheet)
extrascripts create "Sheet Script" --bind-to https://docs.google.com/spreadsheets/d/FILE_ID/edit

# Execute a function
extrascripts run <folder> myFunction

# View execution logs
extrascripts logs <folder>

# Create a versioned deployment
extrascripts deploy <folder> --description "v1.0"

# List versions
extrascripts versions <folder>
```
