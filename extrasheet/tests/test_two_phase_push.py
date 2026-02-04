"""Tests for two-phase push (sequenced push for new sheets)."""

import json
from pathlib import Path

from extrasheet.client import (
    _extract_sheet_id_mapping,
    _remap_sheet_ids,
    _separate_structural_requests,
    _update_local_sheet_ids,
)


class TestSeparateStructuralRequests:
    def test_no_structural_requests(self):
        requests = [
            {"updateCells": {"sheetId": 0}},
            {"repeatCell": {"range": {"sheetId": 1}}},
        ]
        structural, content = _separate_structural_requests(requests)
        assert structural == []
        assert content == requests

    def test_only_structural_requests(self):
        requests = [
            {"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}},
            {"deleteSheet": {"sheetId": 200}},
        ]
        structural, content = _separate_structural_requests(requests)
        assert structural == requests
        assert content == []

    def test_mixed_requests(self):
        requests = [
            {
                "updateSpreadsheetProperties": {
                    "properties": {"title": "My Spreadsheet"}
                }
            },
            {"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}},
            {"updateCells": {"sheetId": 0}},
            {"deleteSheet": {"sheetId": 200}},
            {"repeatCell": {"range": {"sheetId": 1}}},
        ]
        structural, content = _separate_structural_requests(requests)

        assert len(structural) == 2
        assert {
            "addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}
        } in structural
        assert {"deleteSheet": {"sheetId": 200}} in structural

        assert len(content) == 3
        assert {"updateCells": {"sheetId": 0}} in content


class TestExtractSheetIdMapping:
    def test_no_add_sheet_requests(self):
        requests = [{"deleteSheet": {"sheetId": 100}}]
        replies = [{}]
        mapping = _extract_sheet_id_mapping(requests, replies)
        assert mapping == {}

    def test_add_sheet_with_same_id(self):
        """Google returned the same sheetId we requested."""
        requests = [
            {"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}}
        ]
        replies = [{"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}}]
        mapping = _extract_sheet_id_mapping(requests, replies)
        assert mapping == {}  # No mapping needed

    def test_add_sheet_with_different_id(self):
        """Google assigned a different sheetId."""
        requests = [
            {"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}}
        ]
        replies = [{"addSheet": {"properties": {"sheetId": 999, "title": "New Sheet"}}}]
        mapping = _extract_sheet_id_mapping(requests, replies)
        assert mapping == {100: 999}

    def test_multiple_add_sheets(self):
        """Multiple new sheets with ID remapping."""
        requests = [
            {"addSheet": {"properties": {"sheetId": 100, "title": "Sheet A"}}},
            {"addSheet": {"properties": {"sheetId": 200, "title": "Sheet B"}}},
        ]
        replies = [
            {"addSheet": {"properties": {"sheetId": 12345, "title": "Sheet A"}}},
            {"addSheet": {"properties": {"sheetId": 67890, "title": "Sheet B"}}},
        ]
        mapping = _extract_sheet_id_mapping(requests, replies)
        assert mapping == {100: 12345, 200: 67890}

    def test_mixed_structural_requests(self):
        """Mix of addSheet and deleteSheet."""
        requests = [
            {"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}},
            {"deleteSheet": {"sheetId": 999}},
        ]
        replies = [
            {"addSheet": {"properties": {"sheetId": 12345, "title": "New Sheet"}}},
            {},  # deleteSheet has empty reply
        ]
        mapping = _extract_sheet_id_mapping(requests, replies)
        assert mapping == {100: 12345}

    def test_empty_replies(self):
        """Handle empty or missing replies gracefully."""
        requests = [
            {"addSheet": {"properties": {"sheetId": 100, "title": "New Sheet"}}}
        ]
        replies = []  # No replies
        mapping = _extract_sheet_id_mapping(requests, replies)
        assert mapping == {}


class TestUpdateLocalSheetIds:
    def test_update_sheet_ids(self, tmp_path: Path):
        """Update sheetIds in spreadsheet.json."""
        spreadsheet_json = tmp_path / "spreadsheet.json"
        spreadsheet_json.write_text(
            json.dumps(
                {
                    "title": "Test Spreadsheet",
                    "sheets": [
                        {"sheetId": 0, "title": "Sheet1"},
                        {"sheetId": 100, "title": "New Sheet"},
                    ],
                }
            )
        )

        mapping = {100: 12345}
        _update_local_sheet_ids(tmp_path, mapping)

        updated = json.loads(spreadsheet_json.read_text())
        assert updated["sheets"][0]["sheetId"] == 0  # Unchanged
        assert updated["sheets"][1]["sheetId"] == 12345  # Updated

    def test_no_matching_ids(self, tmp_path: Path):
        """No sheetIds match the mapping."""
        spreadsheet_json = tmp_path / "spreadsheet.json"
        original_data = {
            "title": "Test Spreadsheet",
            "sheets": [
                {"sheetId": 0, "title": "Sheet1"},
            ],
        }
        spreadsheet_json.write_text(json.dumps(original_data))

        mapping = {999: 12345}  # No match
        _update_local_sheet_ids(tmp_path, mapping)

        updated = json.loads(spreadsheet_json.read_text())
        assert updated["sheets"][0]["sheetId"] == 0  # Unchanged

    def test_missing_spreadsheet_json(self, tmp_path: Path):
        """Handle missing spreadsheet.json gracefully."""
        mapping = {100: 12345}
        _update_local_sheet_ids(tmp_path, mapping)  # Should not raise


class TestRemapSheetIds:
    def test_remap_simple_request(self):
        """Remap sheetId in simple request."""
        requests = [{"updateCells": {"start": {"sheetId": 100, "rowIndex": 0}}}]
        mapping = {100: 12345}
        result = _remap_sheet_ids(requests, mapping)
        assert result[0]["updateCells"]["start"]["sheetId"] == 12345

    def test_remap_nested_range(self):
        """Remap sheetId in nested range."""
        requests = [
            {
                "repeatCell": {
                    "range": {"sheetId": 100, "startRowIndex": 0},
                    "cell": {"userEnteredFormat": {}},
                }
            }
        ]
        mapping = {100: 12345}
        result = _remap_sheet_ids(requests, mapping)
        assert result[0]["repeatCell"]["range"]["sheetId"] == 12345

    def test_remap_multiple_sheet_ids(self):
        """Remap multiple sheetIds in the same request."""
        requests = [
            {
                "copyPaste": {
                    "source": {"sheetId": 100, "startRowIndex": 0},
                    "destination": {"sheetId": 200, "startRowIndex": 10},
                }
            }
        ]
        mapping = {100: 12345, 200: 67890}
        result = _remap_sheet_ids(requests, mapping)
        assert result[0]["copyPaste"]["source"]["sheetId"] == 12345
        assert result[0]["copyPaste"]["destination"]["sheetId"] == 67890

    def test_no_mapping_unchanged(self):
        """Requests unchanged when sheetId not in mapping."""
        requests = [{"updateCells": {"start": {"sheetId": 0, "rowIndex": 0}}}]
        mapping = {100: 12345}  # sheetId 0 not in mapping
        result = _remap_sheet_ids(requests, mapping)
        assert result[0]["updateCells"]["start"]["sheetId"] == 0

    def test_remap_in_list(self):
        """Remap sheetIds in list items."""
        requests = [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {"sheetId": 100, "startRowIndex": 0},
                            {"sheetId": 100, "startRowIndex": 10},
                        ]
                    }
                }
            }
        ]
        mapping = {100: 12345}
        result = _remap_sheet_ids(requests, mapping)
        ranges = result[0]["addConditionalFormatRule"]["rule"]["ranges"]
        assert ranges[0]["sheetId"] == 12345
        assert ranges[1]["sheetId"] == 12345

    def test_preserves_other_fields(self):
        """Ensure other fields are preserved during remapping."""
        requests = [
            {
                "updateCells": {
                    "rows": [
                        {"values": [{"userEnteredValue": {"stringValue": "test"}}]}
                    ],
                    "fields": "userEnteredValue",
                    "start": {"sheetId": 100, "rowIndex": 5, "columnIndex": 2},
                }
            }
        ]
        mapping = {100: 12345}
        result = _remap_sheet_ids(requests, mapping)

        assert result[0]["updateCells"]["start"]["sheetId"] == 12345
        assert result[0]["updateCells"]["start"]["rowIndex"] == 5
        assert result[0]["updateCells"]["start"]["columnIndex"] == 2
        assert result[0]["updateCells"]["fields"] == "userEnteredValue"
        assert (
            result[0]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"][
                "stringValue"
            ]
            == "test"
        )
