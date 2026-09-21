from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.auth import normalize_username
from app.schemas.common import CurrentUser, Pagination

Role = Literal["ADMIN", "PRODUCT_MANAGER", "SALES"]
Status = Literal["ACTIVE", "DISABLED"]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=64)
    role: Role
    status: Status

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_username(value)


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    role: Role | None = None
    status: Status | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=64)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        return normalize_username(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateUserRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class UserListData(BaseModel):
    items: list[CurrentUser]
    pagination: Pagination


class BulkUserDeleteRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=100)
