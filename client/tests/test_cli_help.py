"""Tests for CLI help topic resolution."""

from __future__ import annotations

from argparse import Namespace

import pytest

from extrasuite.client.cli import build_parser
from extrasuite.client.cli._common import cmd_module_help


def test_sheet_help_lists_formulas_topic(capsys: pytest.CaptureFixture[str]) -> None:
    args = Namespace(command="sheet", topic_parts=[])

    cmd_module_help(args)

    out = capsys.readouterr().out
    assert "extrasuite sheet help formulas" in out


def test_sheet_formula_help_supports_nested_case_insensitive_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    args = parser.parse_args(["sheet", "help", "FORMULAS", "dcount"])

    cmd_module_help(args)

    out = capsys.readouterr().out
    assert "# DCOUNT" in out
    assert "DCOUNT(database, field, criteria)" in out
    assert "https://support.google.com/docs/answer/3094222" in out
