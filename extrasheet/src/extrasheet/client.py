"""
SheetsClient - Main API for extrasheet.

Provides high-level methods for pulling Google Sheets to file representation.
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any

from extrasheet.transformer import SpreadsheetTransformer
from extrasheet.writer import FileWriter

if TYPE_CHECKING:
    from pathlib import Path

    from extrasheet.api_types import Spreadsheet


class SheetsClientError(Exception):
    """Base exception for SheetsClient errors."""


class AuthenticationError(SheetsClientError):
    """Raised when authentication fails."""


class APIError(SheetsClientError):
    """Raised when the Google Sheets API returns an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SheetsClient:
    """Client for transforming Google Sheets to file representation.

    This client pulls spreadsheet data from the Google Sheets API and
    transforms it into a file-based representation optimized for LLM agents.

    Example:
        >>> client = SheetsClient(access_token="ya29...")
        >>> client.pull("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "./output")
    """

    API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

    def __init__(
        self,
        access_token: str,
        *,
        timeout: int = 60,
    ) -> None:
        """Initialize the client.

        Args:
            access_token: OAuth2 access token with sheets.readonly scope
            timeout: Request timeout in seconds
        """
        self.access_token = access_token
        self.timeout = timeout
        self._ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create an SSL context with certificate verification."""
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            return ssl.create_default_context()

    def _make_request(self, url: str) -> dict[str, Any]:
        """Make an authenticated request to the Google Sheets API.

        Args:
            url: Full URL to request

        Returns:
            Parsed JSON response

        Raises:
            AuthenticationError: If the token is invalid
            APIError: If the API returns an error
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

        request = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self._ssl_context
            ) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise AuthenticationError("Invalid or expired access token") from e
            elif e.code == 403:
                raise AuthenticationError(
                    "Access denied. Check your scopes and permissions."
                ) from e
            elif e.code == 404:
                raise APIError(
                    "Spreadsheet not found. Check the ID and sharing permissions.",
                    status_code=e.code,
                ) from e
            else:
                error_body = e.read().decode("utf-8") if e.fp else ""
                raise APIError(
                    f"API error ({e.code}): {error_body}", status_code=e.code
                ) from e
        except urllib.error.URLError as e:
            raise SheetsClientError(f"Network error: {e.reason}") from e

    def get_spreadsheet(
        self,
        spreadsheet_id: str,
        *,
        include_grid_data: bool = True,
        ranges: list[str] | None = None,
    ) -> Spreadsheet:
        """Fetch a spreadsheet from the Google Sheets API.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            include_grid_data: Whether to include cell data
            ranges: Optional list of ranges to fetch (e.g., ["Sheet1!A1:D10"])
                   If not specified, fetches all data.

        Returns:
            Spreadsheet object from the API
        """
        # Build URL with parameters
        params: list[str] = []
        if include_grid_data:
            params.append("includeGridData=true")
        if ranges:
            for r in ranges:
                params.append(f"ranges={urllib.parse.quote(r)}")

        url = f"{self.API_BASE}/{spreadsheet_id}"
        if params:
            url += "?" + "&".join(params)

        return self._make_request(url)

    def pull(
        self,
        spreadsheet_id: str,
        output_path: str | Path,
        *,
        ranges: list[str] | None = None,
        save_raw: bool = False,
    ) -> list[Path]:
        """Pull a spreadsheet and write to file representation.

        This is the main entry point for transforming a Google Sheet
        into the extrasheet file format.

        Args:
            spreadsheet_id: The ID of the spreadsheet (from the URL)
            output_path: Directory to write files to
            ranges: Optional list of ranges to fetch. If not specified,
                   fetches the entire spreadsheet.
            save_raw: If True, also saves the raw API response to raw.json

        Returns:
            List of paths to written files

        Example:
            >>> client = SheetsClient(access_token="ya29...")
            >>> files = client.pull(
            ...     "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            ...     "./output"
            ... )
            >>> print(f"Wrote {len(files)} files")
        """
        # Fetch spreadsheet data
        spreadsheet = self.get_spreadsheet(
            spreadsheet_id,
            include_grid_data=True,
            ranges=ranges,
        )

        # Transform to file representation
        transformer = SpreadsheetTransformer(spreadsheet)
        files = transformer.transform()

        # Write to disk
        writer = FileWriter(output_path)
        written = writer.write_all(files)

        # Optionally save raw API response
        if save_raw:
            raw_path = writer.write_json(f"{spreadsheet_id}/raw.json", spreadsheet)
            written.append(raw_path)

        return written

    def pull_to_dict(
        self,
        spreadsheet_id: str,
        *,
        ranges: list[str] | None = None,
    ) -> dict[str, Any]:
        """Pull a spreadsheet and return as dictionary (without writing to disk).

        Useful for testing or when you want to manipulate the representation
        before writing.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            ranges: Optional list of ranges to fetch

        Returns:
            Dictionary mapping file paths to content
        """
        spreadsheet = self.get_spreadsheet(
            spreadsheet_id,
            include_grid_data=True,
            ranges=ranges,
        )

        transformer = SpreadsheetTransformer(spreadsheet)
        return transformer.transform()

    def transform_from_json(
        self,
        json_data: dict[str, Any] | str,
        output_path: str | Path | None = None,
    ) -> dict[str, Any] | list[Path]:
        """Transform a spreadsheet from JSON data (without making API calls).

        Useful for testing or processing cached API responses.

        Args:
            json_data: Spreadsheet JSON data (dict or JSON string)
            output_path: If provided, write files to this path

        Returns:
            If output_path is None: Dictionary of file paths to content
            If output_path is provided: List of written file paths
        """
        if isinstance(json_data, str):
            json_data = json.loads(json_data)

        transformer = SpreadsheetTransformer(json_data)
        files = transformer.transform()

        if output_path is None:
            return files

        writer = FileWriter(output_path)
        return writer.write_all(files)
