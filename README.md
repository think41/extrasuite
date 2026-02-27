# ExtraSuite

**AI agents that safely read and edit your Google Workspace files — with a full audit trail.**

ExtraSuite gives AI agents (Claude Code, Codex, Cursor, etc.) a structured, sandboxable way to work with Google Docs, Sheets, Slides, Forms, Apps Script, Gmail, and Calendar. Built for small and mid-sized teams who rely on Google Workspace and want AI to help — without handing an agent the keys to your entire Drive.

---

## The Problem with "Give the AI Access to Google Drive"

Most AI tools request broad OAuth permissions. The agent can read any file, write any file, send email on your behalf — all at once, for as long as the token lives. You have no visibility into what changed, and if something goes wrong, you're left hunting through version history manually.

This is [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/): an agent that can read sensitive data, take consequential actions, and communicate externally — all in a single compromised session. ExtraSuite eliminates this by design.

---

## How ExtraSuite Works

### A Dedicated Identity Per Employee

Every employee's agent gets its own Google service account (e.g. `alice-agent@your-project.iam.gserviceaccount.com`). The agent can only access files that have been **explicitly shared with that service account** — nothing else in your Drive is visible. All edits made by the agent appear in Google Drive version history attributed to "Alice's agent", not anonymously, not as Alice herself.

### Short-Lived Tokens, Minimal Scope

Tokens are scoped to the exact operation being performed and expire after ~1 hour. The agent never holds a persistent credential. There are no long-lived API keys to rotate or leak.

### Local-Only Editing — No Arbitrary Code Execution

The agent's job is simple: edit files on disk and call `pull`/`push`. It does not execute arbitrary code against the Google API. This means you can configure your agent sandbox to:

- Whitelist only `extrasuite pull` and `extrasuite push` as allowed commands
- Allow outbound connections only to Google API endpoints

That eliminates the external communication leg of the lethal trifecta entirely.

---

## The Pull → Edit → Push Workflow

This is the core of ExtraSuite. It works like Git for Google Workspace files.

```bash
extrasuite sheet pull https://docs.google.com/spreadsheets/d/...
# Edit the local files
extrasuite sheet push ./spreadsheet_id/
```

### Why Declarative Beats Imperative

Most AI-driven automation is **imperative**: "call the Sheets API to set cell A1 to X, then call it again to set B2 to Y". This is fragile, hard to review, and impossible to sandbox meaningfully.

ExtraSuite is **declarative**: the agent edits local files to express the *desired state*, and `push` figures out what changed and translates it into the correct API calls.

| | Imperative API calls | ExtraSuite pull/push |
|---|---|---|
| Reviewability | Hard — sequence of API calls | Easy — `diff` shows exactly what changes |
| Sandboxability | Hard — agent needs live API access throughout | Simple — agent only touches local files |
| Recoverability | Manual | Re-pull to get back to last-pushed state |
| Token efficiency | High — agent must read/write raw API structures | Low — agent works in human-readable formats |
| Audit trail | Depends on logging | Built-in via Google Drive version history |

### What `pull` Produces

Each file type is converted into a folder of human- and LLM-readable files:

- **Sheets** → `data.tsv`, `formula.json`, `format.json` (factored CSS-like styles)
- **Slides** → `content.sml` per slide (SML: an HTML-inspired markup language)
- **Docs** → `document.xml` (semantic HTML-like XML), `comments.xml`
- **Forms** → a single `form.json` with all questions and settings
- **Scripts** → `.js` and `.html` files, one per script file

A `.pristine/` directory captures the original state. `diff` compares current files against pristine and shows the pending batchUpdate request — no API calls needed. `push` applies it.

---

## What You Can Actually Do

### Document Collaboration, Not Just Creation

Creating a document is easy. The hard part is everything after: multiple stakeholders, rounds of edits, comments that need responses, priorities that shift between drafts.

ExtraSuite lets agents participate in that ongoing collaboration:

- Read comments left by colleagues in a Doc and draft replies
- Incorporate reviewer feedback by editing the local `document.xml` and pushing
- Track which version introduced which change (it's in Drive's version history)
- Pull the latest state before each editing session so the agent always works from current content

### Mini-Applications with Apps Script

