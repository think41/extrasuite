"""Reconcile module — only reindex_document remains after v1/v2 removal."""

from __future__ import annotations

from extradoc.reconcile._core import reindex_document

__all__ = ["reindex_document"]
