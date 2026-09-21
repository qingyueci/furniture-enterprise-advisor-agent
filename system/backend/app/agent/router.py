from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.agent.contracts import ConsultationFormat, PriceType, RoutingDecision, TaskType
from app.agent.evidence import BUSINESS_OBJECT_TERMS, SUPPLIER_DATA_QUERY_TERMS, SUPPLIER_RULE_TERMS
from app.llm.provider import LLMProvider


ROUTING_FALLBACK = "ROUTING_FALLBACK"

_ROUTER_SYSTEM = """你是全屋定制顾问系统的意图分类器和检索问题规划器。只返回一个 JSON 对象，不要 Markdown。
字段：task_type, normalized_query, product_mentions, document_id, price_type, budget, currency, focus_dimensions, retrieval_queries, answer_format, missing_conditions。
task_type 只能是 KNOWLEDGE_QUERY、DOCUMENT_READ、PRICE_QUERY、PRODUCT_COMPARE、PRODUCT_RECOMMENDATION、CONSULTATION、UNSUPPORTED。
price_type 只能是 GUIDE、SALES、INTERNAL_QUOTE 或 null；currency 未说明时固定为 CNY。
只识别用户文本中明确出现的产品名称/型号、UUID、价格类型、预算和关注维度；不要生成产品ID、身份、角色、权限或工具名。
明确一个产品型号的查价使用 PRICE_QUERY；明确两个产品的计算式比较/推荐使用 PRODUCT_COMPARE/PRODUCT_RECOMMENDATION。
场景选材、材料类别比较、无型号报价条件解释、客户疑虑、交付核对使用 CONSULTATION，不要求产品ID。
CONSULTATION 生成最多3个彼此互补、可直接检索资料的 retrieval_queries；answer_format 只能是 CANDIDATES、COMPARISON_TABLE、QUOTE_BREAKDOWN、CHECKLIST。
历史对话只用于解析用户当前条件；助手历史回答不是事实证据，不得把它写进检索结论。
当前问题中的最新明确条件优先于历史条件。
未知字段使用 null 或空数组。
示例 JSON：{"task_type":"CONSULTATION","normalized_query":"厨房柜体选什么材料","product_mentions":[],"document_id":null,"price_type":null,"budget":null,"currency":"CNY","focus_dimensions":["防潮"],"retrieval_queries":["厨房柜体 板材 防潮 适用限制"],"answer_format":"CANDIDATES","missing_conditions":[]}"""


@dataclass(frozen=True)
class RouteResult:
    decision: RoutingDecision
    warnings: list[str]
    model_calls: int
    usage: list[dict[str, int | None]]
    model: str | None = None


