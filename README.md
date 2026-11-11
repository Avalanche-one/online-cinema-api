# Online Cinema API


> The project is under active development.

## Stack

- Python 3.14
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker
- uv

## Setup

Install dependencies:

```bash
uv sync
```

Create the environment file:

```powershell
Copy-Item .env.example .env
```

Start PostgreSQL:

```bash
docker compose up -d
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Run the API:

```bash
uv run uvicorn online_cinema_api.main:app --app-dir src --reload
```

API documentation: http://127.0.0.1:8000/docs

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
