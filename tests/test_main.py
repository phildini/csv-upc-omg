"""Tests for the main module."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from csv_upc_omg.main import cli


def test_hello_command() -> None:
    """Test the hello command runs successfully."""
    runner = CliRunner()
    result = runner.invoke(cli, ["hello"])

    assert result.exit_code == 0
    assert "Hello from CSV UPC OMG!" in result.output


def test_hello_command_verbose() -> None:
    """Test the hello command with verbose flag."""
    runner = CliRunner()
    result = runner.invoke(cli, ["hello", "--verbose"])

    assert result.exit_code == 0
    assert "Starting CSV UPC OMG application..." in result.output
    assert "Hello from CSV UPC OMG!" in result.output


def test_upcs_command_no_csv_files() -> None:
    """Test upcs command with directory containing no CSV files."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        result = runner.invoke(cli, ["upcs", temp_dir])

        assert result.exit_code == 0
        assert "No CSV files found" in result.output


def test_upcs_command_with_csv() -> None:
    """Test upcs command with a CSV file containing UPCs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text(
            "123456789012,Product A\n987654321098,Product B\n111222333444,Product C"
        )

        result = runner.invoke(cli, ["upcs", temp_dir])

        assert result.exit_code == 0
        assert "123456789012" in result.output
        assert "987654321098" in result.output
        assert "111222333444" in result.output


def test_upcs_command_verbose() -> None:
    """Test upcs command with verbose flag."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        result = runner.invoke(cli, ["upcs", temp_dir, "--verbose"])

        assert result.exit_code == 0
        assert "Processing most recent CSV" in result.output
        assert "123456789012" in result.output


def test_titles_command_no_csv_files() -> None:
    """Test titles command with directory containing no CSV files."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        result = runner.invoke(cli, ["titles", temp_dir])

        assert result.exit_code == 0
        assert "No CSV files found" in result.output


def test_titles_command_with_csv() -> None:
    """Test titles command with CSV file."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        # Mock the barcode lookup function
        with patch("csv_upc_omg.main.fetch_product_title_sync") as mock_fetch:
            mock_fetch.return_value = "Test Product Title"

            result = runner.invoke(cli, ["titles", temp_dir])

            assert result.exit_code == 0
            assert "123456789012: Test Product Title" in result.output
            mock_fetch.assert_called_once_with("123456789012", timeout=10.0)


def test_titles_command_product_not_found() -> None:
    """Test titles command when product is not found."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.fetch_product_title_sync") as mock_fetch:
            mock_fetch.return_value = None

            result = runner.invoke(cli, ["titles", temp_dir])

            assert result.exit_code == 0
            assert "123456789012: Product not found" in result.output


def test_titles_command_api_error() -> None:
    """Test titles command when API error occurs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.fetch_product_title_sync") as mock_fetch:
            from csv_upc_omg.barcode_lookup import BarcodeAPIError

            mock_fetch.side_effect = BarcodeAPIError("API Error")

            result = runner.invoke(cli, ["titles", temp_dir])

            assert result.exit_code == 0
            assert "123456789012: Lookup failed" in result.output


def test_titles_command_verbose() -> None:
    """Test titles command with verbose flag."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.fetch_product_title_sync") as mock_fetch:
            mock_fetch.return_value = "Test Product Title"

            result = runner.invoke(cli, ["titles", temp_dir, "--verbose"])

            assert result.exit_code == 0
            assert "Processing most recent CSV" in result.output
            assert "Found 1 UPCs, fetching product titles" in result.output
            assert "123456789012: Test Product Title" in result.output


def test_titles_command_custom_timeout() -> None:
    """Test titles command with custom timeout."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.fetch_product_title_sync") as mock_fetch:
            mock_fetch.return_value = "Test Product Title"

            result = runner.invoke(cli, ["titles", temp_dir, "--timeout", "5.0"])

            assert result.exit_code == 0
            mock_fetch.assert_called_once_with("123456789012", timeout=5.0)


def test_upcs_command_empty_csv() -> None:
    """Test upcs command with CSV file containing no UPCs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("")

        result = runner.invoke(cli, ["upcs", temp_dir])

        assert result.exit_code == 0
        assert "No UPCs found in the CSV file." in result.output


def test_upcs_command_csv_error() -> None:
    """Test upcs command when CSV processing fails."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.extract_upcs_from_csv") as mock_extract:
            mock_extract.side_effect = RuntimeError("CSV processing failed")

            result = runner.invoke(cli, ["upcs", temp_dir])

            assert result.exit_code == 1
            assert "Error processing CSV: CSV processing failed" in result.output


def test_upcs_command_file_not_found() -> None:
    """Test upcs command when directory doesn't exist."""
    runner = CliRunner()

    # Use a path that click will reject before our code runs
    result = runner.invoke(cli, ["upcs", "/totally/nonexistent/path"])

    assert result.exit_code == 2  # Click validation error
    assert "does not exist" in result.output


def test_titles_command_empty_csv() -> None:
    """Test titles command with CSV file containing no UPCs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("")

        result = runner.invoke(cli, ["titles", temp_dir])

        assert result.exit_code == 0
        assert "No UPCs found in the CSV file." in result.output


def test_titles_command_csv_error() -> None:
    """Test titles command when CSV processing fails."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.extract_upcs_from_csv") as mock_extract:
            mock_extract.side_effect = RuntimeError("CSV processing failed")

            result = runner.invoke(cli, ["titles", temp_dir])

            assert result.exit_code == 1
            assert "Error processing CSV: CSV processing failed" in result.output


def test_titles_command_file_not_found() -> None:
    """Test titles command when directory doesn't exist."""
    runner = CliRunner()

    # Use a path that click will reject before our code runs
    result = runner.invoke(cli, ["titles", "/totally/nonexistent/path"])

    assert result.exit_code == 2  # Click validation error
    assert "does not exist" in result.output


def test_titles_command_verbose_api_error() -> None:
    """Test titles command with verbose flag when API error occurs."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.fetch_product_title_sync") as mock_fetch:
            from csv_upc_omg.barcode_lookup import BarcodeAPIError

            mock_fetch.side_effect = BarcodeAPIError("API Error")

            result = runner.invoke(cli, ["titles", temp_dir, "--verbose"])

            assert result.exit_code == 0
            assert "123456789012: Error - API Error" in result.output


def test_main_as_script() -> None:
    """Test main function execution as script."""
    with patch("csv_upc_omg.main.cli") as mock_cli:
        from csv_upc_omg.main import main

        main()
        mock_cli.assert_called_once()


def test_upcs_command_directory_error() -> None:
    """Test upcs command with internal directory error."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.find_most_recent_csv") as mock_find:
            mock_find.side_effect = NotADirectoryError("Not a directory")

            result = runner.invoke(cli, ["upcs", temp_dir])

            assert result.exit_code == 1
            assert "Error: Not a directory" in result.output


def test_titles_command_directory_error() -> None:
    """Test titles command with internal directory error."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / "test.csv"
        csv_path.write_text("123456789012,Product A")

        with patch("csv_upc_omg.main.find_most_recent_csv") as mock_find:
            mock_find.side_effect = NotADirectoryError("Not a directory")

            result = runner.invoke(cli, ["titles", temp_dir])

            assert result.exit_code == 1
            assert "Error: Not a directory" in result.output
