---
name: release
description: Release one or more ExtraSuite packages to PyPI. Use when the user asks to release, publish, or cut a new version of any package. Handles version bumps, changelogs, git tags, PyPI publishing, and dependency propagation in the correct order.
disable-model-invocation: true
argument-hint: "[package(s) or 'all'] [optional: major|minor|patch]"
---

# ExtraSuite Release Skill

Release ExtraSuite packages to PyPI following the correct dependency order.

Usage:
- `/release extradoc` — release one package
- `/release extradoc extrasuite` — release multiple in correct order
- `/release all` — release everything that has unreleased changes

## Package Dependency Order

**Always release in this order** — `extrasuite` (client) depends on all others:

```
1. extrasheet    (standalone)
2. extraslide    (standalone)
3. extraform     (standalone)
4. extrascript   (standalone)
5. extradoc      (standalone)
6. extrasuite    (client — depends on all above)
```

When releasing multiple packages, sort by the order above regardless of what the user specified. Never release `extrasuite` before its dependencies.

## Step 1 — Assess What's Changed

For each package to release, run:

```bash
# Find last tag for this package
git tag --sort=-version:refname | grep "^<package>-v" | head -1

# What changed since that tag
git log --oneline <package>-vX.Y.Z..HEAD -- <package>/
```

If there are **no commits** since the last tag, skip this package — there's nothing to release.

## Step 2 — Determine Version Bump

Read `<package>/pyproject.toml` for the current version, then apply semver:

| Change type | Bump | Example |
|-------------|------|---------|
| Breaking changes, removed APIs | **major** | 1.2.3 → 2.0.0 |
| New features, new commands, new dependencies | **minor** | 1.2.3 → 1.3.0 |
| Bug fixes, docs, internal refactors | **patch** | 1.2.3 → 1.2.4 |

If the user specified a bump level (major/minor/patch), use that. Otherwise infer from the commits.

**Special case:** While any package is pre-1.0, treat minor bumps as patch and new features as minor (no major bumps until 1.0).

## Step 3 — Update CHANGELOG.md

Each package has `<package>/CHANGELOG.md`. Prepend a new section **above** the previous latest entry:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Breaking Changes   ← only if applicable
- ...
```

Rules:
- Date is today's date
- Only include sections that have content (omit empty `### Fixed` etc.)
- Be specific — reference the actual behaviour change, not just commit messages
- "Breaking Changes" section goes first if present

## Step 4 — Bump Version in pyproject.toml

Edit `<package>/pyproject.toml`:
```toml
version = "X.Y.Z"
```

If releasing `extrasuite` after a dependency was also bumped in this session, also update the dependency constraint:
```toml
"extradoc>=0.3.0",   # ← bump lower bound to new version
```

## Step 5 — Update uv.lock (if applicable)

For `extrasuite` (client) only, after updating `pyproject.toml`:
```bash
cd client && uv sync
```

This updates `client/uv.lock`. Commit the lock file alongside the version bump.

## Step 6 — Commit and Tag

```bash
git add <package>/pyproject.toml <package>/CHANGELOG.md [<package>/uv.lock]
git commit -m "Release <package> vX.Y.Z"
git tag <package>-vX.Y.Z
git push && git push origin <package>-vX.Y.Z
```

Tag format: `<package>-vX.Y.Z` (e.g. `extradoc-v0.3.0`, `extrasuite-v0.6.0`).

The GitHub Actions workflow validates that the tag version matches `pyproject.toml` — if they don't match, the publish will fail. Double-check before pushing the tag.

## Step 7 — Wait for PyPI Propagation

After pushing the tag, monitor the GitHub Actions run:

```bash
gh run watch $(gh run list --repo think41/extrasuite --limit 1 --json databaseId -q '.[0].databaseId') --repo think41/extrasuite
```

**Do not proceed to the next package until this completes successfully.**

Once the run shows ✓, verify the package is resolvable:
```bash
uv pip install <package>==X.Y.Z --dry-run --system
```

Only move on when this succeeds.

## Step 8 — Releasing extrasuite After Dependencies

If you bumped any dependency package in this release session, update the lower-bound constraint in `client/pyproject.toml` before releasing `extrasuite`:

```toml
"extradoc>=0.3.0",   # was >=0.2.2
```

Then run `uv sync` in `client/` to update the lock file, and include `uv.lock` in the release commit.

## Pre-Release Checklist

Before cutting any release, verify:

- [ ] Working on `main` branch (not a feature branch)
- [ ] `git status` is clean — no uncommitted changes
- [ ] Tests pass: `cd <package> && uv run pytest tests/ -v`
- [ ] Linter passes: `uv run ruff check .`
- [ ] CHANGELOG.md entry is written and accurate
- [ ] Version in `pyproject.toml` matches the intended tag

## Common Mistakes

**Wrong order** — releasing `extrasuite` before `extradoc` means users get the old extradoc. Always check the dependency graph.

**Skipping the PyPI wait** — the next package's `uv sync` will fail to resolve the new version if PyPI hasn't indexed it yet. Always wait for propagation.

**Tag/version mismatch** — if `pyproject.toml` says `0.3.0` but you tag `extradoc-v0.3.1`, the GitHub Actions workflow aborts. Make sure they match exactly before pushing the tag.

**Forgetting uv.lock** — when bumping `extrasuite`'s dependencies, always run `uv sync` and commit the updated `uv.lock`. Otherwise users installing from source get stale lock resolution.

**Empty changelog section** — don't include `### Fixed` or `### Changed` sections with no content. Only include sections that have actual entries.
