import pytest

from online_cinema_api.db.validators import accounts as validators


@pytest.mark.parametrize("password", ["StrongPass1!", "Aa1@aaaa", "Xy9#abcdefgh"])
def test_validate_password_strength_accepts_valid_password(password):
    assert validators.validate_password_strength(password) == password


@pytest.mark.parametrize("special", list("@$!%*?&#"))
def test_validate_password_strength_accepts_each_allowed_special_char(special):
    password = f"Abcdef1{special}"
    assert validators.validate_password_strength(password) == password


@pytest.mark.parametrize(
    ("password", "expected_fragment"),
    [
        ("Ab1!xyz", "at least 8 characters"),
        ("lowercase1!", "uppercase letter"),
        ("UPPERCASE1!", "lower letter"),
        ("NoDigits!!", "digit"),
        ("NoSpecial12", "special character"),
        ("Passw0rd^^", "special character"),
        ("", "at least 8 characters"),
    ],
)
def test_validate_password_strength_rejects_weak_password(password, expected_fragment):
    with pytest.raises(ValueError, match=expected_fragment):
        validators.validate_password_strength(password)


def test_validate_email_returns_normalized_address():
    result = validators.validate_email("User@EXAMPLE.com")

    assert result.lower() == "user@example.com"
    assert result.split("@")[1] == "example.com"


def test_validate_email_keeps_valid_lowercase_address_unchanged():
    assert validators.validate_email("user@example.com") == "user@example.com"


@pytest.mark.parametrize("value", ["not-an-email", "user@", "@example.com", ""])
def test_validate_email_rejects_invalid_address(value):
    with pytest.raises(ValueError):
        validators.validate_email(value)
