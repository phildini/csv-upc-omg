# CSV UPC OMG

A Python application for CSV and UPC processing.

## Installation

Install the package using uv:

```bash
uv pip install -e .
```

For development:

```bash
uv pip install -e ".[dev]"
```

## Usage

```bash
csv-upc-omg --help
```

## Development

Run tests:

```bash
pytest
```

Format and lint code:

```bash
ruff format .
ruff check .
```

Type checking:

```bash
mypy src/
```

## License

BSD-3-Clause