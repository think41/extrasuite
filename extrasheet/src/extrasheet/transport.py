"""Transport layer for fetching spreadsheet data.

Defines the Transport protocol and implementations:
- GoogleSheetsTransport: Production transport using Google Sheets API
- LocalFileTransport: Test transport reading from local golden files
"""

from __future__ import annotations

import json
import ssl
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import Any

import certifi
import httpx

# API constants
API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DEFAULT_TIMEOUT = 60


class TransportError(Exception):
    """Base exception for transport errors."""


class AuthenticationError(TransportError):
    """Raised when authentication fails (401/403)."""


class NotFoundError(TransportError):
    """Raised when spreadsheet is not found (404)."""


class APIError(TransportError):
    """Raised when the API returns an error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SpreadsheetMetadata:
    """Metadata about a spreadsheet, including sheet information.

    Used to compute ranges for the data fetch.
    """

    spreadsheet_id: str
    title: str
    sheets: tuple[SheetInfo, ...]
    raw: dict[str, Any]  # Original API response for saving to .raw/


@dataclass(frozen=True)
class SheetInfo:
    """Information about a single sheet within a spreadsheet."""

    sheet_id: int
    title: str
    row_count: int
    column_count: int


@dataclass(frozen=True)
class SpreadsheetData:
    """Complete spreadsheet data including all sheets."""

    spreadsheet_id: str
    data: dict[str, Any]  # Full API response with grid data (Spreadsheet TypedDict)
    truncation_info: dict[int, TruncationInfo]  # sheetId -> truncation info


@dataclass(frozen=True)
class TruncationInfo:
    """Information about row truncation for a sheet."""

    total_rows: int
    fetched_rows: int


class Transport(ABC):
    """Abstract base class for spreadsheet data transport.

    Implementations must provide methods to fetch metadata and data
    from a spreadsheet source (Google API, local files, etc.).
    """

    @abstractmethod
    async def get_metadata(self, spreadsheet_id: str) -> SpreadsheetMetadata:
        """Fetch spreadsheet metadata without cell data.

        Args:
            spreadsheet_id: The spreadsheet identifier

        Returns:
            SpreadsheetMetadata with sheet information
        """
        ...

    @abstractmethod
    async def get_data(
        self,
        spreadsheet_id: str,
        metadata: SpreadsheetMetadata,
        max_rows: int,
    ) -> SpreadsheetData:
        """Fetch spreadsheet data with cell contents.

        Args:
            spreadsheet_id: The spreadsheet identifier
            metadata: Previously fetched metadata
            max_rows: Maximum rows to fetch per sheet

        Returns:
            SpreadsheetData with full cell contents
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        ...


