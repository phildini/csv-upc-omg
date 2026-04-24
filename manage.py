#!/usr/bin/env python
"""Django's command-line utility."""

import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    # Add project root to Python path so manage.py can find web/ as the Django project
    project_root = Path(__file__).resolve().parent.parent.parent
    src_path = project_root / "web"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
