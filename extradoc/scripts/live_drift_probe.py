#!/usr/bin/env python3
"""Two-phase live drift probe for extradoc push→repull convergence.

Identifies scenarios where the markdown pushed to Google Docs does not match
the markdown returned by a subsequent re-pull (i.e., "drift").  Run this
script in cycles to accumulate evidence, then use the cycle artifacts to write
xfail regression tests.

Usage
-----
Phase 1 — pull and prepare for manual editing:

    uv run python extradoc/scripts/live_drift_probe.py phase1 \\
        --doc-url "https://docs.google.com/document/d/DOC_ID/edit" \\
        --work-dir /tmp/drift-probe

    This pulls the document into  <work-dir>/cycle-NNN/stage1/<doc_id>/
    and prints the path where you should make edits.

Phase 2 — push, re-pull, and compare:

    uv run python extradoc/scripts/live_drift_probe.py phase2 \\
        --doc-url "https://docs.google.com/document/d/DOC_ID/edit" \\
        --work-dir /tmp/drift-probe

    This pushes the edits from cycle-NNN/stage1, re-pulls to
    cycle-NNN/stage2, diffs the two states, and writes a JSON report.

Repeat in cycles.  Each cycle is auto-numbered (cycle-001, cycle-002, …).
Use --cycle N to target a specific cycle.

Drift report
-----------
For each tab, the report records:
  - identical: True / False
  - diff: unified diff lines (pushed vs re-pulled)
  - pattern_hints: named patterns detected in the diff (bold_boundary,
    footnote_ref, inline_code, underline_boundary)

These hints are the starting point for writing targeted xfail tests.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRASUITE = REPO_ROOT / "extrasuite"

# Patterns to auto-detect in drift lines
DRIFT_PATTERNS: list[tuple[str, str]] = [
    ("bold_boundary", r"\*\*"),
    ("italic_boundary", r"(?<!\*)\*(?!\*)"),
    ("underline_boundary", r"</?u>"),
    ("inline_code", r"`[^`]"),
    ("footnote_ref", r"\[\^"),
    ("strikethrough_boundary", r"~~"),
    ("link_text", r"\[.*?\]\("),
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="phase", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--doc-url",
        required=True,
        help="Google Docs URL (https://docs.google.com/document/d/DOC_ID/...)",
    )
    common.add_argument(
        "--work-dir",
        type=Path,
        default=Path("tmp-drift-probe"),
        help="Root directory for probe artifacts (default: ./tmp-drift-probe)",
    )
    common.add_argument(
        "--cycle",
        type=int,
        default=None,
        help="Explicit cycle number (default: auto-detect next / current)",
    )

    sub.add_parser("phase1", parents=[common], help="Pull and prepare for editing")
    sub.add_parser("phase2", parents=[common], help="Push, re-pull, and compare")

    args = parser.parse_args()
    doc_id = _extract_doc_id(args.doc_url)

    if args.phase == "phase1":
        run_phase1(doc_id, args.doc_url, args.work_dir, args.cycle)
    else:
        run_phase2(doc_id, args.doc_url, args.work_dir, args.cycle)


# ---------------------------------------------------------------------------
# Phase 1: pull + present edit target
# ---------------------------------------------------------------------------


def run_phase1(
    doc_id: str, doc_url: str, work_dir: Path, cycle: int | None
) -> None:
    cycle_n = cycle if cycle is not None else _next_cycle(work_dir)
    cycle_dir = work_dir / f"cycle-{cycle_n:03d}"
    stage1_dir = cycle_dir / "stage1"

    if stage1_dir.exists():
        shutil.rmtree(stage1_dir)
    stage1_dir.mkdir(parents=True)

    print(f"\n[drift-probe] Cycle {cycle_n:03d} — Phase 1")
    print(f"[drift-probe] Pulling {doc_url}")
    _pull_md(doc_url, stage1_dir)

    doc_folder = _find_doc_folder(stage1_dir, doc_id)
    print(f"\n[drift-probe] Pulled to: {doc_folder}")
    print("\n[drift-probe] Current markdown content:")
    print("-" * 72)
    for md_file in sorted((doc_folder / "tabs").glob("*.md")):
        print(f"\n=== {md_file.name} ===")
        print(md_file.read_text(encoding="utf-8"))
    print("-" * 72)
    print(
        f"\n[drift-probe] NOW: edit the markdown files in:\n  {doc_folder}/tabs/\n"
    )
    print(
        "[drift-probe] Focus areas to probe: "
        "bold/italic markers, inline code, links, footnote refs.\n"
    )
    print(
        f"[drift-probe] When done, run:\n"
        f"  uv run python extradoc/scripts/live_drift_probe.py phase2 "
        f"--doc-url '{doc_url}' --work-dir {work_dir} --cycle {cycle_n}\n"
    )

    _write_json(cycle_dir / "meta.json", {"doc_id": doc_id, "doc_url": doc_url, "cycle": cycle_n})


# ---------------------------------------------------------------------------
# Phase 2: push → re-pull → compare
# ---------------------------------------------------------------------------


def run_phase2(
    doc_id: str, doc_url: str, work_dir: Path, cycle: int | None
) -> None:
    cycle_n = cycle if cycle is not None else _current_cycle(work_dir)
    if cycle_n is None:
        print("[drift-probe] ERROR: no phase1 artifacts found — run phase1 first.")
        sys.exit(1)

    cycle_dir = work_dir / f"cycle-{cycle_n:03d}"
    stage1_dir = cycle_dir / "stage1"
    stage2_dir = cycle_dir / "stage2"

    doc_folder = _find_doc_folder(stage1_dir, doc_id)
    print(f"\n[drift-probe] Cycle {cycle_n:03d} — Phase 2")
    print(f"[drift-probe] Pushing from: {doc_folder}")

    # Capture what we're about to push (before push modifies pristine)
    pushed_tabs = _read_tabs(doc_folder)

    _push_md(doc_folder)
    print("[drift-probe] Push complete.  Re-pulling …")

    if stage2_dir.exists():
        shutil.rmtree(stage2_dir)
    stage2_dir.mkdir(parents=True)
    _pull_md(doc_url, stage2_dir)

    repull_folder = _find_doc_folder(stage2_dir, doc_id)
    repull_tabs = _read_tabs(repull_folder)

    report = _build_report(pushed_tabs, repull_tabs, cycle_n)
    report_path = cycle_dir / "drift-report.json"
    _write_json(report_path, report)

    _print_report(report)
    print(f"\n[drift-probe] Full report saved to: {report_path}")

    if report["any_drift"]:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _build_report(
    pushed: dict[str, str],
    repull: dict[str, str],
    cycle_n: int,
) -> dict:
    tab_reports: list[dict] = []
    all_tab_names = sorted(set(pushed) | set(repull))

    for tab in all_tab_names:
        pushed_lines = pushed.get(tab, "").splitlines(keepends=True)
        repull_lines = repull.get(tab, "").splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(
                pushed_lines,
                repull_lines,
                fromfile=f"pushed/{tab}",
                tofile=f"repull/{tab}",
            )
        )
        identical = len(diff) == 0
        patterns = _detect_patterns(diff) if not identical else []

        tab_reports.append(
            {
                "tab": tab,
                "identical": identical,
                "diff": "".join(diff),
                "pattern_hints": patterns,
            }
        )

    any_drift = any(not t["identical"] for t in tab_reports)
    return {
        "cycle": cycle_n,
        "any_drift": any_drift,
        "tabs": tab_reports,
        "summary": _make_summary(tab_reports),
    }


def _detect_patterns(diff_lines: list[str]) -> list[str]:
    """Identify named drift patterns in the diff output."""
    changed = "".join(
        line[1:] for line in diff_lines if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    found: list[str] = []
    for name, pattern in DRIFT_PATTERNS:
        if re.search(pattern, changed):
            found.append(name)
    return found


def _make_summary(tab_reports: list[dict]) -> str:
    drifted = [t for t in tab_reports if not t["identical"]]
    if not drifted:
        return "All tabs converged — no drift detected."
    lines = [f"DRIFT detected in {len(drifted)}/{len(tab_reports)} tab(s):"]
    for t in drifted:
        patterns = ", ".join(t["pattern_hints"]) or "unknown"
        lines.append(f"  {t['tab']}: patterns = [{patterns}]")
    return "\n".join(lines)


def _print_report(report: dict) -> None:
    print(f"\n{'=' * 72}")
    print(f"[drift-probe] {report['summary']}")
    print(f"{'=' * 72}")
    for tab in report["tabs"]:
        if not tab["identical"]:
            print(f"\n=== DRIFT in {tab['tab']} ===")
            print(tab["diff"])
    if not report["any_drift"]:
        print("\n[drift-probe] No drift — pushed markdown == re-pulled markdown.")


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _read_tabs(doc_folder: Path) -> dict[str, str]:
    """Read all tab markdown files, stripping YAML frontmatter."""
    tabs: dict[str, str] = {}
    tabs_dir = doc_folder / "tabs"
    if not tabs_dir.is_dir():
        return tabs
    for md_file in sorted(tabs_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        tabs[md_file.name] = _strip_frontmatter(content)
    return tabs


def _strip_frontmatter(md: str) -> str:
    """Strip YAML front-matter block (--- ... ---) if present."""
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4 :].lstrip("\n")
    return md


def _find_doc_folder(parent: Path, doc_id: str) -> Path:
    """Find the pulled document folder under parent."""
    direct = parent / doc_id
    if direct.is_dir():
        return direct
    # Fallback: single subdirectory
    subdirs = [d for d in parent.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    raise FileNotFoundError(
        f"Cannot locate pulled document folder for {doc_id!r} under {parent}"
    )


def _next_cycle(work_dir: Path) -> int:
    return _current_cycle(work_dir, next_cycle=True) or 1


def _current_cycle(work_dir: Path, *, next_cycle: bool = False) -> int | None:
    if not work_dir.is_dir():
        return 1 if next_cycle else None
    existing = sorted(
        int(d.name.split("-")[1])
        for d in work_dir.iterdir()
        if d.is_dir() and re.match(r"cycle-\d+", d.name)
    )
    if not existing:
        return 1 if next_cycle else None
    return (existing[-1] + 1) if next_cycle else existing[-1]


# ---------------------------------------------------------------------------
# extrasuite CLI wrappers
# ---------------------------------------------------------------------------


def _pull_md(doc_url: str, output_dir: Path) -> None:
    _run([str(EXTRASUITE), "docs", "pull-md", doc_url, str(output_dir)])


def _push_md(folder: Path) -> None:
    _run([str(EXTRASUITE), "docs", "push-md", str(folder)])


def _extract_doc_id(doc_url: str) -> str:
    m = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
    if m is None:
        raise ValueError(f"Cannot extract document ID from URL: {doc_url!r}")
    return m.group(1)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[drift-probe] Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
