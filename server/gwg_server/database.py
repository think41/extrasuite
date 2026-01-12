"""Database layer using Google Cloud Bigtable.

Stores two types of data:
1. Sessions: session_id -> email (for HTTP session management)
2. Users: email -> OAuth credentials + service account info

Tables structure:
- sessions: Row key = session_id, Column family = data
  - data:email - User email associated with session
  - data:created_at - Session creation timestamp

- users: Row key = email, Column family = oauth, metadata
  - oauth:access_token - OAuth access token
  - oauth:refresh_token - OAuth refresh token
  - oauth:scopes - JSON array of scopes
  - metadata:service_account_email - Associated service account
  - metadata:created_at - Record creation timestamp
  - metadata:updated_at - Last update timestamp
"""

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from google.cloud import bigtable
from google.cloud.bigtable import row_filters

from gwg_server.config import get_settings

# Column families
SESSIONS_CF = "data"
USERS_OAUTH_CF = "oauth"
USERS_METADATA_CF = "metadata"

# Bigtable client instance (singleton)
_client: bigtable.Client | None = None
_instance: bigtable.instance.Instance | None = None


@dataclass
class UserCredentials:
    """User OAuth credentials and service account info."""

    email: str
    access_token: str
    refresh_token: str
    scopes: list[str]
    service_account_email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Session:
    """User session data."""

    session_id: str
    email: str
    created_at: datetime | None = None


