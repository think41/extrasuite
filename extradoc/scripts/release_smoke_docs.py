#!/usr/bin/env python3
"""Run release-smoke Docs workflows through the CLI and compare convergence.

This harness uses the CLI for all live Google Docs operations. It writes a
report under ``tmp-doc-md-verify/release-smoke/<run_id>/`` containing:

1. authored folders for each cycle
2. re-pulled folders after each push
3. structured comparison output
4. a summary JSON report
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from extradoc.markdown_compare import compare_markdown_tabs, load_markdown_tabs
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.diff import diff_documents, summarize_semantic_edits
from extradoc.serde.xml import XmlSerde

_xml_serde = XmlSerde()

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRASUITE = REPO_ROOT / "extrasuite"
ARTIFACTS_ROOT = REPO_ROOT / "tmp-doc-md-verify" / "release-smoke"

MARKDOWN_INITIAL_TABS = {
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

MARKDOWN_EDITED_TABS = {
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

XML_INITIAL_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<tab id="t.0" title="Tab 1" index="0">
  <body>
    <sectionbreak
      sectionType="CONTINUOUS"
      contentDirection="LEFT_TO_RIGHT"
      columnSeparatorStyle="NONE"
      defaultHeaderId="h.release"
      defaultFooterId="f.release"
    />
    <h1>Release XML Smoke</h1>
    <p>Paragraph with a <a href="https://example.com/release">release link</a> and a footnote marker<footnoteref id="fn.release" />.</p>
    <li type="bullet">First bullet</li>
    <li type="bullet">Second bullet</li>
    <p>Paragraph before the table.</p>
    <table>
      <tr>
        <td>
          <p><t><b>Bold</b></t><t> cell text</t></p>
        </td>
        <td>
          <p>Plain cell</p>
        </td>
      </tr>
      <tr>
        <td>
          <p>Nested table host.</p>
          <table>
            <tr>
              <td><p>Inner A1</p></td>
              <td><p>Inner A2</p></td>
            </tr>
          </table>
        </td>
        <td>
          <p><a href="https://example.com/table">Cell link</a></p>
        </td>
      </tr>
    </table>
    <p>After table paragraph.</p>
    <pagebreak />
    <h2>After Break</h2>
    <p>Closing prose.</p>
  </body>
  <header id="h.release">
    <p>Release Header</p>
  </header>
  <footer id="f.release">
    <p>Release Footer</p>
  </footer>
  <footnote id="fn.release">
    <p>Release footnote text.</p>
  </footnote>
</tab>
"""

XML_EDITED_DOCUMENT = """<?xml version="1.0" encoding="UTF-8"?>
<tab id="t.0" title="Tab 1" index="0">
  <body>
    <sectionbreak
      sectionType="CONTINUOUS"
      contentDirection="LEFT_TO_RIGHT"
      columnSeparatorStyle="NONE"
      defaultHeaderId="h.release"
      defaultFooterId="f.release"
    />
    <h1>Release XML Smoke Updated</h1>
    <p>Paragraph with a <a href="https://example.com/release-updated">release link</a> and the edited footnote marker<footnoteref id="fn.release" />.</p>
    <li type="bullet">First bullet updated</li>
    <li type="bullet">Second bullet updated</li>
    <p>Paragraph before the table updated.</p>
    <table>
      <tr>
        <td>
          <p><t><b>Bold</b></t><t> cell text updated</t></p>
        </td>
        <td>
          <p>Plain cell updated</p>
        </td>
      </tr>
      <tr>
        <td>
          <p>Nested table host updated.</p>
          <table>
            <tr>
              <td><p>Inner A1 updated</p></td>
              <td><p>Inner A2 updated</p></td>
            </tr>
          </table>
        </td>
        <td>
          <p><a href="https://example.com/table-updated">Cell link updated</a></p>
        </td>
      </tr>
    </table>
    <p>After table paragraph updated.</p>
    <pagebreak />
    <h2>After Break Updated</h2>
    <p>Closing prose updated.</p>
  </body>
  <header id="h.release">
    <p>Release Header Updated</p>
  </header>
  <footer id="f.release">
    <p>Release Footer Updated</p>
  </footer>
  <footnote id="fn.release">
    <p>Release footnote text updated.</p>
  </footnote>
</tab>
"""


