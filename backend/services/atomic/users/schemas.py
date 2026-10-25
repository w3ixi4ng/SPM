from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class SignUpRequest(UserBase):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # 72 bytes is bcrypt's limit -- everything past it is dropped before
    # hashing, so a longer password is not the stronger one it looks like.
    password: str = Field(min_length=8, max_length=72)
    # The only roles anyone may give themselves. Every other role is assigned
    # by an administrator, so it is a 422 here rather than a quiet promotion.
    role: Literal["attendee", "event_organiser"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    # Deliberately not the sign-up rules. Validating a login against the
    # current policy would 422 every account made under an older one, and
    # would tell an attacker what the policy is. Wrong credentials are a 401.
    password: str = Field(min_length=1, max_length=72)


class UserRead(UserBase):
    # The profile shares its id with the Supabase Auth user, so it is a uuid.
    id: str


class CoordinatorRead(BaseModel):
    """Trusted Auth eligibility with optional profile display enrichment."""

    id: str
    name: str
    email: EmailStr | None


class CurrentUserRead(UserRead):
    # This comes from verified Supabase Auth app_metadata, never users.users or
    # user_metadata. None lets clients fail closed for older unassigned users.
    role: str | None


class ProfileLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(max_length=100)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, values: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(values))
