from dataclasses import dataclass, field
from uuid import UUID


class RagProcessingError(Exception):
    """A stable, user-displayable processing failure."""


class EmbeddingInputError(RagProcessingError):
    """A stable validation failure for an overlong embedding input."""


@dataclass(frozen=True)
class ParsedBlock:
    text: str
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    source_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    chunk_text: str
    page_start: int | None
    page_end: int | None
    section_title: str | None
    row_start: int | None
    row_end: int | None
    content_hash: str


@dataclass(frozen=True)
class Citation:
    citation_id: int
    document_id: UUID
    chunk_id: UUID
    document_name: str
    page_start: int | None
    page_end: int | None
    section_title: str | None
    row_start: int | None
    row_end: int | None
    quote: str
    source_type: str = "ENTERPRISE_DOCUMENT"
    evidence_category: str | None = None
    worksheet: str | None = None
    record_id: str | None = None
    source_id: str | None = None
    usage_restriction: str | None = None


@dataclass(frozen=True)
class KnowledgeSearchItem:
    document_id: UUID
    document_name: str
    chunk_id: UUID
    chunk_index: int
    chunk_text: str
    score: float
    page_start: int | None
    page_end: int | None
    section_title: str | None
    row_start: int | None
    row_end: int | None
    product_id: int | None
    product_ids: list[int]
    file_type: str
    citation: Citation
    chunk_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ContextResult:
    context: str
    citations: list[Citation]
    items: list[KnowledgeSearchItem]
