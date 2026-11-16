# Online Cinema API

Production-oriented REST API for an online cinema platform. The service covers user authentication, movie discovery and engagement, shopping carts, orders, Stripe payments, role-based moderation, email notifications, and scheduled background tasks.

> The project is still under active development.

## Live Demo

- **Swagger UI:** [https://online-cinema.space/docs](https://online-cinema.space/docs)
- **API base URL:** `https://online-cinema.space/api/v1`

The documentation endpoint is protected with HTTP Basic Authentication. After opening Swagger UI, use the **Authorize** button with an API access token to call protected endpoints.

### Demo Accounts

The deployed environment provides accounts for each supported role:

| Role | Email | Password |
| --- | --- | --- |
| User | [user@online-cinema.space](mailto:user@online-cinema.space) | `Secret@123` |
| Moderator | [moderator@online-cinema.space](mailto:moderator@online-cinema.space) | `Secret@123` |
| Admin | [admin@online-cinema.space](mailto:admin@online-cinema.space) | `Secret@123` |
| Swagger | docs | `strong_password` |

> These credentials are public demo credentials. Do not reuse the password for personal or production accounts.

## Features

### Accounts and Security

- Email-based registration with unique-email validation.
- Account activation through a time-limited email token.
- Activation-link renewal for inactive accounts.
- Login with JWT access and refresh tokens.
- Refresh-token revocation on logout.
- Password reset through a time-limited email token.
- Password-strength validation.
- User profile management with optional personal information.
- Role-based access control for users, moderators, and administrators.
- Scheduled cleanup of expired activation, password-reset, and refresh tokens.

### Movie Catalog

- Paginated movie catalog and detailed movie pages.
- Search by title, description, actor, or director.
- Filtering by year, IMDb rating, price, genre, certification, actor, and director.
- Sorting by title, year, IMDb rating, price, and popularity.
- Genre listing with movie counts.
- Favorites with the same search, filtering, sorting, and pagination capabilities as the main catalog.
- Likes, dislikes, and ratings on a 10-point scale.
- Comments, replies, comment likes, and in-app notifications.

### Moderation

- CRUD operations for movies.
- CRUD operations for genres, actors, and directors.
- Protection against deleting movies referenced by orders.
- Warning and explicit confirmation when deleting movies present in user carts.
- Administrative user activation and group management.
- Staff access to user carts, orders, and payments.

### Shopping and Payments

- One cart per user.
- Add, remove, list, and clear cart items.
- Duplicate-cart-item and repeat-purchase protection.
- Order creation from the current cart.
- Historical order prices stored per item.
- Pending, paid, and canceled order states.
- User order history and staff-side filters.
- Stripe Checkout integration.
- Signed Stripe webhook processing.
- Payment history with item-level price snapshots.
- Full refund requests and refunded-payment tracking.
- Payment confirmation emails.

## Tech Stack

- **Python 3.14**
- **FastAPI** and OpenAPI
- **PostgreSQL 18**
- **SQLAlchemy 2** with asynchronous sessions
- **Alembic** database migrations
- **Redis**
- **Celery** and Celery Beat
- **Stripe Checkout and Webhooks**
- **Jinja2** and asynchronous SMTP email delivery
- **Pydantic Settings**
- **pytest**, pytest-asyncio, and coverage.py
- **Ruff**
- **uv** for dependency and virtual-environment management
- **Docker** and Docker Compose
- **GitHub Actions**

## Architecture

```text
Client / Swagger UI
        |
        v
     FastAPI
        |
        +-------------------- PostgreSQL
        |
        +-------------------- Stripe API / Webhooks
        |
        +-------------------- SMTP server
        |
        +---- Redis <-------- Celery Worker
                 ^
                 |
             Celery Beat
```

The application uses a layered structure:

```text
src/online_cinema_api/
├── api/             # FastAPI routers
├── core/            # Settings and application exceptions
├── db/              # SQLAlchemy models, sessions, seed data, validators
├── dependencies/    # Authentication and authorization dependencies
├── notifications/   # Email sender and HTML templates
├── schemas/         # Pydantic request and response models
├── security/        # Password hashing and JWT management
├── services/        # Business logic and database operations
└── tasks/           # Celery tasks
```

## API Overview

All application endpoints use the `/api/v1` prefix.

| Area | Main endpoints |
| --- | --- |
| Health | `GET /health` |
| Accounts | `/accounts/register/`, `/accounts/activate/`, `/accounts/login/`, `/accounts/refresh/`, `/accounts/logout/` |
| Password reset | `/accounts/password-reset/request/`, `/accounts/password-reset/complete/` |
| Profile | `GET/PATCH /accounts/me/` |
| Movies | `GET /movies`, `GET /movies/{movie_id}`, `GET /genres` |
| Interactions | `/movies/{movie_id}/reaction`, `/movies/{movie_id}/rating`, `/favorites` |
| Comments | `/movies/{movie_id}/comments`, `/comments/{comment_id}/replies`, `/comments/{comment_id}/like` |
| Notifications | `/notifications`, `/notifications/read-all`, `/notifications/{notification_id}/read` |
| Cart | `/cart`, `/cart/items`, `/cart/purchased` |
| Orders | `/orders`, `/orders/{order_id}`, `/orders/{order_id}/cancel` |
| Payments | `/payments/checkout/{order_id}`, `/payments`, `/payments/{payment_id}/refund` |
| Staff operations | `/admin/movies`, `/admin/genres`, `/admin/stars`, `/admin/directors`, `/orders/all`, `/payments/all` |

Refer to [Swagger UI](https://online-cinema.space/docs) for complete schemas, query parameters, and response models.

## Getting Started

### Prerequisites

- Git
- Docker with Docker Compose
- `uv` for local development without Docker
- Stripe CLI for local webhook testing
- Access to an SMTP server for email delivery

### 1. Clone the Repository

```bash
git clone <repository-url>
cd online-cinema-api
```

### 2. Configure the Environment

Create `.env` from the provided template.

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash:

```bash
cp .env.example .env
```

At minimum, review and replace the following values:

```env
POSTGRES_PASSWORD=change-me
SECRET_KEY_ACCESS=change-me
SECRET_KEY_REFRESH=change-me

STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=change-me
EMAIL_HOST_PASSWORD=change-me
EMAIL_USE_TLS=true

DOCS_ENABLED=true
DOCS_USERNAME=change-me
DOCS_PASSWORD=change-me
```

Never commit a populated `.env` file.

### 3. Start the Application with Docker

```bash
docker compose up --build
```

Docker Compose starts:

- PostgreSQL;
- Redis;
- the Alembic migration job;
- the database seed job;
- FastAPI;
- Celery Worker;
- Celery Beat.

Run the stack in the background:

```bash
docker compose up -d --build
```

The local service is available at:

- API: [http://localhost:8000](http://localhost:8000)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Health check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

Swagger UI and ReDoc use the `DOCS_USERNAME` and `DOCS_PASSWORD` values from `.env`.

### 4. Stop the Application

```bash
docker compose down
```

To also remove the PostgreSQL and Redis volumes:

```bash
docker compose down -v
```

> `docker compose down -v` permanently removes local database and Redis data.

## Local Development without Docker

Install all dependencies:

```bash
uv sync
```

Start PostgreSQL and Redis, configure their URLs in `.env`, then apply migrations:

```bash
uv run alembic upgrade head
```

Optionally seed the movie catalog:

```bash
uv run python -m online_cinema_api.db.seed
```

Start the API:

```bash
uv run uvicorn online_cinema_api.main:app --app-dir src --reload
```

Start Celery Worker:

```bash
uv run celery -A online_cinema_api.celery_app:celery_app worker --loglevel=INFO
```

Start Celery Beat in a separate terminal:

```bash
uv run celery -A online_cinema_api.celery_app:celery_app beat --loglevel=INFO
```

## Authentication

Log in with an active account:

```bash
curl -X POST "http://localhost:8000/api/v1/accounts/login/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "Secret@123"
  }'
```

The response contains an access and refresh token:

```json
{
  "access_token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_type": "bearer"
}
```

Use the access token for protected endpoints:

```bash
curl "http://localhost:8000/api/v1/accounts/me/" \
  -H "Authorization: Bearer <access-token>"
```

## Stripe Test Payments

1. Add a Stripe test secret key to `.env`:

   ```env
   STRIPE_SECRET_KEY=sk_test_xxx
   ```

2. Start Stripe CLI webhook forwarding:

   ```bash
   stripe listen \
     --events checkout.session.completed,checkout.session.expired,charge.refunded \
     --forward-to localhost:8000/api/v1/payments/webhook
   ```

3. Copy the generated signing secret to `.env`:

   ```env
   STRIPE_WEBHOOK_SECRET=whsec_xxx
   ```

4. Recreate the API container:

   ```bash
   docker compose up -d --build web
   ```

5. Complete checkout with Stripe's test card:

   ```text
   Card number: 4242 4242 4242 4242
   Expiration: any future date
   CVC: any three digits
   ```

On a successful webhook, the payment becomes `successful`, the order becomes `paid`, purchased movies are removed from the cart, and a confirmation email is sent.

## Background Tasks

Celery Beat dispatches the expired-token cleanup task every 60 seconds. The worker removes expired records from:

- `activation_tokens`;
- `password_reset_tokens`;
- `refresh_tokens`.

View worker and scheduler logs:

```bash
docker compose logs -f celery-worker celery-beat
```

## Database Migrations

Create a migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Check the current revision:

```bash
uv run alembic current
```

## Code Quality and Tests

Run the test suite:

```bash
uv run pytest
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Apply automatic formatting:

```bash
uv run ruff format .
```

The GitHub Actions pipeline applies migrations to a test PostgreSQL service, runs Ruff and pytest with coverage, uploads the coverage report, builds the Docker image, and deploys the development branch through a self-hosted runner.

## Useful Docker Commands

```bash
# View logs from every service
docker compose logs -f

# View API logs
docker compose logs -f web

# Rebuild only the API
docker compose up -d --build web

# Run migrations manually
docker compose run --rm migrate uv run alembic upgrade head

# Inspect running services
docker compose ps
```

## Security Notes

- Replace all example secrets before exposing the application publicly.
- Keep `.env`, database dumps, Stripe secrets, JWT keys, and SMTP credentials out of Git.
- Use HTTPS for deployed environments.
- Treat the demo accounts as disposable public accounts.
- Rotate demo credentials if the deployment is used for anything beyond portfolio demonstration.

## Project Status

The API is actively developed. The deployed environment is intended for portfolio demonstration and API exploration.
