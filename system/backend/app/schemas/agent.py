"""阶段 7 产品对比与 Agent 输出契约。

本模块只负责描述已经由服务层核验过的事实如何序列化给 API/前端。
它不查询数据库、不调用模型，也不承担产品优劣判断。缺失资料和缺失价格
使用稳定的展示文案，金额在 JSON 输出中始终保留两位小数。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.agent.contracts import PriceType, StrictContract, TaskType, ToolStatus
from app.schemas.common import Pagination


MISSING_INFORMATION_TEXT = "资料未提供"
NO_PRICE_TEXT = "暂无价格"
# 单条消息的警告上限；写入端已去重，此处为持久化数据的防御性边界。
MAX_MESSAGE_WARNINGS = 30


class ComparisonStatus(str, Enum):
    """单个比较维度的证据状态。"""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"
    PRESENT = "AVAILABLE"
    OK = "AVAILABLE"


class CitationSourceType(str, Enum):
    DOCUMENT = "DOCUMENT"
    PRICE = "PRICE"
    PRODUCT = "PRODUCT"


class StrictOutput(BaseModel):
    """输出模型共用的严格配置；未知字段不能进入回答或审计链。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _strip_list(value: Any) -> Any:
    if value is None:
        return value
    if not isinstance(value, (list, tuple)):
        return value
    return [item.strip() if isinstance(item, str) else item for item in value]


def _dedupe_strings(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    return list(dict.fromkeys(value))


def _money(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("金额必须是有效的 Decimal") from exc
    if not result.is_finite():
        raise ValueError("金额必须是有限数")
    return result


ProductId = Annotated[int, Field(gt=0)]


class ProductSummary(StrictOutput):
    """比较结果中一侧产品的摘要。

    ``product_id`` 在实体解析完成后由服务端补入；契约允许仅有名称的
    摘要，便于在产品尚未匹配时明确展示而不是虚构 ID。
    """

    product_id: ProductId | None = None
    product_name: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=80)
    brand: str | None = Field(default=None, max_length=80)
    product_type: str | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=1200)
    source_refs: list[str] = Field(default_factory=list, max_length=12)

    _strip_fields = field_validator(
        "product_name", "model", "brand", "product_type", "summary", mode="before"
    )(_strip)
    _strip_refs = field_validator("source_refs", mode="before")(_strip_list)
    _dedupe_refs = field_validator("source_refs")(_dedupe_strings)


class PriceCard(StrictOutput):
    quote_spec: str | None = None
    pricing_unit: str | None = None
    included_scope: str | None = None

    """产品价格卡。

    ``price=None`` 是合法且明确的“暂无价格”，不会从产品描述推算金额。
    ``update_time`` 使用 PRD/API 的字段名；读取旧客户端的 ``updated_at``
    作为输入别名，但输出仍保持统一字段。
    """

    product_id: ProductId | None = None
    product_name: str = Field(min_length=1, max_length=120)
    price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        validation_alias=AliasChoices("price", "amount"),
    )
    currency: str = Field(default="CNY", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    price_type: PriceType = PriceType.GUIDE
    source: str | None = Field(default=None, max_length=255)
    update_time: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("update_time", "updated_at"),
    )
    status: ComparisonStatus = Field(
        default=ComparisonStatus.AVAILABLE,
        validation_alias=AliasChoices("status", "price_status", "availability"),
    )

    _strip_fields = field_validator("product_name", "source", mode="before")(_strip)
    _strip_currency = field_validator("currency", mode="before")(_strip)
    _normalize_price = field_validator("price", mode="before")(_money)
    _normalize_price_type = field_validator("price_type", mode="before")(_strip)
    _normalize_status = field_validator("status", mode="before")(_strip)

    @model_validator(mode="after")
    def normalize_missing_price(self) -> "PriceCard":
        if self.price is None:
            self.status = ComparisonStatus.MISSING
        return self

    @computed_field
    @property
    def display_price(self) -> str:
        return NO_PRICE_TEXT if self.price is None else f"{self.price:.2f}"

    @property
    def amount(self) -> Decimal | None:
        """兼容前端/服务层把金额称为 amount 的只读别名。"""

        return self.price

    @property
    def updated_at(self) -> datetime | None:
        """兼容旧接口字段名的只读别名。"""

        return self.update_time

    @field_serializer("price")
    def serialize_price(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"


class Citation(StrictOutput):
    """可反查的文档或结构化价格引用。"""

    ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("ref", "citation_id", "source_ref"),
    )
    source_type: CitationSourceType = CitationSourceType.DOCUMENT
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    document_name: str | None = Field(
        default=None,
        max_length=255,
        validation_alias=AliasChoices("document_name", "file_name"),
    )
    page_start: int | None = Field(default=None, gt=0)
    page_end: int | None = Field(default=None, gt=0)
    section_title: str | None = Field(
        default=None,
        max_length=255,
        validation_alias=AliasChoices("section_title", "section"),
    )
    row_start: int | None = Field(default=None, gt=0)
    row_end: int | None = Field(default=None, gt=0)
    price_id: int | None = Field(default=None, gt=0)
    product_id: ProductId | None = None
    source: str | None = Field(default=None, max_length=255)
    quote: str | None = Field(
        default=None,
        max_length=1000,
        validation_alias=AliasChoices("quote", "text", "snippet"),
    )
    evidence_category: str | None = Field(default=None, max_length=80)
    worksheet: str | None = Field(default=None, max_length=255)
    record_id: str | None = Field(default=None, max_length=120)
    source_id: str | None = Field(default=None, max_length=120)
    usage_restriction: str | None = Field(default=None, max_length=500)

    _strip_text = field_validator(
        "ref", "document_name", "section_title", "source", "quote", "evidence_category",
        "worksheet", "record_id", "source_id", "usage_restriction", mode="before"
    )(_strip)

    @model_validator(mode="after")
    def validate_ranges(self) -> "Citation":
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("page_end 不得小于 page_start")
        if self.row_start is not None and self.row_end is not None and self.row_end < self.row_start:
            raise ValueError("row_end 不得小于 row_start")
        if self.source_type is CitationSourceType.PRICE and self.price_id is None and not self.source:
            raise ValueError("价格引用至少需要 price_id 或 source")
        return self


