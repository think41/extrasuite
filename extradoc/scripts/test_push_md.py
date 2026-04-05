#!/usr/bin/env python3
"""Test push-md round-trip scenarios against a real Google Doc.

Creates/resets the doc for each scenario, pushes markdown, re-pulls,
and asserts the resulting structure is correct.

Usage:
    cd /Users/sripathikrishnan/apps/extrasuite-markdown
    uv run python extradoc/scripts/test_push_md.py <doc_url>

The script is non-destructive to other docs — it only modifies the target doc.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

EXTRASUITE = str(Path(__file__).parents[3] / "extrasuite-markdown" / "extrasuite")

PASS_STR = "\033[92mPASS\033[0m"
FAIL_STR = "\033[91mFAIL\033[0m"
_failures: list[str] = []


# ── CLI helpers ──────────────────────────────────────────────────────────────


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  CMD FAILED: {' '.join(cmd)}")
        print(f"  stdout: {result.stdout[:500]}")
        print(f"  stderr: {result.stderr[:500]}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def create_doc(title: str) -> str:
    """Create a new Google Doc and return its URL."""
    result = run([EXTRASUITE, "doc", "create", title])
    for line in result.stdout.splitlines():
        if line.startswith("URL:"):
            return line.split("URL:", 1)[1].strip()
    raise RuntimeError(f"Could not parse URL from create output:\n{result.stdout}")


def pull_md(doc_url: str, outdir: Path) -> Path:
    """Pull doc as markdown into outdir, return the doc folder."""
    run([EXTRASUITE, "doc", "pull-md", doc_url, str(outdir)])
    doc_id = extract_doc_id(doc_url)
    return outdir / doc_id


def push_md(folder: Path) -> None:
    run([EXTRASUITE, "doc", "push-md", str(folder)])


def extract_doc_id(url: str) -> str:
    m = re.search(r"/document/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError(f"Bad URL: {url}")
    return m.group(1)


def get_tab_file(folder: Path) -> Path:
    """Return the first .md tab file (not index.md)."""
    for f in sorted(folder.glob("*.md")):
        if f.name != "index.md":
            return f
    raise FileNotFoundError(f"No tab .md in {folder}")


def get_raw_doc(folder: Path) -> dict[str, Any]:
    raw_path = folder / ".raw" / "document.json"
    return json.loads(raw_path.read_text())


# ── Doc inspection ───────────────────────────────────────────────────────────


def body_content(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return raw["tabs"][0]["documentTab"]["body"]["content"]


def named_ranges(raw: dict[str, Any]) -> dict[str, Any]:
    return raw["tabs"][0]["documentTab"].get("namedRanges", {})


def describe(raw: dict[str, Any]) -> list[str]:
    """Human-readable summary of body elements."""
    lines = []
    for elem in body_content(raw):
        if "sectionBreak" in elem:
            lines.append("SB")
        elif "table" in elem:
            t = elem["table"]
            lines.append(f"Table({t.get('rows')}x{t.get('columns')})")
        elif "paragraph" in elem:
            p = elem["paragraph"]
            text = "".join(
                e.get("textRun", {}).get("content", "") for e in p.get("elements", [])
            )
            style = p.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
            lines.append(f"P({style},{text!r})")
    return lines


# ── Assertion helpers ────────────────────────────────────────────────────────


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"    {PASS_STR}  {label}")
    else:
        _failures.append(label)
        msg = f"    {FAIL_STR}  {label}"
        if detail:
            msg += f"\n           {detail}"
        print(msg)


def assert_body(
    raw: dict[str, Any], expected_types: list[str], label: str = ""
) -> None:
    """Assert body element types (SB/Table/Para) match expected pattern."""
    desc = describe(raw)
    # Match loosely: check expected_types appear in order
    di = 0
    for exp in expected_types:
        while di < len(desc) and exp not in desc[di]:
            di += 1
        if di >= len(desc):
            check(
                f"{label}: body matches {expected_types}",
                False,
                f"actual: {desc}",
            )
            return
        di += 1
    check(f"{label}: body has {expected_types}", True)


def count_stray_paras_before_first_table(raw: dict[str, Any]) -> int:
    """Count empty \\n paragraphs that appear between SB and the first table."""
    content = body_content(raw)
    count = 0
    for elem in content:
        if "table" in elem:
            break
        if "sectionBreak" in elem:
            continue
        if "paragraph" in elem:
            p = elem["paragraph"]
            text = "".join(
                e.get("textRun", {}).get("content", "") for e in p.get("elements", [])
            )
            if text.strip() == "":
                count += 1
    return count


def count_paras_between_tables(raw: dict[str, Any]) -> list[int]:
    """Return list of empty-para counts between consecutive tables."""
    content = body_content(raw)
    result = []
    last_table_idx: int | None = None
    for i, elem in enumerate(content):
        if "table" in elem:
            if last_table_idx is not None:
                between = content[last_table_idx + 1 : i]
                empty = sum(
                    1
                    for e in between
                    if "paragraph" in e
                    and all(
                        (el.get("textRun", {}).get("content", "")).strip() == ""
                        for el in e["paragraph"].get("elements", [])
                    )
                )
                result.append(empty)
            last_table_idx = i
    return result


# ── Scenarios ────────────────────────────────────────────────────────────────


def scenario(name: str, md: str, assertions_fn) -> None:
    print(f"\n── {name} ──")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # 1. Create a fresh doc for this scenario
        doc_url = create_doc(name)
        print(f"    doc: {doc_url}")
        # 2. Pull the empty doc
        folder = pull_md(doc_url, tmp)
        # 3. Write desired markdown
        tab = get_tab_file(folder)
        tab.write_text(md)
        # 4. Push
        push_md(folder)
        # 5. Re-pull (see real result)
        folder2 = pull_md(doc_url, tmp / "after")
        raw = get_raw_doc(folder2)
        desc = describe(raw)
        print(f"    body: {desc}")
        assertions_fn(raw)


def main() -> None:
    # ── S1: single code block + heading ─────────────────────────────────────
    def s1(raw):
        check("S1: has 1 table", sum(1 for e in body_content(raw) if "table" in e) == 1)
        check("S1: HEADING_1 present", any("HEADING_1" in d for d in describe(raw)))
        # insertTable always creates an unavoidable pre-table \n at the
        # insertion point. When the table is the first element after SB there
        # is no preceding paragraph whose trailing \n can absorb it, so at
        # most 1 stray empty para before the first table is expected.
        check(
            "S1: at most 1 stray empty para before table",
            count_stray_paras_before_first_table(raw) <= 1,
            f"stray count: {count_stray_paras_before_first_table(raw)}",
        )
        check(
            "S1: named range extradoc:codeblock:python",
            any(k.startswith("extradoc:codeblock:python") for k in named_ranges(raw)),
            f"named ranges: {list(named_ranges(raw).keys())}",
        )

    scenario(
        "S1: code block + heading",
        "```python\nx = 1\n```\n\n# My Heading\n",
        s1,
    )

    # ── S2: callout + heading ────────────────────────────────────────────────
    def s2(raw):
        check("S2: has 1 table", sum(1 for e in body_content(raw) if "table" in e) == 1)
        check("S2: HEADING_1 present", any("HEADING_1" in d for d in describe(raw)))
        check(
            "S2: at most 1 stray empty para before table",
            count_stray_paras_before_first_table(raw) <= 1,
        )
        check(
            "S2: named range extradoc:callout:warning",
            any(k.startswith("extradoc:callout:warning") for k in named_ranges(raw)),
            f"named ranges: {list(named_ranges(raw).keys())}",
        )

    scenario(
        "S2: callout + heading",
        "> [!WARNING]\n> Be careful here\n\n# My Heading\n",
        s2,
    )

    # ── S3: GFM table + heading ──────────────────────────────────────────────
    def s3(raw):
        check("S3: has 1 table", sum(1 for e in body_content(raw) if "table" in e) == 1)
        check("S3: HEADING_1 present", any("HEADING_1" in d for d in describe(raw)))
        check(
            "S3: at most 1 stray empty para before table",
            count_stray_paras_before_first_table(raw) <= 1,
        )

    scenario(
        "S3: GFM table + heading",
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n# My Heading\n",
        s3,
    )

    # ── S4: two consecutive code blocks + heading ────────────────────────────
    def s4(raw):
        tables = sum(1 for e in body_content(raw) if "table" in e)
        check("S4: has 2 tables", tables == 2, f"got {tables}")
        check("S4: HEADING_1 present", any("HEADING_1" in d for d in describe(raw)))
        check(
            "S4: at most 1 stray empty para before first table",
            count_stray_paras_before_first_table(raw) <= 1,
        )
        between = count_paras_between_tables(raw)
        check(
            "S4: exactly 1 empty para between tables",
            between == [1],
            f"between-table para counts: {between}",
        )
        codeblock_count = sum(
            len(group.get("namedRanges", []))
            for name, group in named_ranges(raw).items()
            if name.startswith("extradoc:codeblock")
        )
        check(
            "S4: 2 named ranges for codeblocks",
            codeblock_count == 2,
            f"got {codeblock_count}",
        )

    scenario(
        "S4: consecutive code blocks + heading",
        "```python\nx = 1\n```\n\n```python\ny = 2\n```\n\n# My Heading\n",
        s4,
    )

    # ── S5: code block between two paragraphs ────────────────────────────────
    def s5(raw):
        desc = describe(raw)
        check("S5: has 1 table", sum(1 for e in body_content(raw) if "table" in e) == 1)
        check(
            "S5: NORMAL_TEXT para before table",
            any("NORMAL_TEXT" in d and "Before" in d for d in desc),
        )
        check("S5: HEADING_1 after table", any("HEADING_1" in d for d in desc))

    scenario(
        "S5: para + code block + heading (inner slot)",
        "Before the code\n\n```python\nx = 1\n```\n\n# After Heading\n",
        s5,
    )

    # ── S6: three consecutive code blocks ────────────────────────────────────
    def s6(raw):
        tables = sum(1 for e in body_content(raw) if "table" in e)
        check("S6: has 3 tables", tables == 3, f"got {tables}")
        between = count_paras_between_tables(raw)
        check(
            "S6: exactly 1 empty para between each consecutive table pair",
            between == [1, 1],
            f"between-table para counts: {between}",
        )

    scenario(
        "S6: three consecutive code blocks",
        "```python\nx = 1\n```\n\n```python\ny = 2\n```\n\n```python\nz = 3\n```\n\n# End\n",
        s6,
    )

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    if not _failures:
        print(f"{PASS_STR}  All scenarios passed")
        sys.exit(0)
    else:
        print(f"{FAIL_STR}  {len(_failures)} assertion(s) failed:")
        for f in _failures:
            print(f"    - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
