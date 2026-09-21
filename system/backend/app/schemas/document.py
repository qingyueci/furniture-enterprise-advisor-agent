from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Pagination
from app.schemas.user import Role

FileType = Literal["PDF", "DOCX", "XLSX"]
ParseStatus = Literal["UPLOADING", "PARSING", "READY", "FAILED"]
SecurityLevel = Literal["PUBLIC", "INTERNAL", "RESTRICTED"]


class DocumentData(BaseModel):
    id: UUID
    document_name: str
    original_name: str
    file_type: FileType
    file_size: int
    security_level: SecurityLevel
    parse_status: ParseStatus
    parse_error: str | None
    upload_user_id: UUID
    product_ids: list[int]
    allowed_roles: list[Role] | None
    created_at: datetime
    updated_at: datetime


class DocumentListData(BaseModel):
    items: list[DocumentData]
    pagination: Pagination


class DocumentUploadData(BaseModel):
    document_id: UUID
    file_type: FileType
    parse_status: Literal["PARSING"]


class DocumentPermissionUpdate(BaseModel):
    security_level: SecurityLevel
    allowed_roles: list[Role] = Field(min_length=1)

    @field_validator("allowed_roles")
    @classmethod
    def normalize_roles(cls, roles: list[Role]) -> list[Role]:
        return list(dict.fromkeys(["ADMIN", *roles]))  # type: ignore[list-item]
