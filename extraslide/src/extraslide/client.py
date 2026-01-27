"""Google Slides client with SML abstraction.

Minimal API for the SML workflow:
1. pull() - Fetch presentation as SML and save to file
2. diff() - Dry-run to see what changes would be applied
3. apply() - Apply SML changes to the presentation

String-based variants (_s suffix) are also available for programmatic use.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from extraslide.credentials import CredentialsManager
from extraslide.diff import diff_sml
from extraslide.generator import json_to_sml
from extraslide.parser import parse_sml
from extraslide.requests import generate_requests

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


class SlidesClient:
    """Client for interacting with Google Slides via SML.

    Example (default authentication - recommended):
        client = SlidesClient()
        url = "https://docs.google.com/presentation/d/abc123/edit"

        # Pull presentation to file
        client.pull(url, "presentation.sml")

        # Edit the file externally or programmatically...

        # Preview changes (dry run)
        requests = client.diff("presentation.sml", "presentation_edited.sml")
        for req in requests:
            print(req)

        # Apply changes
        client.apply(url, "presentation.sml", "presentation_edited.sml")

    Example (with explicit access token):
        client = SlidesClient(access_token="ya29...")
        sml = client.pull_s("https://docs.google.com/presentation/d/abc123/edit")
    """

    def __init__(
        self,
        access_token: str | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            access_token: OAuth2 access token with slides scope.
                If provided, this token is used directly without any credential management.

        Note:
            If access_token is not provided, authentication is handled automatically
            via environment variables, gateway.json, or the ExtraSuite OAuth flow.
        """
        self._access_token = access_token
        self._credentials_manager: CredentialsManager | None = None

    def _get_token(self) -> str:
        """Get a valid access token.

        Returns the configured token, or obtains one from the CredentialsManager.
        """
        if self._access_token:
            return self._access_token

        if self._credentials_manager is None:
            self._credentials_manager = CredentialsManager()

        return self._credentials_manager.get_token().access_token

    # -------------------------------------------------------------------------
    # File-based API (primary interface)
    # -------------------------------------------------------------------------

    def pull(self, url: str, path: str | Path) -> None:
        """Fetch a presentation and save it as SML to a file.

        Args:
            url: Google Slides URL (e.g., https://docs.google.com/presentation/d/ID/edit)
            path: File path to save the SML.

        Raises:
            ValueError: If URL format is invalid.
            urllib.error.HTTPError: If API request fails.
        """
        sml = self.pull_s(url)
        Path(path).write_text(sml, encoding="utf-8")

    def diff(
        self, original_path: str | Path, edited_path: str | Path
    ) -> list[dict[str, Any]]:
        """Preview changes between two SML files (dry run).

        Diffs the original and edited SML files and returns the batchUpdate
        requests that would be sent to the API.

        Args:
            original_path: Path to the original SML file.
            edited_path: Path to the edited SML file.

        Returns:
            List of Google Slides API request objects.
        """
        original_sml = Path(original_path).read_text(encoding="utf-8")
        edited_sml = Path(edited_path).read_text(encoding="utf-8")
        return self.diff_s(original_sml, edited_sml)

    def apply(
        self, url: str, original_path: str | Path, edited_path: str | Path
    ) -> dict[str, Any]:
        """Apply SML changes from files to the presentation.

        Diffs the original and edited SML files, generates batchUpdate requests,
        and sends them to the Google Slides API.

        Args:
            url: Google Slides URL.
            original_path: Path to the original SML file.
            edited_path: Path to the edited SML file.

        Returns:
            The API response from batchUpdate.

        Raises:
            ValueError: If no changes detected or URL is invalid.
            urllib.error.HTTPError: If API request fails.
        """
        original_sml = Path(original_path).read_text(encoding="utf-8")
        edited_sml = Path(edited_path).read_text(encoding="utf-8")
        return self.apply_s(url, original_sml, edited_sml)

    # -------------------------------------------------------------------------
    # String-based API (for programmatic use)
    # -------------------------------------------------------------------------

    def pull_s(self, url: str) -> str:
        """Fetch a presentation and return it as SML string.

        Args:
            url: Google Slides URL (e.g., https://docs.google.com/presentation/d/ID/edit)

        Returns:
            SML string representation of the presentation.

        Raises:
            ValueError: If URL format is invalid.
            urllib.error.HTTPError: If API request fails.
        """
        presentation_json = self._fetch_json(url)
        return json_to_sml(presentation_json)

    def diff_s(self, original_sml: str, edited_sml: str) -> list[dict[str, Any]]:
        """Preview changes between two SML strings (dry run).

        Diffs the original and edited SML and returns the batchUpdate
        requests that would be sent to the API.

        Args:
            original_sml: The original SML string.
            edited_sml: The edited SML string.

        Returns:
            List of Google Slides API request objects.
        """
        original = parse_sml(original_sml)
        edited = parse_sml(edited_sml)
        diff = diff_sml(original, edited)
        return generate_requests(diff)

    def apply_s(self, url: str, original_sml: str, edited_sml: str) -> dict[str, Any]:
        """Apply SML changes to the presentation.

        Diffs the original and edited SML, generates batchUpdate requests,
        and sends them to the Google Slides API.

        Args:
            url: Google Slides URL.
            original_sml: The original SML string.
            edited_sml: The edited SML string with changes.

        Returns:
            The API response from batchUpdate.

        Raises:
            ValueError: If no changes detected or URL is invalid.
            urllib.error.HTTPError: If API request fails.
        """
        requests = self.diff_s(original_sml, edited_sml)

        if not requests:
            return {"replies": [], "message": "No changes detected"}

        presentation_id = self._extract_presentation_id(url)
        return self._batch_update(presentation_id, requests)

    def thumbnail(
        self, url: str, page_id: str, output_path: str | Path | None = None
    ) -> dict[str, Any]:
        """Get a thumbnail image for a specific slide.

        WARNING: This is an expensive operation that counts against API quotas.
        Only use when you need to see how a slide actually looks, such as when
        debugging formatting issues.

        Args:
            url: Google Slides URL.
            page_id: The objectId of the slide/page (from SML id attribute).
            output_path: Optional path to save the image. If not provided,
                returns only the metadata without downloading.

        Returns:
            Dict containing:
                - content_url: Temporary URL of the thumbnail (expires quickly)
                - width: Thumbnail width in pixels
                - height: Thumbnail height in pixels
                - saved_to: Local path if output_path was provided

        Raises:
            urllib.error.HTTPError: If API request fails.

        Example:
            client = SlidesClient()
            url = "https://docs.google.com/presentation/d/abc123/edit"

            # Get metadata only
            info = client.thumbnail(url, "g12345678")
            print(f"Thumbnail: {info['width']}x{info['height']}")

            # Download to file
            info = client.thumbnail(url, "g12345678", "slide_preview.png")
            print(f"Saved to: {info['saved_to']}")
        """
        presentation_id = self._extract_presentation_id(url)
        token = self._get_token()

        api_url = (
            f"https://slides.googleapis.com/v1/presentations/"
            f"{presentation_id}/pages/{page_id}/thumbnail"
        )

        req = urllib.request.Request(
            api_url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
            data = json.loads(response.read().decode("utf-8"))

        result: dict[str, Any] = {
            "content_url": data.get("contentUrl"),
            "width": data.get("width"),
            "height": data.get("height"),
        }

        # Download the image if output_path provided
        if output_path and result["content_url"]:
            img_req = urllib.request.Request(str(result["content_url"]))
            with urllib.request.urlopen(
                img_req, timeout=60, context=SSL_CONTEXT
            ) as img_response:
                img_data = img_response.read()

            output_file = Path(output_path)
            output_file.write_bytes(img_data)
            result["saved_to"] = str(output_file.resolve())

        return result

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _fetch_json(self, url: str) -> dict[str, Any]:
        """Fetch the raw JSON representation of a presentation from the API."""
        presentation_id = self._extract_presentation_id(url)
        token = self._get_token()

        api_url = f"https://slides.googleapis.com/v1/presentations/{presentation_id}"
        req = urllib.request.Request(
            api_url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
            return dict(json.loads(response.read().decode("utf-8")))

    def _batch_update(
        self, presentation_id: str, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Send batchUpdate request to the Google Slides API."""
        token = self._get_token()

        api_url = f"https://slides.googleapis.com/v1/presentations/{presentation_id}:batchUpdate"
        body = json.dumps({"requests": requests}).encode("utf-8")

        req = urllib.request.Request(
            api_url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
            return dict(json.loads(response.read().decode("utf-8")))

    def _extract_presentation_id(self, url: str) -> str:
        """Extract presentation ID from Google Slides URL.

        Supports URLs like:
        - https://docs.google.com/presentation/d/PRESENTATION_ID/edit
        - https://docs.google.com/presentation/d/PRESENTATION_ID/edit#slide=id.xxx
        - https://docs.google.com/presentation/d/PRESENTATION_ID/

        Args:
            url: Google Slides URL

        Returns:
            The presentation ID

        Raises:
            ValueError: If URL format is invalid
        """
        pattern = r"/presentation/d/([a-zA-Z0-9_-]+)"
        match = re.search(pattern, url)
        if not match:
            raise ValueError(f"Invalid Google Slides URL: {url}")
        return match.group(1)
