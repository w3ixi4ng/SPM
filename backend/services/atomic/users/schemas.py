from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class SignUpRequest(UserBase):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # 72 bytes is bcrypt's limit -- everything past it is dropped before
    # hashing, so a longer password is not the stronger one it looks like.
    password: str = Field(min_length=8, max_length=72)


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


class CurrentUserRead(UserRead):
    # This comes from verified Supabase Auth app_metadata, never users.users or
    # user_metadata. None lets clients fail closed for older unassigned users.
    role: str | None
