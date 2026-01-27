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

from extrasheet.credentials import CredentialsManager
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
        # Default authentication (recommended)
        >>> client = SheetsClient()
        >>> client.pull("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "./output")

        # With explicit access token
        >>> client = SheetsClient(access_token="ya29...")
        >>> client.pull("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "./output")
    """

    API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

    def __init__(
        self,
        access_token: str | None = None,
        *,
        timeout: int = 60,
    ) -> None:
        """Initialize the client.

        Args:
            access_token: OAuth2 access token with sheets.readonly scope.
                If provided, this token is used directly without any credential management.
            timeout: Request timeout in seconds.

        Note:
            If access_token is not provided, authentication is handled automatically
            via environment variables, gateway.json, or the ExtraSuite OAuth flow.
        """
        self._access_token = access_token
        self._credentials_manager: CredentialsManager | None = None
        self.timeout = timeout
        self._ssl_context = self._create_ssl_context()

    @property
    def access_token(self) -> str:
        """Get a valid access token.

        Returns the configured token, or obtains one from the CredentialsManager.
        """
        if self._access_token:
            return self._access_token

        if self._credentials_manager is None:
            self._credentials_manager = CredentialsManager()

        return self._credentials_manager.get_token().access_token

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
        max_rows: int | None = None,
    ) -> tuple[Spreadsheet, dict[int, dict[str, Any]] | None]:
        """Fetch a spreadsheet from the Google Sheets API.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            include_grid_data: Whether to include cell data
            ranges: Optional list of ranges to fetch (e.g., ["Sheet1!A1:D10"])
                   If not specified, fetches all data.
            max_rows: Optional maximum number of rows to fetch per sheet.
                     If specified, only the first max_rows rows are fetched.

        Returns:
            Tuple of (Spreadsheet object, truncation_info dict or None).
            truncation_info maps sheetId -> {"totalRows": int, "fetchedRows": int}
            for sheets that were truncated.
        """
        truncation_info: dict[int, dict[str, Any]] | None = None

        # If max_rows is specified and no explicit ranges, we need to:
        # 1. First fetch metadata only to get sheet names and row counts
        # 2. Build limited ranges for each sheet
        # 3. Fetch with those ranges
        if max_rows is not None and ranges is None and include_grid_data:
            # Step 1: Fetch metadata only
            metadata_url = f"{self.API_BASE}/{spreadsheet_id}"
            metadata = self._make_request(metadata_url)

            # Step 2: Build limited ranges and track truncation
            limited_ranges: list[str] = []
            truncation_info = {}

            for sheet in metadata.get("sheets", []):
                props = sheet.get("properties", {})
                title = props.get("title", "Sheet1")
                sheet_id = props.get("sheetId", 0)
                grid_props = props.get("gridProperties", {})
                row_count = grid_props.get("rowCount", 0)
                col_count = grid_props.get("columnCount", 26)

                # Escape sheet title for range notation (single quotes if needed)
                escaped_title = self._escape_sheet_title(title)

                # Calculate how many rows to fetch
                rows_to_fetch = min(max_rows, row_count)

                # Track truncation if we're limiting
                if row_count > max_rows:
                    truncation_info[sheet_id] = {
                        "totalRows": row_count,
                        "fetchedRows": max_rows,
                        "truncated": True,
                    }

                # Build range: SheetName!A1:LastCol{rows_to_fetch}
                # Use column count to determine last column
                last_col = self._column_index_to_letter(col_count - 1)
                range_str = f"{escaped_title}!A1:{last_col}{rows_to_fetch}"
                limited_ranges.append(range_str)

            # Step 3: Fetch with limited ranges
            ranges = limited_ranges

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

        return self._make_request(url), truncation_info

    def _escape_sheet_title(self, title: str) -> str:
        """Escape sheet title for use in A1 notation ranges.

        Sheet names containing spaces, special characters, or starting with
        digits need to be wrapped in single quotes.
        """
        # If title contains special chars or spaces, wrap in single quotes
        # and escape any existing single quotes
        needs_quoting = (
            " " in title
            or "'" in title
            or "!" in title
            or ":" in title
            or title[0:1].isdigit()
        )
        if needs_quoting:
            escaped = title.replace("'", "''")
            return f"'{escaped}'"
        return title

    def _column_index_to_letter(self, index: int) -> str:
        """Convert a 0-based column index to Excel-style letter(s).

        Examples: 0 -> A, 25 -> Z, 26 -> AA, 27 -> AB
        """
        result = ""
        while True:
            result = chr(ord("A") + (index % 26)) + result
            index = index // 26 - 1
            if index < 0:
                break
        return result

    def pull(
        self,
        spreadsheet_id: str,
        output_path: str | Path,
        *,
        ranges: list[str] | None = None,
        save_raw: bool = False,
        max_rows: int | None = None,
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
            max_rows: Optional maximum number of rows to fetch per sheet.
                     If specified, only the first max_rows rows are fetched,
                     and truncation info is included in spreadsheet.json.

        Returns:
            List of paths to written files

        Example:
            >>> client = SheetsClient(access_token="ya29...")
            >>> files = client.pull(
            ...     "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            ...     "./output",
            ...     max_rows=500
            ... )
            >>> print(f"Wrote {len(files)} files")
        """
        # Fetch spreadsheet data
        spreadsheet, truncation_info = self.get_spreadsheet(
            spreadsheet_id,
            include_grid_data=True,
            ranges=ranges,
            max_rows=max_rows,
        )

        # Transform to file representation
        transformer = SpreadsheetTransformer(
            spreadsheet, truncation_info=truncation_info
        )
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
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """Pull a spreadsheet and return as dictionary (without writing to disk).

        Useful for testing or when you want to manipulate the representation
        before writing.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            ranges: Optional list of ranges to fetch
            max_rows: Optional maximum number of rows to fetch per sheet

        Returns:
            Dictionary mapping file paths to content
        """
        spreadsheet, truncation_info = self.get_spreadsheet(
            spreadsheet_id,
            include_grid_data=True,
            ranges=ranges,
            max_rows=max_rows,
        )

        transformer = SpreadsheetTransformer(
            spreadsheet, truncation_info=truncation_info
        )
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