@dataclass(slots=True)
class ScenarioResult:
    name: str
    doc_url: str | None = None
    passed: bool = False
    cycle1: dict[str, Any] = field(default_factory=dict)
    cycle2: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        help="Optional run id for artifact folder naming. Defaults to a timestamp.",
    )
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    artifacts_dir = ARTIFACTS_ROOT / run_id
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    results = [
        _run_markdown_multitab_scenario(artifacts_dir),
        _run_xml_structural_scenario(artifacts_dir),
    ]
    summary = {
        "run_id": run_id,
        "artifacts_dir": str(artifacts_dir),
        "overall_passed": all(result.passed for result in results),
        "scenarios": [asdict(result) for result in results],
    }
    _write_json(artifacts_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    if not summary["overall_passed"]:
        raise SystemExit(1)


def _run_markdown_multitab_scenario(artifacts_dir: Path) -> ScenarioResult:
    result = ScenarioResult(name="markdown_multitab")
    try:
        doc_url = _create_empty_doc("Release Smoke Markdown")
        result.doc_url = doc_url
        doc_id = _extract_document_id(doc_url)
        scenario_dir = artifacts_dir / "markdown_multitab"
        scenario_dir.mkdir(parents=True, exist_ok=True)

        cycle1_authored = scenario_dir / "cycle1-authored"
        cycle1_repull = scenario_dir / "cycle1-repull"
        cycle2_authored = scenario_dir / "cycle2-authored"
        cycle2_repull = scenario_dir / "cycle2-repull"

        authored_folder = _pull_md(doc_url, cycle1_authored)
        _author_markdown_folder(authored_folder, MARKDOWN_INITIAL_TABS)
        _push_md(authored_folder)

        repull1_folder = _pull_md(doc_url, cycle1_repull)
        comparison1 = compare_markdown_tabs(
            MARKDOWN_INITIAL_TABS,
            load_markdown_tabs(repull1_folder),
        )
        result.cycle1 = comparison1.to_dict()
        _write_json(scenario_dir / "cycle1-comparison.json", comparison1.to_dict())

        shutil.copytree(repull1_folder, cycle2_authored)
        authored2_folder = _markdown_folder_under(cycle2_authored, doc_id)
        _author_markdown_folder(authored2_folder, MARKDOWN_EDITED_TABS)
        _push_md(authored2_folder)

        repull2_folder = _pull_md(doc_url, cycle2_repull)
        comparison2 = compare_markdown_tabs(
            MARKDOWN_EDITED_TABS,
            load_markdown_tabs(repull2_folder),
        )
        result.cycle2 = comparison2.to_dict()
        _write_json(scenario_dir / "cycle2-comparison.json", comparison2.to_dict())

        result.passed = comparison1.matching and comparison2.matching
        return result
    except Exception as exc:  # pragma: no cover - live workflow reporting
        result.error = f"{exc}\n{traceback.format_exc()}"
        return result


def _run_xml_structural_scenario(artifacts_dir: Path) -> ScenarioResult:
    result = ScenarioResult(name="xml_structural")
    try:
        doc_url = _create_empty_doc("Release Smoke XML")
        result.doc_url = doc_url
        doc_id = _extract_document_id(doc_url)
        scenario_dir = artifacts_dir / "xml_structural"
        scenario_dir.mkdir(parents=True, exist_ok=True)

        cycle1_authored = scenario_dir / "cycle1-authored"
        cycle1_repull = scenario_dir / "cycle1-repull"
        cycle2_authored = scenario_dir / "cycle2-authored"
        cycle2_repull = scenario_dir / "cycle2-repull"

        authored_folder = _pull_xml(doc_url, cycle1_authored)
        _author_xml_folder(authored_folder, XML_INITIAL_DOCUMENT)
        _push_xml(authored_folder)

        repull1_folder = _pull_xml(doc_url, cycle1_repull)
        comparison1 = _compare_xml_folders(authored_folder, repull1_folder)
        result.cycle1 = comparison1
        _write_json(scenario_dir / "cycle1-comparison.json", comparison1)

        shutil.copytree(repull1_folder, cycle2_authored)
        authored2_folder = _xml_folder_under(cycle2_authored, doc_id)
        _author_xml_folder(authored2_folder, XML_EDITED_DOCUMENT)
        _push_xml(authored2_folder)

        repull2_folder = _pull_xml(doc_url, cycle2_repull)
        comparison2 = _compare_xml_folders(authored2_folder, repull2_folder)
        result.cycle2 = comparison2
        _write_json(scenario_dir / "cycle2-comparison.json", comparison2)

        result.passed = comparison1["matching"] and comparison2["matching"]
        return result
    except Exception as exc:  # pragma: no cover - live workflow reporting
        result.error = f"{exc}\n{traceback.format_exc()}"
        return result


def _compare_xml_folders(desired_folder: Path, actual_folder: Path) -> dict[str, Any]:
    desired_bundle = _xml_serde._parse(desired_folder)
    actual_bundle = _xml_serde._parse(actual_folder)
    desired_doc = reindex_document(desired_bundle.document)
    actual_doc = reindex_document(actual_bundle.document)
    edits = diff_documents(actual_doc, desired_doc)

    desired_xml = _primary_document_xml(desired_folder)
    actual_xml = _primary_document_xml(actual_folder)
    xml_diff = tuple(
        difflib.unified_diff(
            desired_xml.splitlines(),
            actual_xml.splitlines(),
            fromfile="desired/document.xml",
            tofile="actual/document.xml",
            lineterm="",
        )
    )

    return {
        "matching": not edits,
        "semantic_edits": summarize_semantic_edits(edits),
        "xml_diff": list(xml_diff[:200]),
    }


def _primary_document_xml(folder: Path) -> str:
    xml_paths = sorted(folder.glob("*/document.xml"))
    if not xml_paths:
        raise FileNotFoundError(f"No document.xml found under {folder}")
    return xml_paths[0].read_text(encoding="utf-8")


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
                    "id": existing_tab_ids.get(name, f"t.release{index}"),
                    "title": name.replace("_", " "),
                    "folder": name,
                },
            )
        )
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _author_xml_folder(folder: Path, document_xml: str) -> None:
    tab_dirs = [
        path
        for path in folder.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]
    if len(tab_dirs) != 1:
        raise ValueError(
            f"Expected exactly one tab folder under {folder}, found {tab_dirs!r}"
        )
    tab_dir = tab_dirs[0]
    (tab_dir / "document.xml").write_text(document_xml, encoding="utf-8")
    styles_path = tab_dir / "styles.xml"
    if not styles_path.exists():
        styles_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<styles />\n', encoding="utf-8"
        )


