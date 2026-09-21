from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_engine
from app.models import Document, DocumentChunk, DocumentPermission, DocumentProduct, User
from app.rag.chunker import build_chunks, split_chunks_for_embedding
from app.rag.cleaner import clean_blocks
from app.rag.embeddings import EmbeddingProvider, create_embedding_provider, validate_embeddings
from app.rag.parsers import parse_document
from app.rag.types import RagProcessingError
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.audit import AuditAction, AuditResourceType, AuditResult
from app.services.audit_service import AuditService
from app.services.file_storage_service import FileStorageService

FAILURE_GENERIC = "知识库处理失败，请检查文档后重新上传"
STALE_FAILURE = "知识库处理被中断，请删除后重新上传"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingSource:
    document_id: UUID
    document_name: str
    file_type: str
    file_path: Path
    product_ids: list[int]
    allowed_roles: list[str]
    upload_user_id: UUID
    upload_username: str | None
    audit_request_id: str | None = None
    audit_request_ip: str | None = None


def _session() -> Session:
    return SessionLocal(bind=get_engine())


def _stable_error(exc: Exception) -> str:
    if isinstance(exc, RagProcessingError):
        return str(exc)[:500]
    return FAILURE_GENERIC


class KnowledgeProcessor:
    def __init__(self, *, provider: EmbeddingProvider | None = None,
                 session_factory: Callable[[], Session] = _session,
                 storage: FileStorageService | None = None):
        self.provider = provider
        self.session_factory = session_factory
        self.storage = storage or FileStorageService()
        self.repository = KnowledgeRepository()

    def _load_source(
        self,
        document_id: UUID,
        *,
        audit_request_id: str | None = None,
        audit_request_ip: str | None = None,
    ) -> ProcessingSource | None:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None or document.parse_status != "PARSING":
                return None
            path = self.storage._inside(Path(document.file_path), self.storage.upload_dir)
            if not path.is_file():
                raise RagProcessingError("已保存的文档文件不存在")
            products = list(session.scalars(select(DocumentProduct.product_id).where(
                DocumentProduct.document_id == document.id).order_by(DocumentProduct.product_id)))
            roles = list(session.scalars(select(DocumentPermission.role).where(
                DocumentPermission.document_id == document.id).order_by(DocumentPermission.role)))
            username = session.scalar(select(User.username).where(User.id == document.upload_user_id))
            return ProcessingSource(
                document.id, document.document_name, document.file_type, path, products, roles,
                document.upload_user_id, username, audit_request_id, audit_request_ip,
            )

    @staticmethod
    def _audit_parse(source: ProcessingSource, *, success: bool) -> None:
        AuditService().record(
            action=AuditAction.DOCUMENT_PARSE_SUCCESS if success else AuditAction.DOCUMENT_PARSE_FAILED,
            result=AuditResult.SUCCESS if success else AuditResult.FAILED,
            user_id=source.upload_user_id,
            username=source.upload_username,
            request_id_value=source.audit_request_id,
            request_ip_value=source.audit_request_ip,
            resource_type=AuditResourceType.DOCUMENT,
            resource_id=source.document_id,
            error_code=None if success else "DOCUMENT_PARSE_FAILED",
        )

    def process(
        self,
        document_id: UUID,
        *,
        audit_request_id: str | None = None,
        audit_request_ip: str | None = None,
    ) -> None:
        source: ProcessingSource | None = None
        try:
            source = self._load_source(
                document_id,
                audit_request_id=audit_request_id,
                audit_request_ip=audit_request_ip,
            )
            if source is None:
                return
            blocks = clean_blocks(parse_document(source.file_path, source.file_type))
            provider = self.provider or create_embedding_provider()
            chunks = split_chunks_for_embedding(build_chunks(blocks), provider.split_document_text)
            vectors = validate_embeddings(
                provider.embed_documents([chunk.chunk_text for chunk in chunks]), len(chunks), provider.dimensions,
            )
            product_id = source.product_ids[0] if len(source.product_ids) == 1 else None
            rows: list[DocumentChunk] = []
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk_id = uuid4()
                metadata = {
                    "document_id": str(source.document_id), "document_name": source.document_name,
                    "chunk_id": str(chunk_id), "chunk_index": chunk.chunk_index,
                    "page_start": chunk.page_start, "page_end": chunk.page_end,
                    "section_title": chunk.section_title, "row_start": chunk.row_start, "row_end": chunk.row_end,
                    "product_id": product_id, "product_ids": source.product_ids,
                    "allowed_roles": source.allowed_roles, "file_type": source.file_type,
                    "content_hash": chunk.content_hash,
                    "embedding_provider": provider.provider_name, "embedding_model": provider.model_name,
                    "embedding_dimensions": provider.dimensions, "embedding_revision": provider.revision,
                }
                rows.append(DocumentChunk(
                    id=chunk_id, document_id=source.document_id, chunk_index=chunk.chunk_index,
                    chunk_text=chunk.chunk_text, page_start=chunk.page_start, page_end=chunk.page_end,
                    section_title=chunk.section_title, row_start=chunk.row_start, row_end=chunk.row_end,
                    product_id=product_id, content_hash=chunk.content_hash, chunk_metadata=metadata,
                    embedding=vector,
                ))
            with self.session_factory() as session:
                with session.begin():
                    document = session.get(Document, source.document_id, with_for_update=True)
                    if document is None or document.parse_status != "PARSING":
                        return
                    self.repository.delete_chunks(session, source.document_id)
                    session.add_all(rows)
                    document.parse_status = "READY"
                    document.parse_error = None
            self._audit_parse(source, success=True)
        except Exception as exc:
            failed_source = self._fail(
                document_id,
                _stable_error(exc),
                source=source,
                audit_request_id=audit_request_id,
                audit_request_ip=audit_request_ip,
            )
            if failed_source is not None:
                self._audit_parse(failed_source, success=False)

    def _fail(
        self,
        document_id: UUID,
        message: str,
        *,
        source: ProcessingSource | None = None,
        audit_request_id: str | None = None,
        audit_request_ip: str | None = None,
    ) -> ProcessingSource | None:
        try:
            with self.session_factory() as session:
                with session.begin():
                    document = session.get(Document, document_id, with_for_update=True)
                    if document is None or document.parse_status == "READY":
                        return None
                    username = session.scalar(select(User.username).where(User.id == document.upload_user_id))
                    failed_source = source or ProcessingSource(
                        document.id, document.document_name, document.file_type, Path(document.file_path),
                        [], [], document.upload_user_id, username, audit_request_id, audit_request_ip,
                    )
                    self.repository.delete_chunks(session, document_id)
                    document.parse_status = "FAILED"
                    document.parse_error = message[:500]
                return failed_source
        except Exception:
            logger.exception("RAG_FAILURE_TERMINAL_WRITE_FAILED document_id=%s", document_id)
            return None


def process_document_background(
    document_id: UUID,
    *,
    audit_request_id: str | None = None,
    audit_request_ip: str | None = None,
) -> None:
    KnowledgeProcessor().process(
        document_id,
        audit_request_id=audit_request_id,
        audit_request_ip=audit_request_ip,
    )


def mark_stale_parsing_failed() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=get_settings().parsing_stale_minutes)
    with _session() as session:
        with session.begin():
            documents = list(session.scalars(select(Document).where(
                Document.parse_status == "PARSING", Document.updated_at < cutoff,
            )))
            count = KnowledgeRepository().mark_stale(session, cutoff, STALE_FAILURE)
        for document in documents:
            username = session.scalar(select(User.username).where(User.id == document.upload_user_id))
            AuditService().record(
                action=AuditAction.DOCUMENT_PARSE_FAILED,
                result=AuditResult.FAILED,
                user_id=document.upload_user_id,
                username=username,
                resource_type=AuditResourceType.DOCUMENT,
                resource_id=document.id,
                error_code="DOCUMENT_PARSE_FAILED",
            )
        return count
