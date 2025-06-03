"""Main entry point for the CSV UPC OMG application."""

import click


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def main(verbose: bool) -> None:
    """CSV UPC OMG - A Python application for CSV and UPC processing."""
    if verbose:
        click.echo("Starting CSV UPC OMG application...")
    
    click.echo("Hello from CSV UPC OMG!")


if __name__ == "__main__":
    main()