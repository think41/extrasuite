ExtraSuite enables AI agents (Claude Code, Codex, etc.) to automate Google Workspace in a secure, auditable and token-efficent manner. You can read and edit files, automate tasks with google app scripts, delegate calendar and so on. The primary audience is small to medium organizations. 

## Why ExtraSuite?

**Auditable:** The employee's agent gets a dedicated service account. The agent can only access files explicitly shared with that service account. All edits made by the agent appear in version history as "John Doe's agent added this section/modified that formula/so on". Anyone with access to that file can quickly know who changed what. 

**Workflow:** Agents perform a consistent git-like workflow for every supported google drive file - `pull`, edit files locally, `push`.  
- `pull` downloads the doc/slide/sheet/form to a local folder in standard file formats. 
- `skill.md` explains the folder structure and file formats to the agent so that it can effectively read/write these files.
- `push` performs a diff, figures out what changed, converts them into the appropriate google specific batchUpdate API request, and efficiently updates the google file. The changes show up in version history, appropriately tagged to the employee's service account.

**Security:** The agent is only editing local files and invoking `pull` and `push` commands. Notably, it isn't executing arbitrary code. This means that you can whitelist the specific tool calls (pull and push) and network domains (only google APIs) to achieve strong security. This is blocking "the ability to externally communicate" leg in [lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) to make strong security guarantees.

**Token efficiency:** Google Drive files are broken down into several local files to achieve progressive disclosure and task based access. 
- Google Docs is represented as an "html-inspired-xml" + a styles.xml. Styles are factored and converted into CSS styles. The complexity of utf-16 indexes is copmletely hiddent.
- Google Sheets is represented as a JSON summarizing the overall sheet + a sub-folder for each worksheet. Each worksheet has a data.tsv that only contains the data, a formula.json that contains generalized formulas across a range rather than formulas across every cell, and a json representing the factored "css-like" styles. 

**Least Privileges:** The AI is granted the minimum necessary permission to perform the task, and only for about 1 hour. Most activities use a separate identity (all read/write google drive/sheet/docs/slides/forms operations); but some require the agent to act as the employee (app scripts, gmail, calendar). 

## What can I do with ExtraSuite


## Prerequisites
1. Google Workspace must allow collaboration with external users.
2. Access to a project in Google Cloud with editor/administrator access. This cloud project does NOT need to be associated with your organization's domain / google workspace.

## Installation
- You need to deploy ExtraSuite server once for all the employees. 
- See the [deployment documentation](https://extrasuite.think41.com/deployment/) for Cloud Run deployment instructions.

## Employee/Agent Workflow

1. **Install skill:** Employee logs into ExtraSuite server, notes down their agent's email, and also runs a command to install agent skill.
3. **Share file:** Employee shares the google doc/sheet/slide/form with their 1:1 service account. This can be editor or viewer, depending on the use case.
4. **Agent workflow:** Agent runs `login` (if needed) → `pull` → edits files → `diff` (preview) → `push` to achieve the task.

## Packages

| Package | Purpose |
|---------|---------|
| **server/** | Web application to create per-employee service accounts and provide short lived access tokens to the agent. Must be deployed to cloud run. |
| **client/** | Shared library used to authenticate employees and retrieve short-lived access tokens. |
| **extra(doc|sheet|slide|form)/** | Python library + skills read and edit google docs/sheet/slide/form using the pull/diff/push workflow. Can be used as standalone libraries if you have alternative ways to provide service account keys. |
| **website/** | Public website hosted on https://extrasuite.think41.com |




### Quick Deploy

```bash
# Deploy to Cloud Run using pre-built image from GitHub Container Registry
gcloud run deploy extrasuite-server \
  --image=ghcr.io/think41/extrasuite-server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production,GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest,GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest,SECRET_KEY=extrasuite-secret-key:latest"
```

## Development

### Server Development

```bash
cd server
uv sync
uv run uvicorn extrasuite.server.main:app --reload --port 8001
```

### Client Development

```bash
cd client
uv sync
uv run pytest tests/ -v
```

### Run Tests

```bash
cd server
uv run pytest tests/ -v
uv run ruff check .
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?port=<port>` | Start OAuth flow for CLI |
| POST | `/api/token/exchange` | Exchange auth code for token |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/health` | Health check |

## Security

- **Short-lived tokens**: Service account tokens expire after 1 hour
- **Localhost redirects only**: CLI callbacks restricted to localhost
- **OAuth state tokens**: CSRF protection with time-limited state (10 min)
- **Secure token storage**: Tokens stored in OS keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)
- **No private keys**: Service account keys are never downloaded

## License

MIT License - see [LICENSE](LICENSE) for details.
