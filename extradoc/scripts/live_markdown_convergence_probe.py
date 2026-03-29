#!/usr/bin/env python3
"""Run a live multi-tab markdown convergence probe against Google Docs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from extradoc.markdown_compare import compare_markdown_tabs, load_markdown_tabs

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRASUITE = REPO_ROOT / "extrasuite"
ARTIFACTS_ROOT = REPO_ROOT / "tmp-doc-md-verify" / "live-convergence-probe"

INITIAL_TABS = {
    "Tab_1": """# Program Overview

This tab mixes **bold**, *italic*, ~~strikethrough~~, <u>underline</u>, `inline code`, and a [Docs API link](https://developers.google.com/docs/api/reference/rest).

This paragraph also carries a footnote reference.[^overview-note]

## Alerts

> [!INFO]
> Info callout opening text.

> [!WARNING]
> Warning callout opening text.

> This is a plain blockquote that should stay a blockquote.
> It intentionally spans two lines.

## Lists

- First bullet
- Second bullet
  - Nested bullet
1. First number
2. Second number
- [x] Checked item
- [ ] Pending item

## Code Samples

```python
def sprint_status() -> str:
    return "green"
```

```json
{"stage": "initial", "verified": true}
```

---

[^overview-note]: Footnote text for the overview tab.
""",
    "Operations_Tab": """# Operations Matrix

This tab focuses on heading boundaries around tables.

## Delivery Table

| Area | Owner | Status |
| --- | --- | --- |
| Parsing | **IR** | green |
| Lowering | `planner` | yellow |
| Docs | [reference](https://developers.google.com/docs/api/reference/rest) | green |

## HTML Table

<table>
  <tr>
    <th>Track</th>
    <th>Notes</th>
  </tr>
  <tr>
    <td>Planning</td>
    <td><strong>Structured</strong> HTML cell text</td>
  </tr>
  <tr>
    <td>QA</td>
    <td>Watch for heading bleed after edits</td>
  </tr>
</table>

## After Table

Paragraph after the HTML table to verify style boundaries.
""",
    "Cell_Workbench": """# Cell Workbench

## Rich Cells

| Column A | Column B |
| --- | --- |
| Alpha | **Bold** inside a cell |
| Beta | `Code` inside a cell |
| Gamma | [Linked](https://example.com) cell text |
| Delta | *Italic* plus ~~strike~~ in one cell |

## Quotes and Notes

> [!NOTE]
> A note callout after the rich-cell table.

## Edit Targets

Heading-adjacent prose should remain plain text.

### Follow-up

Table edits and heading edits will happen on the second pass.
""",
}

EDITED_TABS = {
    "Tab_1": """# Program Overview Revised

This tab now mixes **bold**, *italic*, ~~strikethrough~~, <u>underline</u>, `inline code`, and a [Docs API link](https://developers.google.com/docs/api/reference/rest) after a second-pass edit.

This replacement paragraph still carries a footnote reference after editing.[^overview-note]

## Alerts Revised

> [!TIP]
> Tip callout replacement text.

> [!WARNING]
> Warning callout edited text.

> The blockquote changed and should still stay ordinary quote prose.
> It now has replacement wording.

## Lists Revised

- First bullet edited
- Second bullet edited
  - Nested bullet edited
1. First number edited
2. Second number edited
- [x] Checked item edited
- [ ] Pending item edited

## Code Samples Revised

```python
def sprint_status() -> str:
    return "blue"
```

```json
{"stage": "edited", "verified": false}
```

---

[^overview-note]: Footnote text for the overview tab after edits.
""",
    "Operations_Tab": """# Operations Matrix Updated

This tab replaces prose around headings and table boundaries.

## Delivery Table Updated

| Area | Owner | Status |
| --- | --- | --- |
| Parsing | **IR Core** | green |
| Lowering | `planner-v2` | green |
| Docs | [REST reference](https://developers.google.com/docs/api/reference/rest) | yellow |

## HTML Table Updated

<table>
  <tr>
    <th>Track</th>
    <th>Notes</th>
  </tr>
  <tr>
    <td>Planning Revised</td>
    <td><strong>Structured</strong> HTML cell text after edits</td>
  </tr>
  <tr>
    <td>QA</td>
    <td>Heading bleed should be gone after replacement edits</td>
  </tr>
</table>

## After Table Updated

Paragraph after the HTML table now has replacement text and should still remain plain prose.
""",
    "Cell_Workbench": """# Cell Workbench Updated

## Rich Cells Updated

| Column A | Column B |
| --- | --- |
| Alpha Revised | **Bold** inside a cell edited |
| Beta Revised | `Code` inside a cell edited |
| Gamma Revised | [Linked replacement](https://example.com/updated) cell text |
| Delta Revised | *Italic* plus ~~strike~~ after edits |

## Quotes and Notes Updated

> [!IMPORTANT]
> The callout below the table was replaced and should not disturb headings.

## Edit Targets Updated

Heading-adjacent prose was replaced and must remain plain text.

### Follow-up Updated

Second-pass heading replacements should not bleed into surrounding table cells or prose.
""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc-url",
        help="Reuse an existing document instead of creating a new one.",
    )
    args = parser.parse_args()

    doc_url = args.doc_url or _create_empty_doc("Live Markdown Convergence Probe")
    doc_id = _extract_document_id(doc_url)
    artifacts_dir = ARTIFACTS_ROOT / doc_id
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    initial_workdir = artifacts_dir / "cycle1-authored"
    repull1_parent = artifacts_dir / "cycle1-repull"
    edited_workdir = artifacts_dir / "cycle2-authored"
    repull2_parent = artifacts_dir / "cycle2-repull"

    initial_folder = _pull_md(doc_url, initial_workdir)
    _author_markdown_folder(initial_folder, INITIAL_TABS)
    _push_md(initial_folder)

    repull1_folder = _pull_md(doc_url, repull1_parent)
    comparison1 = compare_markdown_tabs(INITIAL_TABS, load_markdown_tabs(repull1_folder))
    _write_json(artifacts_dir / "cycle1-comparison.json", comparison1.to_dict())

    shutil.copytree(repull1_folder, edited_workdir)
    edited_folder = _markdown_folder_under(edited_workdir, doc_id)
    _author_markdown_folder(edited_folder, EDITED_TABS)
    _push_md(edited_folder)

    repull2_folder = _pull_md(doc_url, repull2_parent)
    comparison2 = compare_markdown_tabs(EDITED_TABS, load_markdown_tabs(repull2_folder))
    _write_json(artifacts_dir / "cycle2-comparison.json", comparison2.to_dict())

    summary = {
        "doc_url": doc_url,
        "doc_id": doc_id,
        "cycle1_matching": comparison1.matching,
        "cycle2_matching": comparison2.matching,
    }
    _write_json(artifacts_dir / "summary.json", summary)

    print(json.dumps(summary, indent=2))
    if not comparison1.matching or not comparison2.matching:
        raise SystemExit(1)


def _author_markdown_folder(folder: Path, tabs: dict[str, str]) -> None:
    for path in folder.glob("*.md"):
        if path.name == "index.md":
            continue
        path.unlink()
    _rewrite_index_xml(folder / "index.xml", tabs)
    for name, content in tabs.items():
        (folder / f"{name}.md").write_text(content, encoding="utf-8")


def _rewrite_index_xml(path: Path, tabs: dict[str, str]) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    existing_tab_ids: dict[str, str] = {}
    for child in list(root):
        if child.tag == "tab":
            folder = child.get("folder")
            tab_id = child.get("id")
            if folder and tab_id:
                existing_tab_ids[folder] = tab_id
    for child in list(root):
        if child.tag == "tab":
            root.remove(child)
    for index, name in enumerate(tabs):
        root.append(
            ET.Element(
                "tab",
                {
                    "id": existing_tab_ids.get(name, f"t.probe{index}"),
                    "title": name.replace("_", " "),
                    "folder": name,
                },
            )
        )
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _pull_md(doc_url: str, output_dir: Path) -> Path:
    _run([str(EXTRASUITE), "docs", "pull-md", doc_url, str(output_dir)])
    return _markdown_folder_under(output_dir, _extract_document_id(doc_url))


def _markdown_folder_under(output_dir: Path, doc_id: str) -> Path:
    direct_folder = output_dir
    nested_folder = output_dir / doc_id
    if (direct_folder / "index.xml").exists():
        return direct_folder
    if (nested_folder / "index.xml").exists():
        return nested_folder
    raise FileNotFoundError(f"Could not find pulled markdown folder under {output_dir}")


def _push_md(folder: Path) -> None:
    _run([str(EXTRASUITE), "docs", "push-md", str(folder)])


def _create_empty_doc(title: str) -> str:
    result = _run([str(EXTRASUITE), "docs", "create-empty", title])
    match = re.search(r"^URL:\s*(https://docs.google.com/document/d/[^\s]+)$", result.stdout, re.M)
    if match is None:
        raise RuntimeError(f"Could not parse doc URL from output:\n{result.stdout}")
    return match.group(1)


def _extract_document_id(doc_url: str) -> str:
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
    if match is None:
        raise ValueError(f"Bad document URL: {doc_url}")
    return match.group(1)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


if __name__ == "__main__":
    main()
