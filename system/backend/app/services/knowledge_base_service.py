from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import User
from app.rag.context_builder import ContextBuilder
from app.rag.embeddings import EmbeddingProvider, create_embedding_provider, validate_embeddings
from app.rag.types import Citation, ContextResult, EmbeddingInputError, KnowledgeSearchItem
from app.repositories.knowledge_repository import KnowledgeRepository
from app.security.rbac import has_permission

VALID_DOCUMENT_TYPES = {"PDF", "DOCX", "XLSX"}

# 词面补充是有限的召回兜底：只保留少量同时命中明确锚点与业务意图的 Chunk。
LEXICAL_SUPPLEMENT_LIMIT = 4


class KnowledgeBaseService:
    """知识库检索服务。

    向量检索之外可选词面候选补充；补充词由调用方（Agent 层）从当前问题提取，
    服务层只负责在既有权限、文档范围与索引有效性条件下将其与向量候选合并。
    """

    def __init__(self, *, provider: EmbeddingProvider | None = None,
                 repository: KnowledgeRepository | None = None):
        self.provider = provider
        self.repository = repository or KnowledgeRepository()

    def search(self, session: Session, *, query: str, current_user: User,
               product_ids: list[int] | None = None, top_k: int | None = None,
               document_types: list[str] | None = None,
               document_ids: list[UUID] | None = None,
               lexical_terms: tuple[list[str], list[str], list[str]] | None = None,
               ) -> list[KnowledgeSearchItem]:
        settings = get_settings()
        clean_query = query.strip()
        selected_products = list(dict.fromkeys(product_ids or []))
        selected_types = list(dict.fromkeys(document_types or []))
        limit = top_k if top_k is not None else settings.rag_top_k_default
        if not has_permission(current_user, "document:read_allowed"):
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        if not 1 <= len(clean_query) <= 500 or not 1 <= limit <= settings.rag_top_k_max:
            raise AppError(422, "VALIDATION_ERROR", "知识库检索参数不符合要求")
        if len(selected_products) > 5 or any(item <= 0 for item in selected_products):
            raise AppError(422, "VALIDATION_ERROR", "产品筛选参数不符合要求")
        if any(item not in VALID_DOCUMENT_TYPES for item in selected_types):
            raise AppError(422, "VALIDATION_ERROR", "文档类型筛选参数不符合要求")
        provider = self.provider or create_embedding_provider(settings)
        try:
            vector = validate_embeddings([provider.embed_query(clean_query)], 1, provider.dimensions)[0]
        except EmbeddingInputError as exc:
            raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc
        scope = {
            "role": current_user.role, "query_embedding": vector,
            "product_ids": selected_products or None, "document_types": selected_types or None,
            "embedding_provider": provider.provider_name, "embedding_model": provider.model_name,
            "embedding_dimensions": provider.dimensions, "embedding_revision": provider.revision,
            "document_ids": document_ids,
        }
        statement = self.repository.search_statement(
            min_similarity=settings.rag_min_similarity, **scope,
        ).limit(limit)
        seen: set[UUID] = set()
        items: list[KnowledgeSearchItem] = []
        for chunk, document, distance in session.execute(statement).all():
            score = 1.0 - float(distance)
            if score < settings.rag_min_similarity:
                continue
            item = self._build_item(session, chunk, document, score, role=current_user.role)
            if item is None:
                continue
            seen.add(chunk.id)
            items.append(item)
        supplemented = self._lexical_supplement(
            session, scope=scope, terms=lexical_terms, seen=seen, limit=limit,
        )
        # 为两路召回保留容量，再交给咨询层做业务相关性排序。词面候选不得
        # 挤掉全部向量 Top 结果，否则后续排序已经看不到被提前截断的候选。
        return self._merge_candidates(items, supplemented, limit)

    @staticmethod
    def _merge_candidates(vector_items: list, lexical_items: list, limit: int) -> list:
        """合并两路候选，奇数上限时词面多保留一席且仍保留向量候选。"""

        if not lexical_items:
            return vector_items[:limit]
        lexical_capacity = min(len(lexical_items), max(1, (limit + 1) // 2))
        selected = lexical_items[:lexical_capacity]
        selected.extend(vector_items[:max(0, limit - len(selected))])
        return selected[:limit]

    def _build_item(self, session: Session, chunk, document, score: float, *,
                    role: str) -> KnowledgeSearchItem | None:
        if not self.repository.allowed_chunk(
            session, chunk_id=chunk.id, document_id=document.id, role=role
        ):
            return None
        products = self.repository.product_ids(session, document.id)
        citation = Citation(
            citation_id=1, document_id=document.id, chunk_id=chunk.id,
            document_name=document.document_name, page_start=chunk.page_start, page_end=chunk.page_end,
            section_title=chunk.section_title, row_start=chunk.row_start, row_end=chunk.row_end,
            quote=chunk.chunk_text[:240],
            evidence_category=chunk.chunk_metadata.get("evidence_category"),
            worksheet=chunk.chunk_metadata.get("worksheet") or chunk.section_title,
            record_id=chunk.chunk_metadata.get("record_id"),
            source_id=chunk.chunk_metadata.get("source_id"),
            usage_restriction=chunk.chunk_metadata.get("usage_restriction"),
        )
        return KnowledgeSearchItem(
            document_id=document.id, document_name=document.document_name, chunk_id=chunk.id,
            chunk_index=chunk.chunk_index, chunk_text=chunk.chunk_text, score=score,
            page_start=chunk.page_start, page_end=chunk.page_end, section_title=chunk.section_title,
            row_start=chunk.row_start, row_end=chunk.row_end, product_id=chunk.product_id,
            product_ids=products, file_type=document.file_type, citation=citation,
            chunk_metadata=chunk.chunk_metadata,
        )

    def _lexical_supplement(self, session: Session, *, scope: dict,
                            terms: tuple[list[str], list[str], list[str]] | None,
                            seen: set[UUID], limit: int) -> list[KnowledgeSearchItem]:
        """在向量候选之外补充有限的词面候选，复用向量检索的全部过滤条件。

        选择顺序：先看锚点是否命中记录的“条目类别/报价对象”字段（业务对象本人登记的
        记录优先），再看命中词数量与余弦距离。
        """

        if not terms:
            return []
        anchors, intents, object_anchors = terms
        if not anchors or not intents:
            return []
        rows = session.execute(self.repository.search_lexical_statement(
            anchors=anchors, intents=intents, **scope,
        )).all()
        scored = []
        for chunk, document, distance in rows:
            if chunk.id in seen:
                continue
            body = chunk.chunk_text.upper()
            hits = sum(1 for term in (*anchors, *intents) if term and term.upper() in body)
            object_hit = 1 if any(term in chunk.chunk_text for term in object_anchors) else 0
            scored.append((object_hit, hits, 1.0 - float(distance), chunk.chunk_index,
                           chunk, document))
        scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
        capacity = min(LEXICAL_SUPPLEMENT_LIMIT, limit)
        result: list[KnowledgeSearchItem] = []
        for _, _, score, _, chunk, document in scored:
            if len(result) >= capacity:
                break
            item = self._build_item(session, chunk, document, score, role=scope["role"])
            if item is None:
                continue
            seen.add(chunk.id)
            result.append(item)
        return result

    def build_context(self, items: list[KnowledgeSearchItem]) -> ContextResult:
        return ContextBuilder(max_chars=get_settings().rag_context_max_chars).build(items)