def _get_client() -> bigtable.Client:
    """Get or create Bigtable client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = bigtable.Client(project=settings.google_cloud_project, admin=False)
    return _client


def _get_instance() -> bigtable.instance.Instance:
    """Get or create Bigtable instance reference."""
    global _instance
    if _instance is None:
        settings = get_settings()
        client = _get_client()
        _instance = client.instance(settings.bigtable_instance)
    return _instance


def _get_sessions_table():
    """Get sessions table reference."""
    instance = _get_instance()
    return instance.table("sessions")


def _get_users_table():
    """Get users table reference."""
    instance = _get_instance()
    return instance.table("users")


def _decode_cell(row, column_family: str, column: str) -> str | None:
    """Decode a cell value from a Bigtable row."""
    try:
        cells = row.cells.get(column_family, {}).get(column.encode(), [])
        if cells:
            return cells[0].value.decode("utf-8")
    except (KeyError, IndexError, AttributeError):
        pass
    return None


# ============================================================================
# Session Management
# ============================================================================


def create_session(session_id: str, email: str) -> Session:
    """Create a new session in Bigtable."""
    table = _get_sessions_table()
    row_key = session_id.encode("utf-8")
    row = table.direct_row(row_key)

    now = datetime.now(UTC).isoformat()
    row.set_cell(SESSIONS_CF, "email", email.encode("utf-8"))
    row.set_cell(SESSIONS_CF, "created_at", now.encode("utf-8"))
    row.commit()

    return Session(session_id=session_id, email=email, created_at=datetime.now(UTC))


def get_session(session_id: str) -> Session | None:
    """Get session by ID from Bigtable."""
    table = _get_sessions_table()
    row_key = session_id.encode("utf-8")

    # Read only the data column family
    row = table.read_row(row_key, filter_=row_filters.FamilyNameRegexFilter(SESSIONS_CF))

    if row is None:
        return None

    email = _decode_cell(row, SESSIONS_CF, "email")
    if not email:
        return None

    created_at_str = _decode_cell(row, SESSIONS_CF, "created_at")
    created_at = None
    if created_at_str:
        with contextlib.suppress(ValueError):
            created_at = datetime.fromisoformat(created_at_str)

    return Session(session_id=session_id, email=email, created_at=created_at)


def delete_session(session_id: str) -> None:
    """Delete a session from Bigtable."""
    table = _get_sessions_table()
    row_key = session_id.encode("utf-8")
    row = table.direct_row(row_key)
    row.delete()
    row.commit()


# ============================================================================
# User Credentials Management
# ============================================================================


def store_user_credentials(
    email: str,
    access_token: str,
    refresh_token: str,
    scopes: list[str],
    service_account_email: str | None = None,
) -> UserCredentials:
    """Store or update user OAuth credentials in Bigtable."""
    table = _get_users_table()
    row_key = email.encode("utf-8")
    row = table.direct_row(row_key)

    now = datetime.now(UTC).isoformat()

    # OAuth credentials
    row.set_cell(USERS_OAUTH_CF, "access_token", access_token.encode("utf-8"))
    row.set_cell(USERS_OAUTH_CF, "refresh_token", refresh_token.encode("utf-8"))
    row.set_cell(USERS_OAUTH_CF, "scopes", json.dumps(scopes).encode("utf-8"))

    # Metadata
    if service_account_email:
        row.set_cell(
            USERS_METADATA_CF, "service_account_email", service_account_email.encode("utf-8")
        )
    row.set_cell(USERS_METADATA_CF, "updated_at", now.encode("utf-8"))

    # Check if this is a new record to set created_at
    existing = get_user_credentials(email)
    if existing is None:
        row.set_cell(USERS_METADATA_CF, "created_at", now.encode("utf-8"))

    row.commit()

    return UserCredentials(
        email=email,
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
        service_account_email=service_account_email,
        updated_at=datetime.now(UTC),
    )


def get_user_credentials(email: str) -> UserCredentials | None:
    """Get user credentials by email from Bigtable."""
    table = _get_users_table()
    row_key = email.encode("utf-8")

    row = table.read_row(row_key)
    if row is None:
        return None

    access_token = _decode_cell(row, USERS_OAUTH_CF, "access_token")
    refresh_token = _decode_cell(row, USERS_OAUTH_CF, "refresh_token")
    scopes_json = _decode_cell(row, USERS_OAUTH_CF, "scopes")
    service_account_email = _decode_cell(row, USERS_METADATA_CF, "service_account_email")
    created_at_str = _decode_cell(row, USERS_METADATA_CF, "created_at")
    updated_at_str = _decode_cell(row, USERS_METADATA_CF, "updated_at")

    if not access_token or not refresh_token:
        return None

    scopes = []
    if scopes_json:
        with contextlib.suppress(json.JSONDecodeError):
            scopes = json.loads(scopes_json)

    created_at = None
    if created_at_str:
        with contextlib.suppress(ValueError):
            created_at = datetime.fromisoformat(created_at_str)

    updated_at = None
    if updated_at_str:
        with contextlib.suppress(ValueError):
            updated_at = datetime.fromisoformat(updated_at_str)

    return UserCredentials(
        email=email,
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
        service_account_email=service_account_email,
        created_at=created_at,
        updated_at=updated_at,
    )


def update_service_account_email(email: str, service_account_email: str) -> None:
    """Update the service account email for a user."""
    table = _get_users_table()
    row_key = email.encode("utf-8")
    row = table.direct_row(row_key)

    now = datetime.now(UTC).isoformat()
    row.set_cell(USERS_METADATA_CF, "service_account_email", service_account_email.encode("utf-8"))
    row.set_cell(USERS_METADATA_CF, "updated_at", now.encode("utf-8"))
    row.commit()


# ============================================================================
# Database Lifecycle
# ============================================================================


def init_db():
    """Initialize database connection.

    For Bigtable, we just verify connectivity by getting the instance.
    Tables are created via gcloud/cbt commands, not at runtime.
    """
    from gwg_server.logging import logger

    try:
        instance = _get_instance()
        # Verify we can access the tables
        sessions_table = instance.table("sessions")
        users_table = instance.table("users")

        # Simple read to verify connectivity (will return None if no data)
        sessions_table.read_row(b"__connectivity_check__")
        users_table.read_row(b"__connectivity_check__")

        logger.info("Bigtable connection verified")
    except Exception as e:
        logger.error(f"Failed to connect to Bigtable: {e}")
        raise


def close_db():
    """Close database connections."""
    global _client, _instance
    if _client:
        _client.close()
        _client = None
        _instance = None
