# ExtraSuite

ExtraSuite is a library to create and edit google docs/sheets etc using simple formats like markdown / json / tsv. It is meant for AI agents like claude / codex, and is designed to be token efficient. 

Lets assume you want to edit a large google document:

1. You `pull` the google document. This creates a local folder with 1 markdown file per tab, and an index.md with the headings from each tab.
2. You edit the markdown files. No special rules - its simple markdown
3. You `push` the folder. This command understands your changes and applies them to the google document.

The push command does a lot of heavy lifting. 

1. It first diffs the markdown to find exactly what you changed. 
2. Then it finds out what [batchUpdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate) requests are needed to reconcile the document
3. If tracks index drifts and ensures subsequent operations use the correct index
4. It tracks dependencies across batchUpdate calls. For example, if you create a new markdown file for a tab - then it will first create the tab in one request, then use the id to create the contents inside that tab.

Net result:  A single `pull` command can make complex changes across the entire google document. 

The push command makes a few promises:

1. It won't change anything it doesn't understand. So if you have complex formatting, fonts, styles - it won't modify or make changes to it. You can still edit the content without messing with the styles.
2. It will make the smallest operation to reconcile the document. In other words - "Delete and re-insert" is a bug.

The push command also supports comments. This lets you provide feedback to the agent via comments, and then ask the agent to address them. 

Similar principles apply to google sheets:
* A google sheet is a folder with a spreadsheet.json. The spreadsheet.json shows the shape of every worksheet (top 5 rows per worksheet)
* Each worksheet is a folder. It has a data.tsv, formula.json and other feature specific files
* Formulas and formatting details are compressed and applied to a range rather than to a cell. The agent sees 'Okay, this column has sum applied' or 'Okay - that row is bold'. 
* Reference documents are provided - for example, the list of formulas provided by google sheets.

--- 

## Why ExtraSuite when gws / goglcli exist?

[gws](https://github.com/nicholasgasior/gws) and [gogcli](https://github.com/Google/google-office-operations-mcp) cover a breadth of use cases in the google workspace ecosystem, but fail short when it comes to editing files. They can edit small things here are and there, but struggle when you want to make changes in a meaningful manner. You want to take to your agent in your domain - "Modify this SOW based on the pricing from this spreadsheet". For a task like that, gws/gogcli will struggle. 

Google Docs (and spreadsheets to a lesser extent) have a complex representation. 

- The agent must reason about the API's internal structure (paragraph indices, cell references, range coordinates) rather than content.
- Every edit requires reading back the current state to compute correct offsets and IDs.
- Token usage balloons: raw API responses for a 20-page doc or a 500-row sheet are enormous.
- There's no clean way to review or test what the agent will change before it changes it.

ExtraSuite complements gws and gogcli — if you have either of these tools installed, you can directly run 

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
uvx extrasuite sheets pull "https://docs.google.com/spreadsheets/d/..." <folder>
# edit files in <folder>
uvx extrasuite sheets push <folder>

# Pull a doc, edit it, push it back
uvx extrasuite docs pull "https://docs.google.com/document/d/..." <folder>
# edit files in <foldeR>
uvx extrasuite docs push <folder>
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
