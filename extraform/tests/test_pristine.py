"""Tests for pristine handling."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from extraform.exceptions import InvalidFileError, MissingPristineError
from extraform.pristine import (
    create_pristine,
    extract_pristine,
    get_pristine_form,
    update_pristine,
)


class TestCreatePristine:
    """Tests for create_pristine function."""

    def test_create_pristine_basic(self, tmp_path: Path) -> None:
        """Test creating a basic pristine archive."""
        folder = tmp_path / "form123"
        folder.mkdir()

        files = {
            "form.json": {"formId": "123", "info": {"title": "Test"}},
        }

        zip_path = create_pristine(folder, files)

        assert zip_path.exists()
        assert zip_path.name == "form.zip"
        assert zip_path.parent.name == ".pristine"

        # Verify contents
        with zipfile.ZipFile(zip_path) as zf:
            assert "form.json" in zf.namelist()

    def test_create_pristine_excludes_raw(self, tmp_path: Path) -> None:
        """Test that .raw files are excluded from pristine."""
        folder = tmp_path / "form123"
        folder.mkdir()

        files = {
            "form.json": {"formId": "123"},
            ".raw/form.json": {"raw": "data"},
        }

        zip_path = create_pristine(folder, files)

        with zipfile.ZipFile(zip_path) as zf:
            assert "form.json" in zf.namelist()
            assert ".raw/form.json" not in zf.namelist()

    def test_create_pristine_with_responses(self, tmp_path: Path) -> None:
        """Test creating pristine with responses.tsv."""
        folder = tmp_path / "form123"
        folder.mkdir()

        files = {
            "form.json": {"formId": "123"},
            "responses.tsv": "header1\theader2\nval1\tval2",
        }

        zip_path = create_pristine(folder, files)

        with zipfile.ZipFile(zip_path) as zf:
            assert "form.json" in zf.namelist()
            assert "responses.tsv" in zf.namelist()


class TestExtractPristine:
    """Tests for extract_pristine function."""

    def test_extract_pristine_basic(self, tmp_path: Path) -> None:
        """Test extracting a pristine archive."""
        folder = tmp_path / "form123"
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True)

        # Create a zip file
        zip_path = pristine_dir / "form.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("form.json", json.dumps({"formId": "123"}))

        files = extract_pristine(folder)

        assert "form.json" in files
        assert isinstance(files["form.json"], str)
        parsed = json.loads(files["form.json"])
        assert parsed["formId"] == "123"

    def test_extract_pristine_missing(self, tmp_path: Path) -> None:
        """Test extracting when pristine doesn't exist."""
        folder = tmp_path / "form123"
        folder.mkdir()

        with pytest.raises(MissingPristineError) as exc_info:
            extract_pristine(folder)

        assert str(folder) in str(exc_info.value)

    def test_extract_pristine_corrupted(self, tmp_path: Path) -> None:
        """Test extracting a corrupted zip file."""
        folder = tmp_path / "form123"
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True)

        # Create an invalid zip file
        zip_path = pristine_dir / "form.zip"
        zip_path.write_text("not a zip file")

        with pytest.raises(InvalidFileError) as exc_info:
            extract_pristine(folder)

        assert "Corrupted zip file" in str(exc_info.value)


class TestGetPristineForm:
    """Tests for get_pristine_form function."""

    def test_get_pristine_form_basic(self, tmp_path: Path) -> None:
        """Test getting pristine form as dict."""
        folder = tmp_path / "form123"
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True)

        form_data = {
            "formId": "123",
            "info": {"title": "Test Form"},
            "items": [],
        }

        zip_path = pristine_dir / "form.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("form.json", json.dumps(form_data))

        result = get_pristine_form(folder)

        assert result["formId"] == "123"
        assert result["info"]["title"] == "Test Form"

    def test_get_pristine_form_missing_form_json(self, tmp_path: Path) -> None:
        """Test when form.json is missing from archive."""
        folder = tmp_path / "form123"
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True)

        zip_path = pristine_dir / "form.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("other.txt", "some content")

        with pytest.raises(InvalidFileError) as exc_info:
            get_pristine_form(folder)

        assert "Missing form.json" in str(exc_info.value)

    def test_get_pristine_form_invalid_json(self, tmp_path: Path) -> None:
        """Test when form.json contains invalid JSON."""
        folder = tmp_path / "form123"
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True)

        zip_path = pristine_dir / "form.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("form.json", "not valid json")

        with pytest.raises(InvalidFileError) as exc_info:
            get_pristine_form(folder)

        assert "Invalid JSON" in str(exc_info.value)


class TestUpdatePristine:
    """Tests for update_pristine function."""

    def test_update_pristine(self, tmp_path: Path) -> None:
        """Test updating pristine after changes."""
        folder = tmp_path / "form123"
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True)

        # Create initial pristine
        initial_files = {"form.json": {"formId": "123", "version": 1}}
        create_pristine(folder, initial_files)

        # Update with new files
        updated_files = {"form.json": {"formId": "123", "version": 2}}
        update_pristine(folder, updated_files)

        # Verify update
        result = get_pristine_form(folder)
        assert result["version"] == 2