class ComparisonRow(StrictOutput):
    """比较表的一行，``values`` 始终对应两侧产品。"""

    dimension: str = Field(
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("dimension", "field", "field_name"),
    )
    values: list[str] = Field(
        min_length=2,
        max_length=2,
        validation_alias=AliasChoices("values", "product_values"),
    )
    source_refs: list[str] = Field(default_factory=list, max_length=12)
    status: ComparisonStatus = ComparisonStatus.AVAILABLE
    note: str | None = Field(default=None, max_length=500)

    _strip_dimension = field_validator("dimension", mode="before")(_strip)
    _strip_values = field_validator("values", mode="before")(_strip_list)
    _strip_refs = field_validator("source_refs", mode="before")(_strip_list)
    _dedupe_refs = field_validator("source_refs")(_dedupe_strings)
    _strip_note = field_validator("note", mode="before")(_strip)

    @field_validator("values")
    @classmethod
    def exactly_two_values(cls, value: list[str]) -> list[str]:
        if len(value) != 2:
            raise ValueError("比较行必须包含两侧产品值")
        return [item if item else MISSING_INFORMATION_TEXT for item in value]


class BudgetCheck(StrictOutput):
    """双产品预算判断；只表达预算约束，不生成综合评分。"""

    budget: Decimal = Field(ge=Decimal("0"))
    within_budget: list[bool | None] = Field(min_length=2, max_length=2)
    currency: str = Field(default="CNY", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    reasons: list[str] = Field(
        default_factory=lambda: [MISSING_INFORMATION_TEXT, MISSING_INFORMATION_TEXT],
        min_length=2,
        max_length=2,
    )
    over_budget_amounts: list[Decimal | None] = Field(
        default_factory=lambda: [None, None], min_length=2, max_length=2
    )
    price_difference: Decimal | None = None
    price_difference_reason: str | None = Field(default=None, max_length=500)

    _normalize_budget = field_validator("budget", mode="before")(_money)
    _strip_currency = field_validator("currency", mode="before")(_strip)
    _strip_reasons = field_validator("reasons", mode="before")(_strip_list)

    @field_serializer("budget")
    def serialize_budget(self, value: Decimal) -> str:
        return f"{value:.2f}"

    @field_serializer("over_budget_amounts")
    def serialize_over_budget_amounts(self, value: list[Decimal | None]) -> list[str | None]:
        return [None if item is None else f"{item:.2f}" for item in value]

    @field_serializer("price_difference")
    def serialize_price_difference(self, value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"

    @field_validator("within_budget")
    @classmethod
    def exactly_two_budget_results(cls, value: list[bool | None]) -> list[bool | None]:
        if len(value) != 2:
            raise ValueError("预算判断必须对应两侧产品")
        return value

    @model_validator(mode="after")
    def validate_parallel_budget_fields(self) -> "BudgetCheck":
        if len(self.reasons) != 2 or len(self.over_budget_amounts) != 2:
            raise ValueError("预算原因和超预算金额必须对应两侧产品")
        values = [self.budget, self.price_difference, *self.over_budget_amounts]
        if any(value is not None and not value.is_finite() for value in values):
            raise ValueError("预算金额必须是有限数")
        if any(value is not None and value < 0 for value in self.over_budget_amounts):
            raise ValueError("超预算金额不得为负数")
        return self


class ConditionalRecommendation(StrictOutput):
    """有条件的推荐结论；成立条件是必填项。"""

    recommended_product: str | None = Field(default=None, max_length=120)
    condition: str = Field(min_length=1, max_length=500)
    rationale: str | None = Field(default=None, max_length=1200)
    source_refs: list[str] = Field(default_factory=list, max_length=12)

    _strip_fields = field_validator("recommended_product", "condition", "rationale", mode="before")(_strip)
    _strip_refs = field_validator("source_refs", mode="before")(_strip_list)
    _dedupe_refs = field_validator("source_refs")(_dedupe_strings)


class EvidenceClaim(StrictOutput):
    """优势或限制结论；文本与证据编号必须一起返回。"""

    text: str = Field(min_length=1, max_length=500)
    source_refs: list[str] = Field(min_length=1, max_length=12)

    _strip_text = field_validator("text", mode="before")(_strip)
    _strip_refs = field_validator("source_refs", mode="before")(_strip_list)
    _dedupe_refs = field_validator("source_refs")(_dedupe_strings)


class MissingInformation(StrictOutput):
    """一个缺失或冲突字段的可解释提示。"""

    field: str = Field(min_length=1, max_length=80)
    message: str = Field(default=MISSING_INFORMATION_TEXT, min_length=1, max_length=500)
    status: ComparisonStatus = ComparisonStatus.MISSING
    source_refs: list[str] = Field(default_factory=list, max_length=12)

    _strip_fields = field_validator("field", "message", mode="before")(_strip)
    _strip_refs = field_validator("source_refs", mode="before")(_strip_list)
    _dedupe_refs = field_validator("source_refs")(_dedupe_strings)


class ProductComparisonData(StrictOutput):
    """阶段 7 双产品比较结果。"""

    kind: Literal["PRODUCT_COMPARISON"] = "PRODUCT_COMPARISON"
    products: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        min_length=2, max_length=2,
        validation_alias=AliasChoices("products", "product_names"),
    )
    summaries: list[ProductSummary] = Field(
        default_factory=list,
        max_length=2,
        validation_alias=AliasChoices("summaries", "product_summaries"),
    )
    price_cards: list[PriceCard] = Field(
        default_factory=list,
        max_length=2,
        validation_alias=AliasChoices("price_cards", "prices"),
    )
    rows: list[ComparisonRow] = Field(
        default_factory=list,
        max_length=30,
        validation_alias=AliasChoices("rows", "comparison_rows"),
    )
    budget_check: BudgetCheck | None = None
    advantages: dict[str, list[EvidenceClaim]] = Field(default_factory=dict, max_length=2)
    limitations: dict[str, list[EvidenceClaim]] = Field(default_factory=dict, max_length=2)
    missing_fields: list[MissingInformation] = Field(
        default_factory=list,
        max_length=30,
        validation_alias=AliasChoices("missing_fields", "missing_information"),
    )
    citations: list[Citation] = Field(default_factory=list, max_length=40)
    recommendation: ConditionalRecommendation | None = None
    overall_status: ToolStatus = ToolStatus.SUCCESS

    _strip_products = field_validator("products", mode="before")(_strip_list)
    _dedupe_products = field_validator("products")(_dedupe_strings)

    @model_validator(mode="after")
    def validate_two_products(self) -> "ProductComparisonData":
        if len(self.products) != 2:
            raise ValueError("产品比较必须恰好包含两个不同产品")
        if self.products[0] == self.products[1]:
            raise ValueError("两个产品必须不同")
        if self.summaries and len(self.summaries) != 2:
            raise ValueError("产品摘要必须对应两个产品")
        if self.price_cards and len(self.price_cards) != 2:
            raise ValueError("价格卡必须对应两个产品")
        return self

    @property
    def product_summaries(self) -> list[ProductSummary]:
        return self.summaries


class ToolCallSummary(StrictOutput):
    """面向前端的工具状态摘要，不暴露参数或内部 Prompt。"""

    tool: str = Field(min_length=1, max_length=80)
    status: ToolStatus
    duration_ms: int = Field(ge=0)


class PriceQueryData(StrictOutput):
    """单产品价格工具的已核验结构化结果。"""

    kind: Literal["PRICE_QUERY"] = "PRICE_QUERY"
    price_cards: list[PriceCard] = Field(min_length=1, max_length=1)


class ConsultationData(StrictOutput):
    """V1.1 资料咨询结果；正文仍由 ``answer`` 承载。"""

    kind: Literal["CONSULTATION"] = "CONSULTATION"
    answer_format: Literal[
        "CANDIDATES", "COMPARISON_TABLE", "QUOTE_BREAKDOWN", "CHECKLIST"
    ]
    retrieval_queries: list[str] = Field(default_factory=list, max_length=3)
    degraded: bool = False
    pending_slots: list[dict] = Field(default_factory=list)
    conversation_topic: str | None = None
    session_conditions: list[dict] = Field(default_factory=list)


class AgentChatRequest(StrictContract):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)
    selected_product_ids: list[ProductId] = Field(default_factory=list, max_length=2)
    selected_document_id: UUID | None = None

    @field_validator("message", mode="before")
    @classmethod
    def clean_message(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if any((ord(char) < 32 and char not in "\n\t") or 127 <= ord(char) <= 159 for char in value):
            raise ValueError("消息包含非法控制字符")
        return value

    @field_validator("selected_product_ids")
    @classmethod
    def dedupe_product_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("产品 ID 不得重复")
        return value


class AgentChatData(StrictOutput):
    """后续阶段 ``/api/agent/chat`` 可直接复用的响应骨架。"""

    conversation_id: UUID
    message_id: UUID
    task_type: TaskType
    answer: str = Field(min_length=1, max_length=20000)
    structured_data: PriceQueryData | ProductComparisonData | ConsultationData | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=40)
    tool_calls: list[ToolCallSummary] = Field(default_factory=list, max_length=8)
    missing_information: list[str] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=MAX_MESSAGE_WARNINGS)


