from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from online_cinema_api.db.models.accounts import UserModel
from online_cinema_api.db.session import get_db_session
from online_cinema_api.dependencies import get_current_user
from online_cinema_api.schemas.shopping_cart import CartItemAdd, CartItemResponse, CartResponse
from online_cinema_api.services.shopping_cart import (
    add_movie_to_cart,
    delete_movie_from_cart_by_user_id, get_movie_from_cart,
)

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
    return await add_movie_to_cart(data, db, current_user)


@router.delete("/cart/items/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    return await delete_movie_from_cart_by_user_id(db, current_user, movie_id)


@router.get("/cart", response_model=CartResponse, status_code=status.HTTP_200_OK)
async def read_cart(db: AsyncSession = Depends(get_db_session), current_user: UserModel = Depends(get_current_user)):
    return await get_movie_from_cart(db, current_user)