"""reconcile_v3: top-down tree-oriented Google Docs reconciler.

Public API
----------
- ``reconcile(base, desired)`` → flat request list (single batch).
- ``reconcile_batches(base, desired)`` → multi-batch sequence with deferred IDs.
- ``diff(base, desired)`` → op list without lowering.
- ``execute_request_batches(...)`` → execute batches with deferred-ID resolution.
- ``resolve_deferred_placeholders(...)`` → resolve deferred IDs in a single batch.
"""

from extradoc.reconcile_v3.api import diff, reconcile, reconcile_batches
from extradoc.reconcile_v3.executor import (
    BatchExecutionResult,
    BatchUpdateTransport,
    execute_request_batches,
    resolve_deferred_placeholders,
)
from extradoc.reconcile_v3.model import ReconcileOp

__all__ = [
    "BatchExecutionResult",
    "BatchUpdateTransport",
    "ReconcileOp",
    "diff",
    "execute_request_batches",
    "reconcile",
    "reconcile_batches",
    "resolve_deferred_placeholders",
]
