# CSV UPC OMG

A Python application for CSV and UPC processing.

## Installation

Install the package using uv:

```bash
uv pip install -e .
```

For development:

```bash
uv sync --all-extras
```

Set up pre-commit hooks (recommended):

```bash
uv run pre-commit install
```

## Usage

```bash
csv-upc-omg --help
```

## Development

Run tests:

```bash
uv run pytest
```

Format and lint code:

```bash
uv run ruff format .
uv run ruff check .
```

Type checking:

```bash
uv run mypy src/
```

Run all quality checks:

```bash
uv run pre-commit run --all-files
```

## License

BSD-3-Clause
