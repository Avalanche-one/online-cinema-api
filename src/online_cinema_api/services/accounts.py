from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from online_cinema_api.core.dependencies import get_jwt_auth_manager
from online_cinema_api.crud import get_user_by_email
from online_cinema_api.db.session import get_db_session
from online_cinema_api.schemas import UserRead
from online_cinema_api.security.interfaces import JWTAuthManagerInterface

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db_session),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
) -> UserRead:
    payload = jwt_manager.decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    db_user = await get_user_by_email(db, email)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(db_user)
