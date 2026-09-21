"""阶段 1 数据模型；不包含认证、检索和 Agent 业务。"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (BigInteger, CHAR, CheckConstraint, DateTime, ForeignKey, Index,
                        Integer, MetaData, Numeric, String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UpdatedAt(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(UpdatedAt, Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    token_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','PRODUCT_MANAGER','SALES')", name="role"),
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="status"),
        CheckConstraint("token_version >= 0", name="token_version"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        Index("ix_users_role_status", "role", "status"),
    )


class Product(UpdatedAt, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(120), index=True)
    model: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str | None] = mapped_column(String(80))
    brand: Mapped[str] = mapped_column(String(80))
    product_type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (
        UniqueConstraint("brand", "model", name="uq_products_brand_model"),
        CheckConstraint("product_type IN ('INTERNAL','COMPETITOR')", name="product_type"),
        Index("ix_products_type_category", "product_type", "category"),
    )


class ProductPrice(CreatedAt, Base):
    __tablename__ = "product_prices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(CHAR(3), server_default=text("'CNY'"))
    price_type: Mapped[str] = mapped_column(String(32))
    quote_spec: Mapped[str | None] = mapped_column(String(80))
    pricing_unit: Mapped[str | None] = mapped_column(String(20))
    included_scope: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(255))
    update_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("price_type IN ('GUIDE','SALES','INTERNAL_QUOTE')", name="price_type"),
        Index("ix_product_prices_current", "product_id", "price_type", update_time.desc()),
        Index("ix_product_prices_update_time", update_time.desc()),
    )


class Document(UpdatedAt, Base):
    __tablename__ = "documents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_name: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))
    file_size: Mapped[int] = mapped_column(BigInteger)
    file_path: Mapped[str] = mapped_column(String(500), unique=True)
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64))
    security_level: Mapped[str] = mapped_column(String(32), index=True)
    parse_status: Mapped[str] = mapped_column(String(16))
    parse_error: Mapped[str | None] = mapped_column(String(500))
    upload_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    __table_args__ = (
        CheckConstraint("file_type IN ('PDF','DOCX','XLSX')", name="file_type"),
        CheckConstraint("file_size > 0", name="file_size"),
        CheckConstraint("security_level IN ('PUBLIC','INTERNAL','RESTRICTED')", name="security_level"),
        CheckConstraint("parse_status IN ('UPLOADING','PARSING','READY','FAILED')", name="parse_status"),
        Index("ix_documents_status_created", "parse_status", text("created_at DESC")),
    )


class DocumentPermission(CreatedAt, Base):
    __tablename__ = "document_permissions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    __table_args__ = (
        UniqueConstraint("document_id", "role", name="uq_document_permissions_document_role"),
        CheckConstraint("role IN ('ADMIN','PRODUCT_MANAGER','SALES')", name="role"),
        Index("ix_document_permissions_role_document", "role", "document_id"),
    )


class DocumentProduct(CreatedAt, Base):
    __tablename__ = "document_products"
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True)
    __table_args__ = (Index("ix_document_products_product_document", "product_id", "document_id"),)


class DocumentChunk(CreatedAt, Base):
    __tablename__ = "document_chunks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(255))
    row_start: Mapped[int | None] = mapped_column(Integer)
    row_end: Mapped[int | None] = mapped_column(Integer)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index"),
    )


class Conversation(UpdatedAt, Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(120))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", text("updated_at DESC")),)


class Message(CreatedAt, Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    tool_summary: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    warnings: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    structured_data: Mapped[dict | None] = mapped_column(JSONB)
    task_type: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        CheckConstraint("role IN ('USER','ASSISTANT')", name="role"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )


class AuditLog(CreatedAt, Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    request_ip: Mapped[str | None] = mapped_column(String(45))
    result: Mapped[str] = mapped_column(String(16))
    detail: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    __table_args__ = (
        CheckConstraint("result IN ('SUCCESS','FAILED','DENIED')", name="result"),
        Index("ix_audit_logs_created", text("created_at DESC")),
        Index("ix_audit_logs_user_created", "user_id", text("created_at DESC")),
        Index("ix_audit_logs_action_created", "action", text("created_at DESC")),
        Index("ix_audit_logs_result_created", "result", text("created_at DESC")),
    )
