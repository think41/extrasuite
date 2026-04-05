"""reconcile_v3: top-down tree-oriented Google Docs reconciler.

Public API
----------
- ``reconcile_batches(base, desired)`` → multi-batch sequence with deferred IDs.

Internal submodules (not re-exported; import directly when needed):
- ``reconcile_v3.api`` — ``diff()``, ``reconcile()``
- ``reconcile_v3.executor`` — ``execute_request_batches()``, ``BatchUpdateTransport``, ``BatchExecutionResult``
- ``reconcile_v3.model`` — ``ReconcileOp`` and individual op dataclasses
"""

from extradoc.reconcile_v3.api import reconcile_batches

__all__ = [
    "reconcile_batches",
]
