# ExtraSuite

**AI agents that safely read and edit your Google Workspace files — with a full audit trail.**

ExtraSuite is terraform for google drive files. You can `pull` a google drive file (sheets/docs/forms/app scripts/slide), edit the files locally and `push` it back. Extrasuite will figure out what you changed, then create the right API calls to update the google drive file.

> **Requires a server-side component.** ExtraSuite is not a standalone CLI — it connects to a self-hosted ExtraSuite server that manages credentials and authentication. See [Deploy the Server](#deploy-the-server) below.

ExtraSuite gives agents their own identity distinct from the user. For each user, we create a 1:1 service account with a unique "email-like" identity. Users explicitly share files or folders with this service account. This has two unique advantages:
- the agent can only read/comment/edit the files you explicitly share with it
- any changes made by the agent show up in version history as "Edited by Alice's agent" instead of "Edited by Alice"

> **Note:** Agent attribution requires the default `sa+dwd` or `sa+oauth` credential mode. In `oauth` mode, edits appear as the user themselves. See [Credential Modes](#credential-modes) below.

ExtraSuite is built for small and mid-sized teams who rely on Google Workspace and want AI to help — without handing an agent the keys to your entire Drive. Individual users can also use it, but the primary workflow is designed for teams.

---
## The Pull → Edit → Push Workflow

This is the core of ExtraSuite. It works like Git for Google Workspace files.

```bash
uvx extrasuite sheet pull https://docs.google.com/spreadsheets/d/...
# Edit the local files
uvx extrasuite sheet push ./spreadsheet_id/
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

## The Problem with "Give the AI Access to Google Drive"

Most AI tools request broad OAuth permissions. The agent can read any file, write any file, send email on your behalf — all at once, for as long as the token lives. You have no visibility into what changed, and if something goes wrong, you're left hunting through version history manually.

This is [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/): an agent that can read sensitive data, take consequential actions, and communicate externally — all in a single compromised session. ExtraSuite eliminates this by design.

---

## How ExtraSuite Works

### A Dedicated Identity Per Employee

Every employee's agent gets its own Google service account (e.g. `alice-agent@your-project.iam.gserviceaccount.com`). The agent can only access files that have been **explicitly shared with that service account** — nothing else in your Drive is visible. All edits made by the agent appear in Google Drive version history attributed to "Alice's agent", not anonymously, not as Alice herself.

### Typed Commands, Minimal Scope

The client sends a **typed command** to the ExtraSuite server along with the agent's stated reason for the operation. The server uses the command type to determine the minimum required credentials:

- **Pull/push operations** (Sheets, Docs, Slides, Forms, Drive) → a short-lived service account token, valid for 1 hour
- **User-impersonating operations** (Gmail, Calendar, Apps Script, Contacts) → a short-lived delegated access token scoped to exactly the required OAuth scope(s), valid for 1 hour

The client stores a session token locally (valid 30 days) to authenticate these requests without re-opening a browser. The session token never touches the Google API — it only authenticates against the ExtraSuite server. Short-lived Google access tokens are fetched on demand and never stored.

The command type, context fields, and the agent's reason are all logged server-side before any token is issued. The server can reject operations that fall outside the configured scope allowlist.

### Local-Only Editing — No Arbitrary Code Execution

The agent's job is simple: edit files on disk and call `pull`/`push`. It does not execute arbitrary code against the Google API. This means you can configure your agent sandbox to:

- Whitelist only `extrasuite pull` and `extrasuite push` as allowed commands
- Allow outbound connections only to Google API endpoints and the ExtraSuite server

That eliminates the external communication leg of the lethal trifecta entirely.

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

Each module has a `--help` page with workflow overview, directory structure, and key rules. The source for all help text lives in [`client/src/extrasuite/client/help/`](client/src/extrasuite/client/help/).

| Module | Description |
|--------|-------------|
| [`sheet`](client/src/extrasuite/client/help/sheet/README.md) | Google Sheets — pull/edit/push spreadsheets via TSV and JSON |
| [`doc`](client/src/extrasuite/client/help/doc/README.md) | Google Docs — pull/edit/push documents via semantic XML |
| [`slide`](client/src/extrasuite/client/help/slide/README.md) | Google Slides — pull/edit/push presentations via SML markup |
| [`form`](client/src/extrasuite/client/help/form/README.md) | Google Forms — pull/edit/push surveys and quizzes via JSON |
| [`script`](client/src/extrasuite/client/help/script/README.md) | Google Apps Script — pull/edit/push standalone and bound scripts |
| [`gmail`](client/src/extrasuite/client/help/gmail/README.md) | Gmail — compose drafts from markdown files |
| [`calendar`](client/src/extrasuite/client/help/calendar/README.md) | Google Calendar — view, create, update, delete events |
| [`drive`](client/src/extrasuite/client/help/drive/README.md) | Google Drive — list and search files visible to your service account |
| `contacts` | Google Contacts — sync, search, and manage contacts |
| `auth` | Authentication management |

### Core Commands (sheet / doc / slide / form / script)

Each of these commands exists on all five modules. The links below go to the `sheet` reference; the other modules follow the same structure.

| Command | Description | Reference |
|---------|-------------|-----------|
| `pull <url>` | Download the file to a local folder | [sheet](client/src/extrasuite/client/help/sheet/pull.md) · [doc](client/src/extrasuite/client/help/doc/pull.md) · [slide](client/src/extrasuite/client/help/slide/pull.md) · [form](client/src/extrasuite/client/help/form/pull.md) · [script](client/src/extrasuite/client/help/script/pull.md) |
| `diff <folder>` | Preview pending changes as a batchUpdate request (offline, no API calls) | [sheet](client/src/extrasuite/client/help/sheet/diff.md) · [doc](client/src/extrasuite/client/help/doc/diff.md) · [slide](client/src/extrasuite/client/help/slide/diff.md) · [form](client/src/extrasuite/client/help/form/diff.md) · [script](client/src/extrasuite/client/help/script/diff.md) |
| `push <folder>` | Apply changes to Google | [sheet](client/src/extrasuite/client/help/sheet/push.md) · [doc](client/src/extrasuite/client/help/doc/push.md) · [slide](client/src/extrasuite/client/help/slide/push.md) · [form](client/src/extrasuite/client/help/form/push.md) · [script](client/src/extrasuite/client/help/script/push.md) |
| `create <title>` | Create a new file | [sheet](client/src/extrasuite/client/help/sheet/create.md) · [doc](client/src/extrasuite/client/help/doc/create.md) · [slide](client/src/extrasuite/client/help/slide/create.md) · [form](client/src/extrasuite/client/help/form/create.md) · [script](client/src/extrasuite/client/help/script/create.md) |
| `share <folder>` | Share the file with trusted contacts | [sheet](client/src/extrasuite/client/help/sheet/share.md) |
| `help [topic ...]` | Show reference documentation for the module | [sheet topics](client/src/extrasuite/client/help/sheet/README.md) · [doc topics](client/src/extrasuite/client/help/doc/README.md) |

For Sheets formula help, use `extrasuite sheet help formulas` to list all supported formulas by category, or `extrasuite sheet help formulas <formula-name>` for the syntax and reference link for a specific formula.

### Gmail Commands

| Command | Description |
|---------|-------------|
| [`compose <file>`](client/src/extrasuite/client/help/gmail/compose.md) | Save an email draft from a markdown file |
| [`edit-draft <id> <file>`](client/src/extrasuite/client/help/gmail/edit-draft.md) | Update an existing Gmail draft |
| [`reply <thread_id> <file>`](client/src/extrasuite/client/help/gmail/reply.md) | Create a reply draft in an existing thread |
| [`list`](client/src/extrasuite/client/help/gmail/list.md) | Search and list Gmail messages |
| [`read <id>`](client/src/extrasuite/client/help/gmail/read.md) | Read a Gmail message |

### Calendar Commands

| Command | Description |
|---------|-------------|
| [`view`](client/src/extrasuite/client/help/calendar/view.md) | View events for a time range |
| [`list`](client/src/extrasuite/client/help/calendar/list.md) | List all calendars |
| [`search`](client/src/extrasuite/client/help/calendar/search.md) | Search events by title or attendee |
| [`freebusy`](client/src/extrasuite/client/help/calendar/freebusy.md) | Check when a group of people are free |
| [`create <file>`](client/src/extrasuite/client/help/calendar/create.md) | Create an event from a JSON file |
| [`update <id>`](client/src/extrasuite/client/help/calendar/update.md) | Update an existing event |
| [`delete <id>`](client/src/extrasuite/client/help/calendar/delete.md) | Cancel or delete an event |
| [`rsvp <id>`](client/src/extrasuite/client/help/calendar/rsvp.md) | Accept, decline, or mark tentative |

### Drive Commands

| Command | Description |
|---------|-------------|
| [`ls`](client/src/extrasuite/client/help/drive/ls.md) | List files shared with your service account |
| [`search <query>`](client/src/extrasuite/client/help/drive/search.md) | Search files using a Drive query string |

---

## Credential Modes

The server supports three credential modes, configured via `CREDENTIAL_MODE`:

| Mode | Sheet/Doc/Slide/Form access | Gmail/Calendar/Contacts access | Agent attribution in Drive history | Requires DWD |
|---|---|---|---|---|
| `sa+dwd` *(default)* | Per-user service account | Domain-wide delegation | ✅ Yes | ✅ Yes |
| `sa+oauth` | Per-user service account | User's OAuth token | ✅ Yes (for files) | ❌ No |
| `oauth` | User's OAuth token | User's OAuth token | ❌ No — edits appear as the user | ❌ No |

**When to use each:**
- `sa+dwd` — recommended for Google Workspace organizations; provides full agent attribution and the strictest access isolation
- `sa+oauth` — use when your Google Workspace admin cannot enable domain-wide delegation; file edits are still attributed to the agent
- `oauth` — simplest setup for personal use or when attribution is not a requirement; no service accounts or DWD needed

---

## Getting Started

### Prerequisites

1. Google Workspace that allows collaboration with external users
2. A Google Cloud project with editor access (does not need to be your organization's project)
3. ExtraSuite server deployed (see [Deploy the Server](#deploy-the-server) below)

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
| Scoped access | In `sa+dwd`/`sa+oauth` modes, each agent has a dedicated service account; only sees explicitly shared files |
| Short-lived Google tokens | Access tokens expire after ~1 hour; generated on demand, never stored client-side |
| Session token | A 30-day session token stored locally authenticates against the ExtraSuite server only — not against Google APIs |
| Typed commands | Client declares what operation it intends to perform; server issues the minimum required token type and scope |
| Agent intent logging | The agent's stated reason is logged alongside command type and context before any token is issued |
| Audit trail | In `sa+dwd`/`sa+oauth` modes, all agent edits appear attributed to the agent in Drive version history. In `oauth` mode, edits appear as the user. |
| Sandboxable | Agent only edits local files and calls `pull`/`push`; no arbitrary API access |
| No external exfiltration | Outbound connections can be restricted to Google API endpoints and the ExtraSuite server |
| Minimal OAuth scope | Only the scopes needed for the specific operation are requested; administrators control the scope allowlist |

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
