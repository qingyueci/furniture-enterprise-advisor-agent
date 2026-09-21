"""阶段 6 前置的 Agent 数据契约。

本模块只描述输入、输出和静态枚举，不调用模型、数据库或任何外部服务。
所有来自模型或客户端的字段都经过严格的 Pydantic 校验；用户身份和权限
由后续 API 层从服务端上下文注入，而不是由这些契约接收。
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictContract(BaseModel):
    """所有 Agent 契约共用的严格模型基类。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class TaskType(str, Enum):
    KNOWLEDGE_QUERY = "KNOWLEDGE_QUERY"
    DOCUMENT_READ = "DOCUMENT_READ"
    PRICE_QUERY = "PRICE_QUERY"
    PRODUCT_COMPARE = "PRODUCT_COMPARE"
    PRODUCT_RECOMMENDATION = "PRODUCT_RECOMMENDATION"
    CONSULTATION = "CONSULTATION"
    UNSUPPORTED = "UNSUPPORTED"


class ConsultationFormat(str, Enum):
    CANDIDATES = "CANDIDATES"
    COMPARISON_TABLE = "COMPARISON_TABLE"
    QUOTE_BREAKDOWN = "QUOTE_BREAKDOWN"
    CHECKLIST = "CHECKLIST"


class PriceType(str, Enum):
    GUIDE = "GUIDE"
    SALES = "SALES"
    INTERNAL_QUOTE = "INTERNAL_QUOTE"


class DocumentType(str, Enum):
    PDF = "PDF"
    DOCX = "DOCX"
    XLSX = "XLSX"


class ToolName(str, Enum):
    SEARCH_PRODUCT_KNOWLEDGE = "search_product_knowledge"
    READ_DOCUMENT = "read_document"
    QUERY_PRODUCT_PRICE = "query_product_price"
    COMPARE_PRODUCTS = "compare_products"


class ToolStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DENIED = "DENIED"


ProductMention = Annotated[str, Field(min_length=1, max_length=120)]
FocusDimension = Annotated[str, Field(min_length=1, max_length=50)]
PositiveProductId = Annotated[int, Field(gt=0)]


def _strip_items(value: object) -> object:
    """在列表元素约束执行前清理字符串首尾空白。"""

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [item.strip() if isinstance(item, str) else item for item in value]
    return value


