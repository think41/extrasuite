"""Tests for mandatory --reason on credentialed CLI commands (issue #32).

Covers:
- _get_reason() exits with code 1 and a clear stderr message when reason is absent
- _get_reason() returns the reason string when present
- EXTRASUITE_REASON env var is no longer accepted as a fallback
- --reason / -r / -m all set args.reason
- Every credentialed command exits early (before credential fetch) when --reason is absent
- Offline commands (diff, lint) do NOT require --reason
"""

from __future__ import annotations

import contextlib
from argparse import Namespace
from typing import Any
from unittest.mock import patch

import pytest

from extrasuite.client.cli import build_parser
from extrasuite.client.cli._common import _get_reason
from extrasuite.client.cli.calendar import (
    cmd_calendar_create,
    cmd_calendar_delete,
    cmd_calendar_freebusy,
    cmd_calendar_list,
    cmd_calendar_rsvp,
    cmd_calendar_search,
    cmd_calendar_update,
    cmd_calendar_view,
)
from extrasuite.client.cli.contacts import cmd_contacts_search, cmd_contacts_sync
from extrasuite.client.cli.doc import (
    cmd_doc_create,
    cmd_doc_diff,
    cmd_doc_pull,
    cmd_doc_push,
    cmd_doc_share,
)
from extrasuite.client.cli.drive import cmd_drive_ls, cmd_drive_search
from extrasuite.client.cli.form import (
    cmd_form_create,
    cmd_form_diff,
    cmd_form_pull,
    cmd_form_push,
    cmd_form_share,
)
from extrasuite.client.cli.gmail import (
    cmd_gmail_compose,
    cmd_gmail_edit_draft,
    cmd_gmail_list,
    cmd_gmail_read,
    cmd_gmail_reply,
)
from extrasuite.client.cli.script import (
    cmd_script_create,
    cmd_script_diff,
    cmd_script_lint,
    cmd_script_pull,
    cmd_script_push,
    cmd_script_share,
)
from extrasuite.client.cli.sheet import (
    cmd_sheet_batchupdate,
    cmd_sheet_create,
    cmd_sheet_diff,
    cmd_sheet_pull,
    cmd_sheet_push,
    cmd_sheet_share,
)
from extrasuite.client.cli.slide import (
    cmd_slide_create,
    cmd_slide_diff,
    cmd_slide_pull,
    cmd_slide_push,
    cmd_slide_share,
)

# ---------------------------------------------------------------------------
# _get_reason() unit tests
# ---------------------------------------------------------------------------


def test_get_reason_returns_reason_when_provided() -> None:
    args = Namespace(reason="user wants the Q4 budget sheet")
    assert _get_reason(args) == "user wants the Q4 budget sheet"


