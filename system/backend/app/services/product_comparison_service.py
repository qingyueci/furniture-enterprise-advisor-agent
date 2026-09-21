from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from pydantic import BaseModel, ConfigDict, Field

from app.agent.contracts import CompareProductsInput, ToolStatus
from app.models import Product
from app.rag.types import KnowledgeSearchItem
from app.schemas.agent import (
    MISSING_INFORMATION_TEXT,
    NO_PRICE_TEXT,
    BudgetCheck,
    Citation,
    CitationSourceType,
    ComparisonRow,
    ComparisonStatus,
    ConditionalRecommendation,
    EvidenceClaim,
    MissingInformation,
    PriceCard,
    ProductComparisonData,
    ProductSummary,
)


class _StrictGenerated(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GeneratedSide(_StrictGenerated):
    product_id: int = Field(gt=0)
    value: str = Field(min_length=1, max_length=800)
    status: ComparisonStatus
    source_refs: list[str] = Field(default_factory=list, max_length=8)
    excerpts: list[str] = Field(default_factory=list, max_length=8)


class GeneratedRow(_StrictGenerated):
    dimension: str = Field(min_length=1, max_length=80)
    sides: list[GeneratedSide] = Field(min_length=2, max_length=2)
    # 行状态完全由两侧状态推导，属于派生值：模型可以不填，填了也不作为判定依据。
    status: ComparisonStatus | None = None
    note: str | None = Field(default=None, max_length=500)


class GeneratedClaim(_StrictGenerated):
    product_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)
    source_refs: list[str] = Field(min_length=1, max_length=8)
    excerpts: list[str] = Field(min_length=1, max_length=8)


class GeneratedRecommendation(_StrictGenerated):
    recommended_product_id: int | None = Field(default=None, gt=0)
    condition: str = Field(min_length=1, max_length=500)
    rationale: str | None = Field(default=None, max_length=1000)
    source_refs: list[str] = Field(default_factory=list, max_length=8)
    excerpts: list[str] = Field(default_factory=list, max_length=8)


class GeneratedComparison(_StrictGenerated):
    rows: list[GeneratedRow] = Field(default_factory=list, max_length=20)
    advantages: list[GeneratedClaim] = Field(default_factory=list, max_length=12)
    limitations: list[GeneratedClaim] = Field(default_factory=list, max_length=12)
    recommendation: GeneratedRecommendation | None = None


@dataclass(frozen=True)
class ComparisonBundle:
    data: ProductComparisonData
    context: str
    evidence_text_by_ref: dict[str, str]
    evidence_product_by_ref: dict[str, int]


def _normal(value: str) -> str:
    return re.sub(r"\s+", "", value)


