# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv /usr/local/bin/uv

# Copy dependency manifests — deps layer is cached separately from source
COPY pyproject.toml uv.lock ./

# Install all production dependencies except the project itself.
# This layer is only invalidated when pyproject.toml / uv.lock change.
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY . .

# Install the project itself (fast — transitive deps already in place)
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
