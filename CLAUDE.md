## Project Overview

ExtraSuite is an open source umbrella project (https://github.com/think41/extrasuite) that enables AI agents (Claude Code, Codex, etc.) to read or edit Google Drive files (Sheets, Slides, Docs) in a token-efficient, secure, and auditable way.

**Security model:** Each end user gets a dedicated service account. The agent can only access files explicitly shared with that service account. All edits appear in Google Drive version history as "John Doe's agent added this section/modified that diagram/so on"

**Token efficiency:** Google's native file representations are verbose. This project converts Google files into compact, LLM-friendly folder structures that allow agents to understand the big picture and make targeted edits.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ server/         │     │ extrasheet/      │     │ Google APIs     │
│ (auth tokens)   │────▶│ extraslide       │────▶│ (Sheets/Slides) │
│                 │     │ (pull/diff/push) │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │
        ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│ client/         │     │ Local folder     │
│ (CLI auth)      │     │ (agent edits)    │
└─────────────────┘     └──────────────────┘
```

## Public CLI Interface

The unified CLI supports all file types via subcommands:

```bash
# Sheets
extrasuite sheet pull <url> [output_dir]
extrasuite sheet diff <folder>
extrasuite sheet push <folder>

# Slides, Forms, Docs, Scripts
extrasuite slide pull <url> [output_dir]
extrasuite form pull <url> [output_dir]
extrasuite doc pull <url> [output_dir]
extrasuite script pull <url> [output_dir]

# Authentication flags (on pull/push/create commands)
extrasuite sheet pull --gateway /path/to/gateway.json <url>
extrasuite sheet pull --service-account /path/to/sa.json <url>

# Default: uses EXTRASUITE_SERVER_URL env var or ~/.config/extrasuite/gateway.json
```

## Pull-Edit-Diff-Push Workflow

The core workflow for editing Google files:

1. **pull** - Fetches the Google file via API, converts it into a local folder structure. The folder contains:
   - Human/LLM-readable files (TSV for sheets, SML/XML for slides)
   - A `.pristine/` directory containing the original state as a zip file
   - See `extrasheet/docs/on-disk-format.md` or `extraslide/docs/markup-syntax-design.md` for format specs

2. **edit** - Agent modifies files in place according to user instructions and SKILL.md guidance

3. **diff** - Compares current files against `.pristine/` and generates the `batchUpdate` request JSON. This is essentially `push --dry-run`. Does not call any APIs.

4. **push** - Same as diff, but actually invokes the Google API to apply changes

## Packages

| Package | Purpose |
|---------|---------|
| **server/** | FastAPI server providing per-user service accounts and short-lived tokens. Deployed to Cloud Run. Also distributes agent skills. Uses `extrasuite.server` namespace. |
| **client/** | Unified CLI (`extrasuite sheet/slide/form/doc/script pull/diff/push`) and credentials management. Manages token caching. Published to PyPI as `extrasuite`. Uses `extrasuite.client` namespace. |
| **extrasheet/** | Converts Google Sheets to/from folder with TSV + JSON files. Implements pull/diff/push. |
| **extraslide/** | Converts Google Slides to/from SML (Slide Markup Language) XML. Implements pull/diff/push. Alpha quality. |
| **website/** | MkDocs documentation at https://extrasuite.think41.com |

## User Flow

1. **One-time setup:** User logs into server, gets a dedicated service account created
2. **Install skills:** User runs `curl <url> | sh` to install SKILL.md into their agent
3. **Share file:** User shares Google file with their service account email
4. **Agent workflow:** Agent runs `pull` → edits files → `diff` (preview) → `push`

Token caching: Short-lived tokens are cached in `~/.config/extrasuite/`. When expired, browser opens for re-auth (SSO may skip login).

## Development Setup

Each module uses `uv` for dependencies, `ruff` for linting/formatting, `mypy` for type checking, `pytest` for tests.

```bash
cd <module>
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/<module>
```
See `.pre-commit-config.yaml` as well to see the pre-commit checks that our run. See `.github/workflows` for the actions that run on github.

For server development, deploy to Cloud Run and configure `~/.config/extrasuite/gateway.json`:
```json
{"EXTRASUITE_SERVER_URL": "https://your-cloud-run-url"}
```

## Testing Strategy

Tests verify the public API: `login`, `logout`, `pull`, `diff`, `push`.

**Golden file testing for pull:**
- Store raw Google API responses in `tests/golden/<file_id>/` folders
- Tests run `pull` against these cached responses instead of live API
- Assert the generated folder structure matches expected output

**Testing diff/push:**
- Start from a golden file's pulled output
- Apply known edits
- Assert the generated `batchUpdate` JSON matches expected requests

**Creating new golden files:**
1. Create a Google file with the features to test
2. Pull it with `--save-raw` to capture API responses
3. Verify the output looks correct
4. Commit the raw responses as a new golden file

## Releasing to PyPI

Three packages are published to PyPI independently using tag-based releases with GitHub Actions and trusted publishing.

| Package | PyPI Name | Tag Pattern | Workflow |
|---------|-----------|-------------|----------|
| client/ | `extrasuite` | `extrasuite-v*` | `publish-extrasuite.yml` |
| extrasheet/ | `extrasheet` | `extrasheet-v*` | `publish-extrasheet.yml` |
| extraslide/ | `extraslide` | `extraslide-v*` | `publish-extraslide.yml` |

**Release process:**

1. Update version in `<package>/pyproject.toml`
2. Commit the version bump
3. Create and push a tag matching the version:
   ```bash
   git tag extrasuite-v0.2.0 && git push origin extrasuite-v0.2.0
   git tag extrasheet-v0.1.0 && git push origin extrasheet-v0.1.0
   git tag extraslide-v0.1.0 && git push origin extraslide-v0.1.0
   ```
4. GitHub Actions will automatically build and publish to PyPI

**Version validation:** The workflow aborts if the tag version doesn't match `pyproject.toml`. For example, tagging `extrasuite-v0.2.0` when `pyproject.toml` has `version = "0.1.0"` will fail.

**Independent versioning:** Each package has its own version and release cycle. They don't need to be released together.

**Trusted publishing:** Configured on PyPI to trust GitHub Actions. No API tokens needed - authentication uses OIDC with package-specific GitHub environments (`extrasuite`, `extrasheet`, `extraslide`).

## OAuth Delegation Scopes

The server only allows a specific set of OAuth delegation scopes. When calling `get_oauth_token()`, only request these scopes:

- `gmail.compose` - Create Gmail drafts
- `calendar` - Read/write Google Calendar
- `script.projects` - Google Apps Script
- `drive.file` - Access Drive files created by the app

## Skills

Agent skills are markdown files (SKILL.md) that teach agents how to use extrasuite. Skills are distributed by the server from the `server/skills/` directory. See https://agentskills.io/home for the agent skills standard.
