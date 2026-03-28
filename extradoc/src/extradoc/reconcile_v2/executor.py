"""Execute lowered request batches with revision handoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence


class BatchUpdateTransport(Protocol):
    async def batch_update(
        self,
        document_id: str,
        requests: list[dict[str, Any]],
        write_control: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class BatchExecutionResult:
    responses: tuple[dict[str, Any], ...]
    final_revision_id: str | None


async def execute_request_batches(
    transport: BatchUpdateTransport,
    *,
    document_id: str,
    request_batches: Sequence[list[dict[str, Any]]],
    initial_revision_id: str | None,
) -> BatchExecutionResult:
    """Execute request batches, carrying forward returned requiredRevisionId."""
    revision_id = initial_revision_id
    responses: list[dict[str, Any]] = []
    for requests in request_batches:
        write_control = None
        if revision_id is not None:
            write_control = {"requiredRevisionId": revision_id}
        response = await transport.batch_update(
            document_id,
            list(requests),
            write_control=write_control,
        )
        responses.append(response)
        revision_id = _next_required_revision_id(response, revision_id)
    return BatchExecutionResult(
        responses=tuple(responses),
        final_revision_id=revision_id,
    )


def _next_required_revision_id(
    response: dict[str, Any],
    current_revision_id: str | None,
) -> str | None:
    write_control = response.get("writeControl")
    if not isinstance(write_control, dict):
        return current_revision_id
    next_revision_id = write_control.get("requiredRevisionId")
    if not isinstance(next_revision_id, str):
        return current_revision_id
    return next_revision_id