def _pull_md(doc_url: str, output_dir: Path) -> Path:
    _run([str(EXTRASUITE), "docs", "pull-md", doc_url, str(output_dir)])
    return _markdown_folder_under(output_dir, _extract_document_id(doc_url))


def _pull_xml(doc_url: str, output_dir: Path) -> Path:
    _run([str(EXTRASUITE), "docs", "pull", doc_url, str(output_dir)])
    return _xml_folder_under(output_dir, _extract_document_id(doc_url))


def _markdown_folder_under(output_dir: Path, doc_id: str) -> Path:
    direct_folder = output_dir
    nested_folder = output_dir / doc_id
    if (direct_folder / "index.xml").exists():
        return direct_folder
    if (nested_folder / "index.xml").exists():
        return nested_folder
    raise FileNotFoundError(f"Could not find pulled markdown folder under {output_dir}")


def _xml_folder_under(output_dir: Path, doc_id: str) -> Path:
    direct_folder = output_dir
    nested_folder = output_dir / doc_id
    if (direct_folder / "index.xml").exists():
        return direct_folder
    if (nested_folder / "index.xml").exists():
        return nested_folder
    raise FileNotFoundError(f"Could not find pulled XML folder under {output_dir}")


def _push_md(folder: Path) -> None:
    _run([str(EXTRASUITE), "docs", "push-md", str(folder), "--verify"])


def _push_xml(folder: Path) -> None:
    _run([str(EXTRASUITE), "docs", "push", str(folder), "--verify"])


def _create_empty_doc(title: str) -> str:
    result = _run([str(EXTRASUITE), "docs", "create-empty", title])
    match = re.search(
        r"^URL:\s*(https://docs.google.com/document/d/[^\s]+)$", result.stdout, re.M
    )
    if match is None:
        raise RuntimeError(f"Could not parse doc URL from output:\n{result.stdout}")
    return match.group(1)


def _extract_document_id(doc_url: str) -> str:
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
    if match is None:
        raise ValueError(f"Bad document URL: {doc_url}")
    return match.group(1)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
