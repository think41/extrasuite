"""Firestore TTL policy and composite index setup.

Called at server startup to ensure the required TTL policies and composite
indexes exist. Operations are fire-and-forget — failures log a warning but
never prevent the server from starting. All operations are idempotent.

TTL policies required (expires_at field):
  - oauth_states    — 10-minute state tokens
  - auth_codes      — 120-second auth codes
  - session_tokens  — 60-day (30d active + 30d audit)
  - access_logs     — 30-day audit entries

Composite indexes required:
  - session_tokens: email (ASC), active_expires_at (ASC), revoked_at (ASC)
    Used by list_session_tokens() and revoke_all_session_tokens() queries.
"""

import asyncio

from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
from google.cloud.firestore_admin_v1.services.firestore_admin.async_client import (
    FirestoreAdminAsyncClient,
)
from google.cloud.firestore_admin_v1.types import Field, Index
from google.protobuf import field_mask_pb2
from loguru import logger

_TTL_COLLECTIONS = ["oauth_states", "auth_codes", "session_tokens", "access_logs"]

_COMPOSITE_INDEXES = [
    {
        "collection": "session_tokens",
        "fields": [
            ("email", "ASCENDING"),
            ("active_expires_at", "ASCENDING"),
            ("revoked_at", "ASCENDING"),
        ],
    }
]


def ensure_firestore_setup(project: str, database: str = "(default)") -> asyncio.Task:
    """Schedule Firestore TTL and index setup as a background asyncio task.

    Call this inside an async lifespan context. Returns the Task so callers
    can store a reference (required to prevent garbage collection).
    """
    return asyncio.create_task(
        _setup_firestore(project, database),
        name="firestore-setup",
    )


async def _setup_firestore(project: str, database: str) -> None:
    client = FirestoreAdminAsyncClient()
    db_path = f"projects/{project}/databases/{database}"

    try:
        await _ensure_ttl_policies(client, db_path)
        await _ensure_composite_indexes(client, db_path)
    except GoogleAPICallError as e:
        logger.warning(
            "Firestore setup failed — TTL policies or indexes may need manual creation. "
            "Grant the server's service account 'roles/datastore.indexAdmin' to enable auto-setup.",
            extra={"error": str(e)},
        )
    except Exception as e:
        logger.warning("Firestore setup encountered an unexpected error", extra={"error": str(e)})
    finally:
        await client.transport.close()


async def _ensure_ttl_policies(client: FirestoreAdminAsyncClient, db_path: str) -> None:
    """Enable TTL on the expires_at field for all relevant collections."""
    mask = field_mask_pb2.FieldMask(paths=["ttl_config"])

    for collection in _TTL_COLLECTIONS:
        field_name = f"{db_path}/collectionGroups/{collection}/fields/expires_at"
        field = Field(
            name=field_name,
            ttl_config=Field.TtlConfig(state=Field.TtlConfig.State.ACTIVE),
        )
        try:
            operation = await client.update_field(
                request={"field": field, "update_mask": mask}
            )
            await operation.result()
            logger.info("Firestore TTL policy enabled", extra={"collection": collection})
        except Exception as e:
            # TTL already enabled or permission denied — log and continue
            logger.debug(
                "Firestore TTL setup skipped",
                extra={"collection": collection, "reason": str(e)},
            )


async def _ensure_composite_indexes(client: FirestoreAdminAsyncClient, db_path: str) -> None:
    """Create required composite indexes if they don't already exist."""
    for idx_spec in _COMPOSITE_INDEXES:
        collection = idx_spec["collection"]
        parent = f"{db_path}/collectionGroups/{collection}"

        fields = [
            Index.IndexField(field_path=field_path, order=order)
            for field_path, order in idx_spec["fields"]
        ]
        index = Index(
            query_scope=Index.QueryScope.COLLECTION,
            fields=fields,
        )

        try:
            operation = await client.create_index(parent=parent, index=index)
            await operation.result()
            logger.info(
                "Firestore composite index created",
                extra={"collection": collection},
            )
        except AlreadyExists:
            logger.debug("Firestore composite index already exists", extra={"collection": collection})
        except Exception as e:
            logger.warning(
                "Firestore composite index creation failed",
                extra={"collection": collection, "error": str(e)},
            )
