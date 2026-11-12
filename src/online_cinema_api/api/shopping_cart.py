from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status # noqa

import schemas.shopping_cart
from db.models.accounts import UserModel
from db.session import get_db_session
from services.shopping_cart import add_movie_to_cart

router = APIRouter(tags=["ShoppingCart"])


@router.post("/cart/items", response_model=schemas.shopping_cart.CartItemResponse, status_code=status.HTTP_201_CREATED)
async def add_movie_in_cart(data: schemas.shopping_cart.CartItemAdd, db: AsyncSession = Depends(get_db_session), current_user: UserModel = Depends(get_current_user)):
    return add_movie_to_cart(data, db, current_user)