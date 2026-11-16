from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from online_cinema_api.db.models.accounts import GenderEnum, UserGroupEnum
from online_cinema_api.schemas.accounts import (
    MeResponseSchema,
    PasswordResetCompleteRequestSchema,
    PasswordResetRequestSchema,
    ProfileResponseSchema,
    ProfileUpdateSchema,
    Token,
    TokenRefreshRequestSchema,
    TokenRefreshResponseSchema,
    UserActivationRequestSchema,
    UserCreate,
    UserLoginRequestSchema,
    UserLoginResponseSchema,
    UserRead,
    UserRegistrationRequestSchema,
    UserRegistrationResponseSchema,
)

from .conftest import VALID_PASSWORD


def test_registration_lowercases_email():
    schema = UserRegistrationRequestSchema(
        email="User@Example.COM", password=VALID_PASSWORD
    )

    assert schema.email == "user@example.com"
    assert schema.password == VALID_PASSWORD


@pytest.mark.parametrize(
    "password", ["short1!", "nouppercase1!", "NoDigits!!", "NoSpecial12"]
)
def test_registration_rejects_weak_password(password):
    with pytest.raises(ValidationError):
        UserRegistrationRequestSchema(email="user@example.com", password=password)


def test_registration_rejects_invalid_email():
    with pytest.raises(ValidationError):
        UserRegistrationRequestSchema(email="not-an-email", password=VALID_PASSWORD)


def test_password_reset_complete_requires_token_and_strong_password():
    schema = PasswordResetCompleteRequestSchema(
        email="a@example.com", password=VALID_PASSWORD, token="tkn"
    )
    assert schema.token == "tkn"

    with pytest.raises(ValidationError):
        PasswordResetCompleteRequestSchema(
            email="a@example.com", password=VALID_PASSWORD
        )
    with pytest.raises(ValidationError):
        PasswordResetCompleteRequestSchema(
            email="a@example.com", password="weak", token="tkn"
        )


def test_password_reset_request_validates_email():
    assert PasswordResetRequestSchema(email="a@example.com").email == "a@example.com"
    with pytest.raises(ValidationError):
        PasswordResetRequestSchema(email="nope")


def test_login_lowercases_email_and_does_not_check_password_strength():
    schema = UserLoginRequestSchema(email="User@Example.COM", password="weak")

    assert schema.email == "user@example.com"
    assert schema.password == "weak"


def test_login_response_default_token_type():
    schema = UserLoginResponseSchema(access_token="a", refresh_token="r")

    assert schema.token_type == "bearer"


def test_token_refresh_schemas():
    assert TokenRefreshRequestSchema(refresh_token="r").refresh_token == "r"
    assert TokenRefreshResponseSchema(access_token="a").token_type == "bearer"
    assert Token(access_token="a", token_type="bearer").access_token == "a"


def test_activation_request_requires_email_and_token():
    schema = UserActivationRequestSchema(email="a@example.com", token="t")
    assert schema.token == "t"

    with pytest.raises(ValidationError):
        UserActivationRequestSchema(email="a@example.com")


def test_user_read_from_orm_object_ignores_extra_attributes():
    obj = SimpleNamespace(id=5, email="a@example.com", is_active=True, secret="x")

    user = UserRead.model_validate(obj)

    assert user.id == 5
    assert user.email == "a@example.com"
    assert not hasattr(user, "secret")


def test_registration_response_from_attributes():
    obj = SimpleNamespace(id=1, email="a@example.com")

    assert UserRegistrationResponseSchema.model_validate(obj).id == 1


def test_user_create_has_no_password_validation():
    assert UserCreate(email="a@example.com", password="weak").password == "weak"


def test_profile_update_all_fields_optional():
    schema = ProfileUpdateSchema()

    assert schema.model_dump() == {
        "first_name": None,
        "last_name": None,
        "gender": None,
        "date_of_birth": None,
        "info": None,
    }


def test_profile_update_strips_names():
    schema = ProfileUpdateSchema(first_name="  Ann  ", last_name="\tLee\n")

    assert schema.first_name == "Ann"
    assert schema.last_name == "Lee"


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_profile_update_blank_names_become_none(blank):
    schema = ProfileUpdateSchema(first_name=blank, last_name=blank)

    assert schema.first_name is None
    assert schema.last_name is None


def test_profile_update_name_max_length():
    assert ProfileUpdateSchema(first_name="a" * 100).first_name == "a" * 100
    with pytest.raises(ValidationError):
        ProfileUpdateSchema(first_name="a" * 101)


def test_profile_update_forbids_extra_fields():
    with pytest.raises(ValidationError):
        ProfileUpdateSchema(avatar="http://x/y.png")


def test_profile_update_birth_date_in_future_is_rejected():
    with pytest.raises(ValidationError, match="future"):
        ProfileUpdateSchema(date_of_birth=date.today() + timedelta(days=1))


@pytest.mark.parametrize("delta", [0, 1, 365 * 30])
def test_profile_update_birth_date_today_or_past_is_ok(delta):
    value = date.today() - timedelta(days=delta)

    assert ProfileUpdateSchema(date_of_birth=value).date_of_birth == value


def test_profile_update_gender():
    assert ProfileUpdateSchema(gender="woman").gender is GenderEnum.WOMAN
    with pytest.raises(ValidationError):
        ProfileUpdateSchema(gender="other")


def test_profile_response_from_attributes():
    obj = SimpleNamespace(
        first_name="Ann",
        last_name=None,
        avatar=None,
        gender=GenderEnum.WOMAN,
        date_of_birth=date(1990, 1, 1),
        info=None,
    )

    schema = ProfileResponseSchema.model_validate(obj)

    assert schema.first_name == "Ann"
    assert schema.gender is GenderEnum.WOMAN
    assert schema.date_of_birth == date(1990, 1, 1)


def test_me_response_with_and_without_profile():
    base = {"id": 1, "email": "a@example.com", "is_active": True, "group": "admin"}

    without_profile = MeResponseSchema(**base, profile=None)
    assert without_profile.group is UserGroupEnum.ADMIN
    assert without_profile.profile is None

    with_profile = MeResponseSchema(
        **base,
        profile={
            "first_name": "Ann",
            "last_name": None,
            "avatar": None,
            "gender": None,
            "date_of_birth": None,
            "info": None,
        },
    )
    assert with_profile.profile.first_name == "Ann"


def test_me_response_profile_is_required_field():
    with pytest.raises(ValidationError):
        MeResponseSchema(id=1, email="a@example.com", is_active=True, group="user")
