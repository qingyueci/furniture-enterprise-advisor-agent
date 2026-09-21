from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentPermission, DocumentProduct, Product


class DocumentRepository:
    def list_query(self, *, role: str, keyword: str | None, file_type: str | None,
                   parse_status: str | None, product_id: int | None) -> Select[tuple[Document]]:
        statement = select(Document)
        if role != "ADMIN":
            statement = statement.join(DocumentPermission).where(DocumentPermission.role == role)
        if product_id is not None:
            statement = statement.join(DocumentProduct).where(DocumentProduct.product_id == product_id)
        if keyword:
            needle = f"%{keyword.strip()}%"
            statement = statement.where(Document.document_name.ilike(needle))
        if file_type:
            statement = statement.where(Document.file_type == file_type)
        if parse_status:
            statement = statement.where(Document.parse_status == parse_status)
        return statement.distinct().order_by(Document.created_at.desc(), Document.id.desc())

    def get_accessible(self, session: Session, *, document_id: UUID, role: str) -> Document | None:
        statement = select(Document).where(Document.id == document_id)
        if role != "ADMIN":
            statement = statement.join(DocumentPermission).where(DocumentPermission.role == role)
        return session.scalar(statement)

    def get_by_id(self, session: Session, document_id: UUID) -> Document | None:
        return session.get(Document, document_id)

    def count(self, session: Session, statement: Select[tuple[Document]]) -> int:
        return session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0

    def product_ids(self, session: Session, document_id: UUID) -> list[int]:
        return list(session.scalars(select(DocumentProduct.product_id).where(
            DocumentProduct.document_id == document_id).order_by(DocumentProduct.product_id)))

    def allowed_roles(self, session: Session, document_id: UUID) -> list[str]:
        order = {"ADMIN": 0, "PRODUCT_MANAGER": 1, "SALES": 2}
        roles = list(session.scalars(select(DocumentPermission.role).where(DocumentPermission.document_id == document_id)))
        return sorted(roles, key=order.__getitem__)

    def products_exist(self, session: Session, product_ids: list[int]) -> bool:
        if not product_ids:
            return True
        # 软删除产品保留历史关联，但不能再被用于新资料的关联。
        found = session.scalar(select(func.count()).select_from(Product).where(
            Product.id.in_(product_ids), Product.deleted_at.is_(None),
        )) or 0
        return found == len(product_ids)

    def replace_permissions(self, session: Session, document_id: UUID, roles: list[str]) -> None:
        session.execute(delete(DocumentPermission).where(DocumentPermission.document_id == document_id))
        session.add_all(DocumentPermission(document_id=document_id, role=role) for role in roles)
