"""Tests for the csv_utils module."""

import tempfile
from pathlib import Path

import pytest

from csv_upc_omg.csv_utils import extract_upcs_from_csv, find_most_recent_csv


def test_find_most_recent_csv_no_files() -> None:
    """Test finding CSV in directory with no CSV files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        result = find_most_recent_csv(temp_dir)
        assert result is None


def test_find_most_recent_csv_single_file() -> None:
    """Test finding CSV in directory with one CSV file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("data")

        result = find_most_recent_csv(temp_dir)
        assert result == csv_path


def test_find_most_recent_csv_multiple_files() -> None:
    """Test finding most recent CSV when multiple files exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        old_csv = Path(temp_dir) / "old.csv"
        new_csv = Path(temp_dir) / "new.csv"

        old_csv.write_text("old data")
        new_csv.write_text("new data")

        # Ensure new_csv has a later modification time
        import time

        time.sleep(0.01)
        new_csv.touch()

        result = find_most_recent_csv(temp_dir)
        assert result == new_csv


def test_find_most_recent_csv_nonexistent_directory() -> None:
    """Test finding CSV in nonexistent directory."""
    with pytest.raises(FileNotFoundError):
        find_most_recent_csv("/nonexistent/directory")


def test_find_most_recent_csv_not_directory() -> None:
    """Test finding CSV when path is not a directory."""
    with tempfile.NamedTemporaryFile() as temp_file:
        with pytest.raises(NotADirectoryError):
            find_most_recent_csv(temp_file.name)


def test_extract_upcs_basic() -> None:
    """Test extracting UPCs from a basic CSV."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    ) as temp_file:
        temp_file.write("123456789012,Product A\n987654321098,Product B")
        temp_file.flush()

        result = extract_upcs_from_csv(Path(temp_file.name))
        assert result == ["123456789012", "987654321098"]


def test_extract_upcs_empty_file() -> None:
    """Test extracting UPCs from empty CSV."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    ) as temp_file:
        temp_file.write("")
        temp_file.flush()

        result = extract_upcs_from_csv(Path(temp_file.name))
        assert result == []


def test_extract_upcs_with_empty_rows() -> None:
    """Test extracting UPCs from CSV with empty rows."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    ) as temp_file:
        temp_file.write("123456789012,Product A\n,Empty UPC\n987654321098,Product B")
        temp_file.flush()

        result = extract_upcs_from_csv(Path(temp_file.name))
        assert result == ["123456789012", "987654321098"]


def test_extract_upcs_whitespace_handling() -> None:
    """Test extracting UPCs handles whitespace correctly."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    ) as temp_file:
        temp_file.write("  123456789012  ,Product A\n987654321098,Product B")
        temp_file.flush()

        result = extract_upcs_from_csv(Path(temp_file.name))
        assert result == ["123456789012", "987654321098"]


def test_extract_upcs_nonexistent_file() -> None:
    """Test extracting UPCs from nonexistent file."""
    with pytest.raises(FileNotFoundError):
        extract_upcs_from_csv(Path("/nonexistent/file.csv"))
