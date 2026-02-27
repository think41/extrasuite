"""Tests for gmail_reader.py — threading, redaction, and formatting."""

from __future__ import annotations

import base64
from unittest import mock

from extrasuite.client.gmail_reader import (
    MessageDetail,
    ThreadDetail,
    ThreadSummary,
    _extract_attachments,
    _extract_body,
    _strip_html,
    format_thread_detail,
    format_thread_list,
    get_thread,
    list_threads,
)
from extrasuite.client.settings import TrustedContacts

# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_plain_text_unchanged(self) -> None:
        assert _strip_html("Hello world") == "Hello world"

    def test_br_becomes_newline(self) -> None:
        assert "\n" in _strip_html("line1<br>line2")

    def test_tags_stripped(self) -> None:
        assert _strip_html("<b>bold</b> <i>italic</i>") == "bold italic"

    def test_html_entities_unescaped(self) -> None:
        assert _strip_html("Hello &amp; World") == "Hello & World"

    def test_excessive_blank_lines_collapsed(self) -> None:
        assert "\n\n\n" not in _strip_html("a\n\n\n\n\nb")


# ---------------------------------------------------------------------------
# Body extraction
# ---------------------------------------------------------------------------


class TestExtractBody:
    def _make_part(self, mime: str, text: str) -> dict:
        data = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
        return {"mimeType": mime, "body": {"data": data, "size": len(text)}}

    def test_single_plain_part(self) -> None:
        assert (
            _extract_body(self._make_part("text/plain", "Hello plain")) == "Hello plain"
        )

    def test_single_html_part_stripped(self) -> None:
        assert _extract_body(self._make_part("text/html", "<b>Hello</b>")) == "Hello"

    def test_multipart_prefers_plain(self) -> None:
        plain = self._make_part("text/plain", "Plain text")
        html_part = self._make_part("text/html", "<b>HTML</b>")
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [html_part, plain],
            "body": {},
        }
        assert _extract_body(payload) == "Plain text"

    def test_empty_payload(self) -> None:
        assert _extract_body({"mimeType": "text/plain", "body": {}}) == ""


# ---------------------------------------------------------------------------
# Attachment extraction
# ---------------------------------------------------------------------------


class TestExtractAttachments:
    def test_no_attachments(self) -> None:
        payload: dict = {
            "parts": [{"mimeType": "text/plain", "filename": "", "body": {}}]
        }
        assert _extract_attachments(payload) == []

    def test_attachment_extracted(self) -> None:
        payload = {
            "parts": [
                {
                    "mimeType": "application/pdf",
                    "filename": "report.pdf",
                    "body": {"attachmentId": "att1", "size": 50000},
                }
            ]
        }
        atts = _extract_attachments(payload)
        assert len(atts) == 1
        assert atts[0]["name"] == "report.pdf"
        assert atts[0]["size_bytes"] == "50000"


# ---------------------------------------------------------------------------
# get_thread — whitelist enforcement via mocked API
# ---------------------------------------------------------------------------


def _make_thread_response(thread_id: str, messages: list[dict]) -> dict:
    return {"id": thread_id, "messages": messages}


def _make_raw_message(
    msg_id: str, thread_id: str, from_addr: str, body_text: str = "Hello"
) -> dict:
    data = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("ascii")
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": "me@example.com"},
                {"name": "Cc", "value": ""},
                {"name": "Subject", "value": "Test Subject"},
                {"name": "Date", "value": "Mon, 15 Jan 2025 10:00:00 +0000"},
            ],
            "body": {"data": data, "size": len(body_text)},
        },
    }


