from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from online_cinema_api.db.models.accounts import UserModel
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import get_current_user
from online_cinema_api.schemas.shopping_cart import CartItemAdd, CartItemResponse
from online_cinema_api.services.shopping_cart import add_movie_to_cart

router = APIRouter(tags=["ShoppingCart"])


@router.post(
    "/cart/items",
    response_model=CartItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_movie_in_cart(
    data: CartItemAdd,
    db: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    return add_movie_to_cart(data, db, current_user)
