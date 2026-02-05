"""Transport layer for Google Forms API operations."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import certifi
import httpx

from extraform.exceptions import APIError, AuthenticationError, NotFoundError


class FormTransport(ABC):
    """Abstract transport for Google Forms API operations."""

    @abstractmethod
    async def get_form(self, form_id: str) -> dict[str, Any]:
        """Fetch complete form structure.

        Args:
            form_id: The Google Form ID.

        Returns:
            The form data as a dictionary.
        """
        pass

    @abstractmethod
    async def get_responses(
        self,
        form_id: str,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch form responses (paginated).

        Args:
            form_id: The Google Form ID.
            page_size: Maximum number of responses per page.
            page_token: Token for fetching the next page.

        Returns:
            The responses data including pagination info.
        """
        pass

    @abstractmethod
    async def batch_update(
        self,
        form_id: str,
        requests: list[dict[str, Any]],
        include_form_in_response: bool = False,
    ) -> dict[str, Any]:
        """Apply batchUpdate requests to form.

        Args:
            form_id: The Google Form ID.
            requests: List of update requests.
            include_form_in_response: Whether to include updated form in response.

        Returns:
            The batchUpdate response.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close transport and cleanup resources."""
        pass


class GoogleFormsTransport(FormTransport):
    """Production transport using Google Forms API."""

    BASE_URL = "https://forms.googleapis.com/v1/forms"

    def __init__(self, access_token: str) -> None:
        """Initialize the transport with an access token.

        Args:
            access_token: OAuth2 access token for Google Forms API.
        """
        self._access_token = access_token
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"},
            verify=certifi.where(),
            timeout=30.0,
        )

    def _check_response(self, response: httpx.Response, form_id: str) -> None:
        """Check HTTP response and raise appropriate exceptions.

        Args:
            response: The HTTP response.
            form_id: The form ID for error messages.

        Raises:
            AuthenticationError: On 401/403 responses.
            NotFoundError: On 404 responses.
            APIError: On other error responses.
        """
        if response.status_code == 200:
            return

        if response.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed for form {form_id}. "
                "Please run 'extraform login' or check permissions."
            )

        if response.status_code == 404:
            raise NotFoundError(form_id)

        # Try to extract error message from response
        try:
            error_data = response.json()
            message = error_data.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text

        raise APIError(response.status_code, message)

    async def get_form(self, form_id: str) -> dict[str, Any]:
        """GET /v1/forms/{formId}"""
        response = await self._client.get(f"{self.BASE_URL}/{form_id}")
        self._check_response(response, form_id)
        return response.json()  # type: ignore[no-any-return]

    async def get_responses(
        self,
        form_id: str,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/forms/{formId}/responses"""
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token

        response = await self._client.get(
            f"{self.BASE_URL}/{form_id}/responses",
            params=params,
        )
        self._check_response(response, form_id)
        return response.json()  # type: ignore[no-any-return]

    async def batch_update(
        self,
        form_id: str,
        requests: list[dict[str, Any]],
        include_form_in_response: bool = False,
    ) -> dict[str, Any]:
        """POST /v1/forms/{formId}:batchUpdate"""
        body: dict[str, Any] = {"requests": requests}
        if include_form_in_response:
            body["includeFormInResponse"] = True

        response = await self._client.post(
            f"{self.BASE_URL}/{form_id}:batchUpdate",
            json=body,
        )
        self._check_response(response, form_id)
        return response.json()  # type: ignore[no-any-return]

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


class LocalFileTransport(FormTransport):
    """Testing transport using local golden files."""

    def __init__(self, golden_dir: Path) -> None:
        """Initialize the transport with a golden files directory.

        Args:
            golden_dir: Directory containing golden test files.
        """
        self._golden_dir = golden_dir

    async def get_form(self, form_id: str) -> dict[str, Any]:
        """Read form data from local golden file."""
        form_file = self._golden_dir / form_id / "form.json"
        if not form_file.exists():
            raise NotFoundError(form_id, f"Golden file not found: {form_file}")
        return json.loads(form_file.read_text())  # type: ignore[no-any-return]

    async def get_responses(
        self,
        form_id: str,
        page_size: int = 100,  # noqa: ARG002
        page_token: str | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Read responses from local golden file."""
        resp_file = self._golden_dir / form_id / "responses.json"
        if resp_file.exists():
            return json.loads(resp_file.read_text())  # type: ignore[no-any-return]
        return {"responses": []}

    async def batch_update(
        self,
        form_id: str,  # noqa: ARG002
        requests: list[dict[str, Any]],
        include_form_in_response: bool = False,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Return mock response for testing."""
        return {"replies": [{} for _ in requests]}

    async def close(self) -> None:
        """No cleanup needed for local file transport."""
        pass
