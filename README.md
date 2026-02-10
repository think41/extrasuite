# ExtraSuite

**Declarative Google Workspace editing for AI agents.** Pull a file, edit it locally, push it back. Across Sheets, Docs, Slides, and Forms.

ExtraSuite converts Google Workspace files into compact, LLM-friendly local representations. Agents edit files declaratively - like Terraform for Google Workspace - and the library figures out the imperative API calls to sync changes back. No code generation, no arbitrary network calls, no API wrangling.

## Why ExtraSuite?

| Principle | What it means |
|-----------|---------------|
| **Declarative editing** | Edit files, not APIs. The agent modifies a local file and ExtraSuite computes the minimal `batchUpdate` to sync it. Same pattern across Sheets, Docs, Slides, and Forms. |
| **Secure by design** | Each user gets a dedicated service account. Short-lived tokens (1 hour), no stored keys. Agents can only access files explicitly shared with them. Network calls restricted to Google Workspace APIs. |
| **User-auditable** | Every edit appears in Google Drive version history under the agent's identity. "John's agent modified this section" - visible, attributable, and reversible. |
| **Token-efficient** | Custom file representations strip verbose API JSON into compact formats (TSV, SML, structured JSON) that minimize LLM token usage while remaining intuitive. |
| **Consistent workflow** | `pull` -> edit -> `diff` -> `push` across every file type. Learn once, use everywhere. |

## Supported File Types

| Package | File Type | Status | Description |
|---------|-----------|--------|-------------|
| [extrasheet](extrasheet/) | Google Sheets | Stable | TSV + JSON representation |
| [extradoc](extradoc/) | Google Docs | Stable | Structured document format |
| [extraslide](extraslide/) | Google Slides | Stable | SML (Slide Markup Language) XML |
| [extraform](extraform/) | Google Forms | Stable | JSON-based form structure |
| | Google Apps Script | Upcoming | Bound scripts support |

## The Pull-Edit-Diff-Push Workflow

Every file type follows the same workflow:

```bash
# 1. Pull - download the file into a local folder
extrasheet pull https://docs.google.com/spreadsheets/d/abc123/edit

# 2. Edit - agent modifies files in the local folder
#    (TSV for sheets, SML for slides, structured JSON for docs/forms)

# 3. Diff - preview the batchUpdate that would be sent (dry run)
extrasheet diff ./abc123/

# 4. Push - apply changes to Google
extrasheet push ./abc123/
```

Works the same for `extradoc`, `extraslide`, and `extraform`.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ server/         │     │ extrasheet/      │     │ Google APIs     │
│ (auth + tokens) │────>│ extraslide/      │────>│ (Sheets/Slides/ │
│                 │     │ extradoc/        │     │  Docs/Forms)    │
└─────────────────┘     │ extraform/       │     └─────────────────┘
        │               │ (pull/diff/push) │
        v               └──────────────────┘
┌─────────────────┐              │
│ client/         │              v
│ (CLI auth)      │     ┌──────────────────┐
└─────────────────┘     │ Local folder     │
                        │ (agent edits     │
                        │  declaratively)  │
                        └──────────────────┘
```

## Quick Start

### Install

```bash
pip install extrasuite extrasheet  # or: extradoc, extraslide, extraform
```

### Authenticate

```bash
# Login (opens browser for OAuth)
extrasuite login
```

### Work with files

```bash
# Sheets
python -m extrasheet pull <url>
# Edit the local TSV/JSON files...
python -m extrasheet push ./spreadsheet_id/

# Docs
python -m extradoc pull <url>
python -m extradoc push ./document_id/

# Slides
python -m extraslide pull <url>
python -m extraslide push ./presentation_id/

# Forms
python -m extraform pull <url>
python -m extraform push ./form_id/
```

## Project Structure

```
extrasuite/
├── client/          # Python client library (PyPI: extrasuite) - CLI auth
├── server/          # FastAPI server (Cloud Run) - token management
├── extrasheet/      # Google Sheets <-> local files (PyPI: extrasheet)
├── extraslide/      # Google Slides <-> SML files (PyPI: extraslide)
├── extradoc/        # Google Docs <-> local files (PyPI: extradoc)
├── extraform/       # Google Forms <-> local files (PyPI: extraform)
└── website/         # Documentation at https://extrasuite.think41.com
```

## Security Model

- **Dedicated agent identity** - Each user gets their own service account. No shared credentials.
- **Explicit sharing only** - Agents can only access files shared with their service account email via standard Google Drive sharing.
- **Short-lived tokens** - Access tokens expire after 1 hour. No private keys distributed.
- **Declarative = safe** - Agents edit local files, not execute arbitrary code. No network calls beyond Google Workspace APIs (whitelistable).
- **Full audit trail** - All edits attributed to the agent's identity in Google Drive version history.

See the [security documentation](https://extrasuite.think41.com/security/) for details.

## Deploying the Server

See the [deployment documentation](https://extrasuite.think41.com/deployment/) for Cloud Run deployment instructions.

## Development

Each package uses `uv` for dependencies, `ruff` for linting/formatting, `mypy` for type checking, `pytest` for tests.

```bash
cd <package>
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/<package>
```

## License

MIT License - see [LICENSE](LICENSE) for details.
