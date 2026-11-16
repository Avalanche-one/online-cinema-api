from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from online_cinema_api.dependencies.documentation import require_docs_access


def create_documentation_router(app: FastAPI) -> APIRouter:
    router = APIRouter(
        include_in_schema=False,
        dependencies=[Depends(require_docs_access)],
    )

    @router.get(
        "/docs",
        response_class=HTMLResponse,
        summary="Swagger UI",
    )
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{app.title} — Swagger UI",
        )

    @router.get(
        "/redoc",
        response_class=HTMLResponse,
        summary="ReDoc",
    )
    async def redoc() -> HTMLResponse:
        return get_redoc_html(
            openapi_url="/openapi.json",
            title=f"{app.title} — ReDoc",
        )

    @router.get(
        "/openapi.json",
        response_class=JSONResponse,
        summary="OpenAPI schema",
    )
    async def openapi_schema() -> JSONResponse:
        return JSONResponse(content=app.openapi())

    return router
