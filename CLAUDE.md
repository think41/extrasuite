## Project Overview

ExtraSuite is an open source platform (https://github.com/think41/extrasuite) that enables AI agents (Claude Code, Codex, etc.) to declaratively edit Google Workspace files - Sheets, Docs, Slides, and Forms - with Apps Script support upcoming. Think of it as Terraform for Google Workspace: agents edit local files, and ExtraSuite computes the minimal API calls to sync changes back.

**Core principles:**

- **Declarative editing:** Agents edit local file representations, not APIs. ExtraSuite computes the `batchUpdate` to sync changes. Same pattern across all file types.
- **Secure by design:** Each user gets a dedicated service account with short-lived tokens. Agents can only access files explicitly shared with them. No code generation or arbitrary network calls needed - just Google Workspace API calls (whitelistable).
- **User-auditable:** All edits appear in Google Drive version history under the agent's identity. "John's agent modified this section" - visible, attributable, and reversible using native Google Workspace tools.
- **Token-efficient:** Google's native file representations are verbose. ExtraSuite converts files into compact, LLM-friendly folder structures (TSV, SML XML, structured JSON) that minimize token usage.
- **Consistent workflow:** Pull, edit, diff, push - the same workflow across every file type.

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

## Public CLI Interface

All commands work both as `python -m <module>` and via `uvx`:

```bash
# Authentication (extrasuite.client)
python -m extrasuite.client login      # or: uvx extrasuite login
python -m extrasuite.client logout     # or: uvx extrasuite logout

# Working with files (same pattern for all file types)
python -m extrasheet pull <url> [output_dir]   # Downloads to ./<file_id>/ by default
python -m extrasheet diff <folder>             # Shows batchUpdate JSON (dry run)
python -m extrasheet push <folder>             # Applies changes to Google file

python -m extradoc pull <url> [output_dir]
python -m extradoc diff <folder>
python -m extradoc push <folder>

python -m extraslide pull <url> [output_dir]
python -m extraslide diff <folder>
python -m extraslide push <folder>

python -m extraform pull <url> [output_dir]
python -m extraform diff <folder>
python -m extraform push <folder>
```

## Pull-Edit-Diff-Push Workflow

The core workflow for editing Google files (same across all file types):

1. **pull** - Fetches the Google file via API, converts it into a local folder structure. The folder contains:
   - Human/LLM-readable files (TSV for sheets, SML/XML for slides, structured JSON for docs/forms)
   - A `.pristine/` directory containing the original state as a zip file
   - See `extrasheet/docs/on-disk-format.md` or `extraslide/docs/markup-syntax-design.md` for format specs

2. **edit** - Agent modifies files in place according to user instructions and SKILL.md guidance. This is declarative: the agent edits the file representation, not API calls.

3. **diff** - Compares current files against `.pristine/` and generates the `batchUpdate` request JSON. This is essentially `push --dry-run`. Does not call any APIs.

4. **push** - Same as diff, but actually invokes the Google API to apply changes

## Packages

| Package | Purpose |
|---------|---------|
| **server/** | FastAPI server providing per-user service accounts and short-lived tokens. Deployed to Cloud Run. Also distributes agent skills. Uses `extrasuite.server` namespace. |
| **client/** | CLI for authentication (`login`/`logout`). Manages token caching via OS specific keyring. Published to PyPI as `extrasuite`. Uses `extrasuite.client` namespace. |
| **extrasheet/** | Converts Google Sheets to/from folder with TSV + JSON files. Implements pull/diff/push. |
| **extradoc/** | Converts Google Docs to/from structured local files. Implements pull/diff/push. |
| **extraslide/** | Converts Google Slides to/from SML (Slide Markup Language) XML. Implements pull/diff/push. |
| **extraform/** | Converts Google Forms to/from JSON-based local files. Implements pull/diff/push. |
| **website/** | MkDocs documentation at https://extrasuite.think41.com |

## User Flow

1. **One-time setup:** User logs into server, gets a dedicated service account created
2. **Install skills:** User runs `curl <url> | sh` to install SKILL.md into their agent
3. **Share file:** User shares Google file with their service account email
4. **Agent workflow:** Agent runs `login` (if needed) -> `pull` -> edits files declaratively -> `diff` (preview) -> `push`

Token caching: Short-lived tokens are cached using OS specific keyring. When expired, browser opens for re-auth (SSO may skip login).

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

Packages are published to PyPI independently using tag-based releases with GitHub Actions and trusted publishing.

| Package | PyPI Name | Tag Pattern | Workflow |
|---------|-----------|-------------|----------|
| client/ | `extrasuite` | `extrasuite-v*` | `publish-extrasuite.yml` |
| extrasheet/ | `extrasheet` | `extrasheet-v*` | `publish-extrasheet.yml` |
| extraslide/ | `extraslide` | `extraslide-v*` | `publish-extraslide.yml` |
| extradoc/ | `extradoc` | `extradoc-v*` | `publish-extradoc.yml` |
| extraform/ | `extraform` | `extraform-v*` | `publish-extraform.yml` |

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

## Skills

Agent skills are markdown files (SKILL.md) that teach agents how to use extrasuite. Skills are distributed by the server from the `server/skills/` directory. See https://agentskills.io/home for the agent skills standard.
