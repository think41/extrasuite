## Project Overview

ExtraSuite is an open source project (https://github.com/think41/extrasuite) that provides a CLI tool meant for AI agents (Claude Code, Codex, etc.) to perform read/write operations on google workspace files (sheets/docs/slides/forms), create email drafts and manage calendar in a secure, auditable and token efficient manner.

Key innovations:
- A consistent git-like pull, diff and push workflow across all google drive file types. `pull` downloads and converts the google drive file into a folder of files in a format the LLM natively understands. `diff` figures out what changed, and `push` pushes the changes to the google drive file. The LLM only needs to edit files locally to make any change to the google drive file. 
- A unique identity for every employee's agent via a 1:1 service account. Agent only has minimal temporary access, and any changes made by the agent reflect in google drive version history.
- For certain modules (gmail, calendar) - we use domain wide delegation with minimal scope to grant a short lived token to the agent. The agent never sees the tokens. 

There are several modules in this project: 
- `client` (pypi extrasuite) - is the main entrypoint CLI program. In this repository, run `./extrasuite --help` to learn the commands. End users invoke it as `uvx extrasuite --help`. It uses the extra* modules for file specific logic, and the server url as the gateway to get shortlived tokens.
- `extradoc/extrasheet/extraslide/extraform` - are standalond python libraries that implements the pull/push workflow. These are used by client. These packages are also published to pypi and can be used independently.
- `server` - is a gateway to grant short lived tokens. It manages 1:1 service accounts per employee and domain-wide delegation. 
- `website` - is the mkdocs based public documentation that gets deployed to https://extrasuite.think41.com 

## CLI Interface

The unified CLI supports all file types via subcommands:

```bash
./extrasuite --help
```

## Pull-Edit-Diff-Push Workflow

The core workflow for editing Google files:

1. **pull** - Fetches the Google file via API, converts it into a local folder structure. The folder contains:
   - Human/LLM-readable files (TSV for sheets, SML/XML for slides, XML for docs etc.)
   - A `.pristine/` directory containing the original state as a zip file

2. **edit** - Agent modifies files in place according to user instructions and inline help documentation via --help flag.

3. **diff** - Compares current files against `.pristine/` and generates the `batchUpdate` request JSON. This is essentially `push --dry-run`. Does not call any APIs.

4. **push** - Same as diff, but actually invokes the Google API to apply changes

Token caching: Short-lived tokens are cached in `~/.config/extrasuite/`. When expired, browser opens for re-auth (SSO may skip login).

## Development Setup

Each module uses `uv` for dependencies, `ruff` for linting/formatting, `mypy` for type checking, `pytest` for tests.
See `.pre-commit-config.yaml` as well to see the pre-commit checks that our run. See `.github/workflows` for the actions that run on github.

For server development, deploy to Cloud Run and configure `~/.config/extrasuite/gateway.json`:
```json
{"EXTRASUITE_SERVER_URL": "https://your-cloud-run-url"}
```

## Testing Strategy

Tests verify the public API: `pull`, `diff`, `push`.

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

## Code Style: Type Safety and None Discipline

Write code where types are as narrow as possible. `None` is not a valid sentinel for "this should have been set up earlier" — enforce that invariant explicitly at the right boundary instead.

- If a value is always present after a certain lifecycle stage, enforce that stage and reflect it in a non-optional type. Do not propagate `Optional[str]` through the call stack and add `or ""` fallbacks everywhere downstream.
- Prefer raising with a clear invariant-violation message over silently coercing to a default. Loud failures surface bugs early; silent defaults hide them until production.
- `get_oauth_token(scopes)` in v2 mode only supports a single scope per call. Passing multiple scopes raises `ValueError` — do not silently drop extras.

## Skills

Agent skills are markdown files (SKILL.md) that teach agents how to use extrasuite. Skills are distributed by the server from the `server/skills/` directory. See https://agentskills.io/home for the agent skills standard.