def _strip_scalar(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _dedupe(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    return list(dict.fromkeys(value))


def _strip_and_dedupe_items(value: object) -> object:
    """先清理并去重，再让 ``max_length`` 校验唯一值数量。"""

    stripped = _strip_items(value)
    if isinstance(stripped, list):
        # 只对字符串去重；其他类型交给 Pydantic 的元素类型校验，避免
        # 非法的 dict/list 输入在预处理阶段触发原始 TypeError。
        result: list[object] = []
        seen: set[str] = set()
        for item in stripped:
            if isinstance(item, str):
                if item in seen:
                    continue
                seen.add(item)
            result.append(item)
        return result
    return stripped


class RoutingDecision(StrictContract):
    """一次用户问题的受控路由结果。

    模型只能提供业务识别字段。身份、角色、权限、物理路径和工具名均不在
    该模型的输入面中，额外字段会被 ``extra=forbid`` 拒绝。
    """

    task_type: TaskType
    normalized_query: str = Field(min_length=1, max_length=500)
    product_mentions: list[ProductMention] = Field(default_factory=list, max_length=2)
    document_id: UUID | None = None
    price_type: PriceType | None = None
    budget: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str = Field(default="CNY", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    focus_dimensions: list[FocusDimension] = Field(default_factory=list, max_length=5)
    retrieval_queries: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=3
    )
    answer_format: ConsultationFormat | None = None
    missing_conditions: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=5
    )

    _normalize_task_type = field_validator("task_type", mode="before")(_strip_scalar)
    _normalize_query = field_validator("normalized_query", mode="before")(_strip_scalar)
    _normalize_price_type = field_validator("price_type", mode="before")(_strip_scalar)
    _normalize_currency = field_validator("currency", mode="before")(_strip_scalar)
    _normalize_mentions = field_validator("product_mentions", mode="before")(_strip_and_dedupe_items)
    _dedupe_mentions = field_validator("product_mentions")(_dedupe)
    _normalize_dimensions = field_validator("focus_dimensions", mode="before")(_strip_and_dedupe_items)
    _dedupe_dimensions = field_validator("focus_dimensions")(_dedupe)
    _normalize_retrieval_queries = field_validator("retrieval_queries", mode="before")(_strip_and_dedupe_items)
    _dedupe_retrieval_queries = field_validator("retrieval_queries")(_dedupe)
    _normalize_answer_format = field_validator("answer_format", mode="before")(_strip_scalar)
    _normalize_missing_conditions = field_validator("missing_conditions", mode="before")(_strip_and_dedupe_items)
    _dedupe_missing_conditions = field_validator("missing_conditions")(_dedupe)


class SearchProductKnowledgeInput(StrictContract):
    query: str = Field(min_length=1, max_length=500)
    product_ids: list[PositiveProductId] | None = Field(default=None, max_length=5)
    top_k: int = Field(default=5, ge=1, le=8)
    document_types: list[DocumentType] | None = Field(default=None, max_length=3)
    document_ids: list[UUID] | None = Field(default=None, max_length=5)

    _normalize_document_types = field_validator("document_types", mode="before")(_strip_items)


class ReadDocumentInput(StrictContract):
    document_id: UUID
    query: Annotated[str, Field(max_length=500)] | None = None
    page_start: int | None = Field(default=None, gt=0)
    page_end: int | None = Field(default=None, gt=0)
    max_chunks: int = Field(default=8, ge=1, le=12)

    _normalize_query = field_validator("query", mode="before")(
        lambda value: (value.strip() or None) if isinstance(value, str) else value
    )

    @model_validator(mode="after")
    def validate_page_range(self) -> "ReadDocumentInput":
        has_start = self.page_start is not None
        has_end = self.page_end is not None
        if has_start != has_end:
            raise ValueError("page_start 和 page_end 必须同时提供")
        if has_start and has_end:
            assert self.page_start is not None and self.page_end is not None
            if self.page_end < self.page_start:
                raise ValueError("page_end 不得小于 page_start")
            if self.page_end - self.page_start + 1 > 10:
                raise ValueError("连续页数最多为 10 页")
        return self


class QueryProductPriceInput(StrictContract):
    product_id: PositiveProductId
    price_type: PriceType | None = None

    _normalize_price_type = field_validator("price_type", mode="before")(_strip_scalar)


class CompareProductsInput(StrictContract):
    product_a_id: PositiveProductId
    product_b_id: PositiveProductId
    focus_dimensions: list[FocusDimension] | None = Field(default=None, max_length=5)
    budget: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str = Field(default="CNY", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    price_type: PriceType = PriceType.SALES

    _normalize_dimensions = field_validator("focus_dimensions", mode="before")(_strip_and_dedupe_items)
    _dedupe_dimensions = field_validator("focus_dimensions")(_dedupe)
    _normalize_currency = field_validator("currency", mode="before")(_strip_scalar)
    _normalize_price_type = field_validator("price_type", mode="before")(_strip_scalar)

    @model_validator(mode="after")
    def reject_same_product(self) -> "CompareProductsInput":
        if self.product_a_id == self.product_b_id:
            raise ValueError("两个产品 ID 必须不同")
        return self


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:token|access[_ -]?token|password|passwd|api[_ -]?key|secret|authorization|bearer)"
    r"\b\s*[:=]\s*[^\s,;]+"
)
_SECRET_BEARER = re.compile(
    r"(?i)\b(?:bearer|token|password|passwd|api[_ -]?key|secret)\b\s+[^\s,;]+"
)
_FILE_PATH_ASSIGNMENT = re.compile(r"(?i)\bfile[_ -]?path\b\s*[:=]\s*[^\s,;]+")
_CONNECTION_STRING = re.compile(
    r"(?i)\b(?:postgres(?:ql)?(?:\+[^:/\s]+)?|mysql|mariadb|redis|sqlite)://[^\s,;]+"
)
_WINDOWS_PATH = re.compile(r"(?<![\w])(?:[A-Za-z]:[\\/]|\\\\)[^\s,;]+")
_TRACEBACK_LINE = re.compile(r"(?im)^\s*(?:traceback \(most recent call last\)|file\s+[\"'].*?line\s+\d+)")


def sanitize_message(value: str | None) -> str | None:
    """清理工具提示中的凭据、连接串、路径和异常堆栈。

    这里采用稳定的占位符而不是保存原始异常，保证工具记录可以被审计展示，
    同时不会把敏感运行时信息写入会话或日志。
    """

    if value is None:
        return None
    if not isinstance(value, str):
        # 交给 Pydantic 的字符串类型校验，确保错误类型仍以 ValidationError
        # 呈现，而不是在脱敏正则中抛出原始 TypeError。
        return value  # type: ignore[return-value]
    if _TRACEBACK_LINE.search(value):
        return "工具调用失败（异常详情已脱敏）"
    cleaned = _SECRET_ASSIGNMENT.sub("[已脱敏]", value)
    cleaned = _SECRET_BEARER.sub("[已脱敏]", cleaned)
    cleaned = _FILE_PATH_ASSIGNMENT.sub("[已脱敏]", cleaned)
    cleaned = _CONNECTION_STRING.sub("[已脱敏]", cleaned)
    cleaned = _WINDOWS_PATH.sub("[已脱敏]", cleaned)
    # 工具提示只需一行；折叠换行也能避免堆栈片段被拼接保存。
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class ToolCallRecord(StrictContract):
    """一次白名单工具调用的最小、脱敏记录。"""

    tool: ToolName
    status: ToolStatus
    duration_ms: int = Field(ge=0)
    error_code: str | None = Field(default=None, max_length=80)
    message: str | None = Field(default=None, max_length=500)

    _normalize_tool = field_validator("tool", "status", mode="before")(_strip_scalar)
    _sanitize_record_text = field_validator("error_code", "message", mode="before")(
        sanitize_message
    )


__all__ = [
    "CompareProductsInput",
    "DocumentType",
    "FocusDimension",
    "PriceType",
    "QueryProductPriceInput",
    "ReadDocumentInput",
    "RoutingDecision",
    "SearchProductKnowledgeInput",
    "TaskType",
    "ToolCallRecord",
    "ToolName",
    "ToolStatus",
    "sanitize_message",
]