class ProductComparisonService:
    """只聚合本轮已核验的产品、价格和授权文档证据。"""

    _reserved_dimensions = {"产品名称", "型号", "品牌", "价格", "价差（A−B）"}

    def build(
        self,
        *,
        products: tuple[Product, Product],
        price_cards: dict[int, PriceCard],
        price_citations: dict[int, list[Citation]],
        knowledge_items: dict[int, list[KnowledgeSearchItem]],
        payload: CompareProductsInput,
        recommendation_requested: bool,
        had_tool_failure: bool = False,
    ) -> ComparisonBundle:
        product_ids = (products[0].id, products[1].id)
        if product_ids != (payload.product_a_id, payload.product_b_id):
            raise ValueError("比较产品与本轮执行上下文不一致")

        context, document_citations, text_by_ref, product_by_ref = self._build_context(
            products, knowledge_items
        )
        product_citations = [
            Citation(
                ref=f"R{product.id}",
                source_type=CitationSourceType.PRODUCT,
                product_id=product.id,
                source="products",
                quote=f"{product.product_name}；型号 {product.model}；品牌 {product.brand}",
            )
            for product in products
        ]
        cards = [
            price_cards.get(product.id)
            or PriceCard(
                product_id=product.id,
                product_name=product.product_name,
                price=None,
                currency=payload.currency,
                price_type=payload.price_type,
            )
            for product in products
        ]
        prices = [citation for product in products for citation in price_citations.get(product.id, [])]
        document_refs = {
            product.id: [citation.ref for citation in document_citations if citation.product_id == product.id]
            for product in products
        }
        summaries = [
            ProductSummary(
                product_id=product.id,
                product_name=product.product_name,
                model=product.model,
                brand=product.brand,
                product_type=product.product_type,
                summary=product.description,
                source_refs=[f"R{product.id}", *document_refs[product.id]],
            )
            for product in products
        ]
        rows = [
            ComparisonRow(
                dimension="产品名称",
                values=[product.product_name for product in products],
                source_refs=[f"R{product.id}" for product in products],
            ),
            ComparisonRow(
                dimension="型号",
                values=[product.model for product in products],
                source_refs=[f"R{product.id}" for product in products],
            ),
            ComparisonRow(
                dimension="品牌",
                values=[product.brand for product in products],
                source_refs=[f"R{product.id}" for product in products],
            ),
            ComparisonRow(
                dimension="价格",
                values=[
                    NO_PRICE_TEXT if card.price is None else f"{card.price:.2f} {card.currency}"
                    for card in cards
                ],
                source_refs=[citation.ref for citation in prices if citation.ref],
                status=(
                    ComparisonStatus.AVAILABLE
                    if all(card.price is not None for card in cards)
                    else ComparisonStatus.MISSING
                ),
            ),
        ]
        text_dimensions = list(dict.fromkeys([
            "核心参数", "功能", "适用场景", *(payload.focus_dimensions or [])
        ]))
        rows.extend(
            ComparisonRow(
                dimension=dimension,
                values=[MISSING_INFORMATION_TEXT, MISSING_INFORMATION_TEXT],
                status=ComparisonStatus.MISSING,
                note="等待从本轮授权证据整理",
            )
            for dimension in text_dimensions
            if dimension not in self._reserved_dimensions
        )
        basis_reason = self._basis_reason(cards)
        rows.append(ComparisonRow(dimension="价差（A−B）", values=[
            f"{cards[0].price - cards[1].price:.2f} {cards[0].currency}/{cards[0].pricing_unit}", "同口径对比"
        ] if not basis_reason and all(c.price is not None for c in cards) else ["暂不计算", "暂不计算"],
            source_refs=[citation.ref for citation in prices if citation.ref],
            status=ComparisonStatus.AVAILABLE if not basis_reason and all(c.price is not None for c in cards) else ComparisonStatus.MISSING,
            note=basis_reason or ("存在缺失价格" if any(c.price is None for c in cards) else "正数表示A更贵")))
        budget = self._budget(cards, payload)
        recommendation = self._deterministic_recommendation(
            products, budget, payload.focus_dimensions or [], recommendation_requested
        )
        missing = self._missing(products, cards, document_refs, rows)
        base_incomplete = (
            had_tool_failure
            or any(card.price is None for card in cards)
            or any(not document_refs[product.id] for product in products)
        )
        overall = ToolStatus.PARTIAL if base_incomplete else ToolStatus.SUCCESS
        data = ProductComparisonData(
            products=[product.product_name for product in products],
            summaries=summaries,
            price_cards=cards,
            rows=rows,
            budget_check=budget,
            advantages={product.product_name: [] for product in products},
            limitations={product.product_name: [] for product in products},
            missing_fields=missing,
            citations=[*product_citations, *prices, *document_citations],
            recommendation=recommendation,
            overall_status=overall,
        )
        return ComparisonBundle(data, context, text_by_ref, product_by_ref)

    def apply_generated(
        self,
        *,
        bundle: ComparisonBundle,
        generated: GeneratedComparison,
        products: tuple[Product, Product],
        payload: CompareProductsInput,
        recommendation_requested: bool,
    ) -> ProductComparisonData:
        ids = [product.id for product in products]
        names = {product.id: product.product_name for product in products}
        rows = {row.dimension: row for row in bundle.data.rows}
        for item in generated.rows:
            if item.dimension in self._reserved_dimensions:
                continue
            if [side.product_id for side in item.sides] != ids:
                raise ValueError("模型比较行的产品顺序无效")
            for side in item.sides:
                self._validate_side(side, bundle)
            # 行状态是两侧状态的纯函数，由服务端推导；模型自报的行状态不影响证据校验，
            # 只保留两侧各自的 MISSING/CONFLICT 语义，避免多一个可失败点。
            derived_status = (
                ComparisonStatus.CONFLICT
                if any(side.status is ComparisonStatus.CONFLICT for side in item.sides)
                else ComparisonStatus.MISSING
                if any(side.status is ComparisonStatus.MISSING for side in item.sides)
                else ComparisonStatus.AVAILABLE
            )
            refs = list(dict.fromkeys(ref for side in item.sides for ref in side.source_refs))
            rows[item.dimension] = ComparisonRow(
                dimension=item.dimension,
                values=[
                    MISSING_INFORMATION_TEXT if side.status is ComparisonStatus.MISSING else side.value
                    for side in item.sides
                ],
                source_refs=refs,
                status=derived_status,
                note=item.note,
            )

        advantages = {product.product_name: [] for product in products}
        limitations = {product.product_name: [] for product in products}
        for target, claims in ((advantages, generated.advantages), (limitations, generated.limitations)):
            for claim in claims:
                self._validate_claim(claim, bundle, ids)
                target[names[claim.product_id]].append(
                    EvidenceClaim(text=claim.text, source_refs=claim.source_refs)
                )

        recommendation = bundle.data.recommendation
        if recommendation_requested and self._llm_recommendation_allowed(
            bundle.data.budget_check, payload.focus_dimensions or [], list(rows.values())
        ) and generated.recommendation is not None:
            item = generated.recommendation
            if item.recommended_product_id is not None:
                if item.recommended_product_id not in ids:
                    raise ValueError("模型推荐了本轮之外的产品")
                claim = GeneratedClaim(
                    product_id=item.recommended_product_id,
                    text=item.rationale or item.condition,
                    source_refs=item.source_refs,
                    excerpts=item.excerpts,
                )
                self._validate_claim(claim, bundle, ids)
            recommendation = ConditionalRecommendation(
                recommended_product=(names.get(item.recommended_product_id)),
                condition=item.condition,
                rationale=item.rationale,
                source_refs=item.source_refs,
            )

        final_rows = list(rows.values())
        missing = self._missing(products, bundle.data.price_cards, {
            product.id: [
                citation.ref for citation in bundle.data.citations
                if citation.source_type is CitationSourceType.DOCUMENT and citation.product_id == product.id
            ]
            for product in products
        }, final_rows)
        return bundle.data.model_copy(update={
            "rows": final_rows,
            "advantages": advantages,
            "limitations": limitations,
            "missing_fields": missing,
            "recommendation": recommendation,
            "overall_status": ToolStatus.PARTIAL if missing else bundle.data.overall_status,
        })

    def _build_context(
        self,
        products: tuple[Product, Product],
        knowledge_items: dict[int, list[KnowledgeSearchItem]],
    ) -> tuple[str, list[Citation], dict[str, str], dict[str, int]]:
        has_both = all(knowledge_items.get(product.id) for product in products)
        per_product_cap = 4000 if has_both else 8000
        used_total = 0
        seen: set[tuple[object, object]] = set()
        sections: list[str] = []
        citations: list[Citation] = []
        text_by_ref: dict[str, str] = {}
        product_by_ref: dict[str, int] = {}
        for product in products:
            used_side = 0
            for item in knowledge_items.get(product.id, [])[:4]:
                key = (item.document_id, item.chunk_id)
                if key in seen or len(citations) >= 8:
                    continue
                ref = str(len(citations) + 1)
                header = f"[来源 {ref}]\n产品：{product.product_name}\n文件：{item.document_name}"
                if item.page_start is not None:
                    header += f"\n页码：第{item.page_start}页"
                if item.section_title:
                    header += f"\n章节：{item.section_title}"
                if item.row_start is not None:
                    header += f"\n行号：{item.row_start}"
                overhead = len(header) + len("\n<enterprise_document>\n\n</enterprise_document>")
                available = min(per_product_cap - used_side - overhead, 8000 - used_total - overhead)
                if available <= 0:
                    break
                raw_body = item.chunk_text[:available]
                if not raw_body:
                    continue
                section = f"{header}\n<enterprise_document>\n{escape(raw_body, quote=False)}\n</enterprise_document>"
                sections.append(section)
                used_side += len(section) + 2
                used_total += len(section) + 2
                seen.add(key)
                citations.append(Citation(
                    ref=ref,
                    source_type=CitationSourceType.DOCUMENT,
                    document_id=item.document_id,
                    chunk_id=item.chunk_id,
                    product_id=product.id,
                    document_name=item.document_name,
                    page_start=item.page_start,
                    page_end=item.page_end,
                    section_title=item.section_title,
                    row_start=item.row_start,
                    row_end=item.row_end,
                    quote=raw_body[:240],
                ))
                text_by_ref[ref] = raw_body
                product_by_ref[ref] = product.id
        return "\n\n".join(sections), citations, text_by_ref, product_by_ref

    @staticmethod
    def _basis_reason(cards: list[PriceCard]) -> str | None:
        if any(not all((c.quote_spec, c.pricing_unit, c.included_scope)) for c in cards):
            return "报价规格、计价单位或包含范围缺失，不计算价差与单张预算"
        if len({(c.quote_spec, c.pricing_unit, c.included_scope, c.currency, c.price_type) for c in cards}) != 1:
            return "规格、单位、范围、币种或价格类型不一致，不计算价差与单张预算"
        return None

    @staticmethod
    def _budget(cards: list[PriceCard], payload: CompareProductsInput) -> BudgetCheck | None:
        if payload.budget is None:
            return None
        basis_reason = ProductComparisonService._basis_reason(cards)
        if basis_reason or any(c.price_type != payload.price_type for c in cards) or any(c.pricing_unit != "张" for c in cards):
            reason = basis_reason or "价格类型不匹配或不是按张报价，不计算单张预算"
            return BudgetCheck(budget=payload.budget, within_budget=[None, None], currency=payload.currency,
                               reasons=[reason, reason], over_budget_amounts=[None, None],
                               price_difference=None, price_difference_reason=reason)
        within: list[bool | None] = []
        reasons: list[str] = []
        over: list[Decimal | None] = []
        for card in cards:
            if card.price is None:
                within.append(None)
                reasons.append("价格缺失，预算判断条件不足")
                over.append(None)
            elif card.currency != payload.currency:
                within.append(None)
                reasons.append(f"价格币种为{card.currency}，未执行汇率换算")
                over.append(None)
            else:
                result = card.price <= payload.budget
                within.append(result)
                reasons.append("预算以内" if result else "超出预算")
                over.append(max(card.price - payload.budget, Decimal("0")))
        difference = None
        difference_reason = None
        if all(card.price is not None for card in cards):
            if cards[0].currency == cards[1].currency and cards[0].price_type == cards[1].price_type:
                difference = cards[0].price - cards[1].price  # type: ignore[operator]
                difference_reason = "正数表示产品A更贵，负数表示产品B更贵"
            else:
                difference_reason = "币种或价格类型不一致，不计算价差"
        else:
            difference_reason = "存在缺失价格，不计算价差"
        return BudgetCheck(
            budget=payload.budget,
            within_budget=within,
            currency=payload.currency,
            reasons=reasons,
            over_budget_amounts=over,
            price_difference=difference,
            price_difference_reason=difference_reason,
        )

    @staticmethod
    def _deterministic_recommendation(
        products: tuple[Product, Product],
        budget: BudgetCheck | None,
        focus_dimensions: list[str],
        recommendation_requested: bool,
    ) -> ConditionalRecommendation | None:
        if budget is not None:
            states = budget.within_budget
            if states in ([True, False], [False, True]):
                index = 0 if states[0] else 1
                return ConditionalRecommendation(
                    recommended_product=products[index].product_name,
                    condition=f"预算不超过 {budget.budget:.2f} {budget.currency}",
                    rationale="仅作为满足预算的候选，不代表性能更优",
                )
            if states == [False, False]:
                return ConditionalRecommendation(
                    recommended_product=None,
                    condition=f"两款产品均超出 {budget.budget:.2f} {budget.currency} 预算",
                    rationale="当前预算条件下不推荐其中任何一款",
                )
            if any(value is None for value in states):
                return ConditionalRecommendation(
                    recommended_product=None,
                    condition="价格缺失或报价口径条件不足",
                    rationale="预算结论不完整，暂不给出确定推荐",
                )
            if states == [True, True]:
                return ConditionalRecommendation(
                    recommended_product=None,
                    condition="两款产品均在预算内",
                    rationale=(
                        f"需结合有引用的关注维度（{'、'.join(focus_dimensions)}）给出条件式取舍"
                        if focus_dimensions
                        else "未提供偏好，展示取舍而不指定唯一优胜者"
                    ),
                )
        if recommendation_requested:
            return ConditionalRecommendation(
                recommended_product=None,
                condition=(f"关注维度为{'、'.join(focus_dimensions)}" if focus_dimensions else "尚未提供预算或偏好"),
                rationale="仅在资料充分且引用有效时给出条件式建议",
            )
        return None

    @staticmethod
    def _missing(
        products: tuple[Product, Product],
        cards: list[PriceCard],
        document_refs: dict[int, list[str]],
        rows: list[ComparisonRow],
    ) -> list[MissingInformation]:
        result: list[MissingInformation] = []
        for product, card in zip(products, cards, strict=True):
            if card.price is None:
                result.append(MissingInformation(field=f"{product.product_name}-价格", message=NO_PRICE_TEXT))
            if not document_refs.get(product.id):
                result.append(MissingInformation(field=f"{product.product_name}-资料"))
        for row in rows:
            if row.status in {ComparisonStatus.MISSING, ComparisonStatus.CONFLICT}:
                result.append(MissingInformation(
                    field=row.dimension,
                    message=("资料存在冲突" if row.status is ComparisonStatus.CONFLICT else MISSING_INFORMATION_TEXT),
                    status=row.status,
                    source_refs=row.source_refs,
                ))
        deduped: dict[tuple[str, ComparisonStatus], MissingInformation] = {}
        for item in result:
            deduped[(item.field, item.status)] = item
        return list(deduped.values())

    @staticmethod
    def _llm_recommendation_allowed(
        budget: BudgetCheck | None, focus_dimensions: list[str], rows: list[ComparisonRow]
    ) -> bool:
        if not focus_dimensions:
            return False
        if budget is not None and budget.within_budget != [True, True]:
            return False
        by_dimension = {row.dimension: row for row in rows}
        return all(
            dimension in by_dimension
            and by_dimension[dimension].status is ComparisonStatus.AVAILABLE
            and bool(by_dimension[dimension].source_refs)
            for dimension in focus_dimensions
        )

    @staticmethod
    def _validate_side(side: GeneratedSide, bundle: ComparisonBundle) -> None:
        if side.status is ComparisonStatus.MISSING:
            if side.source_refs or side.excerpts:
                raise ValueError("缺失侧不得附加证据")
            return
        if not side.source_refs or not side.excerpts:
            raise ValueError("有资料的一侧必须提供引用与原文摘录")
        if side.status is ComparisonStatus.CONFLICT and len(set(side.source_refs)) < 2:
            raise ValueError("冲突侧至少需要两条不同证据")
        if side.status is ComparisonStatus.CONFLICT and len({_normal(item) for item in side.excerpts}) < 2:
            raise ValueError("冲突侧至少需要两条不同原文摘录")
        sources = ProductComparisonService._cited_sources(
            side.source_refs, bundle, allowed_product_ids={side.product_id},
        )
        for excerpt in side.excerpts:
            if not _normal(excerpt) or not any(
                _normal(excerpt) in _normal(source) for source in sources
            ):
                raise ValueError("原文摘录与已发送证据不匹配")

    @classmethod
    def _validate_claim(
        cls, claim: GeneratedClaim, bundle: ComparisonBundle, product_ids: list[int]
    ) -> None:
        if claim.product_id not in product_ids or not claim.source_refs or not claim.excerpts:
            raise ValueError("结论的产品或证据数量无效")
        owners = [bundle.evidence_product_by_ref.get(ref) for ref in claim.source_refs]
        if claim.product_id not in owners or any(owner not in product_ids for owner in owners):
            raise ValueError("结论缺少本产品证据或引用了本轮之外的产品")
        # 比较类结论允许同时引用两侧证据（例如“续航高于对方”），但不允许引用本轮之外的产品。
        sources = cls._cited_sources(
            claim.source_refs, bundle, allowed_product_ids=set(product_ids),
        )
        for excerpt in claim.excerpts:
            if not _normal(excerpt) or not any(
                _normal(excerpt) in _normal(source) for source in sources
            ):
                raise ValueError("结论原文摘录与已发送证据不匹配")

    @staticmethod
    def _cited_sources(
        source_refs: list[str], bundle: ComparisonBundle, *, allowed_product_ids: set[int]
    ) -> list[str]:
        """返回被引用来源的原文；引用必须属于允许的产品且在本轮证据中存在。

        摘录与引用之间不要求一一对应：同一条来源可以支撑多条摘录。防编造保证仍然是
        “每条摘录必须能在所引用的某一来源原文中逐字找到”。
        """

        sources: list[str] = []
        for ref in source_refs:
            if bundle.evidence_product_by_ref.get(ref) not in allowed_product_ids:
                raise ValueError("证据归属产品不匹配")
            source = bundle.evidence_text_by_ref.get(ref)
            if not source:
                raise ValueError("引用来源不在本轮已发送证据中")
            sources.append(source)
        return sources


__all__ = [
    "ComparisonBundle",
    "GeneratedComparison",
    "ProductComparisonService",
]
