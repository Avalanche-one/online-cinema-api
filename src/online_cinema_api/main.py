from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from online_cinema_api.api.router import api_router
from online_cinema_api.core.config import settings
from online_cinema_api.db.session import engine


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
)

app.include_router(api_router, prefix="/api/v1")