Google Sheets + Forms + Apps Script is the de facto low-code platform for many business teams — expense approvals, onboarding checklists, inventory tracking. ExtraSuite lets agents build and maintain these:

- Pull a script project, add or modify trigger functions, push it back
- Wire a Form submission to an Apps Script that sends a confirmation email
- Update a Sheet with data from an external system and trigger a workflow
- Build the whole thing with an agent, or have an agent maintain an existing one

### Bring in Context from Your Other Systems

Documents and spreadsheets don't exist in a vacuum. Your CRM, your ticketing system, your product database — that's where the real data lives. ExtraSuite handles the Google Workspace side so your agent can:

- Pull a sales pipeline sheet, update it with data from your CRM, push the changes
- Draft a status report doc using data from your project tracker
- Create a Form for collecting information and link it to a Sheet via Apps Script

### Gmail Drafts and Calendar

For Gmail, the agent composes a draft (you review and send). For Calendar, the agent can view availability, create events, and RSVP — useful for scheduling workflows.

---

## CLI Reference

The CLI is self-documenting. Every command has a `--help` flag that serves as the live reference. Run `extrasuite <module> --help` for workflow overview, and `extrasuite <module> <command> --help` for flags.

### Modules

| Module | Description |
|--------|-------------|
| `sheet` | Google Sheets — pull/edit/push spreadsheets via TSV and JSON |
| `doc` | Google Docs — pull/edit/push documents via semantic XML |
| `slide` | Google Slides — pull/edit/push presentations via SML markup |
| `form` | Google Forms — pull/edit/push surveys and quizzes via JSON |
| `script` | Google Apps Script — pull/edit/push standalone and bound scripts |
| `gmail` | Gmail — compose drafts from markdown files |
| `calendar` | Google Calendar — view, create, update, delete events |
| `drive` | Google Drive — list and search files visible to your service account |
| `contacts` | Google Contacts — sync, search, and manage contacts |
| `auth` | Authentication management |

### Core Commands (sheet / doc / slide / form / script)

| Command | Description |
|---------|-------------|
| `pull <url>` | Download the file to a local folder |
| `diff <folder>` | Preview pending changes as a batchUpdate request (offline, no API calls) |
| `push <folder>` | Apply changes to Google |
| `create <title>` | Create a new file |
| `share <folder>` | Share the file with trusted contacts |
| `help [topic]` | Show reference documentation for the module |

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

### Drive Commands

| Command | Description |
|---------|-------------|
| `ls` | List files shared with your service account |
| `search <query>` | Search files using a Drive query string |

---

## Getting Started

### Prerequisites

1. Google Workspace that allows collaboration with external users
2. A Google Cloud project with editor access (does not need to be your organization's project)
3. ExtraSuite server deployed (see below)

### Install the Client

```bash
uvx extrasuite --help
```

Or install persistently:

```bash
uv tool install extrasuite
```

### Deploy the Server

The ExtraSuite server manages service account creation and token issuance. Deploy it once for your whole team:

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

### Employee Onboarding

1. Employee logs into the ExtraSuite server and notes their agent's service account email
2. Runs `extrasuite auth install-skill` to give the agent its instructions
3. Shares specific Google files with the service account (editor or viewer, as needed)
4. Agent runs `extrasuite <module> pull <url>` and the workflow begins

---

## Security Summary

| Property | How ExtraSuite Achieves It |
|----------|---------------------------|
| Scoped access | Each employee's agent has a dedicated service account; only sees explicitly shared files |
| Short-lived credentials | Tokens expire after ~1 hour; no persistent API keys |
| Audit trail | All agent edits appear in Google Drive version history attributed to the agent |
| Sandboxable | Agent only edits local files and calls `pull`/`push`; no arbitrary API access |
| No external exfiltration | Outbound connections can be restricted to Google API endpoints only |
| Minimal OAuth scope | Only the scopes needed for the specific operation are requested |

---

## Development

```bash
# Server
cd server && uv sync
uv run uvicorn extrasuite.server.main:app --reload --port 8001

# Client
cd client && uv sync
uv run pytest tests/ -v

# Tests and linting
cd server && uv run pytest tests/ -v && uv run ruff check .
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