def _json_object(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
    value = json.loads(clean)
    if not isinstance(value, dict):
        raise ValueError("routing response is not an object")
    return value


def _normalize_route_payload(value: dict) -> dict:
    """将模型的自然语言枚举收敛到严格契约，再交给 Pydantic 校验。"""

    normalized = dict(value)
    for key in ("product_mentions", "focus_dimensions", "retrieval_queries", "missing_conditions"):
        if normalized.get(key) is None:
            normalized[key] = []
    if normalized.get("currency") is None:
        normalized["currency"] = "CNY"
    price_type = normalized.get("price_type")
    if isinstance(price_type, str):
        aliases = {
            "指导价": PriceType.GUIDE.value,
            "指导价格": PriceType.GUIDE.value,
            "销售价": PriceType.SALES.value,
            "销售价格": PriceType.SALES.value,
            "售价": PriceType.SALES.value,
            "内部价": PriceType.INTERNAL_QUOTE.value,
            "内部报价": PriceType.INTERNAL_QUOTE.value,
        }
        normalized["price_type"] = aliases.get(price_type.strip(), price_type.strip().upper())
    return normalized


def _explicit_model_mentions(message: str) -> list[str]:
    """仅把文本中明确出现的演示型号当作确定性比较入口。

    咨询场景经常同时出现材料名、系列名或一个具体候选（例如 P10 SPB）。
    这些词不能把“材料类别比较”升级成双产品比较；只有两个明确型号才允许
    进入既有确定性比较路径。
    """
    return list(dict.fromkeys(re.findall(
        r"(?i)(?<![a-z0-9])(?:x100|x200|y200|demo-[bd][0-9]{3})(?![a-z0-9])",
        message,
    )))[:2]


# 咨询词表由“本模块领域词 ＋ 共享词表”构成（单一来源，避免复制）：
# 供应商规则词、业务对象词与“资料咨询”意图词都来自 evidence，确保路由与证据口径一致。
_CONSULTATION_TERMS = (
    "选材", "材料", "基材", "板材", "五金", "柜体", "门板", "增项", "包含项",
    "疑虑", "担心", "避坑", "交付", "验收", "核对", "防潮", "环保", "甲醛",
    "检测", "报告", "质保", "保修", "售后", "怎么选", "选哪个", "具体型号",
    "核验", "已知事实", "证明什么", "缺项", "怎么问", "没型号", "计价", "单位",
    "怎么解释", "怎么筛", "阳台柜", "继续", "下单", "原表", "每平方米", "每平米",
) + SUPPLIER_RULE_TERMS + BUSINESS_OBJECT_TERMS + SUPPLIER_DATA_QUERY_TERMS

_COMPARE_WORDS = ("对比", "比较", "区别", "差异", "哪个好", "选哪个")
_RECOMMEND_WORDS = ("推荐", "建议买", "怎么选", "适合我", "哪款", "更适合")
_NON_PRODUCT_RECOMMEND_PHRASES = ("推荐资料", "推荐文档", "推荐文件", "推荐手册")
_PRODUCT_DIRECTED_RECOMMEND_WORDS = ("建议买", "怎么选", "适合我", "哪款", "更适合", "选哪个")


def _intent_text(message: str) -> str:
    value = message.strip()
    prefixes = (
        "说人话帮我看看：", "先忽略颜色和门店装修风格，真正的问题是：",
        "客户今天到店沟通了很多背景信息，包括预算安排、家庭成员和装修进度；"
        "这些背景不应替代证据。请基于当前资料回答核心问题，并清楚区分已知、未知和待核验项：",
    )
    for prefix in prefixes:
        value = value.replace(prefix, "")
    return value.strip()


def _mention_verbatim_in_text(mention: str, text: str) -> bool:
    """型号是否逐字出现在文本中（忽略大小写，防止把更长编码误认成该型号）。"""

    if not mention:
        return False
    return re.search(
        r"(?i)(?<![a-z0-9])" + re.escape(mention) + r"(?![a-z0-9])", text,
    ) is not None


def _is_model_like(mention: str) -> bool:
    """是否形似产品型号（含 ASCII 字母或数字）。

    纯中文名多为材料或对象类别（冰火海洋板、抽屉、封边条），属于顾问检索
    范围，不升级为结构化产品查价。
    """

    return bool(re.search(r"[A-Za-z0-9]", mention))


def _apply_business_constraints(message: str, decision: RoutingDecision) -> RoutingDecision:
    """让模型路由与确定性路由遵守同一组业务边界。"""

    text = message.strip()
    explicit_mentions = _explicit_model_mentions(text)
    deterministic = deterministic_route(text)
    consultation_intent = any(term in text for term in _CONSULTATION_TERMS)
    explicit_document_action = bool(
        decision.document_id
        or re.search(r"(?:读取|阅读|打开|查看)(?:这|该|指定)?(?:份)?(?:文档|文件|手册|说明书)", text)
        or re.search(r"(?:文档|文件|手册|说明书)(?:第\d+页|内容|原文)", text)
    )

    if decision.task_type is TaskType.DOCUMENT_READ and not explicit_document_action:
        return deterministic if deterministic.task_type is not TaskType.DOCUMENT_READ else decision
    if decision.task_type in {TaskType.PRODUCT_COMPARE, TaskType.PRODUCT_RECOMMENDATION}:
        if len(explicit_mentions) < 2 and consultation_intent:
            return deterministic
    if decision.task_type is TaskType.PRICE_QUERY:
        # 结构化价格工具只覆盖演示型号，以及模型返回且在当前用户消息中
        # 逐字出现的单个产品型号（须形似型号：含 ASCII 字母或数字）；
        # 产品是否真实存在由产品仓储和价格工具核验，路由层不查询数据库。
        # 企业资料中的自然语言报价、金额、计价单位和包含项应继续检索原始
        # 资料，避免产品表未命中时提前结束；模型自行生成而用户未输入的
        # 型号仍降回咨询流程。
        user_verbatim = [
            mention for mention in decision.product_mentions
            if _is_model_like(mention) and _mention_verbatim_in_text(mention, text)
        ]
        if not user_verbatim and deterministic.task_type is TaskType.CONSULTATION:
            return deterministic
    if decision.task_type in {TaskType.KNOWLEDGE_QUERY, TaskType.UNSUPPORTED}:
        if deterministic.task_type is TaskType.CONSULTATION and not explicit_mentions:
            return deterministic
    return decision


def _apply_selected_product_intent(
    message: str,
    decision: RoutingDecision,
    *,
    selected_product_count: int,
) -> RoutingDecision:
    """让当前请求中恰好两个已选产品参与任务类型判定。

    这里只消费选择数量和当前消息中的显式意图；具体产品仍由 Service 在路由后
    解析和鉴权，不向路由模型暴露产品 ID，也不从历史文本继承比较/推荐意图。
    """

    if selected_product_count != 2:
        return decision
    intent = _intent_text(message)
    has_product_directed_recommendation = any(
        word in intent for word in _PRODUCT_DIRECTED_RECOMMEND_WORDS
    )
    is_non_product_recommendation = (
        any(phrase in intent for phrase in _NON_PRODUCT_RECOMMEND_PHRASES)
        and not has_product_directed_recommendation
    )
    if any(word in intent for word in _RECOMMEND_WORDS) and not is_non_product_recommendation:
        task_type = TaskType.PRODUCT_RECOMMENDATION
    elif any(word in intent for word in _COMPARE_WORDS):
        task_type = TaskType.PRODUCT_COMPARE
    else:
        return decision
    return decision.model_copy(update={"task_type": task_type})


def deterministic_route(message: str) -> RoutingDecision:
    text = message.strip()
    intent = _intent_text(text)
    lower = intent.lower()
    document_words = ("文档", "文件", "手册", "说明书", "第几页", "读取", "阅读")
    price_words = ("价格", "多少钱", "售价", "报价", "预算")
    natural_quote = bool(re.search(
        r"\d+(?:\.\d{1,2})?\s*元\s*(?:/|每)?\s*(?:平方米|平米|㎡|张|套|个)?", intent,
    ))
    consultation_words = _CONSULTATION_TERMS
    product_words = ("产品", "型号", "参数", "功能", "性能", "场景", "x100", "x200", "y200", "demo-", "板材", "基材", "限制")
    # Unicode ``\b`` 把中文也视为单词字符，无法识别“对比X100和Y200”。
    # 只排除相邻 ASCII 字母/数字，允许中文紧邻型号且避免误认更长编码。
    mentions = list(dict.fromkeys(re.findall(
        r"(?i)(?<![a-z0-9])(?:x100|x200|y200|demo-[bd][0-9]{3})(?![a-z0-9])", intent,
    )))[:2]
    if any(word in intent for word in _RECOMMEND_WORDS) and len(mentions) == 2:
        task = TaskType.PRODUCT_RECOMMENDATION
    elif any(word in intent for word in _COMPARE_WORDS) and len(mentions) == 2:
        task = TaskType.PRODUCT_COMPARE
    elif any(word in intent for word in document_words) and not any(
        word in intent for word in ("检测报告", "核对资料", "资料核对", "报告待核验")
    ):
        task = TaskType.DOCUMENT_READ
    elif any(word in intent for word in price_words) and len(mentions) == 1:
        task = TaskType.PRICE_QUERY
    elif natural_quote or any(word in intent for word in consultation_words + _COMPARE_WORDS + _RECOMMEND_WORDS + price_words):
        task = TaskType.CONSULTATION
    elif any(word in lower for word in product_words):
        task = TaskType.KNOWLEDGE_QUERY
    else:
        task = TaskType.UNSUPPORTED
    price_type = None
    if "内部" in intent and ("报价" in intent or "价格" in intent):
        price_type = PriceType.INTERNAL_QUOTE
    elif "指导价" in text:
        price_type = PriceType.GUIDE
    elif any(word in text for word in ("销售价", "售价")):
        price_type = PriceType.SALES
    answer_format = None
    if task is TaskType.CONSULTATION:
        if natural_quote or any(word in intent for word in ("报价", "价格", "增项", "包含项", "计价", "下单")):
            answer_format = ConsultationFormat.QUOTE_BREAKDOWN
        elif any(word in intent for word in ("核对", "验收", "交付", "清单", "疑虑", "担心", "避坑")):
            answer_format = ConsultationFormat.CHECKLIST
        elif any(word in text for word in _COMPARE_WORDS):
            answer_format = ConsultationFormat.COMPARISON_TABLE
        else:
            answer_format = ConsultationFormat.CANDIDATES
    return RoutingDecision(
        task_type=task,
        normalized_query=text[:500],
        product_mentions=[item.upper() for item in mentions],
        budget=(re.search(r"预算\s*(?:为|是|不超过|[:：])?\s*(\d+(?:\.\d{1,2})?)", text).group(1) if re.search(r"预算\s*(?:为|是|不超过|[:：])?\s*(\d+(?:\.\d{1,2})?)", text) else None),
        price_type=price_type,
        retrieval_queries=[text[:500]] if task is TaskType.CONSULTATION else [],
        answer_format=answer_format,
    )


class AgentRouter:
    def __init__(self, provider: LLMProvider | None):
        self.provider = provider

    def route(self, message: str, *, timeout: float, max_tokens: int,
              history_text: str = "", effective_query: str | None = None,
              selected_product_count: int = 0) -> RouteResult:
        if self.provider is not None:
            try:
                completion = self.provider.complete(
                    messages=[
                        {"role": "system", "content": _ROUTER_SYSTEM},
                        {"role": "user", "content": (
                            f"最近可访问会话（仅用于理解条件）：\n{history_text}\n\n当前问题：\n{message}"
                            if history_text else message
                        )},
                    ],
                    timeout=timeout,
                    max_tokens=min(max_tokens, 600),
                    model=self.provider.router_model,
                    json_mode=True,
                    thinking_enabled=False,
                )
                decision = RoutingDecision.model_validate(
                    _normalize_route_payload(_json_object(completion.content))
                )
                decision = _apply_business_constraints(effective_query or message, decision)
                decision = _apply_selected_product_intent(
                    message, decision, selected_product_count=selected_product_count,
                )
                return RouteResult(decision, [], 1, [completion.usage], completion.model)
            except (ValidationError, ValueError, json.JSONDecodeError, Exception):
                # 路由失败只保留稳定警告；原始异常不写入消息或日志。
                pass
        decision = deterministic_route(effective_query or message)
        decision = _apply_selected_product_intent(
            message, decision, selected_product_count=selected_product_count,
        )
        return RouteResult(decision, [ROUTING_FALLBACK],
                           0 if self.provider is None else 1, [], None)


__all__ = [
    "AgentRouter", "ROUTING_FALLBACK", "RouteResult", "deterministic_route",
]
