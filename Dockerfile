ARG PYTHON_VERSION=3.14-slim

FROM python:${PYTHON_VERSION} AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

COPY src/ ./src/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync

FROM python:${PYTHON_VERSION} AS runner

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    HOME=/home/appuser \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd -r appgroup && \
    useradd -r -m -g appgroup -d /home/appuser -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app /app

USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "online_cinema_api.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]

