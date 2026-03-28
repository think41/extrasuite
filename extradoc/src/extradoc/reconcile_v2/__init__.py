"""Second-generation reconciler under active development.

This package is intentionally isolated from ``extradoc.reconcile`` so the new
semantic-IR architecture can be implemented incrementally in-tree.
"""

from __future__ import annotations

from extradoc.reconcile_v2.api import reconcile

__all__ = ["reconcile"]
