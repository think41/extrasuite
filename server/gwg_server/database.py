"""Database layer using Google Cloud Firestore.

Stores two types of data:
1. Sessions: session_id -> email (for HTTP session management)
2. Users: email -> OAuth credentials + service account info

Collections structure:
- sessions: Document ID = session_id
  - email: User email associated with session
  - created_at: Session creation timestamp

- users: Document ID = email (with "/" replaced by "__")
  - access_token: OAuth access token
  - refresh_token: OAuth refresh token
  - scopes: List of OAuth scopes
  - service_account_email: Associated service account
  - created_at: Record creation timestamp
  - updated_at: Last update timestamp
"""

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from google.cloud import firestore

from gwg_server.config import get_settings

# Firestore client instance (singleton)
_db: firestore.Client | None = None


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


def _get_db() -> firestore.Client:
    """Get or create Firestore client."""
    global _db
    if _db is None:
        settings = get_settings()
        _db = firestore.Client(
            project=settings.google_cloud_project,
            database=settings.firestore_database,
        )
    return _db


def _email_to_doc_id(email: str) -> str:
    """Convert email to valid Firestore document ID.

    Firestore document IDs cannot contain "/", so we replace it.
    """
    return email.replace("/", "__")


def _doc_id_to_email(doc_id: str) -> str:
    """Convert Firestore document ID back to email."""
    return doc_id.replace("__", "/")


# ============================================================================
# Session Management
# ============================================================================


def create_session(session_id: str, email: str) -> Session:
    """Create a new session in Firestore."""
    db = _get_db()
    now = datetime.now(UTC)

    doc_ref = db.collection("sessions").document(session_id)
    doc_ref.set({"email": email, "created_at": now})

    return Session(session_id=session_id, email=email, created_at=now)


def get_session(session_id: str) -> Session | None:
    """Get session by ID from Firestore."""
    db = _get_db()
    doc_ref = db.collection("sessions").document(session_id)
    doc = doc_ref.get()

    if not doc.exists:
        return None

    data = doc.to_dict()
    email = data.get("email")
    if not email:
        return None

    created_at = data.get("created_at")
    if created_at and hasattr(created_at, "replace"):
        # Firestore returns datetime objects with tzinfo
        pass
    elif created_at:
        with contextlib.suppress(ValueError):
            created_at = datetime.fromisoformat(str(created_at))

    return Session(session_id=session_id, email=email, created_at=created_at)


def delete_session(session_id: str) -> None:
    """Delete a session from Firestore."""
    db = _get_db()
    doc_ref = db.collection("sessions").document(session_id)
    doc_ref.delete()


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
    """Store or update user OAuth credentials in Firestore."""
    db = _get_db()
    doc_id = _email_to_doc_id(email)
    doc_ref = db.collection("users").document(doc_id)

    now = datetime.now(UTC)

    # Check if document exists to preserve created_at
    existing_doc = doc_ref.get()
    created_at = now
    if existing_doc.exists:
        existing_data = existing_doc.to_dict()
        created_at = existing_data.get("created_at", now)

    data = {
        "email": email,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "scopes": scopes,
        "created_at": created_at,
        "updated_at": now,
    }

    if service_account_email:
        data["service_account_email"] = service_account_email

    doc_ref.set(data)

    return UserCredentials(
        email=email,
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=scopes,
        service_account_email=service_account_email,
        created_at=created_at,
        updated_at=now,
    )


def get_user_credentials(email: str) -> UserCredentials | None:
    """Get user credentials by email from Firestore."""
    db = _get_db()
    doc_id = _email_to_doc_id(email)
    doc_ref = db.collection("users").document(doc_id)
    doc = doc_ref.get()

    if not doc.exists:
        return None

    data = doc.to_dict()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if not access_token or not refresh_token:
        return None

    return UserCredentials(
        email=data.get("email", email),
        access_token=access_token,
        refresh_token=refresh_token,
        scopes=data.get("scopes", []),
        service_account_email=data.get("service_account_email"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def update_service_account_email(email: str, service_account_email: str) -> None:
    """Update the service account email for a user."""
    db = _get_db()
    doc_id = _email_to_doc_id(email)
    doc_ref = db.collection("users").document(doc_id)

    now = datetime.now(UTC)
    doc_ref.update({"service_account_email": service_account_email, "updated_at": now})


# ============================================================================
# Database Lifecycle
# ============================================================================


def init_db():
    """Initialize database connection.

    For Firestore, we verify connectivity by attempting to access a collection.
    Collections and documents are created automatically on first write.
    """
    from gwg_server.logging import logger

    try:
        db = _get_db()
        # Simple read to verify connectivity (will return empty if no data)
        db.collection("sessions").limit(1).get()
        logger.info("Firestore connection verified")
    except Exception as e:
        logger.error(f"Failed to connect to Firestore: {e}")
        raise


def close_db():
    """Close database connections."""
    global _db
    if _db:
        _db.close()
        _db = None
