"""diffmerge: diff two Google Docs Documents and merge changes onto a base.

Public API
----------
- ``diff(base, desired)`` → list of DiffOp describing what changed.
- ``apply(base_dict, ops)`` → new document dict with ops applied to base.
- ``DiffOp`` — union type of all diff operation dataclasses.
"""

from extradoc.diffmerge.apply_ops import apply_ops_to_document as apply
from extradoc.diffmerge.content_align import ContentAlignment
from extradoc.diffmerge.diff import diff_documents as diff
from extradoc.diffmerge.errors import (
    ReconcileV3Error,
    ReconcileV3InvariantError,
    UnsupportedReconcileV3Error,
)
from extradoc.diffmerge.model import (
    CreateFooterOp,
    CreateHeaderOp,
    DeleteFooterOp,
    DeleteFootnoteOp,
    DeleteHeaderOp,
    DeleteInlineObjectOp,
    DeleteListOp,
    DeleteNamedRangeOp,
    DeleteNamedStyleOp,
    DeleteTableColumnOp,
    DeleteTableRowOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertInlineObjectOp,
    InsertListOp,
    InsertNamedRangeOp,
    InsertNamedStyleOp,
    InsertTableColumnOp,
    InsertTableRowOp,
    InsertTabOp,
    UpdateBodyContentOp,
    UpdateDocumentStyleOp,
    UpdateFooterContentOp,
    UpdateFootnoteContentOp,
    UpdateHeaderContentOp,
    UpdateInlineObjectOp,
    UpdateListOp,
    UpdateNamedStyleOp,
    UpdateTableCellStyleOp,
    UpdateTableColumnPropertiesOp,
    UpdateTableRowStyleOp,
)
from extradoc.diffmerge.model import (
    ReconcileOp as DiffOp,
)

__all__ = [
    "ContentAlignment",
    "CreateFooterOp",
    "CreateHeaderOp",
    "DeleteFooterOp",
    "DeleteFootnoteOp",
    "DeleteHeaderOp",
    "DeleteInlineObjectOp",
    "DeleteListOp",
    "DeleteNamedRangeOp",
    "DeleteNamedStyleOp",
    "DeleteTabOp",
    "DeleteTableColumnOp",
    "DeleteTableRowOp",
    "DiffOp",
    "InsertFootnoteOp",
    "InsertInlineObjectOp",
    "InsertListOp",
    "InsertNamedRangeOp",
    "InsertNamedStyleOp",
    "InsertTabOp",
    "InsertTableColumnOp",
    "InsertTableRowOp",
    "ReconcileV3Error",
    "ReconcileV3InvariantError",
    "UnsupportedReconcileV3Error",
    "UpdateBodyContentOp",
    "UpdateDocumentStyleOp",
    "UpdateFooterContentOp",
    "UpdateFootnoteContentOp",
    "UpdateHeaderContentOp",
    "UpdateInlineObjectOp",
    "UpdateListOp",
    "UpdateNamedStyleOp",
    "UpdateTableCellStyleOp",
    "UpdateTableColumnPropertiesOp",
    "UpdateTableRowStyleOp",
    "apply",
    "diff",
]