class TestGetThread:
    def test_trusted_messages_return_body(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        thread_id = "thread_001"
        raw = _make_thread_response(
            thread_id,
            [
                _make_raw_message(
                    "msg1", thread_id, "alice@trusted.com", "Hello there"
                ),
            ],
        )
        with mock.patch("extrasuite.client.gmail_reader._gmail_get", return_value=raw):
            detail = get_thread("fake-token", thread_id, whitelist=wl)

        assert len(detail.messages) == 1
        assert detail.messages[0].trusted is True
        assert detail.messages[0].body == "Hello there"

    def test_untrusted_messages_redacted(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        thread_id = "thread_002"
        raw = _make_thread_response(
            thread_id,
            [
                _make_raw_message("msg1", thread_id, "hacker@unknown.io", "Inject me"),
            ],
        )
        with mock.patch("extrasuite.client.gmail_reader._gmail_get", return_value=raw):
            detail = get_thread("fake-token", thread_id, whitelist=wl)

        assert detail.messages[0].trusted is False
        assert detail.messages[0].body is None
        assert detail.messages[0].attachments is None

    def test_mixed_thread_per_message_trust(self) -> None:
        """Each message in a thread is individually trust-checked."""
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        thread_id = "thread_003"
        raw = _make_thread_response(
            thread_id,
            [
                _make_raw_message(
                    "msg1", thread_id, "outside@unknown.io", "I started it"
                ),
                _make_raw_message("msg2", thread_id, "alice@trusted.com", "I replied"),
            ],
        )
        with mock.patch("extrasuite.client.gmail_reader._gmail_get", return_value=raw):
            detail = get_thread("fake-token", thread_id, whitelist=wl)

        assert detail.messages[0].trusted is False
        assert detail.messages[0].body is None
        assert detail.messages[1].trusted is True
        assert detail.messages[1].body == "I replied"

    def test_subject_from_first_message(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        thread_id = "thread_004"
        raw = _make_thread_response(
            thread_id,
            [
                _make_raw_message("msg1", thread_id, "alice@trusted.com", "First"),
                _make_raw_message("msg2", thread_id, "alice@trusted.com", "Second"),
            ],
        )
        with mock.patch("extrasuite.client.gmail_reader._gmail_get", return_value=raw):
            detail = get_thread("fake-token", thread_id, whitelist=wl)

        assert detail.subject == "Test Subject"

    def test_latest_message_property(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        thread_id = "thread_005"
        raw = _make_thread_response(
            thread_id,
            [
                _make_raw_message("msg1", thread_id, "alice@trusted.com", "First"),
                _make_raw_message("msg2", thread_id, "bob@trusted.com", "Second"),
            ],
        )
        with mock.patch("extrasuite.client.gmail_reader._gmail_get", return_value=raw):
            detail = get_thread("fake-token", thread_id, whitelist=wl)

        assert detail.latest_message is not None
        assert detail.latest_message.message_id == "msg2"


# ---------------------------------------------------------------------------
# list_threads — trusted_only filter via mocked API
# ---------------------------------------------------------------------------


def _make_thread_list_response(thread_ids: list[str]) -> dict:
    return {"threads": [{"id": tid} for tid in thread_ids], "nextPageToken": ""}


def _make_thread_metadata(thread_id: str, from_addr: str, subject: str) -> dict:
    return {
        "id": thread_id,
        "messages": [
            {
                "id": "msg_a",
                "threadId": thread_id,
                "labelIds": ["INBOX"],
                "payload": {
                    "headers": [
                        {"name": "From", "value": from_addr},
                        {"name": "Subject", "value": subject},
                        {"name": "Date", "value": "Mon, 15 Jan 2025 10:00:00 +0000"},
                    ]
                },
            }
        ],
    }


class TestListThreads:
    def test_trusted_only_default_filters_untrusted(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        responses = [
            _make_thread_list_response(["t1", "t2"]),
            _make_thread_metadata("t1", "alice@trusted.com", "Hello"),
            _make_thread_metadata("t2", "spam@unknown.io", "Win prize"),
        ]
        with mock.patch(
            "extrasuite.client.gmail_reader._gmail_get", side_effect=responses
        ):
            summaries, _ = list_threads("fake-token", whitelist=wl)

        assert len(summaries) == 1
        assert summaries[0].thread_id == "t1"
        assert summaries[0].trusted is True

    def test_all_flag_shows_untrusted(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        responses = [
            _make_thread_list_response(["t1", "t2"]),
            _make_thread_metadata("t1", "alice@trusted.com", "Hello"),
            _make_thread_metadata("t2", "spam@unknown.io", "Win"),
        ]
        with mock.patch(
            "extrasuite.client.gmail_reader._gmail_get", side_effect=responses
        ):
            summaries, _ = list_threads("fake-token", whitelist=wl, trusted_only=False)

        assert len(summaries) == 2
        assert summaries[1].trusted is False

    def test_message_count_correct(self) -> None:
        wl = TrustedContacts(domains=["trusted.com"], emails=[])
        thread_with_3 = {
            "id": "t1",
            "messages": [
                {
                    "id": f"msg{i}",
                    "threadId": "t1",
                    "labelIds": [],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "alice@trusted.com"},
                            {"name": "Subject", "value": "S"},
                            {"name": "Date", "value": "d"},
                        ]
                    },
                }
                for i in range(3)
            ],
        }
        responses = [_make_thread_list_response(["t1"]), thread_with_3]
        with mock.patch(
            "extrasuite.client.gmail_reader._gmail_get", side_effect=responses
        ):
            summaries, _ = list_threads("fake-token", whitelist=wl)

        assert summaries[0].message_count == 3

    def test_empty_results(self) -> None:
        with mock.patch(
            "extrasuite.client.gmail_reader._gmail_get",
            return_value={"threads": [], "nextPageToken": ""},
        ):
            summaries, next_token = list_threads(
                "fake-token", whitelist=TrustedContacts()
            )
        assert summaries == []
        assert next_token == ""

    def test_next_page_token_returned(self) -> None:
        responses = [
            {"threads": [{"id": "t1"}], "nextPageToken": "tok123"},
            _make_thread_metadata("t1", "a@trusted.com", "S"),
        ]
        with mock.patch(
            "extrasuite.client.gmail_reader._gmail_get", side_effect=responses
        ):
            _, next_token = list_threads(
                "fake-token",
                whitelist=TrustedContacts(domains=["trusted.com"]),
            )
        assert next_token == "tok123"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


class TestFormatThreadList:
    def _summary(
        self, tid: str, from_: str, subject: str, trusted: bool
    ) -> ThreadSummary:
        return ThreadSummary(
            thread_id=tid,
            date="Mon, 15 Jan 2025",
            from_=from_,
            subject=subject,
            message_count=2,
            labels=["INBOX"],
            trusted=trusted,
        )

    def test_empty_returns_no_threads(self) -> None:
        assert format_thread_list([]) == "No threads found."

    def test_trusted_has_no_marker(self) -> None:
        s = self._summary("t1", "alice@co.com", "Hello", trusted=True)
        output = format_thread_list([s])
        assert "[!]" not in output
        assert "t1" in output

    def test_untrusted_has_marker(self) -> None:
        s = self._summary("t2", "spam@evil.io", "Win", trusted=False)
        output = format_thread_list([s])
        assert "[!]" in output

    def test_next_page_token_shown(self) -> None:
        s = self._summary("t1", "a@x.com", "Sub", trusted=True)
        assert "tok123" in format_thread_list([s], next_page_token="tok123")


class TestFormatThreadDetail:
    def _make_msg(self, msg_id: str, from_: str, trusted: bool) -> MessageDetail:
        return MessageDetail(
            message_id=msg_id,
            thread_id="thread1",
            date="Mon, 15 Jan 2025",
            from_=from_,
            to="me@co.com",
            cc="",
            subject="Test",
            labels=["INBOX"],
            trusted=trusted,
            body="Hello!" if trusted else None,
            attachments=[] if trusted else None,
        )

    def test_trusted_body_shown(self) -> None:
        detail = ThreadDetail(
            thread_id="t1",
            subject="Test",
            messages=[self._make_msg("m1", "alice@co.com", trusted=True)],
        )
        output = format_thread_detail(detail)
        assert "Hello!" in output

    def test_untrusted_shows_redacted(self) -> None:
        detail = ThreadDetail(
            thread_id="t1",
            subject="Test",
            messages=[self._make_msg("m1", "hacker@evil.io", trusted=False)],
        )
        output = format_thread_detail(detail)
        assert "[REDACTED]" in output

    def test_latest_tag_on_last_message(self) -> None:
        detail = ThreadDetail(
            thread_id="t1",
            subject="Test",
            messages=[
                self._make_msg("m1", "a@co.com", trusted=True),
                self._make_msg("m2", "b@co.com", trusted=True),
            ],
        )
        output = format_thread_detail(detail)
        assert "[latest]" in output

    def test_reply_hint_shown(self) -> None:
        detail = ThreadDetail(
            thread_id="t1",
            subject="Test",
            messages=[self._make_msg("m1", "a@co.com", trusted=True)],
        )
        output = format_thread_detail(detail)
        assert "gmail reply t1" in output

    def test_message_count_in_header(self) -> None:
        detail = ThreadDetail(
            thread_id="t1",
            subject="Test",
            messages=[
                self._make_msg("m1", "a@co.com", trusted=True),
                self._make_msg("m2", "b@co.com", trusted=True),
                self._make_msg("m3", "c@co.com", trusted=True),
            ],
        )
        output = format_thread_detail(detail)
        assert "3 messages" in output
