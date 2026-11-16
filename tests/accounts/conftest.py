"""Shared fixtures for tests/accounts.

Required packages: pytest, pytest-asyncio, aiosqlite, httpx.
"""

import inspect
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY_ACCESS", "test-access-secret")
os.environ.setdefault("SECRET_KEY_REFRESH", "test-refresh-secret")
os.environ.setdefault("JWT_SIGNING_ALGORITHM", "HS256")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from online_cinema_api.db.base import Base
from online_cinema_api.db.models.accounts import (
    ActivationTokenModel,
    PasswordResetTokenModel,
    RefreshTokenModel,
    UserGroupEnum,
    UserGroupModel,
    UserModel,
    UserProfileModel,
)
from online_cinema_api.security.passwords import pwd_context
from online_cinema_api.security.token_manager import JWTAuthManager

VALID_PASSWORD = "StrongPass1!"

ACCOUNT_TABLES = [
    UserGroupModel.__table__,
    UserModel.__table__,
    UserProfileModel.__table__,
    ActivationTokenModel.__table__,
    PasswordResetTokenModel.__table__,
    RefreshTokenModel.__table__,
]


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makeitem(collector, name, obj):
    """Mark async tests at collection time, so asyncio_mode=auto is not required."""
    if name.startswith("test") and inspect.iscoroutinefunction(obj):
        pytest.mark.asyncio(obj)


@pytest.fixture(scope="session", autouse=True)
def fast_bcrypt():
    """bcrypt with 12 rounds is too slow for tests."""
    pwd_context.update(bcrypt__rounds=4)


@pytest.fixture
def valid_password() -> str:
    return VALID_PASSWORD


@pytest.fixture
def jwt_manager() -> JWTAuthManager:
    return JWTAuthManager(
        secret_key_access="access-secret",
        secret_key_refresh="refresh-secret",
        algorithm="HS256",
    )


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=ACCOUNT_TABLES)
        )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def groups(db_session) -> dict[UserGroupEnum, UserGroupModel]:
    created = {name: UserGroupModel(name=name) for name in UserGroupEnum}
    db_session.add_all(created.values())
    await db_session.commit()
    return created


@pytest_asyncio.fixture
async def user_factory(db_session, groups):
    async def _make(
        email: str = "user@example.com",
        password: str = VALID_PASSWORD,
        is_active: bool = True,
        group: UserGroupEnum = UserGroupEnum.USER,
    ) -> UserModel:
        user = UserModel.create(
            email=email, raw_password=password, group_id=groups[group].id
        )
        user.is_active = is_active
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make