class GoogleSheetsTransport(Transport):
    """Production transport that fetches data from Google Sheets API.

    Handles authentication, SSL, and HTTP communication.
    """

    def __init__(
        self,
        access_token: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the transport.

        Args:
            access_token: OAuth2 access token with sheets.readonly scope
            timeout: Request timeout in seconds
        """
        self._access_token = access_token
        self._timeout = timeout
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=timeout,
            verify=ssl_context,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    async def get_metadata(self, spreadsheet_id: str) -> SpreadsheetMetadata:
        """Fetch spreadsheet metadata from Google Sheets API."""
        url = f"{API_BASE}/{spreadsheet_id}"
        response = await self._request(url)

        sheets: list[SheetInfo] = []
        for sheet in response.get("sheets", []):
            props = sheet.get("properties", {})
            grid_props = props.get("gridProperties", {})
            sheets.append(
                SheetInfo(
                    sheet_id=props.get("sheetId", 0),
                    title=props.get("title", "Sheet1"),
                    row_count=grid_props.get("rowCount", 0),
                    column_count=grid_props.get("columnCount", 26),
                )
            )

        return SpreadsheetMetadata(
            spreadsheet_id=response.get("spreadsheetId", spreadsheet_id),
            title=response.get("properties", {}).get("title", ""),
            sheets=tuple(sheets),
            raw=response,
        )

    async def get_data(
        self,
        spreadsheet_id: str,
        metadata: SpreadsheetMetadata,
        max_rows: int,
    ) -> SpreadsheetData:
        """Fetch spreadsheet data with cell contents from Google Sheets API."""
        # Build ranges for each sheet, limited by max_rows
        ranges: list[str] = []
        truncation_info: dict[int, TruncationInfo] = {}

        for sheet in metadata.sheets:
            escaped_title = _escape_sheet_title(sheet.title)
            rows_to_fetch = min(max_rows, sheet.row_count)
            last_col = _column_index_to_letter(sheet.column_count - 1)
            ranges.append(f"{escaped_title}!A1:{last_col}{rows_to_fetch}")

            if sheet.row_count > max_rows:
                truncation_info[sheet.sheet_id] = TruncationInfo(
                    total_rows=sheet.row_count,
                    fetched_rows=max_rows,
                )

        # Build URL with ranges
        url = f"{API_BASE}/{spreadsheet_id}?includeGridData=true"
        for r in ranges:
            url += f"&ranges={urllib.parse.quote(r, safe='')}"

        response = await self._request(url)

        return SpreadsheetData(
            spreadsheet_id=spreadsheet_id,
            data=response,
            truncation_info=truncation_info,
        )

    async def _request(self, url: str) -> dict[str, Any]:
        """Make an authenticated GET request."""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                raise AuthenticationError("Invalid or expired access token") from e
            if status == 403:
                raise AuthenticationError(
                    "Access denied. Check your scopes and permissions."
                ) from e
            if status == 404:
                raise NotFoundError(
                    "Spreadsheet not found. Check the ID and sharing permissions."
                ) from e
            body = e.response.text
            raise APIError(f"API error ({status}): {body}", status_code=status) from e
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


class LocalFileTransport(Transport):
    """Test transport that reads from local golden files.

    Expected directory structure:
        golden_dir/
            <spreadsheet_id>/
                metadata.json
                data.json
    """

    def __init__(self, golden_dir: Path) -> None:
        """Initialize the transport.

        Args:
            golden_dir: Directory containing golden test files
        """
        self._golden_dir = golden_dir

    async def get_metadata(self, spreadsheet_id: str) -> SpreadsheetMetadata:
        """Read metadata from local file."""
        path = self._golden_dir / spreadsheet_id / "metadata.json"
        response = json.loads(path.read_text())

        sheets: list[SheetInfo] = []
        for sheet in response.get("sheets", []):
            props = sheet.get("properties", {})
            grid_props = props.get("gridProperties", {})
            sheets.append(
                SheetInfo(
                    sheet_id=props.get("sheetId", 0),
                    title=props.get("title", "Sheet1"),
                    row_count=grid_props.get("rowCount", 0),
                    column_count=grid_props.get("columnCount", 26),
                )
            )

        return SpreadsheetMetadata(
            spreadsheet_id=response.get("spreadsheetId", spreadsheet_id),
            title=response.get("properties", {}).get("title", ""),
            sheets=tuple(sheets),
            raw=response,
        )

    async def get_data(
        self,
        spreadsheet_id: str,
        metadata: SpreadsheetMetadata,
        max_rows: int,
    ) -> SpreadsheetData:
        """Read data from local file."""
        path = self._golden_dir / spreadsheet_id / "data.json"
        response = json.loads(path.read_text())

        # Compute truncation info based on metadata and max_rows
        truncation_info: dict[int, TruncationInfo] = {}
        for sheet in metadata.sheets:
            if sheet.row_count > max_rows:
                truncation_info[sheet.sheet_id] = TruncationInfo(
                    total_rows=sheet.row_count,
                    fetched_rows=max_rows,
                )

        return SpreadsheetData(
            spreadsheet_id=spreadsheet_id,
            data=response,
            truncation_info=truncation_info,
        )

    async def close(self) -> None:
        """No-op for local file transport."""
        pass


def _escape_sheet_title(title: str) -> str:
    """Escape sheet title for use in A1 notation ranges.

    Sheet names containing spaces, special characters, or starting with
    digits need to be wrapped in single quotes.
    """
    needs_quoting = (
        " " in title
        or "'" in title
        or "!" in title
        or ":" in title
        or (len(title) > 0 and title[0].isdigit())
    )
    if needs_quoting:
        escaped = title.replace("'", "''")
        return f"'{escaped}'"
    return title


def _column_index_to_letter(index: int) -> str:
    """Convert a 0-based column index to Excel-style letter(s).

    Examples: 0 -> A, 25 -> Z, 26 -> AA, 27 -> AB
    """
    result = ""
    idx = index
    while True:
        result = chr(ord("A") + (idx % 26)) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result
