# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14-slim

# -------------------------------------------------------------------
# Stage 1: Builder
# -------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS builder

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Environment variables for uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency definition files to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies without the root project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Copy project source and sync the full project
COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# -------------------------------------------------------------------
# Stage 2: Runtime
# -------------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS runner

# Install uv in the runner image as well
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Standard Python & uv runtime settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    HOME=/home/appuser \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user and home directory
RUN groupadd -r appgroup && \
    useradd -r -m -g appgroup -d /home/appuser -s /sbin/nologin appuser

WORKDIR /app

# Copy pre-built virtual environment and source code from builder stage
COPY --from=builder --chown=appuser:appgroup /app /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Default command for running the FastAPI application
CMD ["uv", "run", "uvicorn", "online_cinema_api.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]

