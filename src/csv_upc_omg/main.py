"""Main entry point for the CSV UPC OMG application."""

import click

from .barcode_lookup import BarcodeAPIError, fetch_product_title_sync
from .csv_utils import extract_upcs_from_csv, find_most_recent_csv


@click.group()
def cli() -> None:
    """CSV UPC OMG - A Python application for CSV and UPC processing."""
    pass


@cli.command()
@click.argument(
    "directory", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def upcs(directory: str, verbose: bool) -> None:
    """Extract UPCs from the most recently updated CSV in a directory."""
    try:
        csv_path = find_most_recent_csv(directory)

        if csv_path is None:
            click.echo("No CSV files found in the specified directory.")
            return

        if verbose:
            click.echo(f"Processing most recent CSV: {csv_path}")

        upc_list = extract_upcs_from_csv(csv_path)

        if not upc_list:
            click.echo("No UPCs found in the CSV file.")
            return

        for upc in upc_list:
            click.echo(upc)

    except (FileNotFoundError, NotADirectoryError) as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error processing CSV: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument(
    "directory", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--timeout", default=10.0, help="Request timeout in seconds", type=float)
def titles(directory: str, verbose: bool, timeout: float) -> None:
    """Extract UPCs from CSV and fetch product titles from barcodelookup.com."""
    try:
        csv_path = find_most_recent_csv(directory)

        if csv_path is None:
            click.echo("No CSV files found in the specified directory.")
            return

        if verbose:
            click.echo(f"Processing most recent CSV: {csv_path}")

        upc_list = extract_upcs_from_csv(csv_path)

        if not upc_list:
            click.echo("No UPCs found in the CSV file.")
            return

        if verbose:
            click.echo(f"Found {len(upc_list)} UPCs, fetching product titles...")

        for upc in upc_list:
            try:
                title = fetch_product_title_sync(upc, timeout=timeout)
                if title:
                    click.echo(f"{upc}: {title}")
                else:
                    click.echo(f"{upc}: Product not found")

            except BarcodeAPIError as e:
                if verbose:
                    click.echo(f"{upc}: Error - {e}", err=True)
                else:
                    click.echo(f"{upc}: Lookup failed")

    except (FileNotFoundError, NotADirectoryError) as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error processing CSV: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def hello(verbose: bool) -> None:
    """Say hello (legacy command)."""
    if verbose:
        click.echo("Starting CSV UPC OMG application...")

    click.echo("Hello from CSV UPC OMG!")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
