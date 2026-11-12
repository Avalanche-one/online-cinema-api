from fastapi import APIRouter

from online_cinema_api.api.accounts import router as accounts_router
from online_cinema_api.api.health import router as health_router
from online_cinema_api.api.shopping_cart import router as shopping_cart_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(shopping_cart_router)
api_router.include_router(accounts_router, prefix="/accounts")
