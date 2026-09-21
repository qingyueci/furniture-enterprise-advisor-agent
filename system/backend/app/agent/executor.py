from __future__ import annotations

import time
from dataclasses import dataclass, field
from html import escape
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.agent.contracts import (
    CompareProductsInput, QueryProductPriceInput, ReadDocumentInput, SearchProductKnowledgeInput,
    ToolCallRecord, ToolName, ToolStatus,
)
from app.agent.evidence import lexical_supplement_terms
from app.agent.tool_registry import ToolRegistry, ToolRegistryError
from app.core.exceptions import AppError
from app.models import Product, User
from app.rag.types import KnowledgeSearchItem
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.price_repository import PriceRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.agent import (
    Citation, CitationSourceType, ConsultationData, PriceCard, PriceQueryData, ProductComparisonData,
)
from app.schemas.audit import AuditAction, AuditResourceType, AuditResult
from app.services.audit_service import AuditService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.price_service import PriceService
from app.services.product_comparison_service import ComparisonBundle, ProductComparisonService


@dataclass
class AgentRunContext:
    session: Session
    user_id: UUID
    calls: int = 0
    max_calls: int = 8
    comparison_product_ids: tuple[int, int] | None = None
    recommendation_requested: bool = False
    knowledge_items: dict[int, list[KnowledgeSearchItem]] = field(default_factory=dict)
    price_cards: dict[int, PriceCard] = field(default_factory=dict)
    price_citations: dict[int, list[Citation]] = field(default_factory=dict)
    records: list[ToolCallRecord] = field(default_factory=list)
    comparison_bundle: ComparisonBundle | None = None
    audit_request_id: str | None = None
    audit_request_ip: str | None = None
    audit_username: str | None = None


@dataclass
class ToolExecutionResult:
    record: ToolCallRecord | None
    context: str = ""
    citations: list[Citation] = field(default_factory=list)
    structured_data: PriceQueryData | ProductComparisonData | ConsultationData | None = None
    missing_information: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def rag_citation_to_agent(value) -> Citation:
    return Citation(
        ref=str(value.citation_id),
        source_type=CitationSourceType.DOCUMENT,
        document_id=value.document_id,
        chunk_id=value.chunk_id,
        document_name=value.document_name,
        page_start=value.page_start,
        page_end=value.page_end,
        section_title=value.section_title,
        row_start=value.row_start,
        row_end=value.row_end,
        quote=value.quote,
        evidence_category=value.evidence_category,
        worksheet=value.worksheet,
        record_id=value.record_id,
        source_id=value.source_id,
        usage_restriction=value.usage_restriction,
    )


