from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, delete, exists, func, not_, or_, select, update
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentPermission, DocumentProduct


def _like_escape(value: str) -> str:
    """转义用户词面中的 LIKE 通配符，避免把普通字符当成模式。"""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class KnowledgeRepository:
    def delete_chunks(self, session: Session, document_id: UUID) -> None:
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))

    @staticmethod
    def _visibility_clauses(*, role: str, product_ids: list[int] | None,
                            document_types: list[str] | None,
                            embedding_provider: str, embedding_model: str,
                            embedding_dimensions: int, embedding_revision: str,
                            document_ids: list[UUID] | None) -> list:
        """文档、权限、范围与索引有效性条件；向量与词面检索共用同一组合。"""

        clauses = [
            Document.parse_status == "READY",
            DocumentChunk.chunk_metadata["embedding_provider"].astext == embedding_provider,
            DocumentChunk.chunk_metadata["embedding_model"].astext == embedding_model,
            DocumentChunk.chunk_metadata["embedding_dimensions"].as_integer() == embedding_dimensions,
            DocumentChunk.chunk_metadata["embedding_revision"].astext == embedding_revision,
        ]
        if role != "ADMIN":
            document_permission = exists(select(DocumentPermission.id).where(
                DocumentPermission.document_id == Document.id,
                DocumentPermission.role == role,
            ))
            retrieval_permission = DocumentChunk.chunk_metadata["retrieval_roles"].op("?")(role)
            retrieval_revoked = func.coalesce(
                DocumentChunk.chunk_metadata["retrieval_revoked_roles"].op("?")(role), False,
            )
            # ``retrieval_roles`` is a source-level allow list for chunks that may be
            # searchable without exposing the original file.  A management revoke is
            # an explicit deny overlay.  File access still implies chunk access, so a
            # role present in document_permissions is not accidentally locked out by
            # a stale source-level deny marker.
            clauses.append(or_(
                document_permission,
                and_(retrieval_permission, not_(retrieval_revoked)),
            ))
        if product_ids:
            clauses.append(exists(select(DocumentProduct.document_id).where(
                DocumentProduct.document_id == Document.id,
                DocumentProduct.product_id.in_(product_ids),
            )))
        if document_types:
            clauses.append(Document.file_type.in_(document_types))
        if document_ids:
            clauses.append(Document.id.in_(document_ids))
        return clauses

    def search_statement(self, *, role: str, query_embedding: list[float], product_ids: list[int] | None,
                         document_types: list[str] | None, min_similarity: float,
                         embedding_provider: str, embedding_model: str,
                         embedding_dimensions: int, embedding_revision: str,
                         document_ids: list[UUID] | None = None) -> Select:
        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        statement = (select(DocumentChunk, Document, distance)
                     .join(Document, Document.id == DocumentChunk.document_id)
                     .where(*self._visibility_clauses(
                         role=role, product_ids=product_ids, document_types=document_types,
                         embedding_provider=embedding_provider, embedding_model=embedding_model,
                         embedding_dimensions=embedding_dimensions,
                         embedding_revision=embedding_revision, document_ids=document_ids,
                     )))
        statement = statement.where(distance <= 1.0 - min_similarity)
        return statement.order_by(distance.asc(), DocumentChunk.id.asc())

    def search_lexical_statement(self, *, role: str, query_embedding: list[float],
                                 anchors: list[str], intents: list[str],
                                 product_ids: list[int] | None,
                                 document_types: list[str] | None,
                                 embedding_provider: str, embedding_model: str,
                                 embedding_dimensions: int, embedding_revision: str,
                                 document_ids: list[UUID] | None = None) -> Select:
        """词面候选补充：Chunk 正文同时命中至少一个锚点词与一个意图词。

        不适用向量相似度下限，但复用与向量检索完全相同的文档、权限、范围和索引
        有效性条件；调用方按 Chunk 与向量候选去重后再排序。
        """

        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        statement = (select(DocumentChunk, Document, distance)
                     .join(Document, Document.id == DocumentChunk.document_id)
                     .where(*self._visibility_clauses(
                         role=role, product_ids=product_ids, document_types=document_types,
                         embedding_provider=embedding_provider, embedding_model=embedding_model,
                         embedding_dimensions=embedding_dimensions,
                         embedding_revision=embedding_revision, document_ids=document_ids,
                     )))
        if anchors:
            statement = statement.where(or_(*[
                DocumentChunk.chunk_text.ilike(f"%{_like_escape(term)}%", escape="\\") for term in anchors
            ]))
        if intents:
            statement = statement.where(or_(*[
                DocumentChunk.chunk_text.ilike(f"%{_like_escape(term)}%", escape="\\") for term in intents
            ]))
        return statement.order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())

    def read_chunks(self, session: Session, *, document_id: UUID, role: str,
                    page_start: int | None, page_end: int | None, limit: int) -> list[DocumentChunk]:
        # 整文档读取也把实时文档授权放进取 Chunk 的 SQL；前置的详情检查
        # 只是资源隐藏语义，读取授权仍由该查询本身承担。
        statement = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.document_id == document_id,
                Document.parse_status == "READY",
            )
        )
        if role != "ADMIN":
            statement = statement.join(
                DocumentPermission,
                (DocumentPermission.document_id == Document.id) & (DocumentPermission.role == role),
            )
        if page_start is not None and page_end is not None:
            statement = statement.where(
                DocumentChunk.page_start.is_not(None),
                DocumentChunk.page_end.is_not(None),
                DocumentChunk.page_end >= page_start,
                DocumentChunk.page_start <= page_end,
            )
        return list(session.scalars(statement.order_by(DocumentChunk.chunk_index.asc()).limit(limit)))

    def product_ids(self, session: Session, document_id: UUID) -> list[int]:
        return list(session.scalars(select(DocumentProduct.product_id).where(
            DocumentProduct.document_id == document_id).order_by(DocumentProduct.product_id)))

    def revoke_retrieval_roles(self, session: Session, *, document_id: UUID,
                               roles: set[str]) -> int:
        """Apply a document-management deny overlay to existing chunks.

        Source imports may intentionally expose selected chunks to a role that
        cannot read the original workbook.  Removing that role from the
        document's file permissions must still stop those already-indexed
        chunks from entering a later RAG request.  The overlay is stored in
        chunk metadata, so no embedding or re-chunking is required and the
        source-level ``retrieval_roles`` allow list remains intact for roles
        that were not revoked.
        """

        normalized = {role for role in roles if role in {"ADMIN", "PRODUCT_MANAGER", "SALES"}}
        if not normalized:
            return 0
        chunks = list(session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id).with_for_update()
        ))
        changed = 0
        for chunk in chunks:
            metadata = dict(chunk.chunk_metadata or {})
            current = {
                str(role) for role in (metadata.get("retrieval_revoked_roles") or [])
                if str(role) in {"ADMIN", "PRODUCT_MANAGER", "SALES"}
            }
            updated = current | normalized
            if updated == current:
                continue
            metadata["retrieval_revoked_roles"] = sorted(updated)
            chunk.chunk_metadata = metadata
            changed += 1
        return changed

    def allowed(self, session: Session, document_id: UUID, role: str) -> bool:
        if role == "ADMIN":
            return session.scalar(select(Document.id).where(Document.id == document_id,
                                                            Document.parse_status == "READY")) is not None
        return session.scalar(select(DocumentPermission.id).join(Document).where(
            DocumentPermission.document_id == document_id,
            DocumentPermission.role == role,
            Document.parse_status == "READY",
        )) is not None

    def allowed_chunk(self, session: Session, *, chunk_id: UUID, document_id: UUID,
                      role: str) -> bool:
        statement = select(DocumentChunk.id).join(Document).where(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id,
            Document.parse_status == "READY",
        )
        if role != "ADMIN":
            document_permission = exists(select(DocumentPermission.id).where(
                DocumentPermission.document_id == document_id,
                DocumentPermission.role == role,
            ))
            retrieval_permission = DocumentChunk.chunk_metadata["retrieval_roles"].op("?")(role)
            retrieval_revoked = func.coalesce(
                DocumentChunk.chunk_metadata["retrieval_revoked_roles"].op("?")(role), False,
            )
            statement = statement.where(or_(
                document_permission,
                and_(retrieval_permission, not_(retrieval_revoked)),
            ))
        return session.scalar(statement) is not None

    def mark_stale(self, session: Session, cutoff: datetime, message: str) -> int:
        result = session.execute(update(Document).where(
            Document.parse_status == "PARSING", Document.updated_at < cutoff,
        ).values(parse_status="FAILED", parse_error=message, updated_at=func.now()))
        return result.rowcount or 0
