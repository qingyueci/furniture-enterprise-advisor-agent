from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import CurrentUser


def normalize_username(value: str) -> str:
    return value.strip().lower()


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=64)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_username(value)


class LoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUser


class LogoutData(BaseModel):
    logged_out: bool = True
