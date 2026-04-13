# ExtraSuite

**ExtraSuite gives AI agents a local-file interface to Google Workspace. Pull a spreadsheet — get TSV files. Pull a document — get markdown. Edit locally, push back.**

On pull, ExtraSuite breaks down the document into individual chunks so the agent gets an overall picture and can quickly navigate to the right content. An index document provides the overall structure of the sheet or document at a glance — interconnecting all tabs and sheets so the agent can jump directly to what it needs.

On push, ExtraSuite figures out the exact changes necessary — respecting original formatting, guaranteeing it doesn't mess up anything it doesn't understand, and doing so in a token-efficient manner.

Like pull request comments, you can leave comments directly on the Google Doc or Sheet. The agent can then read and act on them.

---

## Why ExtraSuite?

Tools like [gws](https://github.com/nicholasgasior/gws) and [gogcli](https://github.com/Google/google-office-operations-mcp) are great for reading files, navigating Drive, sending email, and managing calendar. Where they fall short is **editing** — particularly moderately complex documents or spreadsheets.

The standard approach — "give the agent API access and let it issue batchUpdate calls" — works for trivial edits but breaks down quickly:

- The agent must reason about the API's internal structure (paragraph indices, cell references, range coordinates) rather than content.
- Every edit requires reading back the current state to compute correct offsets and IDs.
- Token usage balloons: raw API responses for a 20-page doc or a 500-row sheet are enormous.
- There's no clean way to review or test what the agent will change before it changes it.

ExtraSuite is designed to complement gws and gogcli — use them for discovery, navigation, email, and calendar; use ExtraSuite when the agent needs to make substantial edits.

---

## The Pull → Edit → Push Workflow

```bash
uvx extrasuite docs pull https://docs.google.com/document/d/...
# Edit the local markdown files
uvx extrasuite docs push ./document_id/
```

```bash
uvx extrasuite sheets pull https://docs.google.com/spreadsheets/d/...
# Edit the local TSV files
uvx extrasuite sheets push ./spreadsheet_id/
```

### What the Agent Sees After `pull`

**Google Docs** → a folder of GitHub-flavored markdown files, one per tab, plus an `index.md`:

`index.md` lists every heading in every tab with its line number — the agent opens this first to orient, then jumps directly to the right file and line.

```markdown
---
id: t.0
title: Q3 Planning
---

## Goals

This quarter we are focused on **reliability** and **developer experience**.

- Reduce p99 latency below 200ms
- Improve onboarding time for new engineers

## Key Metrics

| Metric         | Current | Target |
|----------------|---------|--------|
| p99 latency    | 340ms   | 200ms  |
| Onboarding     | 2 weeks | 3 days |
```

Standard GFM — headings, bold/italic, tables, lists, code blocks, callouts — all round-trip cleanly.

**Google Sheets** → a `data.tsv` per sheet tab, plus JSON files for formulas, formatting, charts, and more. A `spreadsheet.json` at the top level lists every sheet with its row count — the agent opens this first.

```tsv
Name	Age	City
Alice	30	NYC
Bob	25	LA
```

To update a cell, the agent just edits the TSV. No cell references, no range coordinates.

### Full File Type Coverage

| File type | Pull format | Key files |
|-----------|-------------|-----------|
| Sheets | TSV + JSON | `<sheet>/data.tsv`, `formula.json`, `format.json`, `spreadsheet.json` |
| Docs | Markdown | `tabs/<tab>.md`, `index.md` (heading outline) |
| Slides | SML markup | `<slide>.sml` per slide |
| Forms | JSON | `form.json` |
| Apps Script | JavaScript | `.js` and `.html` files, one per script file |

A `.pristine/` directory captures the state at pull time. `push` compares current files against pristine to generate only the necessary changes.

---

## Getting Started

### Install

```bash
uvx extrasuite --help
```

Or install persistently:

```bash
uv tool install extrasuite
```

The `--help` flag on any command is the authoritative reference. Run `extrasuite <module> --help` for a workflow overview, and `extrasuite <module> <command> --help` for full flag documentation.

### Authentication

ExtraSuite piggybacks on credentials from other Google CLI tools you may already have configured.

**If you use [gws](https://github.com/nicholasgasior/gws):** ExtraSuite auto-detects your gws credentials (`~/.config/gws/client_secret.json`) and reuses them. No additional setup.

**If you use [gogcli](https://github.com/Google/google-office-operations-mcp):** ExtraSuite auto-detects your gogcli credentials and reuses them. No additional setup.

**From scratch:** Set up OAuth client credentials using either [gws's setup guide](https://github.com/nicholasgasior/gws) or [gogcli's setup guide](https://github.com/Google/google-office-operations-mcp), then use ExtraSuite alongside them.

> In all the above modes, edits appear in Google Drive under your own Google account.

**ExtraSuite gateway server (teams):** For a distinct agent identity and audit trail, deploy the ExtraSuite server. See the [deployment documentation](https://extrasuite.think41.com/deployment/) for setup.

### Quick Start

Once authenticated:

```bash
# Pull a sheet, edit it, push it back
uvx extrasuite sheets pull https://docs.google.com/spreadsheets/d/YOUR_ID
# edit ./YOUR_ID/Sheet1/data.tsv
uvx extrasuite sheets push ./YOUR_ID/

# Pull a doc, edit it, push it back
uvx extrasuite docs pull https://docs.google.com/document/d/YOUR_ID
# edit ./YOUR_ID/tabs/Tab_1.md
uvx extrasuite docs push ./YOUR_ID/
```

---

## Agent Identity and Security (ExtraSuite Gateway Mode)

The features below require deploying the ExtraSuite server. This is suitable for teams and small organizations who want tighter control over what agents can access and do.

### A Dedicated Identity Per Employee

Every employee's agent gets its own Google service account (e.g. `alice-agent@your-project.iam.gserviceaccount.com`). The agent can only access files that have been **explicitly shared with that service account** — nothing else in Drive is visible. All edits appear in Google Drive version history as "Edited by Alice's agent", not as Alice herself.

### Typed Commands and Minimal Scope

The client sends a **typed command** to the ExtraSuite server along with the agent's stated reason. The server determines the minimum required credentials:

- **Pull/push operations** (Sheets, Docs, Slides, Forms, Drive) → short-lived service account token, valid 1 hour
- **User-impersonating operations** (Gmail, Calendar, Apps Script, Contacts) → short-lived delegated token scoped to exactly the required OAuth scope, valid 1 hour

The command type, context, and reason are logged server-side before any token is issued.

### Security Properties

| Property | How ExtraSuite Achieves It |
|----------|---------------------------|
| Scoped access | Each agent has a dedicated service account; only sees explicitly shared files |
| Short-lived tokens | Google access tokens expire after ~1 hour; generated on demand, never stored |
| Typed commands | Server issues the minimum token type and scope for the declared operation |
| Agent intent logging | Reason logged alongside command type before any token is issued |
| Audit trail | All agent edits appear in Google Drive version history attributed to the agent |
| Sandboxable | Agent only edits local files and calls `pull`/`push`; no arbitrary API access |
| Minimal OAuth scope | Only the scopes needed for the specific operation are requested |

### Deploy the Server

```bash
gcloud run deploy extrasuite-server \
  --image=ghcr.io/think41/extrasuite-server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production,GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest,GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest,SECRET_KEY=extrasuite-secret-key:latest"
```

See the [deployment documentation](https://extrasuite.think41.com/deployment/) for full setup instructions.

### Employee Onboarding (gateway mode)

1. Employee logs into the ExtraSuite server and notes their agent's service account email
2. Runs `extrasuite auth install-skill` to give the agent its instructions
3. Shares specific Google files with the service account (editor or viewer, as needed)
4. Agent runs `extrasuite <module> pull <url>` and the workflow begins

---

## CLI Reference

### Modules

| Module | Description |
|--------|-------------|
| `sheets` | Google Sheets — pull/edit/push spreadsheets via TSV and JSON |
| `docs` | Google Docs — pull/edit/push documents via markdown |
| `slides` | Google Slides — pull/edit/push presentations via SML markup |
| `forms` | Google Forms — pull/edit/push surveys and quizzes via JSON |
| `script` | Google Apps Script — pull/edit/push standalone and bound scripts |
| `gmail` | Gmail — compose drafts, read and reply to emails |
| `calendar` | Google Calendar — view, create, update, delete events |
| `drive` | Google Drive — list and search files |
| `contacts` | Google Contacts — sync, search, and manage contacts |
| `auth` | Authentication management |

### Core Commands (sheets / docs / slides / forms / script)

| Command | Description |
|---------|-------------|
| `pull <url>` | Download the file to a local folder |
| `push <folder>` | Apply changes to Google |
| `create <title>` | Create a new file |
| `share <url> <emails>` | Share the file with trusted contacts |

### Gmail Commands

| Command | Description |
|---------|-------------|
| `compose <file>` | Save an email draft from a markdown file |
| `edit-draft <id> <file>` | Update an existing Gmail draft |
| `reply <thread_id> <file>` | Create a reply draft in an existing thread |
| `list` | Search and list Gmail messages |
| `read <id>` | Read a Gmail message |

### Calendar Commands

| Command | Description |
|---------|-------------|
| `view` | View events for a time range |
| `list` | List all calendars |
| `search` | Search events by title or attendee |
| `freebusy` | Check when a group of people are free |
| `create <file>` | Create an event from a JSON file |
| `update <id>` | Update an existing event |
| `delete <id>` | Cancel or delete an event |
| `rsvp <id>` | Accept, decline, or mark tentative |

---

## Development

```bash
# Client
cd client && uv sync
uv run pytest tests/ -v

# Server
cd server && uv sync
uv run uvicorn extrasuite.server.main:app --reload --port 8001

# Tests and linting
cd server && uv run pytest tests/ -v && uv run ruff check .
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