class AgentToolExecutor:
    def __init__(self, *, knowledge: KnowledgeBaseService | None = None,
                 documents: DocumentRepository | None = None,
                 chunks: KnowledgeRepository | None = None,
                 products: ProductRepository | None = None,
                 prices: PriceRepository | None = None):
        self.knowledge = knowledge or KnowledgeBaseService()
        self.documents = documents or DocumentRepository()
        self.chunks = chunks or KnowledgeRepository()
        self.products = products or ProductRepository()
        self.prices = prices or PriceRepository()
        self.price_service = PriceService(self.prices)
        self.comparisons = ProductComparisonService()

    def _current_user(self, context: AgentRunContext) -> User:
        user = context.session.scalar(
            select(User).where(User.id == context.user_id).execution_options(populate_existing=True)
        )
        if user is None or user.status != "ACTIVE":
            raise AppError(403, "ACCOUNT_DISABLED", "账号已被禁用")
        return user

    @staticmethod
    def _audit_result(status: ToolStatus) -> AuditResult:
        if status is ToolStatus.SUCCESS:
            return AuditResult.SUCCESS
        if status is ToolStatus.DENIED:
            return AuditResult.DENIED
        return AuditResult.FAILED

    def _record_tool_audits(
        self,
        context: AgentRunContext,
        *,
        name: ToolName | None,
        params: dict,
        record: ToolCallRecord,
    ) -> None:
        if context.audit_request_id is None:
            return
        audit = AuditService()
        common = {
            "user_id": context.user_id,
            "username": context.audit_username,
            "request_id_value": context.audit_request_id,
            "request_ip_value": context.audit_request_ip,
            "result": self._audit_result(record.status),
            "error_code": record.error_code or ("PARTIAL" if record.status is ToolStatus.PARTIAL else None),
            # 只有通过白名单校验的工具才写入 detail.tool；未知工具的
            # 失败记录仍可保留 AGENT_TOOL_CALL，但不伪装成搜索工具。
            "tool": name,
            "duration_ms": record.duration_ms,
        }
        audit.record(
            action=AuditAction.AGENT_TOOL_CALL,
            resource_type=AuditResourceType.AGENT,
            **common,
        )
        business_action: AuditAction | None = None
        business_resource = None
        if name is ToolName.SEARCH_PRODUCT_KNOWLEDGE:
            business_action = AuditAction.PRODUCT_QUERY
            product_ids = params.get("product_ids") if isinstance(params, dict) else None
            business_resource = product_ids[0] if isinstance(product_ids, list) and len(product_ids) == 1 else None
        elif name is ToolName.READ_DOCUMENT:
            business_action = AuditAction.DOCUMENT_READ
            business_resource = params.get("document_id") if isinstance(params, dict) else None
        elif name is ToolName.QUERY_PRODUCT_PRICE:
            business_action = AuditAction.PRICE_QUERY
            business_resource = params.get("product_id") if isinstance(params, dict) else None
        if business_action is not None:
            audit.record(
                action=business_action,
                resource_type={
                    AuditAction.PRODUCT_QUERY: AuditResourceType.PRODUCT,
                    AuditAction.DOCUMENT_READ: AuditResourceType.DOCUMENT,
                    AuditAction.PRICE_QUERY: AuditResourceType.PRICE,
                }[business_action],
                resource_id=business_resource,
                **common,
            )

    def execute(self, context: AgentRunContext, tool: ToolName | str, params: dict) -> ToolExecutionResult:
        if context.calls >= context.max_calls:
            raise AppError(422, "TOOL_CALL_LIMIT", "单轮工具调用次数已达到上限")
        context.calls += 1
        started = time.monotonic()
        try:
            name: ToolName | None = tool if isinstance(tool, ToolName) else ToolName(tool)
        except (TypeError, ValueError):
            name = None
        try:
            validated = ToolRegistry.validate_input(tool, params)
            user = self._current_user(context)
            assert name is not None
            if name is ToolName.SEARCH_PRODUCT_KNOWLEDGE:
                result = self._search(context, user, validated)  # type: ignore[arg-type]
            elif name is ToolName.READ_DOCUMENT:
                result = self._read_document(context.session, user, validated)  # type: ignore[arg-type]
            elif name is ToolName.QUERY_PRODUCT_PRICE:
                result = self._price(context, user, validated)  # type: ignore[arg-type]
            else:
                result = self._compare(context, validated)  # type: ignore[arg-type]
            duration = max(0, int((time.monotonic() - started) * 1000))
            assert result.record is not None
            result.record = result.record.model_copy(update={"duration_ms": duration})
            context.records.append(result.record)
            self._record_tool_audits(context, name=name, params=params, record=result.record)
            return result
        except ToolRegistryError as exc:
            duration = max(0, int((time.monotonic() - started) * 1000))
            result = ToolExecutionResult(ToolCallRecord(
                tool=name or ToolName.SEARCH_PRODUCT_KNOWLEDGE,
                status=ToolStatus.FAILED, duration_ms=duration,
                error_code=exc.error_code, message=exc.message,
            ), warnings=[exc.error_code])
            context.records.append(result.record)
            self._record_tool_audits(
                context, name=name, params=params, record=result.record,
            )
            return result
        except AppError as exc:
            duration = max(0, int((time.monotonic() - started) * 1000))
            safe_tool = name or ToolName.SEARCH_PRODUCT_KNOWLEDGE
            status = (
                ToolStatus.DENIED
                if exc.code in {
                    "PERMISSION_DENIED",
                    "DOCUMENT_NOT_ACCESSIBLE",
                    "CONVERSATION_NOT_ACCESSIBLE",
                    "RESOURCE_NOT_ACCESSIBLE",
                }
                else ToolStatus.FAILED
            )
            result = ToolExecutionResult(ToolCallRecord(
                tool=safe_tool, status=status, duration_ms=duration,
                error_code=exc.code, message=exc.message,
            ), warnings=[exc.code])
            context.records.append(result.record)
            self._record_tool_audits(
                context, name=name, params=params, record=result.record,
            )
            return result
        except ValidationError:
            duration = max(0, int((time.monotonic() - started) * 1000))
            safe_tool = name or ToolName.SEARCH_PRODUCT_KNOWLEDGE
            result = ToolExecutionResult(ToolCallRecord(
                tool=safe_tool, status=ToolStatus.FAILED, duration_ms=duration,
                error_code="VALIDATION_ERROR", message="工具参数不符合要求",
            ), warnings=["VALIDATION_ERROR"])
            context.records.append(result.record)
            self._record_tool_audits(
                context, name=name, params=params, record=result.record,
            )
            return result
        except Exception:
            duration = max(0, int((time.monotonic() - started) * 1000))
            safe_tool = name or ToolName.SEARCH_PRODUCT_KNOWLEDGE
            result = ToolExecutionResult(ToolCallRecord(
                tool=safe_tool, status=ToolStatus.FAILED, duration_ms=duration,
                error_code="TOOL_EXECUTION_FAILED", message="工具执行失败",
            ), warnings=["TOOL_EXECUTION_FAILED"])
            context.records.append(result.record)
            self._record_tool_audits(
                context, name=name, params=params, record=result.record,
            )
            return result

    def _search(self, context: AgentRunContext, user: User,
                payload: SearchProductKnowledgeInput) -> ToolExecutionResult:
        items = self.knowledge.search(
            context.session, query=payload.query, current_user=user,
            product_ids=payload.product_ids, top_k=payload.top_k,
            document_types=[item.value for item in payload.document_types] if payload.document_types else None,
            document_ids=payload.document_ids,
            lexical_terms=lexical_supplement_terms(payload.query),
        )
        if context.comparison_product_ids is not None and payload.product_ids and len(payload.product_ids) == 1:
            product_id = payload.product_ids[0]
            items = [
                item for item in items
                if item.product_id == product_id
                or (item.product_id is None and item.product_ids == [product_id])
            ]
            context.knowledge_items[product_id] = items
        if not items:
            return ToolExecutionResult(
                ToolCallRecord(tool=ToolName.SEARCH_PRODUCT_KNOWLEDGE,
                               status=ToolStatus.PARTIAL, duration_ms=0),
                missing_information=["当前可访问资料中未找到相关信息"],
            )
        built = self.knowledge.build_context(items)
        return ToolExecutionResult(
            ToolCallRecord(tool=ToolName.SEARCH_PRODUCT_KNOWLEDGE,
                           status=ToolStatus.SUCCESS, duration_ms=0),
            context=built.context,
            citations=[rag_citation_to_agent(item) for item in built.citations],
        )

    def _read_document(self, session: Session, user: User,
                       payload: ReadDocumentInput) -> ToolExecutionResult:
        document = self.documents.get_accessible(session, document_id=payload.document_id, role=user.role)
        if document is None:
            raise AppError(404, "DOCUMENT_NOT_ACCESSIBLE", "资料不存在或当前无权访问")
        if document.parse_status != "READY":
            raise AppError(409, "DOCUMENT_NOT_READY", "资料尚未完成解析")
        if payload.query:
            items = self.knowledge.search(
                session, query=payload.query, current_user=user, top_k=min(payload.max_chunks, 8),
                document_ids=[document.id],
            )
            if not items:
                return ToolExecutionResult(
                    ToolCallRecord(tool=ToolName.READ_DOCUMENT, status=ToolStatus.PARTIAL, duration_ms=0),
                    missing_information=["当前文档中未找到相关信息"],
                )
            built = self.knowledge.build_context(items)
            return ToolExecutionResult(
                ToolCallRecord(tool=ToolName.READ_DOCUMENT, status=ToolStatus.SUCCESS, duration_ms=0),
                context=built.context,
                citations=[rag_citation_to_agent(item) for item in built.citations],
            )
        chunks = self.chunks.read_chunks(
            session, document_id=document.id, role=user.role, page_start=payload.page_start,
            page_end=payload.page_end, limit=payload.max_chunks,
        )
        sections: list[str] = []
        citations: list[Citation] = []
        used = 0
        truncated = False
        for chunk in chunks:
            ref = str(len(citations) + 1)
            location = [f"文件：{document.document_name}"]
            if chunk.page_start is not None:
                location.append(f"页码：第{chunk.page_start}页")
            if chunk.section_title:
                location.append(f"章节：{chunk.section_title}")
            if chunk.row_start is not None:
                location.append(f"行号：{chunk.row_start}")
            header = "\n".join([f"[来源 {ref}]", *location])
            available = 8000 - used - len(header) - 50
            if available <= 0:
                truncated = True
                break
            body = escape(chunk.chunk_text[:available], quote=False)
            if len(body) < len(escape(chunk.chunk_text, quote=False)):
                truncated = True
            section = f"{header}\n<enterprise_document>\n{body}\n</enterprise_document>"
            sections.append(section)
            used += len(section) + 2
            citations.append(Citation(
                ref=ref, source_type=CitationSourceType.DOCUMENT,
                document_id=document.id, chunk_id=chunk.id,
                document_name=document.document_name, page_start=chunk.page_start,
                page_end=chunk.page_end, section_title=chunk.section_title,
                row_start=chunk.row_start, row_end=chunk.row_end,
                quote=chunk.chunk_text[:240],
            ))
        if not citations:
            return ToolExecutionResult(
                ToolCallRecord(tool=ToolName.READ_DOCUMENT, status=ToolStatus.PARTIAL, duration_ms=0),
                missing_information=["当前文档中没有可读取内容"],
            )
        return ToolExecutionResult(
            ToolCallRecord(tool=ToolName.READ_DOCUMENT,
                           status=ToolStatus.PARTIAL if truncated else ToolStatus.SUCCESS,
                           duration_ms=0),
            context="\n\n".join(sections), citations=citations,
            warnings=["DOCUMENT_TRUNCATED"] if truncated else [],
        )

    def _price(self, context: AgentRunContext, user: User,
               payload: QueryProductPriceInput) -> ToolExecutionResult:
        product = self.products.get_by_id(context.session, payload.product_id)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息")
        requested = payload.price_type.value if payload.price_type else "SALES"
        allowed = self.price_service.allowed_types(user)
        if requested not in allowed:
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        price = self.prices.latest_for_type(context.session, product_id=product.id, price_type=requested)
        card = PriceCard(
            product_id=product.id, product_name=product.product_name,
            price=price.price if price else None,
            currency=price.currency if price else "CNY",
            price_type=requested,
            source=price.source if price else None,
            update_time=price.update_time if price else None,
            quote_spec=price.quote_spec if price else None,
            pricing_unit=price.pricing_unit if price else None,
            included_scope=price.included_scope if price else None,
        )
        citations = [] if price is None else [Citation(
            ref=f"P{price.id}", source_type=CitationSourceType.PRICE,
            price_id=price.id, product_id=product.id, source=price.source,
            quote=f"{product.product_name} {requested} {price.price:.2f} {price.currency}/{price.pricing_unit or '单位未提供'}；{price.quote_spec or '规格未提供'}；{price.included_scope or '范围未提供'}",
        )]
        if context.comparison_product_ids is not None:
            context.price_cards[product.id] = card
            context.price_citations[product.id] = citations
        return ToolExecutionResult(
            ToolCallRecord(tool=ToolName.QUERY_PRODUCT_PRICE,
                           status=ToolStatus.PARTIAL if price is None else ToolStatus.SUCCESS,
                           duration_ms=0),
            structured_data=PriceQueryData(price_cards=[card]), citations=citations,
            missing_information=["暂无价格"] if price is None else [],
        )

    def _compare(self, context: AgentRunContext,
                 payload: CompareProductsInput) -> ToolExecutionResult:
        if context.comparison_product_ids != (payload.product_a_id, payload.product_b_id):
            raise AppError(422, "INVALID_COMPARISON_CONTEXT", "比较工具只能聚合本轮已选择的两个产品")
        product_a = self.products.get_by_id(context.session, payload.product_a_id)
        product_b = self.products.get_by_id(context.session, payload.product_b_id)
        if product_a is None or product_b is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息")
        had_failure = any(
            record.status in {ToolStatus.PARTIAL, ToolStatus.FAILED}
            for record in context.records
        )
        bundle = self.comparisons.build(
            products=(product_a, product_b),
            price_cards=context.price_cards,
            price_citations=context.price_citations,
            knowledge_items=context.knowledge_items,
            payload=payload,
            recommendation_requested=context.recommendation_requested,
            had_tool_failure=had_failure,
        )
        context.comparison_bundle = bundle
        status = bundle.data.overall_status
        return ToolExecutionResult(
            record=ToolCallRecord(tool=ToolName.COMPARE_PRODUCTS, status=status, duration_ms=0),
            context=bundle.context,
            citations=bundle.data.citations,
            structured_data=bundle.data,
            missing_information=[item.message for item in bundle.data.missing_fields],
            warnings=["PARTIAL_RESULT"] if status is ToolStatus.PARTIAL else [],
        )


__all__ = [
    "AgentRunContext", "AgentToolExecutor", "ToolExecutionResult", "rag_citation_to_agent",
]
