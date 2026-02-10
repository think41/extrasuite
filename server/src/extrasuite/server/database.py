"""Database layer using Google Cloud Firestore (async).

Stores three types of data:
1. Users: email -> service account mapping
2. OAuth States: state_token -> redirect_url (for OAuth flow)
3. Auth Codes: auth_code -> service_account_email (for secure token delivery)

Collections structure:
- users: Document ID = email (with "/" replaced by "__")
  - email: User's email address
  - service_account_email: Associated service account
  - updated_at: Last update timestamp

- oauth_states: Document ID = state_token
  - redirect_url: Redirect URL for CLI callback
  - expires_at: Firestore TTL field (OAUTH_STATE_TTL after creation)

- auth_codes: Document ID = auth_code
  - service_account_email: Associated service account
  - expires_at: Firestore TTL field (AUTH_CODE_TTL after creation)

Note: Sessions are handled via starlette's signed cookies (stateless).
The cookie stores the user email, which is validated against the users collection.

Note: We do NOT store OAuth access tokens. Tokens are generated on-demand when
the auth code is exchanged. We only store the service account email needed to
generate the token.

TTL cleanup: Configure Firestore TTL policies on the `expires_at` field for
`oauth_states` and `auth_codes` collections to automatically delete expired documents.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import Request
from google.cloud.firestore_v1 import AsyncClient, AsyncQuery, DocumentSnapshot
from google.cloud.firestore_v1.async_transaction import async_transactional

# OAuth state TTL (10 minutes)
OAUTH_STATE_TTL = timedelta(minutes=10)

# Auth code TTL (120 seconds for security)
AUTH_CODE_TTL = timedelta(seconds=120)

# Default timeout for database operations (seconds)
DEFAULT_TIMEOUT = 10.0


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

    async def save_state(
        self,
        state: str,
        redirect_url: str,
        scopes: list[str] | None = None,
        reason: str = "",
        flow_type: str = "",
    ) -> None:
        """Save OAuth state token with redirect URL and optional delegation fields.

        Includes expires_at field for Firestore TTL automatic cleanup.
        """
        expires_at = datetime.now(UTC) + OAUTH_STATE_TTL
        doc_ref = self._client.collection("oauth_states").document(state)

        data: dict[str, object] = {
            "redirect_url": redirect_url,
            "expires_at": expires_at,
        }
        if scopes is not None:
            data["scopes"] = scopes
        if reason:
            data["reason"] = reason
        if flow_type:
            data["flow_type"] = flow_type

        async def _create() -> None:
            await doc_ref.set(data)

        await asyncio.wait_for(_create(), timeout=self._timeout)

    async def retrieve_state(self, state: str) -> dict[str, object] | None:
        """Retrieve AND delete OAuth state. Returns state data dict or None if not found/expired.

        Returns dict with keys: redirect_url, scopes (optional), reason (optional), flow_type (optional).
        Uses a Firestore transaction for atomic get-and-delete to prevent race conditions.
        """
        doc_ref = self._client.collection("oauth_states").document(state)

        @async_transactional
        async def _atomic_retrieve(transaction) -> dict[str, object] | None:
            doc = await doc_ref.get(transaction=transaction)

            if not doc.exists:
                return None

            data = doc.to_dict()
            if data is None:
                return None

            redirect_url = data.get("redirect_url")
            expires_at = data.get("expires_at")

            if not redirect_url or not expires_at:
                transaction.delete(doc_ref)
                return None

            # Check if state is expired
            if datetime.now(UTC) > expires_at:
                transaction.delete(doc_ref)
                return None

            # Delete the state (one-time use)
            transaction.delete(doc_ref)

            result: dict[str, object] = {"redirect_url": redirect_url}
            if "scopes" in data:
                result["scopes"] = data["scopes"]
            if "reason" in data:
                result["reason"] = data["reason"]
            if "flow_type" in data:
                result["flow_type"] = data["flow_type"]
            return result

        transaction = self._client.transaction()
        return await asyncio.wait_for(_atomic_retrieve(transaction), timeout=self._timeout)

    async def cleanup_expired_oauth_states(self) -> int:
        """Clean up expired OAuth states. Returns count of deleted states."""
        now = datetime.now(UTC)

        async def _query() -> AsyncQuery:
            return (
                self._client.collection("oauth_states")
                .where("expires_at", "<", now)
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
    # Auth Code Exchange (for secure token delivery)
    # =========================================================================

    async def save_auth_code(self, auth_code: str, service_account_email: str) -> None:
        """Save auth code with associated service account email.

        Auth codes are single-use and expire after AUTH_CODE_TTL.
        Tokens are NOT stored - they are generated on-demand when the auth code is exchanged.
        Includes expires_at field for Firestore TTL automatic cleanup.
        """
        expires_at = datetime.now(UTC) + AUTH_CODE_TTL
        doc_ref = self._client.collection("auth_codes").document(auth_code)

        async def _create() -> None:
            await doc_ref.set(
                {
                    "service_account_email": service_account_email,
                    "expires_at": expires_at,
                }
            )

        await asyncio.wait_for(_create(), timeout=self._timeout)

    async def retrieve_auth_code(self, auth_code: str) -> str | None:
        """Retrieve AND delete auth code. Returns service_account_email or None if not found/expired.

        Uses a Firestore transaction for atomic get-and-delete to prevent race conditions.
        """
        doc_ref = self._client.collection("auth_codes").document(auth_code)

        @async_transactional
        async def _atomic_retrieve(transaction) -> str | None:
            doc = await doc_ref.get(transaction=transaction)

            if not doc.exists:
                return None

            data = doc.to_dict()
            if data is None:
                return None

            service_account_email = data.get("service_account_email")
            expires_at = data.get("expires_at")

            if not service_account_email or not expires_at:
                transaction.delete(doc_ref)
                return None

            # Check if auth code is expired
            if datetime.now(UTC) > expires_at:
                transaction.delete(doc_ref)
                return None

            # Delete the auth code (one-time use)
            transaction.delete(doc_ref)
            return service_account_email

        transaction = self._client.transaction()
        return await asyncio.wait_for(_atomic_retrieve(transaction), timeout=self._timeout)

    # =========================================================================
    # User -> Service Account Mapping
    # =========================================================================

    async def get_service_account_email(self, email: str) -> str | None:
        """Get service account email for a user.

        Returns the service_account_email if found, None otherwise.
        """
        doc_id = self._email_to_doc_id(email)
        doc_ref = self._client.collection("users").document(doc_id)
        doc = await asyncio.wait_for(doc_ref.get(), timeout=self._timeout)

        if not doc.exists:
            return None

        data = doc.to_dict()
        if data is None:
            return None

        return data.get("service_account_email")

    async def set_service_account_email(self, email: str, service_account_email: str) -> None:
        """Set the service account email for a user."""
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

    # =========================================================================
    # Delegation Auth Codes (for domain-wide delegation token delivery)
    # =========================================================================

    async def save_delegation_auth_code(
        self, auth_code: str, email: str, scopes: list[str], reason: str
    ) -> None:
        """Save delegation auth code with user email and requested scopes.

        Auth codes are single-use and expire after AUTH_CODE_TTL.
        """
        expires_at = datetime.now(UTC) + AUTH_CODE_TTL
        doc_ref = self._client.collection("auth_codes").document(auth_code)

        async def _create() -> None:
            await doc_ref.set(
                {
                    "email": email,
                    "scopes": scopes,
                    "reason": reason,
                    "flow_type": "delegation",
                    "expires_at": expires_at,
                }
            )

        await asyncio.wait_for(_create(), timeout=self._timeout)

    async def retrieve_delegation_auth_code(self, auth_code: str) -> dict[str, object] | None:
        """Retrieve AND delete delegation auth code.

        Returns {email, scopes, reason} or None if not found/expired.
        Uses a Firestore transaction for atomic get-and-delete.
        """
        doc_ref = self._client.collection("auth_codes").document(auth_code)

        @async_transactional
        async def _atomic_retrieve(transaction) -> dict[str, object] | None:
            doc = await doc_ref.get(transaction=transaction)

            if not doc.exists:
                return None

            data = doc.to_dict()
            if data is None:
                return None

            # Only retrieve delegation auth codes
            if data.get("flow_type") != "delegation":
                return None

            expires_at = data.get("expires_at")
            if not expires_at or datetime.now(UTC) > expires_at:
                transaction.delete(doc_ref)
                return None

            # Delete the auth code (one-time use)
            transaction.delete(doc_ref)
            return {
                "email": data.get("email", ""),
                "scopes": data.get("scopes", []),
                "reason": data.get("reason", ""),
            }

        transaction = self._client.transaction()
        return await asyncio.wait_for(_atomic_retrieve(transaction), timeout=self._timeout)

    # =========================================================================
    # Delegation Audit Log
    # =========================================================================

    async def log_delegation_request(self, email: str, scopes: list[str], reason: str) -> None:
        """Log a delegation token request for audit purposes.

        Stored in delegation_logs collection with 30-day TTL for auto-cleanup.
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=30)
        doc_ref = self._client.collection("delegation_logs").document()

        async def _create() -> None:
            await doc_ref.set(
                {
                    "email": email,
                    "scopes": scopes,
                    "reason": reason,
                    "timestamp": now,
                    "expires_at": expires_at,
                }
            )

        await asyncio.wait_for(_create(), timeout=self._timeout)


def get_database(request: Request) -> Database:
    """FastAPI dependency to get the database instance.

    The database is stored in app.state during application lifespan.

    Usage:
        @router.get("/example")
        async def example(db: Database = Depends(get_database)):
            ...
    """
    return request.app.state.database