class ConversationSummary(StrictOutput):
    id: UUID
    title: str = Field(min_length=1, max_length=120)
    updated_at: datetime


class ConversationMessage(StrictOutput):
    id: UUID
    role: Literal["USER", "ASSISTANT"]
    content: str
    task_type: TaskType | None = None
    structured_data: PriceQueryData | ProductComparisonData | ConsultationData | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=40)
    tool_summary: list[ToolCallSummary] = Field(default_factory=list, max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=MAX_MESSAGE_WARNINGS)
    created_at: datetime


class ConversationListData(StrictOutput):
    items: list[ConversationSummary]
    pagination: Pagination


class ConversationData(StrictOutput):
    id: UUID
    title: str
    messages: list[ConversationMessage]
    pagination: Pagination
    created_at: datetime
    updated_at: datetime


class BulkConversationDeleteRequest(StrictOutput):
    ids: list[UUID] = Field(min_length=1, max_length=100)


# 语义别名：为后续 API/论文代码提供稳定、易发现的导出名，不复制模型实现。
ComparisonOutput = ProductComparisonData
ProductComparisonOutput = ProductComparisonData
ComparisonData = ProductComparisonData
ProductCompareOutput = ProductComparisonData
ComparisonTable = ProductComparisonData
BudgetJudgement = BudgetCheck
BudgetJudgment = BudgetCheck
BudgetCheckData = BudgetCheck
Recommendation = ConditionalRecommendation
ConditionalRecommendationData = ConditionalRecommendation
ComparisonCitation = Citation
CitationData = Citation
PriceCardStatus = ComparisonStatus


__all__ = [
    "AgentChatData",
    "AgentChatRequest",
    "BudgetCheck",
    "BudgetJudgement",
    "Citation",
    "CitationSourceType",
    "ComparisonCitation",
    "ComparisonOutput",
    "ComparisonData",
    "ComparisonTable",
    "ComparisonRow",
    "ComparisonStatus",
    "ConditionalRecommendation",
    "ConditionalRecommendationData",
    "ConsultationData",
    "EvidenceClaim",
    "CitationData",
    "MAX_MESSAGE_WARNINGS",
    "MISSING_INFORMATION_TEXT",
    "MissingInformation",
    "NO_PRICE_TEXT",
    "PriceCard",
    "PriceQueryData",
    "ProductComparisonData",
    "ProductComparisonOutput",
    "ProductCompareOutput",
    "ProductSummary",
    "Recommendation",
    "BudgetCheckData",
    "BudgetJudgment",
    "PriceCardStatus",
    "ToolCallSummary",
    "ConversationData",
    "ConversationListData",
    "ConversationMessage",
    "ConversationSummary",
]
