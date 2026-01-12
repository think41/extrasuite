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

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from google.cloud import firestore


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


class Database:
    """Firestore database client for GWG.

    This class encapsulates all database operations and manages the Firestore
    client lifecycle. Use dependency injection to provide instances to handlers.
    """

    def __init__(self, project: str, database: str = "(default)"):
        """Initialize database with project and database name.

        Args:
            project: Google Cloud project ID
            database: Firestore database name (defaults to "(default)")
        """
        self._client = firestore.Client(project=project, database=database)

    def close(self) -> None:
        """Close the database connection."""
        self._client.close()

    def verify_connection(self) -> None:
        """Verify database connectivity by attempting a read."""
        self._client.collection("sessions").limit(1).get()

    @staticmethod
    def _email_to_doc_id(email: str) -> str:
        """Convert email to valid Firestore document ID."""
        return email.replace("/", "__")

    # =========================================================================
    # Session Management
    # =========================================================================

    def create_session(self, session_id: str, email: str) -> Session:
        """Create a new session."""
        now = datetime.now(UTC)
        doc_ref = self._client.collection("sessions").document(session_id)
        doc_ref.set({"email": email, "created_at": now})
        return Session(session_id=session_id, email=email, created_at=now)

    def get_session(self, session_id: str) -> Session | None:
        """Get session by ID."""
        doc_ref = self._client.collection("sessions").document(session_id)
        doc = doc_ref.get()

        if not doc.exists:
            return None

        data = doc.to_dict()
        email = data.get("email")
        if not email:
            return None

        return Session(
            session_id=session_id,
            email=email,
            created_at=data.get("created_at"),
        )

    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        doc_ref = self._client.collection("sessions").document(session_id)
        doc_ref.delete()

    # =========================================================================
    # User Credentials Management
    # =========================================================================

    def store_user_credentials(
        self,
        email: str,
        access_token: str,
        refresh_token: str,
        scopes: list[str],
        service_account_email: str | None = None,
    ) -> UserCredentials:
        """Store or update user OAuth credentials."""
        doc_id = self._email_to_doc_id(email)
        doc_ref = self._client.collection("users").document(doc_id)

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

    def get_user_credentials(self, email: str) -> UserCredentials | None:
        """Get user credentials by email."""
        doc_id = self._email_to_doc_id(email)
        doc_ref = self._client.collection("users").document(doc_id)
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

    def update_service_account_email(self, email: str, service_account_email: str) -> None:
        """Update the service account email for a user."""
        doc_id = self._email_to_doc_id(email)
        doc_ref = self._client.collection("users").document(doc_id)

        now = datetime.now(UTC)
        doc_ref.update({"service_account_email": service_account_email, "updated_at": now})


def get_database(request: Request) -> Database:
    """FastAPI dependency to get the database instance.

    The database is stored in app.state during application lifespan.

    Usage:
        @router.get("/example")
        async def example(db: Database = Depends(get_database)):
            ...
    """
    return request.app.state.database
