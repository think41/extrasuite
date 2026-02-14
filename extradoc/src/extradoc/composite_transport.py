"""Composite transport for recording mode - compares real API with mock.

This module provides a composite transport that calls both the real Google Docs
API and the mock API in parallel, compares their responses, and logs any
mismatches for analysis.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.mock.exceptions import MockAPIError
from extradoc.transport import APIError, DocumentData, Transport


class MismatchLogger:
    """Logs mismatches between real and mock API responses."""

    def __init__(self, log_dir: Path) -> None:
        """Initialize the mismatch logger.

        Args:
            log_dir: Directory to save mismatch logs
        """
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.mismatch_count = 0

    def log_get_mismatch(
        self,
        document_id: str,
        real_response: dict[str, Any],
        mock_response: dict[str, Any],
    ) -> None:
        """Log a mismatch in get_document responses.

        Args:
            document_id: The document ID
            real_response: Response from real API
            mock_response: Response from mock API
        """
        self.mismatch_count += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mismatch_dir = self.log_dir / f"get_mismatch_{timestamp}_{self.mismatch_count}"
        mismatch_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata = {
            "timestamp": timestamp,
            "operation": "get_document",
            "document_id": document_id,
        }
        (mismatch_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # Save real response
        (mismatch_dir / "real_response.json").write_text(
            json.dumps(real_response, indent=2), encoding="utf-8"
        )

        # Save mock response
        (mismatch_dir / "mock_response.json").write_text(
            json.dumps(mock_response, indent=2), encoding="utf-8"
        )

        print(f"⚠️  GET mismatch logged to: {mismatch_dir}")

    def log_batch_update_mismatch(
        self,
        document_id: str,
        requests: list[dict[str, Any]],
        input_document: dict[str, Any],
        real_response: dict[str, Any],
        mock_response: dict[str, Any],
        real_document_after: dict[str, Any],
        mock_document_after: dict[str, Any],
    ) -> None:
        """Log a mismatch in batch_update responses.

        Args:
            document_id: The document ID
            requests: The batchUpdate requests that were sent
            input_document: Document state before the update
            real_response: Response from real API
            mock_response: Response from mock API
            real_document_after: Document state after real API update
            mock_document_after: Document state after mock API update
        """
        self.mismatch_count += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mismatch_dir = (
            self.log_dir / f"batch_update_mismatch_{timestamp}_{self.mismatch_count}"
        )
        mismatch_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata = {
            "timestamp": timestamp,
            "operation": "batch_update",
            "document_id": document_id,
            "num_requests": len(requests),
        }
        (mismatch_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # Save input document
        (mismatch_dir / "input_document.json").write_text(
            json.dumps(input_document, indent=2), encoding="utf-8"
        )

        # Save requests
        (mismatch_dir / "requests.json").write_text(
            json.dumps({"requests": requests}, indent=2), encoding="utf-8"
        )

        # Save real API results
        (mismatch_dir / "real_response.json").write_text(
            json.dumps(real_response, indent=2), encoding="utf-8"
        )
        (mismatch_dir / "real_document_after.json").write_text(
            json.dumps(real_document_after, indent=2), encoding="utf-8"
        )

        # Save mock API results
        (mismatch_dir / "mock_response.json").write_text(
            json.dumps(mock_response, indent=2), encoding="utf-8"
        )
        (mismatch_dir / "mock_document_after.json").write_text(
            json.dumps(mock_document_after, indent=2), encoding="utf-8"
        )

        print(f"⚠️  BATCH_UPDATE mismatch logged to: {mismatch_dir}")

    def get_summary(self) -> str:
        """Get a summary of logged mismatches.

        Returns:
            Summary string
        """
        if self.mismatch_count == 0:
            return "✅ No mismatches detected"
        return f"⚠️  {self.mismatch_count} mismatch(es) logged to {self.log_dir}"


class MockTransport(Transport):
    """Transport that wraps MockGoogleDocsAPI.

    This adapter makes MockGoogleDocsAPI compatible with the Transport interface.
    """

    def __init__(self, initial_document: dict[str, Any]) -> None:
        """Initialize the mock transport.

        Args:
            initial_document: Initial document state for the mock API
        """
        self.mock_api = MockGoogleDocsAPI(initial_document)
        self.document_id = initial_document.get("documentId", "mock_doc")

    async def get_document(self, document_id: str) -> DocumentData:
        """Get document from mock API.

        Args:
            document_id: Document ID (ignored, uses mock state)

        Returns:
            DocumentData with mock state
        """
        response = self.mock_api.get()
        return DocumentData(
            document_id=response.get("documentId", document_id),
            title=response.get("title", ""),
            raw=response,
        )

    async def batch_update(
        self,
        document_id: str,  # noqa: ARG002
        requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply batch update to mock API.

        Args:
            document_id: Document ID (ignored)
            requests: Update requests

        Returns:
            Mock API response
        """
        return self.mock_api.batch_update(requests)

    async def list_comments(self, file_id: str) -> list[dict[str, Any]]:  # noqa: ARG002
        """Mock comments - returns empty list.

        Args:
            file_id: File ID

        Returns:
            Empty list
        """
        return []

    async def create_reply(
        self,
        file_id: str,  # noqa: ARG002
        comment_id: str,  # noqa: ARG002
        content: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Mock create reply.

        Args:
            file_id: File ID
            comment_id: Comment ID
            content: Reply content
            action: Optional action

        Returns:
            Mock reply
        """
        result: dict[str, Any] = {
            "id": "mock_reply_id",
            "content": content,
        }
        if action:
            result["action"] = action
        return result

    async def close(self) -> None:
        """No-op for mock transport."""
        pass


class CompositeTransport(Transport):
    """Composite transport that calls both real and mock APIs.

    This transport calls both the real Google Docs API and a mock API,
    compares their responses, and logs any mismatches. It always returns
    the real API's response.
    """

    def __init__(
        self,
        real_transport: Transport,
        mismatch_logger: MismatchLogger | None = None,
    ) -> None:
        """Initialize the composite transport.

        Args:
            real_transport: The real Google Docs transport
            mismatch_logger: Optional logger for mismatches (created if not provided)
        """
        self.real_transport = real_transport
        self.mock_transport: MockTransport | None = None
        self.mismatch_logger = mismatch_logger or MismatchLogger(Path("mismatch_logs"))

    async def get_document(self, document_id: str) -> DocumentData:
        """Get document from real API and initialize mock.

        Args:
            document_id: Document ID

        Returns:
            DocumentData from real API
        """
        # Get from real API
        real_data = await self.real_transport.get_document(document_id)

        # Initialize mock transport with the real document state
        self.mock_transport = MockTransport(real_data.raw)

        # Get from mock (should match since we just initialized it)
        mock_data = await self.mock_transport.get_document(document_id)

        # Compare responses (should be identical on first get)
        match, diffs = self._documents_match(real_data.raw, mock_data.raw)
        if not match:
            print("GET document diffs:")
            print("\n".join(diffs))
            self.mismatch_logger.log_get_mismatch(
                document_id, real_data.raw, mock_data.raw
            )

        return real_data

    async def batch_update(
        self, document_id: str, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply batch update to both APIs and compare.

        Args:
            document_id: Document ID
            requests: Update requests

        Returns:
            Response from real API
        """
        if self.mock_transport is None:
            raise RuntimeError("Must call get_document before batch_update")

        # Get document state before update (for logging)
        input_document = self.mock_transport.mock_api.get()

        # Apply to real API - may raise APIError on 400
        try:
            real_response = await self.real_transport.batch_update(
                document_id, requests
            )
        except APIError as real_err:
            if real_err.status_code == 400:
                # Real API rejected the request. Mock should also reject it.
                return self._handle_real_api_400(
                    document_id, requests, input_document, real_err
                )
            raise

        # Get real document state after update
        real_data_after = await self.real_transport.get_document(document_id)

        # Apply to mock API
        try:
            mock_response = await self.mock_transport.batch_update(
                document_id, requests
            )
            mock_data_after = await self.mock_transport.get_document(document_id)

            # Compare responses and documents
            resp_match, resp_diffs = self._batch_update_responses_match(
                real_response, mock_response
            )
            doc_match, doc_diffs = self._documents_match(
                real_data_after.raw, mock_data_after.raw
            )

            if not resp_match or not doc_match:
                all_diffs = []
                if not resp_match:
                    all_diffs.append("Response diffs:")
                    all_diffs.extend(resp_diffs)
                if not doc_match:
                    all_diffs.append("Document diffs:")
                    all_diffs.extend(doc_diffs)
                print("\n".join(all_diffs))
                self.mismatch_logger.log_batch_update_mismatch(
                    document_id=document_id,
                    requests=requests,
                    input_document=input_document,
                    real_response=real_response,
                    mock_response=mock_response,
                    real_document_after=real_data_after.raw,
                    mock_document_after=mock_data_after.raw,
                )
        except Exception as e:
            # Mock API raised an error when real succeeded - log as mismatch
            print(f"⚠️  Mock API raised error: {e}")
            self.mismatch_logger.log_batch_update_mismatch(
                document_id=document_id,
                requests=requests,
                input_document=input_document,
                real_response=real_response,
                mock_response={"error": str(e), "type": type(e).__name__},
                real_document_after=real_data_after.raw,
                mock_document_after=input_document,  # No change since it errored
            )

        return real_response

    def _handle_real_api_400(
        self,
        document_id: str,
        requests: list[dict[str, Any]],
        input_document: dict[str, Any],
        real_err: APIError,
    ) -> dict[str, Any]:
        """Handle real API 400 error by verifying mock also rejects.

        When the real API returns 400, the mock should also raise an error.
        If it doesn't, that means mock validation is too lenient.

        Args:
            document_id: Document ID
            requests: The requests that caused the 400
            input_document: Document state before the request
            real_err: The APIError from the real API

        Returns:
            Empty response dict

        Raises:
            APIError: Always re-raises the original real API error
        """
        try:
            self.mock_transport.mock_api.batch_update(requests)  # type: ignore[union-attr]
            # Mock succeeded when real API returned 400 — mock is too lenient
            print(
                "⚠️  Real API returned 400 but mock succeeded. "
                "Mock validation too lenient."
            )
            print(f"  Real error: {real_err}")
            self.mismatch_logger.log_batch_update_mismatch(
                document_id=document_id,
                requests=requests,
                input_document=input_document,
                real_response={"error": str(real_err), "status_code": 400},
                mock_response={"success": True, "error": "Mock should have rejected"},
                real_document_after=input_document,
                mock_document_after=self.mock_transport.mock_api.get()
                if self.mock_transport
                else input_document,
            )
        except MockAPIError:
            # Both real and mock rejected — this is correct behavior
            print("  Both real API and mock rejected request (400). OK.")
        except Exception as e:
            # Mock raised a different error — still counts as rejection
            print(
                f"  Both real API (400) and mock rejected request "
                f"({type(e).__name__}: {e}). OK."
            )

        raise real_err

    async def list_comments(self, file_id: str) -> list[dict[str, Any]]:
        """List comments from real API only.

        Args:
            file_id: File ID

        Returns:
            Comments from real API
        """
        return await self.real_transport.list_comments(file_id)

    async def create_reply(
        self,
        file_id: str,
        comment_id: str,
        content: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Create reply using real API only.

        Args:
            file_id: File ID
            comment_id: Comment ID
            content: Reply content
            action: Optional action

        Returns:
            Reply from real API
        """
        return await self.real_transport.create_reply(
            file_id, comment_id, content, action
        )

    async def close(self) -> None:
        """Close both transports."""
        await self.real_transport.close()
        if self.mock_transport:
            await self.mock_transport.close()

    @staticmethod
    def _find_diffs(d1: Any, d2: Any, path: str = "") -> list[str]:
        """Recursively find differences between two JSON-like structures.

        Args:
            d1: First structure (real).
            d2: Second structure (mock).
            path: Current JSON path for reporting.

        Returns:
            List of human-readable diff descriptions.
        """
        diffs: list[str] = []
        if type(d1) is not type(d2):
            diffs.append(
                f"  TYPE at {path}: real={type(d1).__name__} vs mock={type(d2).__name__}"
            )
            return diffs
        if isinstance(d1, dict):
            all_keys = set(d1.keys()) | set(d2.keys())
            for k in sorted(all_keys):
                if k not in d1:
                    val = str(d2[k])[:120]
                    diffs.append(f"  EXTRA in mock at {path}.{k}: {val}")
                elif k not in d2:
                    val = str(d1[k])[:120]
                    diffs.append(f"  MISSING in mock at {path}.{k}: {val}")
                else:
                    diffs.extend(
                        CompositeTransport._find_diffs(d1[k], d2[k], f"{path}.{k}")
                    )
        elif isinstance(d1, list):
            if len(d1) != len(d2):
                diffs.append(f"  LENGTH at {path}: real={len(d1)} vs mock={len(d2)}")
            for i in range(min(len(d1), len(d2))):
                diffs.extend(
                    CompositeTransport._find_diffs(d1[i], d2[i], f"{path}[{i}]")
                )
        elif d1 != d2:
            diffs.append(
                f"  VALUE at {path}: real={str(d1)[:120]} vs mock={str(d2)[:120]}"
            )
        return diffs

    def _documents_match(
        self, doc1: dict[str, Any], doc2: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Compare two documents for equality.

        Args:
            doc1: First document (real)
            doc2: Second document (mock)

        Returns:
            Tuple of (match, list of diff descriptions)
        """

        # Top-level fields to drop entirely (not meaningful for comparison)
        _drop_fields = {
            "revisionId",
            "suggestionsViewMode",
            "lists",
            "documentStyle",
            "namedStyles",
        }

        # Fields whose values are server-generated IDs - presence matters
        # but exact values will differ between real and mock
        _id_fields = {
            "headingId",
            "listId",
            "objectId",
            "footerId",
            "headerId",
            "footnoteId",
            "namedRangeId",
            "tabId",
        }

        def normalize(obj: Any) -> Any:
            if isinstance(obj, dict):
                result: dict[str, Any] = {}
                for k, v in obj.items():
                    if k in _drop_fields:
                        continue
                    if k in _id_fields:
                        result[k] = "__ID__"
                    # Real API omits startIndex when 0 (first element in segment)
                    elif k == "startIndex" and v == 0:
                        continue
                    else:
                        result[k] = normalize(v)
                return result
            if isinstance(obj, list):
                return [normalize(item) for item in obj]
            # Normalize float/int: 1.0 == 1, 0.0 == 0
            if isinstance(obj, float) and obj == int(obj):
                return int(obj)
            return obj

        def normalize_colors(obj: Any) -> Any:
            """Remove zero-valued RGB components (real API omits them)."""
            if isinstance(obj, dict):
                if "rgbColor" in obj:
                    rgb = obj["rgbColor"]
                    if isinstance(rgb, dict):
                        obj = dict(obj)
                        obj["rgbColor"] = {k: v for k, v in rgb.items() if v != 0}
                return {k: normalize_colors(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [normalize_colors(item) for item in obj]
            return obj

        n1, n2 = normalize_colors(normalize(doc1)), normalize_colors(normalize(doc2))
        if n1 == n2:
            return True, []
        return False, self._find_diffs(n1, n2)

    def _batch_update_responses_match(
        self, response1: dict[str, Any], response2: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Compare two batch update responses for equality.

        Args:
            response1: First response (real)
            response2: Second response (mock)

        Returns:
            Tuple of (match, list of diff descriptions)
        """

        # Server-generated ID fields in replies
        _reply_id_fields = {
            "headerId",
            "footerId",
            "footnoteId",
            "namedRangeId",
            "tabId",
        }

        def normalize(obj: Any) -> Any:
            if isinstance(obj, dict):
                result: dict[str, Any] = {}
                for k, v in obj.items():
                    if k in ("documentId", "writeControl"):
                        continue
                    if k in _reply_id_fields:
                        result[k] = "__ID__"
                    else:
                        result[k] = normalize(v)
                return result
            if isinstance(obj, list):
                return [normalize(item) for item in obj]
            return obj

        n1, n2 = normalize(response1), normalize(response2)
        if n1 == n2:
            return True, []
        return False, self._find_diffs(n1, n2)
