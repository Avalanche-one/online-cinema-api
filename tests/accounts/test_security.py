import time
from datetime import timedelta

import pytest

from online_cinema_api.exceptions import (
    BaseSecurityError,
    InvalidTokenError,
    TokenExpiredError,
)
from online_cinema_api.security.interfaces import JWTAuthManagerInterface
from online_cinema_api.security.passwords import hash_password, verify_password
from online_cinema_api.security.token_manager import JWTAuthManager
from online_cinema_api.security.utils import generate_secure_token


def test_hash_password_is_not_plain_text_and_is_bcrypt():
    hashed = hash_password("StrongPass1!")

    assert hashed != "StrongPass1!"
    assert hashed.startswith("$2")


def test_hash_password_is_salted():
    assert hash_password("StrongPass1!") != hash_password("StrongPass1!")


def test_verify_password():
    hashed = hash_password("StrongPass1!")

    assert verify_password("StrongPass1!", hashed) is True
    assert verify_password("strongpass1!", hashed) is False
    assert verify_password("", hashed) is False


def test_generate_secure_token_default_length():
    assert len(generate_secure_token()) == 43


def test_generate_secure_token_custom_length():
    assert len(generate_secure_token(16)) == 22


def test_generate_secure_token_is_url_safe_and_unique():
    tokens = {generate_secure_token() for _ in range(100)}

    assert len(tokens) == 100
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert all(set(t) <= allowed for t in tokens)


def test_security_exceptions_hierarchy_and_messages():
    assert issubclass(TokenExpiredError, BaseSecurityError)
    assert issubclass(InvalidTokenError, BaseSecurityError)
    assert str(BaseSecurityError()) == "A security error occurred."
    assert str(TokenExpiredError()) == "Token has expired."
    assert str(InvalidTokenError()) == "Invalid token."
    assert str(InvalidTokenError("custom")) == "custom"


def test_manager_implements_interface():
    assert issubclass(JWTAuthManager, JWTAuthManagerInterface)
    with pytest.raises(TypeError):
        JWTAuthManagerInterface()


def test_access_token_roundtrip(jwt_manager):
    token = jwt_manager.create_access_token({"sub": "user@example.com"})

    payload = jwt_manager.decode_access_token(token)

    assert payload["sub"] == "user@example.com"
    assert "exp" in payload
    assert "jti" in payload


def test_refresh_token_roundtrip(jwt_manager):
    token = jwt_manager.create_refresh_token({"sub": "user@example.com", "x": 1})

    payload = jwt_manager.decode_refresh_token(token)

    assert payload["sub"] == "user@example.com"
    assert payload["x"] == 1


def test_create_token_does_not_mutate_input(jwt_manager):
    data = {"sub": "user@example.com"}

    jwt_manager.create_access_token(data)

    assert data == {"sub": "user@example.com"}


def test_tokens_have_unique_jti(jwt_manager):
    first = jwt_manager.decode_access_token(jwt_manager.create_access_token({"a": 1}))
    second = jwt_manager.decode_access_token(jwt_manager.create_access_token({"a": 1}))

    assert first["jti"] != second["jti"]


def test_default_expiration_times(jwt_manager):
    now = time.time()
    access = jwt_manager.decode_access_token(jwt_manager.create_access_token({}))
    refresh = jwt_manager.decode_refresh_token(jwt_manager.create_refresh_token({}))

    assert abs(access["exp"] - (now + 60 * 60)) < 5
    assert abs(refresh["exp"] - (now + 7 * 24 * 60 * 60)) < 5


def test_custom_expiration(jwt_manager):
    now = time.time()
    token = jwt_manager.create_access_token({}, expires_delta=timedelta(minutes=5))

    assert abs(jwt_manager.decode_access_token(token)["exp"] - (now + 300)) < 5


def test_expired_tokens_raise_token_expired(jwt_manager):
    delta = timedelta(seconds=-1)
    access = jwt_manager.create_access_token({}, expires_delta=delta)
    refresh = jwt_manager.create_refresh_token({}, expires_delta=delta)

    with pytest.raises(TokenExpiredError):
        jwt_manager.decode_access_token(access)
    with pytest.raises(TokenExpiredError):
        jwt_manager.decode_refresh_token(refresh)


@pytest.mark.parametrize("garbage", ["", "garbage", "a.b.c"])
def test_garbage_token_raises_invalid_token(jwt_manager, garbage):
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_access_token(garbage)
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_refresh_token(garbage)


def test_access_and_refresh_tokens_are_not_interchangeable(jwt_manager):
    access = jwt_manager.create_access_token({"sub": "x"})
    refresh = jwt_manager.create_refresh_token({"sub": "x"})

    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_refresh_token(access)
    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_access_token(refresh)


def test_token_signed_with_other_secret_is_rejected(jwt_manager):
    other = JWTAuthManager("other-access", "other-refresh", "HS256")

    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_access_token(other.create_access_token({"sub": "x"}))


def test_token_signed_with_other_algorithm_is_rejected(jwt_manager):
    other = JWTAuthManager("access-secret", "refresh-secret", "HS512")

    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_access_token(other.create_access_token({"sub": "x"}))


def test_tampered_token_is_rejected(jwt_manager):
    token = jwt_manager.create_access_token({"sub": "x"})
    head, body, signature = token.split(".")
    tampered = ".".join(
        [head, body[:-2] + ("AA" if body[-2:] != "AA" else "BB"), signature]
    )

    with pytest.raises(InvalidTokenError):
        jwt_manager.decode_access_token(tampered)


def test_verify_or_raise_methods(jwt_manager):
    access = jwt_manager.create_access_token({})
    refresh = jwt_manager.create_refresh_token({})

    assert jwt_manager.verify_access_token_or_raise(access) is None
    assert jwt_manager.verify_refresh_token_or_raise(refresh) is None
    with pytest.raises(InvalidTokenError):
        jwt_manager.verify_access_token_or_raise("garbage")
    with pytest.raises(InvalidTokenError):
        jwt_manager.verify_refresh_token_or_raise(access)
    with pytest.raises(TokenExpiredError):
        jwt_manager.verify_access_token_or_raise(
            jwt_manager.create_access_token({}, expires_delta=timedelta(seconds=-1))
        )
