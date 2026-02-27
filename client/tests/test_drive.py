"""Tests for Drive API helpers: list_drive_files, copy_drive_file, format_drive_files."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from extrasuite.client.google_api import (
    copy_drive_file,
    format_drive_files,
    list_drive_files,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_response(data: dict[str, Any]) -> MagicMock:
    """Return a mock HTTP response that behaves like urllib.request.urlopen."""
    body = json.dumps(data).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(status: int, message: str) -> urllib.error.HTTPError:
    body = json.dumps({"error": {"message": message}}).encode("utf-8")
    return urllib.error.HTTPError(
        url="https://www.googleapis.com/drive/v3/files",
        code=status,
        msg=message,
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


def _fake_urlopen(response_data: dict[str, Any]) -> Any:
    """Return a fake urlopen function that returns the given response data."""

    def _inner(_req: Any, **_kwargs: Any) -> Any:
        return _make_http_response(response_data)

    return _inner


def _capturing_urlopen(captured: list[Any], response_data: dict[str, Any]) -> Any:
    """Return a fake urlopen that appends requests to captured list."""

    def _inner(req: Any, **_kwargs: Any) -> Any:
        captured.append(req)
        return _make_http_response(response_data)

    return _inner


# ---------------------------------------------------------------------------
# list_drive_files
# ---------------------------------------------------------------------------


class TestListDriveFiles:
    def test_basic_list(self) -> None:
        files = [
            {
                "id": "abc123",
                "name": "Budget Q1",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "modifiedTime": "2025-01-15T10:30:00.000Z",
                "webViewLink": "https://docs.google.com/spreadsheets/d/abc123",
            }
        ]
        response_data = {"files": files}

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen(response_data)):
            result = list_drive_files("fake-token")

        assert result["files"] == files

    def test_query_parameter_included(self) -> None:
        captured: list[Any] = []

        with patch(
            "urllib.request.urlopen",
            side_effect=_capturing_urlopen(captured, {"files": []}),
        ):
            list_drive_files("fake-token", query="name contains 'budget'")

        assert len(captured) == 1
        url = captured[0].full_url
        assert "name" in url and "budget" in url

    def test_page_size_parameter(self) -> None:
        captured: list[Any] = []

        with patch(
            "urllib.request.urlopen",
            side_effect=_capturing_urlopen(captured, {"files": []}),
        ):
            list_drive_files("fake-token", page_size=50)

        assert "pageSize=50" in captured[0].full_url

    def test_page_token_parameter(self) -> None:
        captured: list[Any] = []

        with patch(
            "urllib.request.urlopen",
            side_effect=_capturing_urlopen(captured, {"files": []}),
        ):
            list_drive_files("fake-token", page_token="next-page-xyz")

        assert "pageToken=next-page-xyz" in captured[0].full_url

    def test_next_page_token_returned(self) -> None:
        response_data = {"files": [], "nextPageToken": "abc-token"}

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen(response_data)):
            result = list_drive_files("fake-token")

        assert result.get("nextPageToken") == "abc-token"

    def test_api_error_raises(self) -> None:
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=_make_http_error(403, "Forbidden"),
            ),
            pytest.raises(Exception, match="403"),
        ):
            list_drive_files("bad-token")

    def test_empty_query_not_in_url(self) -> None:
        captured: list[Any] = []

        with patch(
            "urllib.request.urlopen",
            side_effect=_capturing_urlopen(captured, {"files": []}),
        ):
            list_drive_files("fake-token", query="")

        assert "q=" not in captured[0].full_url


# ---------------------------------------------------------------------------
# copy_drive_file
# ---------------------------------------------------------------------------


class TestCopyDriveFile:
    def test_basic_copy(self) -> None:
        new_file = {
            "id": "new-id-xyz",
            "name": "Copy of Budget",
            "webViewLink": "https://docs.google.com/spreadsheets/d/new-id-xyz",
        }

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen(new_file)):
            result = copy_drive_file("fake-token", "source-id", title="Copy of Budget")

        assert result["id"] == "new-id-xyz"
        assert result["name"] == "Copy of Budget"

    def test_copy_sends_post_with_name(self) -> None:
        captured: list[Any] = []

        with patch(
            "urllib.request.urlopen",
            side_effect=_capturing_urlopen(captured, {"id": "new-id"}),
        ):
            copy_drive_file("fake-token", "src-id", title="New Name")

        req = captured[0]
        assert req.method == "POST"
        assert "src-id/copy" in req.full_url
        body = json.loads(req.data.decode("utf-8"))
        assert body["name"] == "New Name"

    def test_copy_without_title_sends_empty_body(self) -> None:
        captured: list[Any] = []

        with patch(
            "urllib.request.urlopen",
            side_effect=_capturing_urlopen(captured, {"id": "new-id"}),
        ):
            copy_drive_file("fake-token", "src-id", title=None)

        req = captured[0]
        body = json.loads(req.data.decode("utf-8"))
        assert body == {}

    def test_api_error_raises(self) -> None:
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=_make_http_error(404, "Not Found"),
            ),
            pytest.raises(Exception, match="404"),
        ):
            copy_drive_file("fake-token", "nonexistent-id")


# ---------------------------------------------------------------------------
# format_drive_files
# ---------------------------------------------------------------------------


class TestFormatDriveFiles:
    def _make_file(
        self,
        name: str = "Budget",
        mime: str = "application/vnd.google-apps.spreadsheet",
        modified: str = "2025-01-15T10:30:00.000Z",
        url: str = "https://docs.google.com/spreadsheets/d/abc",
    ) -> dict[str, Any]:
        return {
            "name": name,
            "mimeType": mime,
            "modifiedTime": modified,
            "webViewLink": url,
        }

    def test_empty_files_returns_no_files_message(self) -> None:
        result = format_drive_files([])
        assert result == "No files found."

    def test_known_mime_type_label(self) -> None:
        files = [self._make_file(mime="application/vnd.google-apps.spreadsheet")]
        result = format_drive_files(files)
        assert "Sheet" in result

    def test_slide_label(self) -> None:
        files = [self._make_file(mime="application/vnd.google-apps.presentation")]
        result = format_drive_files(files)
        assert "Slide" in result

    def test_doc_label(self) -> None:
        files = [self._make_file(mime="application/vnd.google-apps.document")]
        result = format_drive_files(files)
        assert "Doc" in result

    def test_unknown_mime_type_fallback(self) -> None:
        files = [self._make_file(mime="application/vnd.google-apps.drawing")]
        result = format_drive_files(files)
        assert "Drawing" in result or "drawing" in result.lower()

    def test_non_google_mime_type_shown_raw(self) -> None:
        files = [self._make_file(mime="application/pdf")]
        result = format_drive_files(files)
        assert "application/pdf" in result or "pdf" in result.lower()

    def test_header_row_present(self) -> None:
        files = [self._make_file()]
        result = format_drive_files(files)
        assert "NAME" in result
        assert "TYPE" in result
        assert "MODIFIED" in result
        assert "URL" in result

    def test_file_name_in_output(self) -> None:
        files = [self._make_file(name="My Special Budget")]
        result = format_drive_files(files)
        assert "My Special Budget" in result

    def test_url_in_output(self) -> None:
        files = [self._make_file(url="https://docs.google.com/spreadsheets/d/xyz123")]
        result = format_drive_files(files)
        assert "https://docs.google.com/spreadsheets/d/xyz123" in result

    def test_modified_time_formatted(self) -> None:
        files = [self._make_file(modified="2025-06-15T14:30:00.000Z")]
        result = format_drive_files(files)
        assert "2025-06-15" in result

    def test_next_page_token_shown(self) -> None:
        files = [self._make_file()]
        result = format_drive_files(files, next_page_token="abc-xyz-token")
        assert "abc-xyz-token" in result

    def test_no_next_page_token_not_shown(self) -> None:
        files = [self._make_file()]
        result = format_drive_files(files, next_page_token="")
        assert "Next page token" not in result

    def test_multiple_files(self) -> None:
        files = [
            self._make_file(name="File A"),
            self._make_file(name="File B"),
            self._make_file(name="File C"),
        ]
        result = format_drive_files(files)
        assert "File A" in result
        assert "File B" in result
        assert "File C" in result


# ---------------------------------------------------------------------------
# _parse_drive_file_id (from _common)
# ---------------------------------------------------------------------------

from extrasuite.client.cli._common import _parse_drive_file_id  # noqa: E402


class TestParseDriveFileId:
    def test_spreadsheet_url(self) -> None:
        url = "https://docs.google.com/spreadsheets/d/SHEET_ID/edit"
        assert _parse_drive_file_id(url) == "SHEET_ID"

    def test_presentation_url(self) -> None:
        url = "https://docs.google.com/presentation/d/SLIDE_ID/edit"
        assert _parse_drive_file_id(url) == "SLIDE_ID"

    def test_document_url(self) -> None:
        url = "https://docs.google.com/document/d/DOC_ID/edit"
        assert _parse_drive_file_id(url) == "DOC_ID"

    def test_form_url(self) -> None:
        url = "https://docs.google.com/forms/d/FORM_ID/edit"
        assert _parse_drive_file_id(url) == "FORM_ID"

    def test_drive_file_url(self) -> None:
        url = "https://drive.google.com/file/d/DRIVE_ID/view"
        assert _parse_drive_file_id(url) == "DRIVE_ID"

    def test_raw_id_returned_as_is(self) -> None:
        raw_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
        assert _parse_drive_file_id(raw_id) == raw_id
