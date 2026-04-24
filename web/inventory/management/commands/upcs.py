"""Process CSV command - mirrors existing CLI upcs command."""

from django.core.management.base import BaseCommand

from csv_upc_omg.csv_utils import extract_upcs_from_csv, find_most_recent_csv


class Command(BaseCommand):
    help = "Extract UPCs from the most recently updated CSV in a directory."

    def add_arguments(self, parser):
        parser.add_argument(
            "directory",
            help="Directory containing CSV files",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output",
        )

    def handle(self, *args, **options):
        directory = options["directory"]
        verbose = options["verbose"]

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

        for upc in upc_list:
            self.stdout.write(upc)
