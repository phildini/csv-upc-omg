"""Look up product titles for UPCs in a directory."""

from django.core.management.base import BaseCommand

from csv_upc_omg.barcode_lookup import BarcodeAPIError, fetch_product_title_sync
from csv_upc_omg.csv_utils import extract_upcs_from_csv, find_most_recent_csv


class Command(BaseCommand):
    help = "Extract UPCs from CSV and fetch product titles from barcodelookup.com."

    def add_arguments(self, parser):
        parser.add_argument(
            "directory",
            help="Directory containing CSV files",
        )
        parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Enable verbose output",
        )
        parser.add_argument(
            "--timeout",
            default=10.0,
            type=float,
            help="Request timeout in seconds",
        )

    def handle(self, *args, **options):
        directory = options["directory"]
        verbose = options["verbose"]
        timeout = options["timeout"]

        csv_path = find_most_recent_csv(directory)

        if csv_path is None:
            self.stdout.write(
                self.style.WARNING("No CSV files found in the specified directory.")
            )
            return

        if verbose:
            self.stdout.write(f"Processing most recent CSV: {csv_path}")

        upc_list = extract_upcs_from_csv(csv_path)

        if not upc_list:
            self.stdout.write(self.style.WARNING("No UPCs found in the CSV file."))
            return

        if verbose:
            self.stdout.write(f"Found {len(upc_list)} UPCs, fetching product titles...")

        for upc in upc_list:
            try:
                title = fetch_product_title_sync(upc, timeout=timeout)
                if title:
                    self.stdout.write(f"{upc}: {title}")
                else:
                    self.stdout.write(f"{upc}: Product not found")

            except BarcodeAPIError as e:
                if verbose:
                    self.stderr.write(f"{upc}: Error - {e}")
                else:
                    self.stdout.write(f"{upc}: Lookup failed")
