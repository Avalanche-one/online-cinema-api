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

## Docker Deployment

### Environment Setup

Create the environment file from the example:

```bash
cp .env.example .env
```

### Start All Services

Build and start all services (including PostgreSQL, Redis, FastAPI, Celery Worker, and Celery Beat):

```bash
docker compose up --build
```

To run in detached mode (background):

```bash
docker compose up -d
```

### Stop Services

Stop all running services:

```bash
docker compose down
```

To stop and remove volumes (delete database data):

```bash
docker compose down -v
```

### View Logs

View logs from all services:

```bash
docker compose logs -f
```

View logs for a specific service:

```bash
docker compose logs -f web
docker compose logs -f celery-worker
docker compose logs -f celery-beat
```

### Service Access

- FastAPI application: http://localhost:8000
- API documentation (Swagger UI): http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
