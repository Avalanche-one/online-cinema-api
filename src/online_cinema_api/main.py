from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from online_cinema_api.api.documentation import create_documentation_router
from online_cinema_api.api.router import api_router
from online_cinema_api.core.config import settings
from online_cinema_api.core.exceptions import AppError
from online_cinema_api.db.session import engine
from online_cinema_api.exceptions import BaseEmailError, BaseSecurityError


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(BaseSecurityError)
async def security_error_handler(_: Request, exc: BaseSecurityError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(BaseEmailError)
async def email_error_handler(_: Request, exc: BaseEmailError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Email service is temporarily unavailable."},
    )


if settings.docs_enabled:
    if not settings.docs_username or not settings.docs_password:
        raise RuntimeError(
            "DOCS_USERNAME and DOCS_PASSWORD must be configured "
            "when documentation is enabled."
        )

    app.include_router(create_documentation_router(app))
app.include_router(api_router, prefix="/api/v1")
