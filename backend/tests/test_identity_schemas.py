import pytest
from pydantic import ValidationError

from app.modules.identity.schemas import RegisterRequest, normalise_institute_email

VALID = {"name": "A Student", "email": "a@iitk.ac.in", "password": "12345678"}


def test_email_is_normalised_to_lower_case() -> None:
    assert normalise_institute_email("  A.B@IITK.AC.IN ") == "a.b@iitk.ac.in"


@pytest.mark.parametrize(
    "email",
    [
        "a@gmail.com",
        "a@cse.iitk.ac.in",
        "a@iitk.ac.in.evil.com",
        "iitk.ac.in",
        "@iitk.ac.in",
        "a@b@iitk.ac.in",
        "a b@iitk.ac.in",
    ],
)
def test_non_institute_or_malformed_email_is_rejected(email: str) -> None:
    with pytest.raises(ValueError):
        normalise_institute_email(email)


def test_password_shorter_than_8_characters_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate({**VALID, "password": "1234567"})


def test_blank_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate({**VALID, "name": "   "})


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate({**VALID, "role": "ADMIN"})
