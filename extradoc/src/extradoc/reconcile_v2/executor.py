"""Execute lowered request batches with revision handoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

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


def resolve_deferred_placeholders(
    prior_responses: Sequence[dict[str, Any]],
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve DeferredID-style placeholder dicts inside raw request payloads."""

    def extract_path(data: Any, path: str) -> str:
        current = data
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                raise ValueError(f"Could not resolve deferred path {path!r} at key {key!r}")
            current = current[key]
        if not isinstance(current, str):
            raise ValueError(f"Deferred path {path!r} did not resolve to a string")
        return current

    def is_deferred_id_dict(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and "placeholder" in value
            and "batch_index" in value
            and "request_index" in value
            and "response_path" in value
        )

    def resolve(value: Any) -> Any:
        if is_deferred_id_dict(value):
            batch_index = value["batch_index"]
            request_index = value["request_index"]
            if not isinstance(batch_index, int) or not isinstance(request_index, int):
                raise ValueError("Deferred placeholder batch/request indexes must be integers")
            if batch_index >= len(prior_responses):
                raise ValueError(
                    f"Deferred placeholder references batch {batch_index}, "
                    f"but only {len(prior_responses)} response(s) are available"
                )
            replies = prior_responses[batch_index].get("replies", [])
            if not isinstance(replies, list) or request_index >= len(replies):
                raise ValueError(
                    f"Deferred placeholder references request {request_index}, "
                    f"but batch {batch_index} has {len(replies) if isinstance(replies, list) else 0} replies"
                )
            return extract_path(replies[request_index], value["response_path"])
        if isinstance(value, str) and value == "__LAST_ADDED_TAB_ID__":
            for response in reversed(prior_responses):
                replies = response.get("replies", [])
                if not isinstance(replies, list):
                    continue
                for reply in reversed(replies):
                    if not isinstance(reply, dict):
                        continue
                    add_document_tab = reply.get("addDocumentTab")
                    if not isinstance(add_document_tab, dict):
                        continue
                    tab_properties = add_document_tab.get("tabProperties")
                    if not isinstance(tab_properties, dict):
                        continue
                    tab_id = tab_properties.get("tabId")
                    if isinstance(tab_id, str):
                        return tab_id
            raise ValueError("Could not resolve __LAST_ADDED_TAB_ID__ from prior responses")
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    return cast(list[dict[str, Any]], resolve(batch))


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
    for batch in request_batches:
        requests = resolve_deferred_placeholders(responses, list(batch))
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
