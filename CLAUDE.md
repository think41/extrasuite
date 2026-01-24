## Project Overview
ExtraSuite is an open source project (https://github.com/think41/extrasuite) that enables an AI agent such as claude code or codex to get temporary service account tokens on behalf of the user so that it can read or edit google sheets, docs or slides. Each end user gets their own private service account. `extrasuite-server` generates this service account on first access and returns a short lived token. End users must share the google drive file with this service account, and then instruct their AI agent to access the file. This ensures the AI agent has temporary access to the files. It also ensures that any edits made by the AI show up in the version history clearly attributed to the service account email, thereby maintaining an audit trail.

This project publishes a public docker image on google cloud artifact registry. Each organization or group that wishes to use this project must deploy the container via google cloud run in a google cloud project. In addition, to authenticate end users belonging to that organization or group, they must setup OAuth credentials in google cloud. 

## Packages
The project is a monorepo consisting of the following packages:
1. **extrasuite-server** - Containerized FastAPI application to provide employee-specific service accounts and short-lived access tokens that can be used to call google drive/sheets/docs/slides APIs. It also has minimal UI to allow employees to install skills via a command line installation command.
2. **extrasuite-client** - CLI based application to call extrasuite-server from an AI Agent and provide it shortlived access tokens. This will eventually be published to a pypi package, but currently extrasuite-client/src/extrasuite_client/credentials.py is manually copied by the projects that wish to use it.
3. **extraslide** - Python library that simplifies editing Google Slides through an SML (Slide Markup Language) abstraction. "Pulls" google slides into an XML file, AI agents make edits to this XML, a "diff" process identifies changes, and "push" invokes appropriate Google Slides API. This library is alpha quality.
4. **website** - mkdocs based documentation website, hosted on github pages, automatically deployed to https://extrasuite.think41.com on every commit to main branch. The website also has instructions to deploy, end user documentation and other product usage.

## Skills for Slides, Docs and Sheets
The AI agent needs instructions on how to read or edit google drive files. These are provided as "Agent Skills" which are an open standard. See https://agentskills.io/home. At its core, a skill is a markdown file <skillname>/SKILL.md that is saved by end users at a well known agent specific location. The skills are distributed by extrasuite-server, see extrasuite-server/skills.

The SKILL.md file explains how to use `extrasuite-client` to get the temporary service account token, and then use the appropriate library to read or edit the specific file type.

### Package Naming Convention
The packages are being renamed for consistency:
- **extraslide** (formerly gslidex) - Google Slides manipulation, now part of this monorepo at `/extraslide/`
- **extrasheet** (formerly gsheetx) - Google Sheets manipulation, see https://github.com/think41/gsheetx
- **extradoc** (formerly gdocx) - Google Docs manipulation, see https://github.com/think41/gdocx (under development)

### Current Status
- **extraslide** skill is available at `extrasuite-server/skills/extraslide/`
- **gsheetx** skill is working at `extrasuite-server/skills/gsheetx/` and uses the underlying gspread library directly

## Organization Setup (prerequisite)

Before end users can use ExtraSuite, an administrator must deploy extrasuite-server for their organization:

1. **Create a Google Cloud project** with billing enabled
2. **Enable required APIs**: IAM, Service Account Credentials, Firestore, Drive, Sheets, Docs, Slides
3. **Configure OAuth consent screen** and create OAuth 2.0 credentials (Web application type)
4. **Create a Firestore database** in the project
5. **Deploy extrasuite-server to Cloud Run** using the public image: `asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server`
6. **Set environment variables** on Cloud Run: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_CLOUD_PROJECT`, `SECRET_KEY`
7. **Share the Cloud Run URL** with end users in the organization

See `website/docs/deployment/` for detailed deployment instructions.

## User Flow

### One-Time Setup (per user)
1. User logs in to **extrasuite-server** via OAuth using their Google Workspace or Gmail account
2. Server creates a dedicated service account for this user, granting it read access to Google Drive API and read/write access to Sheets/Docs/Slides APIs (no credentials are stored for this service account)
3. User copies the skill installation command from the server UI and runs it to install the skill into their AI agent (e.g., Claude Code's `~/.claude/commands/` directory)

### Runtime Flow (each time agent needs access)
4. User shares a Google Drive file with their service account email, then instructs the agent to access it
5. Agent invokes the skill, which calls `CredentialsManager` (in `extrasuite-client`) to get a short-lived access token
6. If a valid cached token exists in `~/.config/extrasuite/token.json`, it's returned immediately
7. Otherwise, `CredentialsManager` starts a local HTTP server on a random port and opens the browser to `/api/token/auth?port=<port>` (or prints the URL if browser launch fails)
8. User authenticates with Google, then is redirected to `/api/auth/callback`
9. Server redirects browser to `http://localhost:<port>/on-authentication?code=<auth_code>` (also displays the code for manual entry if needed)
10. `CredentialsManager` exchanges the auth code via `/api/token/exchange`
11. Server uses domain-wide delegation to impersonate the user's service account and returns a short-lived access token
12. `CredentialsManager` caches the token locally (with 600 permissions) and provides it to the agent
13. Agent uses the token to make Google API calls directly from the user's device

### Token Refresh
When the token expires, the runtime flow repeats from step 7. If the user still has a valid session with extrasuite-server, the browser opens briefly and closes automatically (no re-authentication required).

## Development Commands

### Client Library
```bash
cd extrasuite-client
uv sync
uv run python -c "from extrasuite_client import ExtraSuiteClient; print('OK')"
uv run ruff check .
```

### Server (FastAPI)
```bash
cd extrasuite-server
uv sync
uv run uvicorn extrasuite_server.main:app --reload --port 8001
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
```

### Extraslide Library
```bash
cd extraslide
uv sync
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
uv run mypy src/extraslide
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/login` | Start Oauth authentication flow from the UI to login the user |
| GET | `/api/token/auth?port=<port>` | CLI entry point - starts OAuth (port 1024-65535) |
| POST | `/api/token/exchange` | Exchange auth code for token |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for token |
| GET | `/api/health` | Health check |

## Environment Setup

Copy `extrasuite-server/.env.template` to `extrasuite-server/.env` and configure:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation
- `SECRET_KEY` - For signing state tokens

Server uses Application Default Credentials (ADC) for service account management and Firestore access.

## Firestore Setup

Firestore collections are created automatically on first use. No manual setup required.

Enable the Firestore API and create a database:
```bash
gcloud services enable firestore.googleapis.com --project=<project>
gcloud firestore databases create --location=asia-south1 --project=<project>
```

## Token Storage

- **Server-side:** Tokens are not stored on the server. They are generated on demand and returned immediately to the client.
- **Client-side:** Short-lived SA tokens in `~/.config/extrasuite/token.json`

## Testing

Due to tight integration with Google Cloud APIs, local testing is impractical. Developers should set up their own Google Cloud project following the same steps as Organization Setup (see `website/docs/deployment/`).

### Deploy from a branch

To test changes before merging to main:

1. Push your changes to a feature branch on GitHub
2. GitHub Actions automatically builds and pushes a container tagged with the branch name
3. Deploy the branch image to your Cloud Run instance:
   ```bash
   gcloud run deploy extrasuite-server \
     --image asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:<branch-name> \
     --region asia-southeast1 \
     --project <your-project>
   ```

### Validate auth flows

Use `extrasuite-client/examples/basic_usage.py` to test the three main authentication scenarios:

1. **First run (no cache):** Token file missing, browser opens, user authenticates
2. **Cached token:** Token file present and valid, no browser opens
3. **Session reuse:** Delete token cache, browser opens but SSO skips login

```bash
# Clear cache and test fresh authentication
rm -f ~/.config/extrasuite/token.json
PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
  --auth-url https://<your-cloud-run-url>/api/token/auth \
  --exchange-url https://<your-cloud-run-url>/api/token/exchange
```

## Exception Handling

The server uses centralized exception handling via FastAPI's `add_exception_handler`. Follow these principles:

1. **Don't catch exceptions just to re-raise as HTTPException(500)** - Let exceptions propagate to the global handler which logs them and returns a safe error response

2. **Only catch exceptions when you can:**
   - Handle them meaningfully (e.g., return `None` to trigger re-auth flow)
   - Add context that would otherwise be missing, then re-raise
   - Handle specific cases (e.g., `HttpError` with status 404 vs other errors)

3. **For non-critical operations**, catch and log but continue (e.g., updating optional metadata)

4. **Use domain exceptions** (`ValueError`, `RefreshError`) rather than `HTTPException` in business logic modules

## CI/CD

Docker images are automatically built and published to Google Artifact Registry via GitHub Actions on every push to `main`.

**Public image location:** `asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server`

**Automatic tagging:**
| Trigger | Tags Created |
|---------|--------------|
| Push to any branch | `<branch-name>`, `sha-<commit>` |
| Git tag `v*` | `<version>`, `latest` |
| Pull request | Build only (no push) |

### Creating a Release

To create a new release:
```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions will automatically build and push the image with tags `v1.0.0` and `latest`.