def test_get_reason_exits_when_reason_is_none(capsys: pytest.CaptureFixture[str]) -> None:
    args = Namespace(reason=None)
    with pytest.raises(SystemExit) as exc_info:
        _get_reason(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "--reason" in err
    assert "audit log" in err


def test_get_reason_exits_when_reason_is_empty_string() -> None:
    args = Namespace(reason="")
    with pytest.raises(SystemExit) as exc_info:
        _get_reason(args)
    assert exc_info.value.code == 1


def test_get_reason_exits_when_reason_attribute_missing() -> None:
    """Args object with no 'reason' attribute at all should also fail."""
    args = Namespace()  # no reason attribute
    with pytest.raises(SystemExit) as exc_info:
        _get_reason(args)
    assert exc_info.value.code == 1


def test_get_reason_error_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    args = Namespace(reason=None)
    with pytest.raises(SystemExit):
        _get_reason(args)
    out, err = capsys.readouterr()
    assert out == ""  # nothing on stdout
    assert "This command requires --reason" in err


def test_extrasuite_reason_env_var_is_not_a_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting EXTRASUITE_REASON must NOT bypass the --reason requirement."""
    monkeypatch.setenv("EXTRASUITE_REASON", "some env reason")
    args = Namespace(reason=None)
    with pytest.raises(SystemExit) as exc_info:
        _get_reason(args)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Parser alias tests
# ---------------------------------------------------------------------------


def test_reason_long_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["sheet", "pull", "https://docs.google.com/spreadsheets/d/abc", "--reason", "user wants data"])
    assert args.reason == "user wants data"


def test_reason_short_flag_r() -> None:
    parser = build_parser()
    args = parser.parse_args(["sheet", "pull", "https://docs.google.com/spreadsheets/d/abc", "-r", "user wants data"])
    assert args.reason == "user wants data"


def test_reason_short_flag_m() -> None:
    parser = build_parser()
    args = parser.parse_args(["sheet", "pull", "https://docs.google.com/spreadsheets/d/abc", "-m", "user wants data"])
    assert args.reason == "user wants data"


def test_reason_default_is_none() -> None:
    """Without any flag, reason should be None (so _get_reason fails fast)."""
    parser = build_parser()
    args = parser.parse_args(["sheet", "pull", "https://docs.google.com/spreadsheets/d/abc"])
    assert args.reason is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SA_PATH = "/tmp/fake-sa.json"

_SHEET_URL = "https://docs.google.com/spreadsheets/d/abc"
_SLIDE_URL = "https://docs.google.com/presentation/d/abc"
_FORM_URL  = "https://docs.google.com/forms/d/abc"
_DOC_URL   = "https://docs.google.com/document/d/abc"
_SCRIPT_URL = "https://script.google.com/d/abc"


def _parse(*argv: str) -> Any:
    return build_parser().parse_args(list(argv))


def _assert_exits_without_reason(
    handler: Any, args: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Assert that a command handler exits with code 1 and the --reason message."""
    with pytest.raises(SystemExit) as exc_info:
        handler(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "--reason" in err


def _assert_no_reason_error(
    handler: Any, args: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run handler and confirm it did NOT fail with the --reason message."""
    with contextlib.suppress(SystemExit, Exception):
        handler(args)
    err = capsys.readouterr().err
    assert "This command requires --reason" not in err


# ---------------------------------------------------------------------------
# Credentialed commands: all must fail without --reason
# ---------------------------------------------------------------------------
# We pass --service-account to bypass any browser/keyring flow — the command
# should still die at _get_reason() before reaching any credential logic.


class TestCredentialedCommandsRequireReason:
    """Each credentialed command must exit 1 with a clear message when --reason is absent."""

    def test_sheet_pull(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_sheet_pull,
            _parse("sheet", "pull", _SHEET_URL, "--service-account", _SA_PATH),
            capsys,
        )

    def test_sheet_push(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_sheet_push,
            _parse("sheet", "push", "/tmp/folder", "--service-account", _SA_PATH),
            capsys,
        )

    def test_sheet_batchupdate(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_sheet_batchupdate,
            _parse("sheet", "batchUpdate", _SHEET_URL, "/tmp/requests.json", "--service-account", _SA_PATH),
            capsys,
        )

    def test_sheet_create(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_sheet_create,
            _parse("sheet", "create", "My Sheet", "--service-account", _SA_PATH),
            capsys,
        )

    def test_sheet_share(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_sheet_share,
            _parse("sheet", "share", _SHEET_URL, "bob@example.com", "--service-account", _SA_PATH),
            capsys,
        )

    def test_slide_pull(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_slide_pull,
            _parse("slide", "pull", _SLIDE_URL, "--service-account", _SA_PATH),
            capsys,
        )

    def test_slide_push(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_slide_push,
            _parse("slide", "push", "/tmp/folder", "--service-account", _SA_PATH),
            capsys,
        )

    def test_slide_create(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_slide_create,
            _parse("slide", "create", "My Deck", "--service-account", _SA_PATH),
            capsys,
        )

    def test_slide_share(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_slide_share,
            _parse("slide", "share", _SLIDE_URL, "bob@example.com", "--service-account", _SA_PATH),
            capsys,
        )

    def test_form_pull(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_form_pull,
            _parse("form", "pull", _FORM_URL, "--service-account", _SA_PATH),
            capsys,
        )

    def test_form_push(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_form_push,
            _parse("form", "push", "/tmp/folder", "--service-account", _SA_PATH),
            capsys,
        )

    def test_form_create(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_form_create,
            _parse("form", "create", "My Form", "--service-account", _SA_PATH),
            capsys,
        )

    def test_form_share(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_form_share,
            _parse("form", "share", _FORM_URL, "bob@example.com", "--service-account", _SA_PATH),
            capsys,
        )

    def test_doc_pull(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_doc_pull,
            _parse("doc", "pull", _DOC_URL, "--service-account", _SA_PATH),
            capsys,
        )

    def test_doc_push(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_doc_push,
            _parse("doc", "push", "/tmp/folder", "--service-account", _SA_PATH),
            capsys,
        )

    def test_doc_create(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_doc_create,
            _parse("doc", "create", "My Doc", "--service-account", _SA_PATH),
            capsys,
        )

    def test_doc_share(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_doc_share,
            _parse("doc", "share", _DOC_URL, "bob@example.com", "--service-account", _SA_PATH),
            capsys,
        )

    def test_script_pull(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_script_pull,
            _parse("script", "pull", _SCRIPT_URL, "--service-account", _SA_PATH),
            capsys,
        )

    def test_script_push(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_script_push,
            _parse("script", "push", "/tmp/folder", "--service-account", _SA_PATH),
            capsys,
        )

    def test_script_create(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_script_create,
            _parse("script", "create", "My Script", "--service-account", _SA_PATH),
            capsys,
        )

    def test_script_share(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_script_share,
            _parse("script", "share", _SCRIPT_URL, "bob@example.com", "--service-account", _SA_PATH),
            capsys,
        )

    def test_gmail_compose(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_gmail_compose,
            _parse("gmail", "compose", "/tmp/email.md", "--service-account", _SA_PATH),
            capsys,
        )

    def test_gmail_edit_draft(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_gmail_edit_draft,
            _parse("gmail", "edit-draft", "draft123", "/tmp/email.md", "--service-account", _SA_PATH),
            capsys,
        )

    def test_gmail_reply(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_gmail_reply,
            _parse("gmail", "reply", "thread123", "/tmp/reply.md", "--service-account", _SA_PATH),
            capsys,
        )

    def test_gmail_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_gmail_list,
            _parse("gmail", "list", "--service-account", _SA_PATH),
            capsys,
        )

    def test_gmail_read(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_gmail_read,
            _parse("gmail", "read", "thread123", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_view(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_view,
            _parse("calendar", "view", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_list,
            _parse("calendar", "list", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_search(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_search,
            _parse("calendar", "search", "--query", "standup", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_freebusy(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_freebusy,
            _parse("calendar", "freebusy", "--attendees", "alice@example.com", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_create(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_create,
            _parse("calendar", "create", "--json", "/tmp/event.json", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_update(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_update,
            _parse("calendar", "update", "evt123", "--json", "/tmp/patch.json", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_delete(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_delete,
            _parse("calendar", "delete", "evt123", "--service-account", _SA_PATH),
            capsys,
        )

    def test_calendar_rsvp(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_calendar_rsvp,
            _parse("calendar", "rsvp", "evt123", "--response", "accept", "--service-account", _SA_PATH),
            capsys,
        )

    def test_contacts_sync(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_contacts_sync,
            _parse("contacts", "sync", "--service-account", _SA_PATH),
            capsys,
        )

    def test_contacts_search(self, capsys: pytest.CaptureFixture[str]) -> None:
        # contacts search only hits _get_reason when a sync is needed;
        # force the sync path by pretending the DB doesn't exist.
        # _DB_PATH is imported locally inside cmd_contacts_search, so patch at source.
        with patch("extrasuite.client.contacts._DB_PATH") as mock_db_path:
            mock_db_path.exists.return_value = False
            _assert_exits_without_reason(
                cmd_contacts_search,
                _parse("contacts", "search", "alice", "--service-account", _SA_PATH),
                capsys,
            )

    def test_drive_ls(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_drive_ls,
            _parse("drive", "ls", "--service-account", _SA_PATH),
            capsys,
        )

    def test_drive_search(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_exits_without_reason(
            cmd_drive_search,
            _parse("drive", "search", "budget", "--service-account", _SA_PATH),
            capsys,
        )


# ---------------------------------------------------------------------------
# Offline commands must NOT require --reason
# ---------------------------------------------------------------------------
# These commands do no credential fetching; they should not exit due to a
# missing --reason.  They may fail for other reasons (bad folder path, etc.)
# but NOT with the "This command requires --reason" message.


class TestOfflineCommandsDoNotRequireReason:
    def test_sheet_diff(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_no_reason_error(
            cmd_sheet_diff,
            _parse("sheet", "diff", "/tmp/nonexistent"),
            capsys,
        )

    def test_slide_diff(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_no_reason_error(
            cmd_slide_diff,
            _parse("slide", "diff", "/tmp/nonexistent"),
            capsys,
        )

    def test_form_diff(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_no_reason_error(
            cmd_form_diff,
            _parse("form", "diff", "/tmp/nonexistent"),
            capsys,
        )

    def test_doc_diff(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_no_reason_error(
            cmd_doc_diff,
            _parse("doc", "diff", "/tmp/nonexistent"),
            capsys,
        )

    def test_script_diff(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_no_reason_error(
            cmd_script_diff,
            _parse("script", "diff", "/tmp/nonexistent"),
            capsys,
        )

    def test_script_lint(self, capsys: pytest.CaptureFixture[str]) -> None:
        _assert_no_reason_error(
            cmd_script_lint,
            _parse("script", "lint", "/tmp/nonexistent"),
            capsys,
        )
