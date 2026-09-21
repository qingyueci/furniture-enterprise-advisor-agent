from typing import Generic, TypeVar
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiSuccess(BaseModel, Generic[T]):
    success: bool = True
    data: T
    request_id: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: None = None


class ApiError(BaseModel):
    success: bool = False
    error: ErrorBody
    request_id: str


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    role: str
    status: str
    created_at: datetime


class Pagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
