from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Document, DocumentPermission, DocumentProduct, User
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.document import DocumentData, DocumentPermissionUpdate
from app.services.file_storage_service import FileStorageService

VALID_ROLES = ("ADMIN", "PRODUCT_MANAGER", "SALES")


@dataclass(frozen=True)
class DownloadFile:
    path: Path
    original_name: str
    file_type: str


class DocumentService:
    def __init__(self, documents: DocumentRepository | None = None, storage: FileStorageService | None = None):
        self.documents = documents or DocumentRepository()
        self.knowledge = KnowledgeRepository()
        self.storage = storage or FileStorageService()

    @staticmethod
    def _normalize_roles(roles: list[str]) -> list[str]:
        if not roles or any(role not in VALID_ROLES for role in roles):
            raise AppError(422, "VALIDATION_ERROR", "文档角色权限不符合要求")
        chosen = set(roles)
        chosen.add("ADMIN")
        return [role for role in VALID_ROLES if role in chosen]

    def _to_data(self, session: Session, document: Document, *, admin: bool) -> DocumentData:
        return DocumentData(
            id=document.id, document_name=document.document_name, original_name=document.original_name,
            file_type=document.file_type, file_size=document.file_size, security_level=document.security_level,
            parse_status=document.parse_status, parse_error=document.parse_error if admin else None,
            upload_user_id=document.upload_user_id, product_ids=self.documents.product_ids(session, document.id),
            allowed_roles=self.documents.allowed_roles(session, document.id) if admin else None,
            created_at=document.created_at, updated_at=document.updated_at,
        )

    def list_documents(self, session: Session, *, user: User, keyword: str | None, file_type: str | None,
                       parse_status: str | None, product_id: int | None, page: int, page_size: int):
        statement = self.documents.list_query(role=user.role, keyword=keyword, file_type=file_type,
                                              parse_status=parse_status, product_id=product_id)
        total = self.documents.count(session, statement)
        items = list(session.scalars(statement.offset((page - 1) * page_size).limit(page_size)))
        return [self._to_data(session, item, admin=user.role == "ADMIN") for item in items], total

    def get_accessible(self, session: Session, *, document_id: UUID, user: User) -> Document:
        document = self.documents.get_accessible(session, document_id=document_id, role=user.role)
        if document is None:
            raise AppError(404, "DOCUMENT_NOT_ACCESSIBLE", "未找到可访问的文档")
        return document

    def detail(self, session: Session, *, document_id: UUID, user: User) -> DocumentData:
        document = self.get_accessible(session, document_id=document_id, user=user)
        return self._to_data(session, document, admin=user.role == "ADMIN")

    async def upload(self, session: Session, *, upload: UploadFile, document_name: str, security_level: str,
                     allowed_roles: list[str], product_ids: list[int], user: User) -> Document:
        if user.role != "ADMIN":
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        clean_name = document_name.strip()
        if not clean_name or len(clean_name) > 255:
            raise AppError(422, "VALIDATION_ERROR", "文档名称不符合要求")
        roles = self._normalize_roles(allowed_roles)
        products = list(dict.fromkeys(product_ids))
        stored = await self.storage.save_upload(upload)
        try:
            if not self.documents.products_exist(session, products):
                raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
            document = Document(document_name=clean_name, original_name=stored.original_name,
                                file_type=stored.file_type, file_size=stored.size, file_path=str(stored.path),
                                checksum_sha256=stored.checksum_sha256, security_level=security_level,
                                parse_status="PARSING", parse_error=None, upload_user_id=user.id)
            session.add(document)
            session.flush()
            session.add_all(DocumentPermission(document_id=document.id, role=role) for role in roles)
            session.add_all(DocumentProduct(document_id=document.id, product_id=product_id) for product_id in products)
            session.commit()
            session.refresh(document)
            return document
        except Exception:
            session.rollback()
            self.storage.remove_exact(stored.path)
            raise

    def download(self, session: Session, *, document_id: UUID, user: User) -> DownloadFile:
        document = self.get_accessible(session, document_id=document_id, user=user)
        path = self.storage._inside(Path(document.file_path), self.storage.upload_dir)
        if not path.is_file():
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成")
        return DownloadFile(path, document.original_name, document.file_type)

    def update_permissions(self, session: Session, *, document_id: UUID, payload: DocumentPermissionUpdate,
                           user: User) -> DocumentData:
        if user.role != "ADMIN":
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        document = self.get_accessible(session, document_id=document_id, user=user)
        previous_roles = set(self.documents.allowed_roles(session, document.id))
        roles = self._normalize_roles(list(payload.allowed_roles))
        document.security_level = payload.security_level
        self.documents.replace_permissions(session, document.id, roles)
        # File permissions and source-level retrieval_roles are intentionally
        # independent: a public chunk may remain searchable when its original
        # workbook is restricted.  Once a role is explicitly removed from the
        # document, however, preserve that revocation for already-indexed
        # retrieval-only chunks in the same transaction.
        self.knowledge.revoke_retrieval_roles(
            session, document_id=document.id, roles=previous_roles - set(roles),
        )
        session.commit()
        session.refresh(document)
        return self._to_data(session, document, admin=True)

    def delete(self, session: Session, *, document_id: UUID, user: User) -> None:
        if user.role != "ADMIN":
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        document = self.get_accessible(session, document_id=document_id, user=user)
        source, isolated = self.storage.quarantine(document.file_path)
        try:
            session.delete(document)
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            self.storage.restore(source, isolated)
            raise
        self.storage.remove_exact(isolated)
