from __future__ import annotations

from typing import Any

import pytest

from extradoc.reconcile_v2.executor import execute_request_batches


class FakeBatchTransport:
    def __init__(self, revision_ids: list[str | None]) -> None:
        self._revision_ids = revision_ids
        self.calls: list[dict[str, Any]] = []

    async def batch_update(
        self,
        document_id: str,
        requests: list[dict[str, Any]],
        write_control: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "document_id": document_id,
                "requests": requests,
                "write_control": write_control,
            }
        )
        revision_id = self._revision_ids[len(self.calls) - 1]
        response: dict[str, Any] = {"replies": [{}] * len(requests)}
        if revision_id is not None:
            response["writeControl"] = {"requiredRevisionId": revision_id}
        return response


@pytest.mark.asyncio
async def test_execute_request_batches_threads_required_revision_id() -> None:
    transport = FakeBatchTransport(["rev-2", "rev-3"])

    result = await execute_request_batches(
        transport,
        document_id="doc-123",
        request_batches=(
            [{"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "a"}}],
            [{"insertText": {"location": {"index": 2, "tabId": "t.0"}, "text": "b"}}],
        ),
        initial_revision_id="rev-1",
    )

    assert [call["write_control"] for call in transport.calls] == [
        {"requiredRevisionId": "rev-1"},
        {"requiredRevisionId": "rev-2"},
    ]
    assert result.final_revision_id == "rev-3"


@pytest.mark.asyncio
async def test_execute_request_batches_tolerates_missing_write_control_in_response() -> None:
    transport = FakeBatchTransport([None, "rev-2"])

    result = await execute_request_batches(
        transport,
        document_id="doc-123",
        request_batches=(
            [{"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "a"}}],
            [{"insertText": {"location": {"index": 2, "tabId": "t.0"}, "text": "b"}}],
        ),
        initial_revision_id="rev-1",
    )

    assert [call["write_control"] for call in transport.calls] == [
        {"requiredRevisionId": "rev-1"},
        {"requiredRevisionId": "rev-1"},
    ]
    assert result.final_revision_id == "rev-2"
