"""Database layer using Google Cloud Firestore (async).

Stores two types of data:
1. Users: email -> OAuth credentials + service account info
2. OAuth States: state_token -> redirect_url + created_at (for OAuth flow)

Collections structure:
- users: Document ID = email (with "/" replaced by "__")
  - access_token: OAuth access token
  - refresh_token: OAuth refresh token
  - scopes: List of OAuth scopes
  - service_account_email: Associated service account
  - created_at: Record creation timestamp
  - updated_at: Last update timestamp

- oauth_states: Document ID = state_token
  - redirect_url: Redirect URL for CLI callback
  - created_at: State creation timestamp (TTL: 10 minutes)

Note: Sessions are handled via starlette's signed cookies (stateless).
The cookie stores the user email, which is validated against the users collection.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from google.cloud.firestore_v1 import AsyncClient, AsyncQuery, DocumentSnapshot

# OAuth state TTL
OAUTH_STATE_TTL = timedelta(minutes=10)

# Default timeout for database operations (seconds)
DEFAULT_TIMEOUT = 10.0


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


class Database:
    """Async Firestore database client for ExtraSuite.

    This class encapsulates all database operations and manages the Firestore
    client lifecycle. Use dependency injection to provide instances to handlers.
    All operations have a configurable timeout (default 10 seconds).
    """

    def __init__(self, project: str, database: str = "(default)", timeout: float = DEFAULT_TIMEOUT):
        """Initialize database with project and database name.

        Args:
            project: Google Cloud project ID
            database: Firestore database name (defaults to "(default)")
            timeout: Timeout in seconds for database operations (default 10)
        """
        self._client = AsyncClient(project=project, database=database)
        self._timeout = timeout

    async def close(self) -> None:
        """Close the database connection."""
        self._client.close()

    @staticmethod
    def _email_to_doc_id(email: str) -> str:
        """Convert email to valid Firestore document ID."""
        return email.replace("/", "__")

    # =========================================================================
    # OAuth State Management (for CSRF protection during OAuth flow)
    # =========================================================================

    async def save_state(self, state: str, redirect_url: str) -> None:
        """Save OAuth state token with redirect URL."""
        now = datetime.now(UTC)
        doc_ref = self._client.collection("oauth_states").document(state)

        async def _create() -> None:
            await doc_ref.set({"redirect_url": redirect_url, "created_at": now})

        await asyncio.wait_for(_create(), timeout=self._timeout)

    async def retrieve_state(self, state: str) -> str | None:
        """Retrieve AND delete OAuth state. Returns redirect_url or None if not found/expired.

        This is an atomic consume operation - the state is deleted after retrieval
        to ensure one-time use.
        """
        doc_ref = self._client.collection("oauth_states").document(state)

        async def _get() -> DocumentSnapshot:
            return await doc_ref.get()

        doc = await asyncio.wait_for(_get(), timeout=self._timeout)

        if not doc.exists:
            return None

        data = doc.to_dict()
        if data is None:
            return None

        redirect_url = data.get("redirect_url")
        created_at = data.get("created_at")

        if not redirect_url or not created_at:
            return None

        # Check if state is expired
        if datetime.now(UTC) - created_at > OAUTH_STATE_TTL:
            # Clean up expired state
            await asyncio.wait_for(doc_ref.delete(), timeout=self._timeout)
            return None

        # Delete the state (one-time use)
        await asyncio.wait_for(doc_ref.delete(), timeout=self._timeout)

        return redirect_url

    async def cleanup_expired_oauth_states(self) -> int:
        """Clean up expired OAuth states. Returns count of deleted states."""
        cutoff = datetime.now(UTC) - OAUTH_STATE_TTL

        async def _query() -> AsyncQuery:
            return (
                self._client.collection("oauth_states")
                .where("created_at", "<", cutoff)
                .limit(100)  # Batch size to avoid timeout
            )

        query = await asyncio.wait_for(_query(), timeout=self._timeout)
        expired_docs = await asyncio.wait_for(query.get(), timeout=self._timeout)

        count = 0
        for doc in expired_docs:
            await asyncio.wait_for(doc.reference.delete(), timeout=self._timeout)
            count += 1

        return count

    # =========================================================================
    # User Credentials Management
    # =========================================================================

    async def store_user_credentials(
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
        existing_doc = await asyncio.wait_for(doc_ref.get(), timeout=self._timeout)
        created_at = now
        if existing_doc.exists:
            existing_data = existing_doc.to_dict()
            if existing_data is not None:
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

        await asyncio.wait_for(doc_ref.set(data), timeout=self._timeout)

        return UserCredentials(
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            service_account_email=service_account_email,
            created_at=created_at,
            updated_at=now,
        )

    async def get_user_credentials(self, email: str) -> UserCredentials | None:
        """Get user credentials by email."""
        doc_id = self._email_to_doc_id(email)
        doc_ref = self._client.collection("users").document(doc_id)
        doc = await asyncio.wait_for(doc_ref.get(), timeout=self._timeout)

        if not doc.exists:
            return None

        data = doc.to_dict()
        if data is None:
            return None

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

    async def update_service_account_email(self, email: str, service_account_email: str) -> None:
        """Update the service account email for a user.

        Uses set with merge=True to handle both new and existing users.
        """
        doc_id = self._email_to_doc_id(email)
        doc_ref = self._client.collection("users").document(doc_id)

        now = datetime.now(UTC)
        await asyncio.wait_for(
            doc_ref.set(
                {
                    "email": email,
                    "service_account_email": service_account_email,
                    "updated_at": now,
                },
                merge=True,
            ),
            timeout=self._timeout,
        )

    async def list_users_with_service_accounts(self) -> list[dict]:
        """List all users who have service accounts.

        Returns a list of dicts with email and service_account_email.
        Only includes users who have a service account assigned.
        """
        users_ref = self._client.collection("users")

        async def _query() -> list[DocumentSnapshot]:
            query = users_ref.where("service_account_email", "!=", None)
            return await query.get()

        docs = await asyncio.wait_for(_query(), timeout=self._timeout)

        result = []
        for doc in docs:
            data = doc.to_dict()
            if data and data.get("service_account_email"):
                result.append(
                    {
                        "email": data.get("email", ""),
                        "service_account_email": data.get("service_account_email"),
                    }
                )

        # Sort by email for consistent ordering
        result.sort(key=lambda x: x["email"])
        return result


def get_database(request: Request) -> Database:
    """FastAPI dependency to get the database instance.

    The database is stored in app.state during application lifespan.

    Usage:
        @router.get("/example")
        async def example(db: Database = Depends(get_database)):
            ...
    """
    return request.app.state.database
