"""Tests for the main module."""

from click.testing import CliRunner

from csv_upc_omg.main import main


def test_main_command() -> None:
    """Test the main command runs successfully."""
    runner = CliRunner()
    result = runner.invoke(main)
    
    assert result.exit_code == 0
    assert "Hello from CSV UPC OMG!" in result.output


def test_main_command_verbose() -> None:
    """Test the main command with verbose flag."""
    runner = CliRunner()
    result = runner.invoke(main, ["--verbose"])
    
    assert result.exit_code == 0
    assert "Starting CSV UPC OMG application..." in result.output
    assert "Hello from CSV UPC OMG!" in result.output