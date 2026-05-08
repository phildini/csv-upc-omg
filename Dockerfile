FROM python:3.11-slim-bullseye AS builder

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./
COPY src/pyproject.toml ./src/
COPY web/pyproject.toml ./web/

# Copy application code (needed for workspace package installation)
COPY . .

# Install dependencies (no dev) with all workspace packages
RUN uv sync --frozen --no-dev --all-packages

# Build Tailwind CSS
RUN uv run python web/manage.py tailwind build

# Collect static files
RUN uv run python web/manage.py collectstatic --noinput

# Runtime image
FROM python:3.11-slim-bullseye

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary
COPY --from=builder /bin/uv /bin/uvx /bin/

# Copy installed packages
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

# Create data directory
RUN mkdir -p /data && chown -R 1000:1000 /data

# Create uv cache directory at default location with proper permissions
RUN mkdir -p /.cache/uv && chown -R 1000:1000 /.cache

# Create gunicorn control directory
RUN mkdir -p /.gunicorn && chown -R 1000:1000 /.gunicorn

USER 1000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health/ || exit 1

EXPOSE 8080

CMD ["sh", "-c", "uv run python web/manage.py migrate --noinput && uv run gunicorn --bind 0.0.0.0:8080 --workers 1 --max-requests 1000 --max-requests-jitter 100 config.wsgi"]
