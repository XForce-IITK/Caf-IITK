import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import Role

INSTITUTE_DOMAIN = "iitk.ac.in"


def normalise_institute_email(value: str) -> str:
    """Lower-case the address and require exactly one @ and the @iitk.ac.in domain (FR-1)."""
    email = value.strip().lower()
    local, sep, domain = email.partition("@")
    if not sep or not local or "@" in domain or any(c.isspace() for c in email):
        raise ValueError("must be a valid email address")
    if domain != INSTITUTE_DOMAIN:
        raise ValueError(f"must be an @{INSTITUTE_DOMAIN} address")
    return email


InstituteEmail = Annotated[str, Field(max_length=254), AfterValidator(normalise_institute_email)]


class RegisterRequest(BaseModel):
    # Unknown fields (e.g. role) are rejected with 422 (US-03 AC3).
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    email: InstituteEmail
    # Upper bound keeps hashing cost bounded; minimum from the SRS password NFR.
    password: Annotated[str, Field(min_length=8, max_length=128)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: Role
