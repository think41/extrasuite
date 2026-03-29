"""Tests for CLI help topic resolution."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from extrasuite.client.cli import build_parser
from extrasuite.client.cli._common import cmd_module_help

if TYPE_CHECKING:
    import pytest


def test_sheet_help_lists_formulas_topic(capsys: pytest.CaptureFixture[str]) -> None:
    args = Namespace(command="sheet", topic_parts=[])

    cmd_module_help(args)

    out = capsys.readouterr().out
    assert "extrasuite sheet help formulas" in out


def test_sheet_formula_help_supports_nested_case_insensitive_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    args = parser.parse_args(["sheets", "help", "FORMULAS", "dcount"])

    cmd_module_help(args)

    out = capsys.readouterr().out
    assert "# DCOUNT" in out
    assert "DCOUNT(database, field, criteria)" in out
    assert "https://support.google.com/docs/answer/3094222" in out


def test_docs_parser_supports_confidence_sprint_raw_commands() -> None:
    parser = build_parser()

    create_args = parser.parse_args(["docs", "create-empty", "Spike Doc"])
    assert create_args.command == "docs"
    assert create_args.subcommand == "create-empty"
    assert create_args.title == "Spike Doc"

    download_args = parser.parse_args(
        ["docs", "download-raw", "https://docs.google.com/document/d/abc123", "out"]
    )
    assert download_args.command == "docs"
    assert download_args.subcommand == "download-raw"
    assert download_args.url.endswith("/abc123")
    assert download_args.output == "out"


def test_docs_help_hides_internal_reconciler_flag() -> None:
    help_dir = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "extrasuite"
        / "client"
        / "help"
        / "doc"
    )
    for name in ("push.md", "push-md.md", "diff.md"):
        text = (help_dir / name).read_text(encoding="utf-8")
        assert "EXTRADOC_RECONCILER" not in text


def test_docs_help_reflects_current_release_contract() -> None:
    help_dir = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "extrasuite"
        / "client"
        / "help"
        / "doc"
    )
    readme = (help_dir / "README.md").read_text(encoding="utf-8")
    pull_md = (help_dir / "pull-md.md").read_text(encoding="utf-8")

    assert "Footnote creation/editing in body content is supported" in readme
    assert "New-tab header/footer creation in an existing multi-tab doc is not supported" in readme
    assert "Footnotes:" in pull_md
    assert "Horizontal rules pulled from Docs are read-only" in pull_md
