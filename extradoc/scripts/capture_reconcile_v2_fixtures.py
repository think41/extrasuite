#!/usr/bin/env python3
"""Capture small real-Docs fixture pairs for reconcile_v2 confidence sprints.

The fixtures are intentionally tiny and purpose-built. Each scenario creates a
fresh live Google Doc, applies a base state, captures raw transport JSON, then
applies a desired state and captures raw JSON again.

Run from the repo root:

    uv run --project client python extradoc/scripts/capture_reconcile_v2_fixtures.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from extrasuite.client import CredentialsManager

from extradoc import GoogleDocsTransport
from extradoc.api_types._generated import Document
from extradoc.reconcile_v2.api import summarize_document

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRASUITE = REPO_ROOT / "extrasuite"
DEFAULT_FIXTURES_ROOT = REPO_ROOT / "extradoc" / "tests" / "reconcile_v2" / "fixtures"


@dataclass(frozen=True, slots=True)
class MarkdownScenario:
    name: str
    title: str
    description: str
    base_md: str | None = None
    desired_md: str | None = None
    base_tabs: dict[str, str] | None = None
    desired_tabs: dict[str, str] | None = None
    expected_lowered_requests: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class BatchScenario:
    name: str
    title: str
    description: str
    base_md: str


@dataclass(frozen=True, slots=True)
class HeaderScenario:
    name: str
    title: str
    description: str
    base_md: str
    base_header_text: str
    desired_header_text: str


@dataclass(frozen=True, slots=True)
class NamedRangeScenario:
    name: str
    title: str
    description: str
    base_md: str
    range_name: str
    target_text: str


@dataclass(frozen=True, slots=True)
class RequestScenario:
    name: str
    title: str
    description: str
    base_md: str
    desired_requests: tuple[dict, ...] = ()
    base_setup_requests: tuple[dict, ...] = ()
    base_setup_builder: Callable[[dict], list[dict]] | None = None
    base_setup_procedure: Callable[[_RawDocsClient, str, dict], list[list[dict]]] | None = None
    desired_request_builder: Callable[[dict], list[dict]] | None = None
    expected_lowered_requests: tuple[dict, ...] = ()
    expected_lowered_builder: Callable[[dict], list[dict]] | None = None


@dataclass(frozen=True, slots=True)
class TableScenario:
    name: str
    title: str
    description: str
    base_md: str
    desired_requests: tuple[dict, ...] = ()
    base_setup_requests: tuple[dict, ...] = ()
    base_setup_builder: Callable[[dict], list[dict]] | None = None
    desired_request_builder: Callable[[dict], list[dict]] | None = None


MARKDOWN_SCENARIOS = (
    MarkdownScenario(
        name="paragraph_to_heading",
        title="Confidence Sprint Fixture Paragraph To Heading",
        description="Promote a paragraph to a heading without changing text.",
        base_md="alpha paragraph\n",
        desired_md="# alpha paragraph\n",
    ),
    MarkdownScenario(
        name="list_append",
        title="Confidence Sprint Fixture List Append",
        description="Append one item to an existing contiguous semantic list.",
        base_md="- one\n- two\n",
        desired_md="- one\n- two\n- three\n",
    ),
    MarkdownScenario(
        name="text_replace",
        title="Confidence Sprint Fixture Text Replace",
        description="Replace plain paragraph text without changing paragraph role.",
        base_md="alpha paragraph\n",
        desired_md="omega paragraph\n",
    ),
    MarkdownScenario(
        name="paragraph_split",
        title="Confidence Sprint Fixture Paragraph Split",
        description="Split one normal paragraph into two normal paragraphs.",
        base_md="alpha beta\n",
        desired_md="alpha\n\nbeta\n",
    ),
    MarkdownScenario(
        name="table_cell_text_replace",
        title="Confidence Sprint Fixture Table Cell Text Replace",
        description="Replace the text inside a simple one-column table cell.",
        base_md="| col |\n| --- |\n| alpha |\n",
        desired_md="| col |\n| --- |\n| omega |\n",
    ),
)

REQUEST_SCENARIOS = (
    RequestScenario(
        name="list_relevel",
        title="Confidence Sprint Fixture List Relevel",
        description="Increase the nesting level of one existing list item without changing list text or kind.",
        base_md="- one\n- two\n",
        desired_requests=(
            {
                "deleteParagraphBullets": {
                    "range": {"startIndex": 1, "endIndex": 9, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 5, "tabId": "t.0"},
                    "text": "\t",
                }
            },
            {
                "createParagraphBullets": {
                    "range": {"startIndex": 1, "endIndex": 10, "tabId": "t.0"},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            },
        ),
        expected_lowered_requests=(
            {
                "deleteParagraphBullets": {
                    "range": {"startIndex": 1, "endIndex": 9, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 5, "tabId": "t.0"},
                    "text": "\t",
                }
            },
            {
                "createParagraphBullets": {
                    "range": {"startIndex": 1, "endIndex": 10, "tabId": "t.0"},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            },
        ),
    ),
    RequestScenario(
        name="multitab_text_replace",
        title="Confidence Sprint Fixture Multi-Tab Text Replace",
        description="Replace text in the second tab while leaving the first tab unchanged.",
        base_md="alpha first tab\n",
        base_setup_procedure=lambda raw_client, document_id, base_raw: _setup_multitab_base_state(
            raw_client,
            document_id,
            base_raw,
        ),
        desired_request_builder=lambda base_raw: _build_multitab_text_replace_requests(
            base_raw,
            tab_id=_find_second_tab_id(base_raw),
            desired_text="omega second tab",
        ),
        expected_lowered_builder=lambda base_raw: _build_multitab_text_replace_requests(
            base_raw,
            tab_id=_find_second_tab_id(base_raw),
            desired_text="omega second tab",
        ),
    ),
)

SECTION_SCENARIO = BatchScenario(
    name="section_split",
    title="Confidence Sprint Fixture Section Split",
    description="Split one body section into two by inserting a section break before the second paragraph.",
    base_md="First paragraph.\n\nSecond paragraph.\n",
)

HEADER_SCENARIO = HeaderScenario(
    name="header_text_replace",
    title="Confidence Sprint Fixture Header Text Replace",
    description="Replace text inside an existing default header story.",
    base_md="Body paragraph.\n",
    base_header_text="Header Alpha",
    desired_header_text="Header Omega",
)

NAMED_RANGE_SCENARIO = NamedRangeScenario(
    name="named_range_add",
    title="Confidence Sprint Fixture Named Range Add",
    description="Add a named range over body text without changing content.",
    base_md="alpha bravo charlie\n",
    range_name="spike:bravo",
    target_text="bravo",
)

TABLE_BASE_MD = "| **col** |  |\n| --- | --- |\n| omega |  |\n"
TABLE_TRAILING_COLUMN_MD = "| **left** | **right** |\n| --- | --- |\n| alpha | bravo |\n"
TABLE_MIDDLE_ROW_MD = (
    "| **left** | **right** |\n"
    "| --- | --- |\n"
    "| alpha | bravo |\n"
    "| charlie | delta |\n"
)
TABLE_MIDDLE_COLUMN_MD = (
    "| **one** | **two** | **three** |\n"
    "| --- | --- | --- |\n"
    "| alpha | bravo | charlie |\n"
)

TABLE_SCENARIOS = (
    TableScenario(
        name="table_pin_header_rows",
        title="Confidence Sprint Fixture Table Pin Header Rows",
        description="Pin one header row on a multi-row table.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_requests=(
            {
                "pinTableHeaderRows": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "pinnedHeaderRowsCount": 1,
                }
            },
        ),
    ),
    TableScenario(
        name="table_row_style_min_height",
        title="Confidence Sprint Fixture Table Row Style Min Height",
        description="Update one table row to have a minimum height.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_requests=(
            {
                "updateTableRowStyle": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "rowIndices": [1],
                    "tableRowStyle": {
                        "minRowHeight": {"magnitude": 30, "unit": "PT"}
                    },
                    "fields": "minRowHeight",
                }
            },
        ),
    ),
    TableScenario(
        name="table_column_properties_width",
        title="Confidence Sprint Fixture Table Column Properties Width",
        description="Update one table column to a fixed width.",
        base_md=TABLE_MIDDLE_COLUMN_MD,
        desired_requests=(
            {
                "updateTableColumnProperties": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "columnIndices": [1],
                    "tableColumnProperties": {
                        "widthType": "FIXED_WIDTH",
                        "width": {"magnitude": 72, "unit": "PT"},
                    },
                    "fields": "widthType,width",
                }
            },
        ),
    ),
    TableScenario(
        name="table_cell_style_background",
        title="Confidence Sprint Fixture Table Cell Style Background",
        description="Update one table cell background color.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_requests=(
            {
                "updateTableCellStyle": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 1,
                            "columnIndex": 1,
                        },
                        "rowSpan": 1,
                        "columnSpan": 1,
                    },
                    "tableCellStyle": {
                        "backgroundColor": {
                            "color": {"rgbColor": {"red": 1.0}}
                        }
                    },
                    "fields": "backgroundColor",
                }
            },
        ),
    ),
    TableScenario(
        name="table_middle_row_insert",
        title="Confidence Sprint Fixture Table Middle Row Insert",
        description="Insert one empty row between two existing data rows in a 3x2 table.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_requests=(
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_row_and_column_insert",
        title="Confidence Sprint Fixture Table Row And Column Insert",
        description="Insert one row and one column in the same table diff.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_requests=(
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_middle_row_delete",
        title="Confidence Sprint Fixture Table Middle Row Delete",
        description="Delete one empty middle row from a 4x2 table.",
        base_md=TABLE_MIDDLE_ROW_MD,
        base_setup_requests=(
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
        ),
        desired_requests=(
            {
                "deleteTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 2,
                        "columnIndex": 0,
                    }
                }
            },
        ),
    ),
    TableScenario(
        name="table_middle_column_insert",
        title="Confidence Sprint Fixture Table Middle Column Insert",
        description="Insert one empty column between existing columns in a 2x3 table.",
        base_md=TABLE_MIDDLE_COLUMN_MD,
        desired_requests=(
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_middle_column_insert_with_inserted_content",
        title="Confidence Sprint Fixture Table Middle Column Insert With Inserted Content",
        description="Insert one middle column and populate a cell in the newly inserted column.",
        base_md=TABLE_MIDDLE_COLUMN_MD,
        desired_request_builder=lambda base_raw: _build_table_middle_column_insert_with_inserted_content_requests(base_raw),
    ),
    TableScenario(
        name="table_middle_column_delete",
        title="Confidence Sprint Fixture Table Middle Column Delete",
        description="Delete one empty middle column from a 2x4 table.",
        base_md=TABLE_MIDDLE_COLUMN_MD,
        base_setup_requests=(
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            },
        ),
        desired_requests=(
            {
                "deleteTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 2,
                    }
                }
            },
        ),
    ),
    TableScenario(
        name="table_middle_row_insert_with_cell_edit",
        title="Confidence Sprint Fixture Table Middle Row Insert With Cell Edit",
        description="Insert one middle row and also edit a later matched cell in the same table.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_request_builder=lambda base_raw: _build_table_middle_row_insert_with_cell_edit_requests(base_raw),
    ),
    TableScenario(
        name="table_middle_row_insert_with_inserted_content",
        title="Confidence Sprint Fixture Table Middle Row Insert With Inserted Content",
        description="Insert one middle row and populate a cell in the newly inserted row.",
        base_md=TABLE_MIDDLE_ROW_MD,
        desired_request_builder=lambda base_raw: _build_table_middle_row_insert_with_inserted_content_requests(base_raw),
    ),
    TableScenario(
        name="table_row_insert_below_merged",
        title="Confidence Sprint Fixture Table Row Insert Below Merged",
        description="Insert one row directly below an existing merged top row.",
        base_md=TABLE_BASE_MD,
        base_setup_requests=(
            {
                "mergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            },
        ),
        desired_requests=(
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_column_insert_through_merged",
        title="Confidence Sprint Fixture Table Column Insert Through Merged",
        description="Insert one column through an existing merged top-row region.",
        base_md=TABLE_BASE_MD,
        base_setup_requests=(
            {
                "mergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            },
        ),
        desired_requests=(
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "insertRight": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_row_insert",
        title="Confidence Sprint Fixture Table Row Insert",
        description="Insert one empty row at the end of a 2x2 table.",
        base_md=TABLE_BASE_MD,
        desired_requests=(
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_row_delete",
        title="Confidence Sprint Fixture Table Row Delete",
        description="Delete the final empty row from a 3x2 table.",
        base_md=TABLE_BASE_MD,
        base_setup_requests=(
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
        ),
        desired_requests=(
            {
                "deleteTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 2,
                        "columnIndex": 0,
                    }
                }
            },
        ),
    ),
    TableScenario(
        name="table_column_insert",
        title="Confidence Sprint Fixture Table Column Insert",
        description="Insert one empty column at the end of a 2x2 table.",
        base_md=TABLE_TRAILING_COLUMN_MD,
        desired_requests=(
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            },
        ),
    ),
    TableScenario(
        name="table_column_delete",
        title="Confidence Sprint Fixture Table Column Delete",
        description="Delete the final empty column from a 2x3 table.",
        base_md=TABLE_TRAILING_COLUMN_MD,
        base_setup_requests=(
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            },
        ),
        desired_requests=(
            {
                "deleteTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 2,
                    }
                }
            },
        ),
    ),
    TableScenario(
        name="table_merge_cells",
        title="Confidence Sprint Fixture Table Merge Cells",
        description="Merge the first-row cells of a 2x2 table into a 1x2 span.",
        base_md=TABLE_BASE_MD,
        desired_requests=(
            {
                "mergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            },
        ),
    ),
    TableScenario(
        name="table_unmerge_cells",
        title="Confidence Sprint Fixture Table Unmerge Cells",
        description="Unmerge the first-row 1x2 span in a 2x2 table.",
        base_md=TABLE_BASE_MD,
        base_setup_requests=(
            {
                "mergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            },
        ),
        desired_requests=(
            {
                "unmergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            },
        ),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=DEFAULT_FIXTURES_ROOT,
        help="Directory where scenario folders should be written.",
    )
    parser.add_argument(
        "--only",
        action="append",
        dest="only",
        help="Capture only a named scenario. Repeat to select multiple.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=2.0,
        help="Pause between scenarios to reduce create-doc rate-limit failures.",
    )
    args = parser.parse_args()

    selected = set(args.only or [])
    args.fixtures_root.mkdir(parents=True, exist_ok=True)

    raw_client = _RawDocsClient()
    try:
        for scenario in MARKDOWN_SCENARIOS:
            if selected and scenario.name not in selected:
                continue
            _capture_markdown_scenario(
                scenario=scenario,
                fixtures_root=args.fixtures_root,
                raw_client=raw_client,
            )
            time.sleep(args.pause_seconds)
        for scenario in REQUEST_SCENARIOS:
            if selected and scenario.name not in selected:
                continue
            _capture_request_scenario(
                scenario=scenario,
                fixtures_root=args.fixtures_root,
                raw_client=raw_client,
            )
            time.sleep(args.pause_seconds)
        if not selected or SECTION_SCENARIO.name in selected:
            _capture_section_scenario(
                scenario=SECTION_SCENARIO,
                fixtures_root=args.fixtures_root,
                raw_client=raw_client,
            )
            time.sleep(args.pause_seconds)
        if not selected or HEADER_SCENARIO.name in selected:
            _capture_header_scenario(
                scenario=HEADER_SCENARIO,
                fixtures_root=args.fixtures_root,
                raw_client=raw_client,
            )
            time.sleep(args.pause_seconds)
        if not selected or NAMED_RANGE_SCENARIO.name in selected:
            _capture_named_range_scenario(
                scenario=NAMED_RANGE_SCENARIO,
                fixtures_root=args.fixtures_root,
                raw_client=raw_client,
            )
            time.sleep(args.pause_seconds)
        for scenario in TABLE_SCENARIOS:
            if selected and scenario.name not in selected:
                continue
            _capture_table_scenario(
                scenario=scenario,
                fixtures_root=args.fixtures_root,
                raw_client=raw_client,
            )
            time.sleep(args.pause_seconds)
    finally:
        raw_client.close()


def _capture_markdown_scenario(
    *,
    scenario: MarkdownScenario,
    fixtures_root: Path,
    raw_client: _RawDocsClient,
) -> None:
    print(f"[capture] {scenario.name}")
    doc_url = _create_empty_doc(scenario.title)
    doc_id = _extract_document_id(doc_url)

    with tempfile.TemporaryDirectory(prefix=f"reconcile-v2-{scenario.name}-") as tmpdir:
        tmp = Path(tmpdir)

        base_folder = tmp / "base"
        _pull_md(doc_url, base_folder)
        _write_markdown_tabs(base_folder, _base_tabs_for_markdown_scenario(scenario))
        _push_md(base_folder)
        base_raw = raw_client.get_document_raw(doc_id)

        desired_folder = tmp / "desired"
        _pull_md(doc_url, desired_folder)
        _write_markdown_tabs(desired_folder, _desired_tabs_for_markdown_scenario(scenario))
        _push_md(desired_folder)
        desired_raw = raw_client.get_document_raw(doc_id)

    extra_files = _markdown_scenario_extra_files(scenario)
    if scenario.expected_lowered_requests:
        extra_files["expected.lowered.json"] = (
            json.dumps(list(scenario.expected_lowered_requests), indent=2) + "\n"
        )

    _write_fixture_pair(
        fixture_dir=fixtures_root / scenario.name,
        description=scenario.description,
        workflow="pull-md/push-md",
        doc_url=doc_url,
        base_raw=base_raw,
        desired_raw=desired_raw,
        extra_files=extra_files,
    )


def _capture_request_scenario(
    *,
    scenario: RequestScenario,
    fixtures_root: Path,
    raw_client: _RawDocsClient,
) -> None:
    print(f"[capture] {scenario.name}")
    doc_url = _create_empty_doc(scenario.title)
    doc_id = _extract_document_id(doc_url)

    with tempfile.TemporaryDirectory(prefix=f"reconcile-v2-{scenario.name}-") as tmpdir:
        tmp = Path(tmpdir)

        base_folder = tmp / "base"
        _pull_md(doc_url, base_folder)
        (base_folder / "Tab_1.md").write_text(scenario.base_md, encoding="utf-8")
        _push_md(base_folder)
        base_raw = raw_client.get_document_raw(doc_id)

        base_setup_requests = list(scenario.base_setup_requests)
        base_setup_batches: list[list[dict]] = []
        if scenario.base_setup_procedure is not None:
            base_setup_batches = scenario.base_setup_procedure(
                raw_client,
                doc_id,
                base_raw,
            )
            base_raw = raw_client.get_document_raw(doc_id)
        if scenario.base_setup_builder is not None:
            base_setup_requests = scenario.base_setup_builder(base_raw)
        if base_setup_requests:
            raw_client.batch_update(doc_id, base_setup_requests)
            base_raw = raw_client.get_document_raw(doc_id)

        desired_requests = list(scenario.desired_requests)
        if scenario.desired_request_builder is not None:
            desired_requests = scenario.desired_request_builder(base_raw)
        raw_client.batch_update(doc_id, desired_requests)
        desired_raw = raw_client.get_document_raw(doc_id)

    extra_files = {
        "base.md": scenario.base_md,
        "desired.requests.json": json.dumps(desired_requests, indent=2) + "\n",
    }
    if base_setup_batches:
        extra_files["base.setup.batches.json"] = (
            json.dumps(base_setup_batches, indent=2) + "\n"
        )
    if base_setup_requests:
        extra_files["base.setup.requests.json"] = (
            json.dumps(base_setup_requests, indent=2) + "\n"
        )
    expected_lowered = list(scenario.expected_lowered_requests)
    if scenario.expected_lowered_builder is not None:
        expected_lowered = scenario.expected_lowered_builder(base_raw)
    if expected_lowered:
        extra_files["expected.lowered.json"] = (
            json.dumps(expected_lowered, indent=2) + "\n"
        )

    _write_fixture_pair(
        fixture_dir=fixtures_root / scenario.name,
        description=scenario.description,
        workflow="pull-md/push-md + direct batchUpdate",
        doc_url=doc_url,
        base_raw=base_raw,
        desired_raw=desired_raw,
        extra_files=extra_files,
    )


def _base_tabs_for_markdown_scenario(scenario: MarkdownScenario) -> dict[str, str]:
    if scenario.base_tabs is not None:
        return scenario.base_tabs
    if scenario.base_md is None:
        raise ValueError(f"Markdown scenario {scenario.name} is missing base content")
    return {"Tab_1.md": scenario.base_md}


def _desired_tabs_for_markdown_scenario(scenario: MarkdownScenario) -> dict[str, str]:
    if scenario.desired_tabs is not None:
        return scenario.desired_tabs
    if scenario.desired_md is None:
        raise ValueError(f"Markdown scenario {scenario.name} is missing desired content")
    return {"Tab_1.md": scenario.desired_md}


def _markdown_scenario_extra_files(scenario: MarkdownScenario) -> dict[str, str]:
    extra_files: dict[str, str] = {}
    if scenario.base_tabs is None and scenario.base_md is not None:
        extra_files["base.md"] = scenario.base_md
    else:
        extra_files["base.tabs.json"] = (
            json.dumps(_base_tabs_for_markdown_scenario(scenario), indent=2) + "\n"
        )
    if scenario.desired_tabs is None and scenario.desired_md is not None:
        extra_files["desired.md"] = scenario.desired_md
    else:
        extra_files["desired.tabs.json"] = (
            json.dumps(_desired_tabs_for_markdown_scenario(scenario), indent=2) + "\n"
        )
    return extra_files


def _write_markdown_tabs(folder: Path, tabs: dict[str, str]) -> None:
    for filename, content in tabs.items():
        (folder / filename).write_text(content, encoding="utf-8")


def _capture_section_scenario(
    *,
    scenario: BatchScenario,
    fixtures_root: Path,
    raw_client: _RawDocsClient,
) -> None:
    print(f"[capture] {scenario.name}")
    doc_url = _create_empty_doc(scenario.title)
    doc_id = _extract_document_id(doc_url)

    with tempfile.TemporaryDirectory(prefix=f"reconcile-v2-{scenario.name}-") as tmpdir:
        tmp = Path(tmpdir)

        base_folder = tmp / "base"
        _pull_md(doc_url, base_folder)
        (base_folder / "Tab_1.md").write_text(scenario.base_md, encoding="utf-8")
        _push_md(base_folder)
        base_raw = raw_client.get_document_raw(doc_id)

        requests = _build_section_split_requests(base_raw)
        raw_client.batch_update(doc_id, requests)
        desired_raw = raw_client.get_document_raw(doc_id)

    _write_fixture_pair(
        fixture_dir=fixtures_root / scenario.name,
        description=scenario.description,
        workflow="pull-md/push-md + direct batchUpdate",
        doc_url=doc_url,
        base_raw=base_raw,
        desired_raw=desired_raw,
        extra_files={
            "base.md": scenario.base_md,
            "desired.requests.json": json.dumps(requests, indent=2) + "\n",
        },
    )


def _capture_header_scenario(
    *,
    scenario: HeaderScenario,
    fixtures_root: Path,
    raw_client: _RawDocsClient,
) -> None:
    print(f"[capture] {scenario.name}")
    doc_url = _create_empty_doc(scenario.title)
    doc_id = _extract_document_id(doc_url)

    with tempfile.TemporaryDirectory(prefix=f"reconcile-v2-{scenario.name}-") as tmpdir:
        tmp = Path(tmpdir)
        base_folder = tmp / "base"
        _pull_md(doc_url, base_folder)
        (base_folder / "Tab_1.md").write_text(scenario.base_md, encoding="utf-8")
        _push_md(base_folder)

        create_header_response = raw_client.batch_update(
            doc_id,
            [{"createHeader": {"type": "DEFAULT"}}],
        )
        header_id = create_header_response["replies"][0]["createHeader"]["headerId"]
        raw_client.batch_update(
            doc_id,
            [
                {
                    "insertText": {
                        "endOfSegmentLocation": {"segmentId": header_id},
                        "text": scenario.base_header_text,
                    }
                }
            ],
        )
        base_raw = raw_client.get_document_raw(doc_id)

        requests = _build_header_text_replace_requests(
            base_raw=base_raw,
            desired_text=scenario.desired_header_text,
        )
        raw_client.batch_update(doc_id, requests)
        desired_raw = raw_client.get_document_raw(doc_id)

    _write_fixture_pair(
        fixture_dir=fixtures_root / scenario.name,
        description=scenario.description,
        workflow="pull-md/push-md + direct batchUpdate header edits",
        doc_url=doc_url,
        base_raw=base_raw,
        desired_raw=desired_raw,
        extra_files={
            "base.md": scenario.base_md,
            "base.header.txt": scenario.base_header_text + "\n",
            "desired.header.txt": scenario.desired_header_text + "\n",
            "desired.requests.json": json.dumps(requests, indent=2) + "\n",
        },
    )


def _capture_named_range_scenario(
    *,
    scenario: NamedRangeScenario,
    fixtures_root: Path,
    raw_client: _RawDocsClient,
) -> None:
    print(f"[capture] {scenario.name}")
    doc_url = _create_empty_doc(scenario.title)
    doc_id = _extract_document_id(doc_url)

    with tempfile.TemporaryDirectory(prefix=f"reconcile-v2-{scenario.name}-") as tmpdir:
        tmp = Path(tmpdir)
        base_folder = tmp / "base"
        _pull_md(doc_url, base_folder)
        (base_folder / "Tab_1.md").write_text(scenario.base_md, encoding="utf-8")
        _push_md(base_folder)
        base_raw = raw_client.get_document_raw(doc_id)

        requests = _build_named_range_add_requests(
            base_raw=base_raw,
            name=scenario.range_name,
            target_text=scenario.target_text,
        )
        raw_client.batch_update(doc_id, requests)
        desired_raw = raw_client.get_document_raw(doc_id)

    _write_fixture_pair(
        fixture_dir=fixtures_root / scenario.name,
        description=scenario.description,
        workflow="pull-md/push-md + direct batchUpdate named range",
        doc_url=doc_url,
        base_raw=base_raw,
        desired_raw=desired_raw,
        extra_files={
            "base.md": scenario.base_md,
            "desired.requests.json": json.dumps(requests, indent=2) + "\n",
        },
    )


def _capture_table_scenario(
    *,
    scenario: TableScenario,
    fixtures_root: Path,
    raw_client: _RawDocsClient,
) -> None:
    print(f"[capture] {scenario.name}")
    doc_url = _create_empty_doc(scenario.title)
    doc_id = _extract_document_id(doc_url)

    with tempfile.TemporaryDirectory(prefix=f"reconcile-v2-{scenario.name}-") as tmpdir:
        tmp = Path(tmpdir)
        base_folder = tmp / "base"
        _pull_md(doc_url, base_folder)
        (base_folder / "Tab_1.md").write_text(scenario.base_md, encoding="utf-8")
        _push_md(base_folder)

        base_setup_requests = list(scenario.base_setup_requests)
        if scenario.base_setup_builder is not None:
            base_setup_requests = scenario.base_setup_builder(raw_client.get_document_raw(doc_id))
        if base_setup_requests:
            raw_client.batch_update(doc_id, base_setup_requests)
        base_raw = raw_client.get_document_raw(doc_id)

        desired_requests = list(scenario.desired_requests)
        if scenario.desired_request_builder is not None:
            desired_requests = scenario.desired_request_builder(base_raw)
        raw_client.batch_update(doc_id, desired_requests)
        desired_raw = raw_client.get_document_raw(doc_id)

    extra_files = {
        "base.md": scenario.base_md,
        "desired.requests.json": json.dumps(desired_requests, indent=2) + "\n",
    }
    if base_setup_requests:
        extra_files["base.setup.requests.json"] = (
            json.dumps(base_setup_requests, indent=2) + "\n"
        )

    _write_fixture_pair(
        fixture_dir=fixtures_root / scenario.name,
        description=scenario.description,
        workflow="pull-md/push-md + direct batchUpdate table edits",
        doc_url=doc_url,
        base_raw=base_raw,
        desired_raw=desired_raw,
        extra_files=extra_files,
    )


def _write_fixture_pair(
    *,
    fixture_dir: Path,
    description: str,
    workflow: str,
    doc_url: str,
    base_raw: dict,
    desired_raw: dict,
    extra_files: dict[str, str],
) -> None:
    if fixture_dir.exists():
        shutil.rmtree(fixture_dir)
    fixture_dir.mkdir(parents=True, exist_ok=True)

    (fixture_dir / "base.json").write_text(
        json.dumps(base_raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (fixture_dir / "desired.json").write_text(
        json.dumps(desired_raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for name, content in extra_files.items():
        (fixture_dir / name).write_text(content, encoding="utf-8")

    base_doc = Document.model_validate(base_raw)
    desired_doc = Document.model_validate(desired_raw)
    (fixture_dir / "base.summary.txt").write_text(
        summarize_document(base_doc) + "\n",
        encoding="utf-8",
    )
    (fixture_dir / "desired.summary.txt").write_text(
        summarize_document(desired_doc) + "\n",
        encoding="utf-8",
    )
    (fixture_dir / "metadata.json").write_text(
        json.dumps(
            {
                "description": description,
                "workflow": workflow,
                "doc_url": doc_url,
                "document_id": base_raw.get("documentId"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _build_section_split_requests(base_raw: dict) -> list[dict]:
    content = base_raw["tabs"][0]["documentTab"]["body"]["content"]
    paragraph_starts = [
        elem["startIndex"]
        for elem in content
        if "paragraph" in elem and _visible_paragraph_text(elem["paragraph"])
    ]
    if len(paragraph_starts) < 2:
        raise RuntimeError("Section split scenario requires at least two paragraphs")
    return [
        {
            "insertSectionBreak": {
                "location": {"index": paragraph_starts[1]},
                "sectionType": "NEXT_PAGE",
            }
        }
    ]


def _build_header_text_replace_requests(
    *,
    base_raw: dict,
    desired_text: str,
) -> list[dict]:
    headers = base_raw["tabs"][0]["documentTab"].get("headers", {})
    if len(headers) != 1:
        raise RuntimeError("Header text scenario expects exactly one header")
    header_id, header = next(iter(headers.items()))
    end_index = header["content"][0]["endIndex"]
    text_end = end_index - 1
    requests: list[dict] = []
    if text_end > 0:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "segmentId": header_id,
                        "startIndex": 0,
                        "endIndex": text_end,
                    }
                }
            }
        )
    requests.append(
        {
            "insertText": {
                "location": {"segmentId": header_id, "index": 0},
                "text": desired_text,
            }
        }
    )
    return requests


def _build_named_range_add_requests(
    *,
    base_raw: dict,
    name: str,
    target_text: str,
) -> list[dict]:
    for element in base_raw["tabs"][0]["documentTab"]["body"]["content"]:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        visible_text = _visible_paragraph_text(paragraph)
        offset = visible_text.find(target_text)
        if offset < 0:
            continue
        start_index = element["startIndex"] + offset
        end_index = start_index + len(target_text)
        return [
            {
                "createNamedRange": {
                    "name": name,
                    "range": {
                        "startIndex": start_index,
                        "endIndex": end_index,
                    },
                }
            }
        ]
    raise RuntimeError(f"Could not locate target text {target_text!r} for named range")


def _setup_multitab_base_state(
    raw_client: _RawDocsClient,
    document_id: str,
    base_raw: dict,  # noqa: ARG001
) -> list[list[dict]]:
    batch_0 = [
        {
            "addDocumentTab": {
                "tabProperties": {
                    "title": "Second Tab",
                    "index": 1,
                }
            }
        }
    ]
    response = raw_client.batch_update(document_id, batch_0)
    tab_properties = response["replies"][0]["addDocumentTab"]["tabProperties"]
    tab_id = tab_properties["tabId"]
    batch_2_actual = [
        {
            "insertText": {
                "location": {"index": 1, "tabId": tab_id},
                "text": "bravo second tab",
            }
        }
    ]
    raw_client.batch_update(document_id, batch_2_actual)
    batch_2_template = [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "__LAST_ADDED_TAB_ID__"},
                "text": "bravo second tab",
            }
        }
    ]
    return [batch_0, batch_2_template]


def _build_multitab_text_replace_requests(
    base_raw: dict,
    *,
    tab_id: str,
    desired_text: str,
) -> list[dict]:
    content = _tab_body_content(base_raw, tab_id)
    paragraphs = [
        element
        for element in content
        if "paragraph" in element and _visible_paragraph_text(element["paragraph"])
    ]
    if len(paragraphs) != 1:
        raise RuntimeError("Multi-tab text scenario expects one visible paragraph in the target tab")
    paragraph = paragraphs[0]
    start_index = paragraph["startIndex"]
    end_index = paragraph["endIndex"] - 1
    requests: list[dict] = []
    if end_index > start_index:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": end_index,
                        "tabId": tab_id,
                    }
                }
            }
        )
    requests.append(
        {
            "insertText": {
                "location": {"index": start_index, "tabId": tab_id},
                "text": desired_text,
            }
        }
    )
    return requests


def _find_second_tab_id(base_raw: dict) -> str:
    tabs = base_raw.get("tabs", [])
    if len(tabs) < 2:
        raise RuntimeError("Expected captured base fixture to contain at least two tabs")
    return tabs[1]["tabProperties"]["tabId"]


def _build_table_middle_row_insert_with_cell_edit_requests(base_raw: dict) -> list[dict]:
    start_index, end_index = _table_cell_text_range(base_raw, row_index=2, column_index=0)
    return [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": start_index,
                    "endIndex": end_index,
                    "tabId": "t.0",
                }
            }
        },
        {
            "insertText": {
                "location": {
                    "index": start_index,
                    "tabId": "t.0",
                },
                "text": "omega",
            }
        },
        {
            "insertTableRow": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "rowIndex": 1,
                    "columnIndex": 0,
                },
                "insertBelow": True,
            }
        },
    ]


def _build_table_middle_row_insert_with_inserted_content_requests(base_raw: dict) -> list[dict]:
    start_index, _ = _table_cell_text_range(base_raw, row_index=2, column_index=0)
    return [
        {
            "insertTableRow": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "rowIndex": 1,
                    "columnIndex": 0,
                },
                "insertBelow": True,
            }
        },
        {
            "insertText": {
                "location": {
                    "index": start_index,
                    "tabId": "t.0",
                },
                "text": "NEW",
            }
        },
    ]


def _build_table_middle_column_insert_with_inserted_content_requests(base_raw: dict) -> list[dict]:
    start_index, _ = _table_cell_text_range(base_raw, row_index=1, column_index=2)
    return [
        {
            "insertTableColumn": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "rowIndex": 0,
                    "columnIndex": 1,
                },
                "insertRight": True,
            }
        },
        {
            "insertText": {
                "location": {
                    "index": start_index + 2,
                    "tabId": "t.0",
                },
                "text": "NEW",
            }
        },
    ]


def _table_cell_text_range(base_raw: dict, *, row_index: int, column_index: int) -> tuple[int, int]:
    table = next(
        element["table"]
        for element in base_raw["tabs"][0]["documentTab"]["body"]["content"]
        if "table" in element
    )
    cell = table["tableRows"][row_index]["tableCells"][column_index]
    paragraphs = [element["paragraph"] for element in cell["content"] if "paragraph" in element]
    if len(paragraphs) != 1:
        raise RuntimeError("Expected one paragraph in target table cell")
    paragraph = paragraphs[0]
    start_index = paragraph["elements"][0]["startIndex"]
    end_index = paragraph["elements"][-1]["endIndex"] - 1
    return start_index, end_index


def _tab_body_content(base_raw: dict, tab_id: str) -> list[dict]:
    for tab in base_raw.get("tabs", []):
        if tab.get("tabProperties", {}).get("tabId") == tab_id:
            return tab.get("documentTab", {}).get("body", {}).get("content", [])
    raise RuntimeError(f"Could not find tab {tab_id!r} in captured fixture")


def _visible_paragraph_text(paragraph: dict) -> str:
    text = "".join(
        element.get("textRun", {}).get("content", "")
        for element in paragraph.get("elements", [])
    )
    return text.strip()


class _RawDocsClient:
    def __init__(self) -> None:
        manager = CredentialsManager()
        self._cred = manager.get_credential(
            command={"type": "doc.push", "file_url": "", "file_name": ""},
            reason="Capturing reconcile_v2 confidence-sprint fixtures",
        )

    def get_document_raw(self, document_id: str) -> dict:
        return asyncio.run(self._get_document_raw(document_id))

    async def _get_document_raw(self, document_id: str) -> dict:
        transport = GoogleDocsTransport(self._cred.token)
        try:
            return (await transport.get_document(document_id)).raw
        finally:
            await transport.close()

    def batch_update(self, document_id: str, requests: list[dict]) -> dict:
        return asyncio.run(self._batch_update(document_id, requests))

    async def _batch_update(self, document_id: str, requests: list[dict]) -> dict:
        transport = GoogleDocsTransport(self._cred.token)
        try:
            return await transport.batch_update(document_id, requests)
        finally:
            await transport.close()

    def close(self) -> None:
        return None


def _create_empty_doc(title: str) -> str:
    result = _run([str(EXTRASUITE), "doc", "create-empty", title])
    match = re.search(r"^URL:\s*(https://docs.google.com/document/d/[^\s]+)$", result.stdout, re.M)
    if match is None:
        raise RuntimeError(f"Could not parse doc URL from output:\n{result.stdout}")
    return match.group(1)


def _pull_md(doc_url: str, output_dir: Path) -> None:
    _run([str(EXTRASUITE), "doc", "pull-md", doc_url, str(output_dir)])


def _push_md(folder: Path) -> None:
    _run([str(EXTRASUITE), "doc", "push-md", str(folder), "--verify"])


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


if __name__ == "__main__":
    main()
