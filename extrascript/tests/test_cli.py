"""Tests for the CLI argument parsing and URL parsing."""

from __future__ import annotations

from extrascript.client import parse_file_id, parse_script_id


def test_parse_script_id_from_url() -> None:
    """Should extract script ID from Apps Script editor URL."""
    url = "https://script.google.com/d/1abc_xyz/edit"
    assert parse_script_id(url) == "1abc_xyz"


def test_parse_script_id_from_projects_url() -> None:
    """Should extract script ID from projects URL."""
    url = "https://script.google.com/home/projects/1abc_xyz/edit"
    assert parse_script_id(url) == "1abc_xyz"


def test_parse_script_id_from_macros_url() -> None:
    """Should extract script ID from macros URL."""
    url = "https://script.google.com/macros/d/1abc_xyz/edit"
    assert parse_script_id(url) == "1abc_xyz"


def test_parse_script_id_plain() -> None:
    """Should return plain script IDs unchanged."""
    assert parse_script_id("1abc_xyz") == "1abc_xyz"


def test_parse_file_id_sheets() -> None:
    """Should extract file ID from a Sheets URL."""
    url = "https://docs.google.com/spreadsheets/d/1abc_xyz/edit"
    assert parse_file_id(url) == "1abc_xyz"


def test_parse_file_id_docs() -> None:
    """Should extract file ID from a Docs URL."""
    url = "https://docs.google.com/document/d/1abc_xyz/edit"
    assert parse_file_id(url) == "1abc_xyz"


def test_parse_file_id_slides() -> None:
    """Should extract file ID from a Slides URL."""
    url = "https://docs.google.com/presentation/d/1abc_xyz/edit"
    assert parse_file_id(url) == "1abc_xyz"


def test_parse_file_id_forms() -> None:
    """Should extract file ID from a Forms URL."""
    url = "https://docs.google.com/forms/d/1abc_xyz/edit"
    assert parse_file_id(url) == "1abc_xyz"


def test_parse_file_id_plain() -> None:
    """Should return plain file IDs unchanged."""
    assert parse_file_id("1abc_xyz") == "1abc_xyz"
