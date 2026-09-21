"""Consultation evidence labels and lightweight relevance policy.

The knowledge index remains unchanged.  This module only decides how already
authorized chunks are presented to the consultation generator, so that a
selection guide or platform statement cannot silently become a product fact.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.schemas.agent import Citation


CATEGORY_LABELS: dict[str, str] = {
    "PRODUCT_FACT": "产品事实",
    "OFFICIAL_SOURCE": "官方来源",
    "PRODUCT_RELATION": "产品关系",
    "SELECTION_GUIDE": "选型参考",
    "PLATFORM_STATEMENT": "平台观点",
    "USER_PAIN_POINT": "用户痛点",
    "SUPPLIER_QUOTE": "供应商报价",
    "SOURCE_REGISTRY": "来源登记",
    "CHANGE_EVENT": "变化事件",
    "PRICE": "结构化价格",
}

_FACT_CATEGORIES = {"PRODUCT_FACT", "OFFICIAL_SOURCE", "PRODUCT_RELATION"}
_PLATFORM_CATEGORIES = {"PLATFORM_STATEMENT", "USER_PAIN_POINT"}
_QUOTE_CATEGORIES = {"SUPPLIER_QUOTE", "PRICE"}
_REFERENCE_CATEGORIES = {"SELECTION_GUIDE", "SOURCE_REGISTRY"}

# These are deliberately small, domain terms rather than a general Chinese
# tokenizer.  They make the filter deterministic and preserve recall for
# ordinary Chinese questions while dropping an unrelated platform anecdote.
_DOMAIN_TERMS = (
    "厨房", "衣柜", "阳台", "卫浴", "柜体", "门板", "五金", "板材", "基材",
    "防潮", "防水", "环保", "甲醛", "ENF", "HENF", "MODEL_A", "OSB", "PET",
    "厚度", "尺寸", "承重", "封边", "安装", "交付", "验收", "核对", "合同",
    "质保", "售后", "增项", "包含项", "报价", "价格", "单位", "预算", "检测",
    "报告", "来源", "型号", "品牌", "适用", "限制", "痛点", "选材", "材料",
    "墙板", "金属", "素色", "下单", "按张", "平方米", "平米",
)
_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,30}")
_NOISE_PREFIXES = (
    "说人话帮我看看：", "先忽略颜色和门店装修风格，真正的问题是：",
    "客户今天到店沟通了很多背景信息，包括预算安排、家庭成员和装修进度；"
    "这些背景不应替代证据。请基于当前资料回答核心问题，并清楚区分已知、未知和待核验项：",
)
_SUBJECT_MARKERS = (
    "示例品牌A", "示例品牌B", "示例板材", "MODEL_A", "MODEL_B", "SPB",
    "多层板", "OSB", "欧松板", "颗粒板", "竹材板", "密度板", "门把手",
)
_FOLLOW_UP_MARKERS = (
    "继续", "刚才", "前面", "上述", "最新条件", "按最新", "总结", "改成", "改为",
    "换成", "调整为", "以我刚说的", "为准", "那", "这个", "这两个", "再看",
)
_SCENE_MARKERS = ("厨房", "衣柜", "阳台", "卫浴", "柜体", "门板")
_COLOR_MARKERS = ("素色", "木纹", "金属", "哑光", "亮光", "肤感", "颜色", "饰面")

# 业务对象词：供应商记录的“条目类别/报价对象”字段用的就是这类词。既是词面补充的
# 锚点、也从“去词”结果中剔除避免连写片段污染，并作为路由与证据共用的对象词汇。
BUSINESS_OBJECT_TERMS = (
    "抽屉", "拉手", "玻璃拉手", "通体长拉手", "封边条", "墙板", "柜体", "柜门",
    "门板", "五金", "台面", "板材", "基材", "铰链", "滑轨", "拉篮", "窄柜", "矮柜",
    "不锈钢", "木门", "原木门", "储物柜", "吊柜", "地柜", "电视柜", "鞋柜", "酒柜",
    "餐边柜", "橱柜", "衣柜", "卫浴柜", "阳台柜", "移门", "免漆门", "上翻门", "上翻柜",
    "投影报价", "保修",
)

# “资料咨询”意图词：客户在问已有资料里写了什么、有哪些候选、内部价是否可查。
# 与对象词一起构成路由的咨询判定依据，避免只为个别案例追加句式。
SUPPLIER_DATA_QUERY_TERMS = (
    "现有资料", "资料里", "资料中", "资料显示", "明确了", "写明", "候选",
    "内部价", "底价", "内部报价", "内部供应商",
)


def category_key(value: str | None) -> str:
    return (value or "").strip().upper() or "UNKNOWN"


def category_label(value: str | None) -> str:
    key = category_key(value)
    return CATEGORY_LABELS.get(key, "其他资料")


def _terms(text: str) -> set[str]:
    value = text.upper()
    terms = {term.upper() for term in _DOMAIN_TERMS if term.upper() in value}
    terms.update(term.upper() for term in BUSINESS_OBJECT_TERMS if term.upper() in value)
    terms.update(token.upper() for token in _ASCII_TOKEN.findall(text))
    return terms


def _overlap(query: str, text: str) -> int:
    query_terms = _terms(query)
    if not query_terms:
        return 0
    body = text.upper()
    return sum(1 for term in query_terms if term in body)


def normalize_consultation_query(query: str) -> str:
    """移除测试式口语前缀和已明确取消的条件，保留可检索业务词。"""

    value = query.strip()
    for prefix in _NOISE_PREFIXES:
        value = value.replace(prefix, "")
    value = re.sub(r"先忽略[^，。；：:]{1,80}[，。；：:]", "", value)
    value = re.sub(r"不沿用之前[^，。；]{1,30}(?:条件)?", "", value)
    value = re.sub(r"(?:预算|品牌|型号)(?:先)?(?:不考虑|取消|不要|不沿用)[^，。；]{0,30}", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ，。；：:")
    return value[:500] or query.strip()[:500]


def _condition_tokens(text: str) -> set[str]:
    """提取会造成旧条件污染的显式对象和数值条件。"""

    tokens = {term.upper() for term in (*_SUBJECT_MARKERS, *_SCENE_MARKERS) if term.upper() in text.upper()}
    tokens.update(match.upper().replace(" ", "") for match in re.findall(
        r"\d+(?:\.\d+)?\s*(?:毫米|mm|厘米|cm|元|万元|平方(?:米)?|㎡)", text, re.IGNORECASE,
    ))
    return tokens


def effective_consultation_query(current_query: str, user_history: Iterable[str]) -> str:
    """构造轻量的当前有效咨询上下文。

    只继承用户消息；短追问或条件修正才承接历史。当前厚度、预算、颜色及明确
    替换项会覆盖旧值，避免把已取消条件再次送入路由、检索和证据筛选。
    """

    raw_current = current_query.strip()
    raw_history = [item.strip() for item in user_history if item.strip()]
    cancelled_values = re.findall(
        r"不再按([^，。；\s]{1,16}?)(?:报价|条件|计算|比较|考虑|处理)", raw_current,
    )
    historical_cancelled = re.findall(
        r"不再按([^，。；\s]{1,16}?)(?:报价|条件|计算|比较|考虑|处理)",
        "；".join(raw_history[-4:]),
    )
    current = normalize_consultation_query(raw_current)
    # 修正句在有效上下文中只保留新值，避免旧值仍被检索器当成有效条件。
    current = re.sub(
        r"\d+(?:\.\d+)?\s*(?:毫米|mm|厘米|cm)\s*(?:改成|改为|换成|调整为)\s*"
        r"(\d+(?:\.\d+)?\s*(?:毫米|mm|厘米|cm))",
        r"\1", current, flags=re.IGNORECASE,
    )
    current = re.sub(
        r"(?:素色|木纹|金属|哑光|亮光|肤感)\s*(?:改成|改为|换成|调整为)\s*"
        r"(素色|木纹|金属|哑光|亮光|肤感)",
        r"\1", current,
    )
    current = re.sub(
        r"(颜色|饰面)\s*(?:改成|改为|换成|调整为)\s*"
        r"(素色|木纹|金属|哑光|亮光|肤感)",
        r"\1 \2", current,
    )
    current = re.sub(r"不再按[^，。；]{1,24}(?:报价|条件|计算|比较|考虑|处理)", "", current)
    history = [normalize_consultation_query(item) for item in raw_history]
    if not history:
        return current
    # 显式型号/系列是新的明确对象，不能因为问句较短就把上一轮主题拼进来。
    # 例如从“厨房潮湿柜体板”转问“DEMO-B001 的检测报告编号”时，继续
    # 继承厨房主题会把无关甲醛/选型记录带入检索和生成降级结果。
    has_subject = bool(
        object_anchors(current)
        or _specific_subjects(current)
        or any(term in current for term in _SCENE_MARKERS)
    )
    is_follow_up = any(marker in current for marker in _FOLLOW_UP_MARKERS) or (len(current) <= 80 and not has_subject)
    if not is_follow_up:
        return current

    inherited = "；".join(history[-4:])
    for value in [*cancelled_values, *historical_cancelled]:
        inherited = inherited.replace(value, "")
    # 显式的 old -> new 修正优先删除旧字面值。
    for old in re.findall(r"([^，。；\s]{1,16}?)(?:改成|改为|换成|调整为)", current):
        inherited = inherited.replace(old, "")
    thicknesses = re.findall(r"\d+(?:\.\d+)?\s*(?:毫米|mm|厘米|cm)", current, re.IGNORECASE)
    if thicknesses:
        inherited = re.sub(r"\d+(?:\.\d+)?\s*(?:毫米|mm|厘米|cm)", "", inherited, flags=re.IGNORECASE)
    if "预算" in current:
        inherited = re.sub(r"预算\s*(?:为|是|不超过|[:：])?\s*\d+(?:\.\d+)?\s*(?:元|万元)?", "", inherited)
    if any(term in current for term in _COLOR_MARKERS):
        for term in _COLOR_MARKERS:
            if term not in current or term in cancelled_values or term in historical_cancelled:
                inherited = inherited.replace(term, "")
        recent_color_correction = any(
            any(marker in item for marker in ("改成", "改为", "换成", "调整为", "不再按"))
            and any(term in item for term in _COLOR_MARKERS)
            for item in raw_history[-4:]
        )
        if recent_color_correction or any(
            marker in raw_current for marker in ("改成", "改为", "换成", "调整为", "不再按")
        ):
            inherited = re.sub(
                r"\d+(?:\.\d+)?\s*元",
                lambda match: match.group(0) if inherited[max(0, match.start() - 2):match.start()] == "预算" else "",
                inherited,
            )
    if any(marker in current for marker in ("为准", "不沿用", "取消")):
        current_scenes = {term for term in _SCENE_MARKERS if term in current}
        for term in _SCENE_MARKERS:
            if term not in current_scenes:
                inherited = inherited.replace(term, "")
    combined = normalize_consultation_query(f"{inherited}；{current}")
    return combined[:500]


def consultation_queries(current_query: str, proposed: Iterable[str],
                         follow_up_question: str | None = None) -> list[str]:
    """在现有检索链内生成至多三个简洁、互补的检索问题。

    原始有效问题始终排第一，路由模型生成的检索词只能作为补充。
    复合问题中的明确型号/系列锚点优先于模型补充检索式：并列询问的每个对象
    各得一个专属查询，避免在合并查询里互相挤出（如“A100和B系列分别明确了什么”）。
    后续轮（``follow_up_question`` 非空）用会话主题承载历史对象上下文，并让当前
    问题本身成为独立查询——安装字段等新意图不再被裸对象名挤出。
    """

    current = normalize_consultation_query(current_query)
    candidates: list[str] = [current] if current else []
    follow = normalize_consultation_query(follow_up_question or "")
    if (follow and follow != current and len(follow) >= 4
            and not re.match(r"^(?:改成|改为|换成|调整为)", follow)
            and re.search(r"[\u4e00-\u9fa5A-Za-z]", follow)):
        # 纯数字/短承接（“20000”“按米”）与条件纠正（“改成5”）不作为独立查询
        if follow not in candidates:
            candidates.append(follow)
    else:
        follow = ""
    if not follow:
        # 首轮复合问题：锚点专查保证并列对象各自召回
        for anchor in object_anchors(current):
            if anchor not in candidates:
                candidates.append(anchor)
    for item in proposed:
        clean = normalize_consultation_query(item)
        if clean and clean != current and clean not in candidates:
            # 模型生成的检索式不得重新带回当前有效上下文已经取消的对象或数值条件。
            stale_terms = _condition_tokens(item) - _condition_tokens(current)
            if stale_terms:
                continue
            candidates.append(clean)
    if follow:
        # 后续轮兜底：会话对象 + 当前问题组合，替代裸对象名专查
        for anchor in object_anchors(current):
            combined = normalize_consultation_query(f"{anchor} {follow}")
            if combined and combined not in candidates:
                candidates.append(combined)
                break
    terms = [term for term in _DOMAIN_TERMS if term in current]
    subjects = [term for term in _SUBJECT_MARKERS if term.upper() in current.upper()]
    compact = " ".join(dict.fromkeys([*subjects, *terms]))
    if len(candidates) == 1 and compact and compact not in candidates:
        candidates.append(compact[:500])
    if any(term in current for term in ("有人说", "说法", "冲突", "分别能证明")) and len(candidates) < 3:
        candidates.append("官方来源 平台观点 环保等级 封边 检测报告")
    return candidates[:3]


# 复合问题中的明确对象锚点：ASCII 型号（A100、X100、ENF）与“品牌＋系列”（B系列）。
_OBJECT_ANCHOR_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<model>[A-Za-z][A-Za-z0-9_-]{1,15})(?![A-Za-z0-9_-])"
    r"|(?P<series>[\u4e00-\u9fa5]{0,3}[A-Za-z0-9][A-Za-z0-9.]{0,8}系列)"
)
# 系列名只保留紧邻“系列”的 ≤2 字品牌前缀，剥离“对比/和”等动词与连词。
_SERIES_ANCHOR_RE = re.compile(r"[\u4e00-\u9fa5]{0,2}[A-Za-z0-9][A-Za-z0-9.]{0,8}系列")


def object_anchors(query: str, limit: int = 2) -> list[str]:
    """从复合咨询问题中提取至多 ``limit`` 个明确对象锚点（型号或系列名）。"""

    anchors: list[str] = []
    for match in _OBJECT_ANCHOR_RE.finditer(query):
        value = (match.group("model") or match.group("series") or "").strip()
        if match.group("series"):
            trimmed = _SERIES_ANCHOR_RE.search(value)
            value = trimmed.group(0) if trimmed else value
        if value and value.upper() not in {item.upper() for item in anchors}:
            anchors.append(value)
        if len(anchors) >= limit:
            break
    return anchors


def _specific_subjects(query: str) -> set[str]:
    return {term.upper() for term in _SUBJECT_MARKERS if term.upper() in query.upper()}


def is_session_follow_up(query: str) -> bool:
    """判断当前消息是否为对上一轮条件的延续或修正，从而应继承会话条件。

    新业务对象（含明确场景/主题词）不视为延续，旧会话条件不继承。
    """

    value = query.strip()
    if any(marker in value for marker in _FOLLOW_UP_MARKERS):
        return True
    has_subject = bool(
        object_anchors(value)
        or _specific_subjects(value)
        or any(term in value for term in _SCENE_MARKERS)
    )
    return len(value) <= 80 and not has_subject


def is_quote_query(query: str) -> bool:
    return any(term in query for term in (
        "报价", "多少钱", "单价", "价格", "计价", "金额", "预算", "定金", "税",
    )) or bool(re.search(
        r"\d+(?:\.\d{1,2})?\s*元|(?:元\s*)?[/每]\s*(?:平方米|平米|㎡|张|套|个)", query,
        re.IGNORECASE,
    ))


# “含报价字样”不等于“具有可用报价证据”：只有出现具体金额、计价单位或
# 定金/计价/单价等业务词，才算可支撑价格或定金回答的报价证据。
_QUOTE_AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:元|万元|%|％)")
_QUOTE_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:/|每)?\s*(?:平方米|平米|㎡|平|米|张|卷|套|个|付|扇|片|项|托)"
)
_QUOTE_BUSINESS_TERMS = (
    "单价", "定金", "订金", "计价", "金额", "收费", "费用", "付款", "结算",
    "尾款", "首付", "税金",
)


def _has_quote_evidence(chunk_text: str) -> bool:
    return bool(
        _QUOTE_AMOUNT_RE.search(chunk_text)
        or _QUOTE_UNIT_RE.search(chunk_text)
        or any(term in chunk_text for term in _QUOTE_BUSINESS_TERMS)
    )


# “CAD”在报价语境中是业务词（凭CAD图下单 / CAD设计服务），不是产品型号，
# 不能像型号一样要求 Chunk 逐字包含，否则会误删同一供应商的其它报价记录。
_MODEL_NOISE = {"mm", "cm", "m", "元", "价格", "报价", "多少钱", "cad"}

# 业务对象意图：用于区分“柜体/整单下单规则”和“CAD设计服务”，避免用设计服务
# 定金替代柜体订单定金。词表是业务词汇，不包含具体供应商、记录编号或答案。
_ORDER_INTENT_TERMS = ("下单", "订单", "柜体", "柜子", "整单", "出货", "尾款", "首付")
_DESIGN_INTENT_TERMS = ("设计服务", "设计费", "效果图", "改图", "出图", "制图", "测量")

# 供应商记录内的“规则/条件”内容：供应商报价表把付款、计量、交付等规则登记在同一批
# 记录里。问句问的是这类内容时，报价类记录不应因“不像价格问句”被整类过滤（例如
# “最低计量怎么算”“生产周期怎么规定”），路由也应把它识别为咨询而非 UNSUPPORTED。
# 该常量是唯一来源，由本模块与 `router.py` 共同使用，避免两处口径漂移。
SUPPLIER_RULE_TERMS = (
    "规则", "条件", "口径", "条款", "规定", "怎么算", "如何算", "按什么算",
    "最低计量", "计量", "递增", "起订", "起付", "不足",
    "生产周期", "补单", "工期", "交期", "交付", "提货", "发货", "出货", "仓储",
    "包含", "包含项", "增项", "不含", "赠送", "运费", "质保", "售后",
)


# 记录的“条目类别/报价对象/实体类型/选型维度”字段是业务对象最集中的位置。查询问到的
# 业务对象直接出现在这里，说明该记录就是针对该对象登记的规则或选型维度，而不是顺带提及。
_METADATA_FIELD_RE = re.compile(
    r"(?:条目类别|报价对象|实体类型|选型维度)[：:]([^；;]{1,120})"
)
_OBJECT_FIELD_LABELS = ("条目类别：", "报价对象：", "实体类型：", "选型维度：")


def lexical_object_anchors(anchors: Iterable[str]) -> list[str]:
    """把锚点扩成“字段限定”形式（如“报价对象：抽屉”）。

    词面候选补充用它优先命中记录的业务对象字段，避免仅凭正文里顺带出现的对象词
    把无关记录排到补充候选前面。
    """

    return [f"{label}{term}" for term in anchors for label in _OBJECT_FIELD_LABELS]


def is_supplier_rule_query(query: str) -> bool:
    """问句是否在询问记录内的规则/条件内容（而非价格数字本身）。"""

    return any(term in query for term in SUPPLIER_RULE_TERMS)


def _query_object_terms(query: str) -> list[str]:
    """查询中的业务对象词（业务名词、场景词、材料/品牌词）。"""

    upper = query.upper()
    return [
        term for term in (*BUSINESS_OBJECT_TERMS, *_SCENE_MARKERS, *_SUBJECT_MARKERS)
        if term.upper() in upper
    ]


def _object_relevance(query: str, chunk_text: str) -> bool:
    """查询的业务对象是否出现在记录的“条目类别/报价对象”字段中。

    这是规则型问句放行报价记录时的对象相关性约束：只有记录本身就是针对该对象
    登记的规则，才允许进入上下文；仅有字面重叠的无关记录仍被过滤。
    """

    fields = "；".join(_METADATA_FIELD_RE.findall(chunk_text)).upper()
    if not fields:
        return False
    return any(term.upper() in fields for term in _query_object_terms(query))


def _query_model_token(query: str) -> str | None:
    """提取查询中的明确型号/编号（字母开头），用于对象匹配约束。"""

    for token in _ASCII_TOKEN.findall(query):
        if token.lower() not in _MODEL_NOISE and len(token) >= 2:
            return token
    return None


def consultation_allowed(query: str, citation: Citation, chunk_text: str) -> bool:
    """Return whether a category is usable for this consultation.

    Product facts and relations are retained even when lexical overlap is low:
    vector retrieval already established relevance.  Restricted categories are
    removed only when their own usage boundary is clearly unrelated.
    """

    key = category_key(citation.evidence_category)
    overlap = _overlap(query, chunk_text)
    quote_query = is_quote_query(query)
    # 报价/定金问题对所有类别都要求可用的报价证据：只带“报价字样”的选型参考、
    # 平台观点或来源登记不能单独支撑价格或定金回答。
    if quote_query and not _has_quote_evidence(chunk_text):
        return False
    if key in _QUOTE_CATEGORIES:
        if not quote_query:
            # 供应商报价表同时登记付款/计量/交付等规则。问句在问这类规则内容、且记录
            # 本身就是针对该对象登记时放行；仅有字面重叠的无关报价记录仍被过滤。
            if not (
                is_supplier_rule_query(query)
                and _has_quote_evidence(chunk_text)
                and _object_relevance(query, chunk_text)
            ):
                return False
        quote_variants = {term for term in ("素色", "金属", "木纹") if term in query}
        if len(quote_variants) == 1 and not next(iter(quote_variants)) in chunk_text:
            return False
        # 明确型号对象匹配：查询含明确型号/编号，chunk 不含该编号则过滤，不用相似候选兜底。
        model = _query_model_token(query)
        if model and model not in chunk_text:
            return False
        return True
    subjects = _specific_subjects(query)
    body_upper = chunk_text.upper()
    if subjects and key in _FACT_CATEGORIES and not any(subject in body_upper for subject in subjects):
        return False
    if key in _PLATFORM_CATEGORIES:
        required = 1 if any(term in query for term in (
            "平台", "疑虑", "避坑", "交付", "售后", "有人说", "说法", "冲突", "分别能证明",
        )) else 2
        return overlap >= required
    if key == "SOURCE_REGISTRY":
        return overlap > 0 or any(term in query for term in ("来源", "证据", "出处"))
    if key in _REFERENCE_CATEGORIES:
        # 选型参考/来源登记：只在与本问题的业务对象相关时才保留。
        # 对象相关性优先于字面重叠——查询只含场景描述（“600毫米高、1700毫米宽的上翻柜”）
        # 时，选型维度记录仍应放行，而不是被字面重叠为 0 丢掉。
        # 安装字段问句的会话对象在历史主题里、当前意图在最新问题里，两类记录
        # （登记了必须字段/输入条件/来源要求的选型维度）按结构字段对齐放行。
        return overlap > 0 or _object_relevance(query, chunk_text) or _installation_intent_relevance(query, chunk_text)
    return True


# 安装字段问句的触发词（与 _QUERY_INTENT_MAP 的安装映射触发词一致）。
_INSTALL_INTENT_TRIGGERS = ("安装字段", "核对哪些安装", "安装条件", "安装资料")
# 选型记录登记“该维度需要什么资料”的结构字段；记录正文与安装意图的
# 相关性看这些字段值与问句条件词的交集，而不是整段字面重叠。
_INSTALL_STRUCTURE_FIELD_RE = re.compile(
    r"(?:必须字段|输入条件|来源要求|当前覆盖)[：:]([^；;]{1,120})"
)
_CONDITION_PREFIX_RE = re.compile(r"[\u4e00-\u9fff]{2,4}(?=\d)")


def _install_structure_alignment(query: str, chunk_text: str) -> int:
    """安装字段问句与选型记录结构字段的对齐度：2=条件词精确对齐，1=意图词对齐，0=无关。

    查询含安装意图触发词时，比对其登记的必须字段/输入条件/来源要求/当前覆盖
    与问句条件词（如“门厚22毫米”的“门厚”）或安装意图词本身的交集；
    客户数值落在记录选型维度登记的适用范围内（如“15-26mm厚柜门”与 22 毫米）
    同样属于条件词精确对齐。
    """

    if not any(term in query for term in _INSTALL_INTENT_TRIGGERS):
        return 0
    structured = _INSTALL_STRUCTURE_FIELD_RE.findall(chunk_text)
    if not structured:
        return 0
    condition_terms = set(_CONDITION_PREFIX_RE.findall(query))
    if condition_terms and any(
        any(term in value for term in condition_terms) for value in structured
    ):
        return 2
    if _query_number_within_dimension_range(query, chunk_text):
        return 2
    intent_terms = {term for term in _INSTALL_INTENT_TRIGGERS if term in query}
    if intent_terms and any(
        any(term in value for term in intent_terms) for value in structured
    ):
        return 1
    return 0


_RANGE_DIMENSION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?")
_NUMBER_RE_INSTALL = re.compile(r"\d+(?:\.\d+)?")


def _query_number_within_dimension_range(query: str, chunk_text: str) -> bool:
    """客户输入数值是否落在记录选型维度登记的数值范围内。"""

    numbers = [float(value) for value in _NUMBER_RE_INSTALL.findall(
        _CONDITION_PREFIX_RE.split(query or "")[-1] if _CONDITION_PREFIX_RE.search(query or "") else ""
    )]
    if not numbers:
        return False
    dimension_values = "；".join(_METADATA_FIELD_RE.findall(chunk_text))
    for low, high in _RANGE_DIMENSION_RE.findall(dimension_values):
        low_value, high_value = float(low), float(high)
        if any(low_value <= number <= high_value for number in numbers):
            return True
    return False


def _installation_intent_relevance(query: str, chunk_text: str) -> bool:
    """安装字段问句与选型记录结构字段的对齐判定（用于参考类记录放行）。"""

    return _install_structure_alignment(query, chunk_text) > 0


def _intent_affinity(query: str, chunk_text: str) -> int:
    """业务对象兼容度：柜体/整单下单规则与 CAD 设计服务互不替代。"""

    query_order = any(term in query for term in _ORDER_INTENT_TERMS)
    query_design = any(term in query for term in _DESIGN_INTENT_TERMS)
    chunk_order = any(term in chunk_text for term in _ORDER_INTENT_TERMS)
    chunk_design = any(term in chunk_text for term in _DESIGN_INTENT_TERMS)
    score = 0
    if query_order and chunk_order:
        score += 1
    if query_design and chunk_design:
        score += 1
    if query_order and chunk_design and not chunk_order:
        score -= 1
    if query_design and chunk_order and not chunk_design:
        score -= 1
    return score


def _metadata_object_hit(query: str, chunk_text: str) -> int:
    fields = "；".join(_METADATA_FIELD_RE.findall(chunk_text))
    if not fields:
        return 0
    terms = [
        term for term in (
            *_SUPPLEMENT_INTENT_TERMS, *_ORDER_INTENT_TERMS, *_DESIGN_INTENT_TERMS,
            *BUSINESS_OBJECT_TERMS, *_SCENE_MARKERS,
        )
        if term in query
    ]
    return 1 if any(term in fields for term in terms) else 0


def consultation_rank(query: str, citation: Citation, chunk_text: str, order: int) -> tuple[int, int, int]:
    key = category_key(citation.evidence_category)
    priority = {
        "PRODUCT_FACT": 50,
        "OFFICIAL_SOURCE": 48,
        "PRODUCT_RELATION": 44,
        "CHANGE_EVENT": 35,
        "SELECTION_GUIDE": 25,
        "PLATFORM_STATEMENT": 15,
        "USER_PAIN_POINT": 14,
        "SOURCE_REGISTRY": 5,
        "SUPPLIER_QUOTE": 60 if (is_quote_query(query) or is_supplier_rule_query(query)) else 10,
        "PRICE": 60 if is_quote_query(query) else 10,
        "UNKNOWN": 0,
    }.get(key, 0)
    return (_overlap(query, chunk_text) * 10 + priority
            + _intent_affinity(query, chunk_text) * 20
            + _metadata_object_hit(query, chunk_text) * 15
            + _install_structure_alignment(query, chunk_text) * 15,
            -order, -len(chunk_text))


def evidence_context_lines(citation: Citation) -> list[str]:
    """Human-readable metadata passed to the model and shown in the UI."""

    lines = [f"证据类别：{category_label(citation.evidence_category)}"]
    if citation.evidence_category:
        lines.append(f"证据枚举：{category_key(citation.evidence_category)}")
    if citation.source_id:
        lines.append(f"来源ID：{citation.source_id}")
    if citation.record_id:
        lines.append(f"记录ID：{citation.record_id}")
    if citation.usage_restriction:
        lines.append(f"使用限制：{citation.usage_restriction}")
    return lines


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


# ---------------------------------------------------------------------------
# 短回复槽位绑定
# ---------------------------------------------------------------------------

_SLOT_PATTERNS = (
    (re.compile(r"投影面积|多少平方米|多少㎡|多少平米|几个平方|几平方米"), "投影面积", "㎡"),
    (re.compile(r"计价长度|多少米|几米|多长"), "计价长度", "米"),
    (re.compile(r"订单金额|定金金额|金额多少|多少金额"), "订单金额", "元"),
    (re.compile(r"几卷|多少卷"), "数量", "卷"),
    (re.compile(r"几张|多少张"), "数量", "张"),
    (re.compile(r"几套|多少套"), "数量", "套"),
    (re.compile(r"多少个|几个|数量(?:是多少|多少|为多少|几)"), "数量", "个"),
)

# 确认式数值追问：回答复述一个数值并请客户确认（“这10个抽屉的计价数量就是10个吗”
# “数量是10个吗”“按80㎡确认吗”“长度就是2.5米吗”）。这类问句同样是待补数值条件，
# 但数值在客户确认前只登记为待补槽位，不写入已确认条件。
_CONFIRM_NUMERIC_RE = re.compile(
    r"(?:是否就是|是不是|就是|确认为|确认按|是|按|为)\s*"
    r"(\d+(?:\.\d+)?)\s*(平方米|平米|㎡|米|个|张|套|卷|项|付|扇|片|托|元)"
)
_CONFIRM_UNIT_SLOTS: dict[str, tuple[str, str]] = {
    "平方米": ("投影面积", "㎡"), "平米": ("投影面积", "㎡"), "㎡": ("投影面积", "㎡"),
    "米": ("计价长度", "米"),
    "元": ("订单金额", "元"),
    "个": ("数量", "个"), "张": ("数量", "张"), "套": ("数量", "套"), "卷": ("数量", "卷"),
    "项": ("数量", "项"), "付": ("数量", "付"), "扇": ("数量", "扇"),
    "片": ("数量", "片"), "托": ("数量", "托"),
}

# 简短数值回复中允许显式出现的单位；单位始终以用户显式输入为准，槽位单位仅作默认。
_SHORT_REPLY_UNITS = ("㎡", "平方米", "平米", "米", "个", "张", "套", "卷")

# 计量单位选择问题涉及的单位（用于识别“按米还是按卷”这类选择澄清）。
_MEASURE_UNITS = ("平方米", "平米", "㎡", "卷", "张", "套", "个", "米", "元", "付", "扇", "片", "项", "托")

# 只问“按什么计价单位/计价口径”的疑问句：没有并列单位，也属于单位选择澄清，
# 必须登记为选择槽位，否则下一轮的单位回复会成为无人承接的悬空消息。
_UNIT_QUERY_RE = re.compile(
    r"计价单位|计价口径|什么单位|哪个单位|按什么单位|按哪个单位|单位是什么|用什么单位"
)

# 只有疑问句或“请补充/请确认”语句才是真正的追问；回答正文中的陈述句不得再生槽位。
_ASK_MARKERS = (
    "请补充", "请确认", "请提供", "请说明", "请告知", "请明确", "麻烦确认", "请问",
    "需要确认", "需要补充", "需要先确认", "还需确认", "还需要", "待确认",
)
_ASK_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


def extract_object(query: str) -> str:
    """从查询提取业务对象，用于把简短数字回复绑定到正确的对象。"""

    # 会话感知查询含“；客户会话条件：”后缀，剥离后再提取对象，避免对象被污染漂移。
    query = query.split("；客户会话条件：")[0].strip()
    scenes = [term for term in _SCENE_MARKERS if term in query]
    if scenes:
        return scenes[0]
    subjects = [term for term in _SUBJECT_MARKERS if term.upper() in query.upper()]
    if subjects:
        return subjects[0]
    cleaned = query
    for noise in ("怎么算", "怎么报价", "多少钱", "报价", "单价", "下单", "收多少",
                  "定金", "是什么", "多少", "一个", "几个", "我需要"):
        cleaned = cleaned.replace(noise, "")
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:mm|毫米|元|㎡|平方米|米|个|张|×)", " ", cleaned)
    # 业务对象只取问句主干：在首个句末标点处截断，避免把“？还有哪些规则”并入对象名。
    head = re.split(r"[？?！!。；;]", cleaned, maxsplit=1)[0].strip(" ，,、：:（(")
    if head:
        cleaned = head
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。；：？！,?!")
    return cleaned[:20] or query[:20]


def _ask_sentences(answer: str) -> list[str]:
    """切分回答并只保留疑问句或“请补充/请确认”语句。"""

    result: list[str] = []
    for segment in _ASK_SENTENCE_SPLIT.split(answer):
        clean = segment.strip().strip("*#- ").strip()
        if not clean:
            continue
        if any(marker in clean for marker in _ASK_MARKERS) or "？" in clean or "?" in clean:
            result.append(clean)
    return result


def _prev_char(sentence: str, index: int) -> str:
    """返回位置 ``index`` 之前最近的非空格字符；无则返回空串。"""

    cursor = index - 1
    while cursor >= 0 and sentence[cursor] == " ":
        cursor -= 1
    return sentence[cursor] if cursor >= 0 else ""


def _is_number_attached(sentence: str, index: int) -> bool:
    """判断位置 ``index`` 的单位是否紧跟在数字之后（如“55元”“100 米”）。

    这类单位表示金额或规格数值，不是被对比的计价口径，不应作为选择项。
    """

    return _prev_char(sentence, index).isdigit()


def _is_unit_mention(sentence: str, index: int) -> bool:
    """判断该位置的单位是否为真正的计量单位提及。

    “哪个”“哪些”中的“个”是疑问语素，不是计量单位。
    """

    return _prev_char(sentence, index) != "哪"


def _unit_position(sentence: str, unit: str) -> int | None:
    """返回单位作为计价口径出现的位置；跳过数值后或疑问语素中的同名单位。"""

    start = 0
    while True:
        index = sentence.find(unit, start)
        if index == -1:
            return None
        if not _is_number_attached(sentence, index) and _is_unit_mention(sentence, index):
            return index
        start = index + 1


def _choice_options(sentence: str) -> list[str]:
    """提取句中作为计价口径对比的单位，按出现顺序去重。"""

    ordered = sorted(
        ((index, unit) for unit in _MEASURE_UNITS
         if (index := _unit_position(sentence, unit)) is not None),
        key=lambda item: item[0],
    )
    units = [unit for _, unit in ordered]
    # 更长单位优先：出现“平方米”时不再同时列出其子串“米”。
    return [unit for unit in units if not any(unit != other and unit in other for other in units)]


def _is_unit_choice_question(sentence: str) -> bool:
    """判断语句是否为计量单位选择（如“按米还是按卷”），而非数值追问。"""

    if "还是" not in sentence and "或者" not in sentence:
        return False
    return len(_choice_options(sentence)) >= 2


def _is_business_choice_question(sentence: str) -> bool:
    """识别“生产下单还是设计服务”一类前置业务场景选择。

    只有问句真正并列两个业务场景时才成立：生产/下单侧与设计服务侧同时出现，
    或出现“场景/前者/后者”这类场景标记。条件确认句（“请确认是按80㎡计算，还是
    改成其他面积”）不属于业务场景选择。
    """

    if _is_unit_choice_question(sentence):
        return False
    if "还是" not in sentence and "或者" not in sentence:
        return False
    order_side = any(term in sentence for term in _ORDER_INTENT_TERMS)
    design_side = any(term in sentence for term in _DESIGN_INTENT_TERMS)
    if order_side and design_side:
        return True
    if any(marker in sentence for marker in ("场景", "前者", "后者")):
        return order_side or design_side
    return False


def _depends_on_previous_choice(sentence: str) -> bool:
    """后续数值问题依赖尚未完成的前置选择时，暂不开放数值槽位。"""

    return any(marker in sentence for marker in (
        "如果是前者", "如果是后者", "若是前者", "若是后者", "选择前者", "选择后者",
    ))


def extract_pending_slots(answer: str, object_name: str, *,
                          confirmed: Iterable[dict] = (), degraded: bool = False) -> list[dict]:
    """从顾问回答的追问语句中提取待补条件。

    - 只扫描疑问句或“请补充/请确认”语句，并从整段回答提取改为按句提取；
    - 数值问题与单位选择分流，“按米还是按卷”不产生长度数值槽位；
    - 确认式追问（“这10个抽屉的计价数量就是10个吗”）按复述值对应的单位登记数值槽位；
    - ``ask_text`` 保存实际追问原句；
    - 已确认条件不重复加入待补槽位；
    - 生成降级回答不从资料摘录中派生新槽位。
    """

    if degraded:
        return []
    confirmed_names = {item.get("name") for item in confirmed}
    slots: list[dict] = []
    seen: set[str] = set()
    unresolved_business_choice = False
    for sentence in _ask_sentences(answer):
        # 单位选择澄清：既包括“按米还是按卷”这类并列问题，也包括只问“按什么计价单位”的单一问题。
        if _is_unit_choice_question(sentence) or _UNIT_QUERY_RE.search(sentence):
            name = "计价单位"
            if name in seen or name in confirmed_names:
                continue
            seen.add(name)
            slots.append({
                "name": name, "value_type": "choice", "unit": "",
                "options": _choice_options(sentence), "object": object_name,
                "ask_text": sentence,
            })
            continue
        if _is_business_choice_question(sentence):
            name = "咨询场景"
            if name not in seen and name not in confirmed_names:
                seen.add(name)
                slots.append({
                    "name": name, "value_type": "choice", "unit": "",
                    "options": [], "object": object_name, "ask_text": sentence,
                })
            unresolved_business_choice = True
            continue
        if unresolved_business_choice and _depends_on_previous_choice(sentence):
            continue
        for pattern, name, unit in _SLOT_PATTERNS:
            if name in seen or name in confirmed_names:
                continue
            if pattern.search(sentence):
                seen.add(name)
                slots.append({"name": name, "value_type": "number", "unit": unit,
                              "object": object_name, "ask_text": sentence})
        for value, unit in _CONFIRM_NUMERIC_RE.findall(sentence):
            name, slot_unit = _CONFIRM_UNIT_SLOTS[unit]
            if name in seen or name in confirmed_names:
                continue
            seen.add(name)
            slots.append({"name": name, "value_type": "number", "unit": slot_unit,
                          "object": object_name, "ask_text": sentence})
    return slots


_MISSING_PRICING_UNIT_RE = re.compile(
    r"(?:未|没有|尚未|无法)(?:在[^，。；]{0,12})?(?:注明|标注|明确|确认|判断)[^，。；]{0,12}"
    r"(?:计价单位|计价口径|按米|按卷)|(?:计价单位|计价口径)[^，。；]{0,10}(?:不明|未知|待确认)"
)
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*[%％]")
_COUNTABLE_UNITS = {"卷", "张", "套", "个", "付", "扇", "片", "项", "托"}


def is_rule_explanation(query: str) -> bool:
    """规则说明无需默认索取订单金额；显式核算和金额门槛问题除外。"""
    return bool(re.search(r"规则|适用条件|例外|凭证|条款|交付", query)) and not bool(
        re.search(r"算出|计算|核算|应付|要付|付多少|多少钱|定金金额|订单金额|金额门槛|满\d|超过\d", query)
    )


def trim_unneeded_amount_question(answer: str, query: str) -> str:
    """仅移除规则说明中索取订单金额的问句，保留付款事实与引用。"""
    if not is_rule_explanation(query):
        return answer
    return re.sub(
        r"[^。！？\n]*订单金额[^。！？\n]*[？?]", "", answer
    ).strip()


def plan_pending_slots(answer: str, object_name: str, *, query: str,
                       confirmed: Iterable[dict] = (), degraded: bool = False) -> list[dict]:
    """结合当前业务意图与回答文本，生成下一轮唯一待补槽位。

    自然语言模型负责组织回答，但关键追问顺序由确定性规则收口：
    业务场景选择优先；定金比例计算优先补订单金额；一般报价依次补模型已明确
    追问的数值、计价单位和可数单位对应的数量。这样模型未在正文末尾稳定输出
    疑问句时，短回复仍有明确承接目标。
    """

    confirmed_items = list(confirmed)
    base = extract_pending_slots(
        answer, object_name, confirmed=confirmed_items, degraded=degraded,
    )
    if degraded:
        return base
    if is_rule_explanation(query):
        base = [slot for slot in base if slot.get("name") != "订单金额"]
    # 前置业务场景尚未确认时，任何下属数值槽位都不得开放。
    business_choices = [item for item in base if item.get("name") == "咨询场景"]
    if business_choices:
        return business_choices[:1]

    confirmed_names = {item.get("name") for item in confirmed_items}
    query_order = any(term in query for term in _ORDER_INTENT_TERMS)
    query_deposit = any(term in query for term in ("定金", "订金", "首付"))
    query_design = any(term in query for term in _DESIGN_INTENT_TERMS)
    if (query_order and query_deposit and not query_design and not is_rule_explanation(query)
            and "订单金额" not in confirmed_names and _PERCENT_RE.search(answer)):
        return [{
            "name": "订单金额", "value_type": "number", "unit": "元",
            "object": object_name, "ask_text": "请提供本次订单金额（元），用于按资料中的定金比例计算。",
        }]

    # 保留模型已经提出的单一明确追问；一次只开放一个槽位。
    if base:
        return base[:1]

    if "计价单位" not in confirmed_names and _MISSING_PRICING_UNIT_RE.search(answer):
        return [{
            "name": "计价单位", "value_type": "choice", "unit": "", "options": [],
            "object": object_name, "ask_text": "请确认本次采用的计价单位。",
        }]

    pricing_unit = next((
        str(item.get("value") or "") for item in reversed(confirmed_items)
        if item.get("name") == "计价单位"
    ), "")
    if pricing_unit in _COUNTABLE_UNITS and "数量" not in confirmed_names:
        return [{
            "name": "数量", "value_type": "number", "unit": pricing_unit,
            "object": object_name, "ask_text": f"请提供本次计价数量（{pricing_unit}）。",
        }]
    return []


def slot_visible_in_answer(slot: dict, answer: str) -> bool:
    """判断槽位的追问句是否出现在客户可见回答中。"""

    ask_text = (slot.get("ask_text") or "").strip()
    return bool(ask_text) and ask_text in (answer or "")


def align_visible_followup(answer: str, slots: list[dict]) -> tuple[str, list[dict]]:
    """让客户可见追问与后台待补槽位保持一致。

    - 计划槽位的追问句必须出现在回答中：确定性规划新增的追问补写到回答末尾；
    - 回答中其它会与计划槽位冲突的追问句被替换掉，避免同时显示“问面积”、
      后台却按另一个条件承接；
    - 只有带可见追问的槽位才被标记 ``visible``，无可见追问的槽位不是短回复目标。
    """

    planned = [slot for slot in slots if (slot.get("ask_text") or "").strip()]
    if not planned:
        return answer, []
    asks = [(slot.get("ask_text") or "").strip() for slot in planned]
    body = answer
    for sentence in _ask_sentences(answer):
        if sentence not in asks:
            body = body.replace(sentence, "")
    missing = [text for text in asks if text not in body]
    if missing:
        body = body.strip()
        body = f"{body}\n\n{missing[0]}" if body else missing[0]
    return body, [{**slot, "visible": True} for slot in planned]


_SHORT_REPLY_RE = re.compile(
    rf"\s*(\d+(?:\.\d+)?)\s*({'|'.join(_SHORT_REPLY_UNITS)})?\s*"
)


def is_short_numeric_reply(message: str) -> bool:
    """判断是否为纯数字或「改成N」的简短回复。"""

    return bool(
        _SHORT_REPLY_RE.fullmatch(message)
        or re.fullmatch(r"\s*改成\s*\d+(?:\.\d+)?\s*", message)
    )


def _parse_short_reply(message: str) -> tuple[str, str | None] | None:
    """解析简短数值回复，返回 (value, 显式单位或 None)。无法解析返回 None。"""

    change = re.fullmatch(r"\s*改成\s*(\d+(?:\.\d+)?)\s*", message)
    if change:
        return change.group(1), None
    number = _SHORT_REPLY_RE.fullmatch(message)
    if not number:
        return None
    return number.group(1), number.group(2)


def _pick_slot(value: str, explicit_unit: str | None, slots: list[dict]) -> tuple[dict, str] | None:
    """在数值槽位中选择绑定目标；返回 (slot, unit) 或 None（多槽位且无法唯一确定）。"""

    numeric_slots = [slot for slot in slots if slot.get("value_type") == "number"]
    if explicit_unit is not None:
        matching = [slot for slot in numeric_slots if slot.get("unit") == explicit_unit]
        if len(matching) == 1:
            return matching[0], explicit_unit
        if len(numeric_slots) == 1:
            # 显式单位优先于槽位单位：用户明确输入“3卷”时保留“卷”。
            return numeric_slots[0], explicit_unit
        return None
    if len(numeric_slots) != 1:
        return None
    return numeric_slots[0], numeric_slots[0]["unit"]


def bind_short_reply_condition(message: str, slots: list[dict]) -> dict | None:
    """纯数字或「改成N」绑定为一条会话条件；多槽位且无法唯一确定返回 None（需澄清）。"""

    parsed = _parse_short_reply(message)
    if parsed is None:
        return None
    value, explicit_unit = parsed
    picked = _pick_slot(value, explicit_unit, slots)
    if picked is None:
        return None
    slot, unit = picked
    return {
        "object": slot["object"],
        "name": slot["name"],
        "value": value,
        "unit": unit,
        "source": "USER",
        "original_reply": message.strip(),
    }


def bind_short_reply(message: str, slots: list[dict]) -> str | None:
    """纯数字或「改成N」绑定到上一轮唯一数值槽位；多槽位或无法绑定返回 None（需澄清）。"""

    condition = bind_short_reply_condition(message, slots)
    if condition is None:
        return None
    return f"{condition['object']} {condition['name']} {condition['value']}{condition['unit']}"


_UNIT_REPLY_RE = re.compile(
    r"^\s*(?:按|用|按照|按着)?\s*(平方米|平米|㎡|卷|张|套|个|米|元|付|扇|片|项|托)"
    r"\s*(?:计价|计算|算|来|收|结算)?\s*[。.!！]?\s*$"
)
_CHANGE_REPLY_RE = re.compile(r"^\s*改成\s*(\d+(?:\.\d+)?)\s*$")

# 选择型条件名：取值是枚举选项，不能被「改成N」当成数值覆盖。
_CHOICE_CONDITION_NAMES = frozenset({"计价单位", "咨询场景"})


def is_numeric_condition(condition: dict) -> bool:
    """判断已确认条件是否为数值型（而非选择型），用于「改成N」的目标选择。"""

    return condition.get("name") not in _CHOICE_CONDITION_NAMES


def is_change_reply(message: str) -> bool:
    """判断是否为「改成N」形式的条件纠正。"""

    return bool(_CHANGE_REPLY_RE.fullmatch(message))


def bind_choice_reply(message: str, slots: list[dict]) -> dict | None:
    """把单位选择回复（如“按卷”）绑定到上一轮唯一的选择槽位。"""

    choices = [slot for slot in slots if slot.get("value_type") == "choice"]
    if len(choices) != 1:
        return None
    match = _UNIT_REPLY_RE.fullmatch(message)
    if match is None:
        return None
    slot = choices[0]
    return {
        "object": slot.get("object") or "",
        "name": slot.get("name") or "计价单位",
        "value": match.group(1),
        "unit": "",
        "source": "USER",
        "original_reply": message.strip(),
    }


def plan_change_binding(message: str, slots: list[dict],
                        conditions: list[dict]) -> tuple[dict | None, list[str]]:
    """规划「改成N」的修改目标。

    选择型槽位尚未完成、或存在多个可能修改目标时返回歧义而不绑定；
    无待补数值槽位时只更新最近一次**数值型**已确认条件，不把选择条件当数值覆盖。
    """

    match = _CHANGE_REPLY_RE.fullmatch(message)
    if match is None:
        return None, []
    value = match.group(1)
    choices = [slot for slot in slots if slot.get("value_type") == "choice"]
    if choices:
        return None, [slot.get("name") or "计价单位" for slot in choices]
    numeric = [slot for slot in slots if slot.get("value_type") == "number"]
    if len(numeric) == 1:
        slot = numeric[0]
        return {
            "object": slot.get("object") or "", "name": slot.get("name") or "",
            "value": value, "unit": slot.get("unit", ""),
            "source": "USER", "original_reply": message.strip(),
        }, []
    if len(numeric) > 1:
        return None, [slot.get("name", "") for slot in numeric]
    targets = [item for item in conditions if is_numeric_condition(item)]
    names = {item.get("name") for item in targets if item.get("name")}
    if len(names) == 1:
        last = targets[-1]
        return {
            "object": last.get("object"), "name": last.get("name"), "value": value,
            "unit": last.get("unit", ""), "source": "USER", "original_reply": message.strip(),
        }, []
    if names:
        return None, sorted(names)
    return None, []


def merge_session_conditions(conditions: list[dict], new_condition: dict) -> list[dict]:
    """以 object + name 为键合并会话条件；新条件覆盖同键旧值，不同键累积。"""

    key = (new_condition.get("object"), new_condition.get("name"))
    merged = [item for item in conditions
              if (item.get("object"), item.get("name")) != key]
    merged.append(new_condition)
    return merged


# ---------------------------------------------------------------------------
# 词面候选补充（用于供应商＋定金等明确业务对象的报价证据召回）
# ---------------------------------------------------------------------------

# 报价/付款意图词：词面补充必须以其中一个为条件，避免对普通选材问题扩召。
# 这里只放金额/计价意图；“柜体、订单、设计服务”等业务对象词另作排序信号，不参与
# 词面扩召条件，否则会把大量只带业务名词的记录一起拉进来。
_SUPPLEMENT_INTENT_TERMS = (
    "定金", "订金", "报价", "价格", "单价", "金额", "付款", "结算", "尾款", "首付",
    "税金", "计价", "收费", "费用", "运费", "仓储费",
)

# 口语问法 → 记录侧词面意图。记录正文用“单价/报价/计量/生产周期”等词登记，
# 客户却常说“多少钱/怎么算”，直接按问句字面做词面条件会一条都命不中。
_QUERY_INTENT_MAP: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("多少钱", "几个钱", "多贵", "什么价", "什么价格", "怎么卖"),
     ("单价", "报价", "价格", "计价")),
    (("怎么算", "如何算", "怎么计算", "怎么收"),
     ("计价", "计量", "规则")),
    (("最低计量", "计量", "起订", "起付", "不足"),
     ("计量", "递增", "最低")),
    (("生产周期", "补单", "工期", "交期", "提货", "发货"),
     ("生产周期", "补单", "工期", "交期", "交付")),
    (("包含", "包含项", "增项", "不含", "赠送"),
     ("包含", "增项", "不含", "赠送")),
    (("规则", "条件", "口径", "规定"),
     ("规则", "条件", "口径")),
    # 安装字段咨询 → 选型维度记录的资料结构词（必须字段/来源要求侧的登记词），
    # 不绑定具体场景或记录编号。
    (("安装字段", "核对哪些安装", "安装条件", "安装资料"),
     ("必须字段", "安装尺寸", "安装资料", "门板结构")),
)

_SUPPLEMENT_STOP_WORDS = (
    "多少", "怎么", "什么", "如何", "请问", "一下", "规则", "还有", "哪些", "我想",
    "需要", "可以", "是否", "包括", "例如", "比如", "就是", "这个", "那个", "他们",
    "我们", "你们", "以及", "并且", "但是", "如果", "现在", "然后", "关于", "对于",
    "收", "要", "是", "的", "吗", "呢", "了", "和", "与", "或", "我", "请", "帮",
    "一个", "两个", "三个", "一件", "两件", "每",
)

_SUPPLEMENT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,8}")


def lexical_supplement_terms(query: str) -> tuple[list[str], list[str], list[str]]:
    """从查询提取 (锚点词, 意图词, 字段限定锚点)。

    锚点词是查询中的业务对象/供应商片段；意图词是记录正文里实际出现的报价、计量、
    交付等侧词，由问句的直白说法或口语说法映射得到；字段限定锚点用于优先命中记录的
    业务对象字段。锚点与意图缺一不可：只问“怎么算”而不指向任何对象时不启用词面
    补充，避免对普通选材问题扩大召回。
    """

    value = normalize_consultation_query(query).upper()
    intents = [term for term in _SUPPLEMENT_INTENT_TERMS if term.upper() in value]
    for triggers, mapped in _QUERY_INTENT_MAP:
        if any(trigger.upper() in value for trigger in triggers):
            intents.extend(mapped)
    if not intents:
        return [], [], []
    nouns = [term for term in BUSINESS_OBJECT_TERMS if term.upper() in value]
    removable = {
        term.upper() for term in (
            *_DOMAIN_TERMS, *_SCENE_MARKERS, *_SUBJECT_MARKERS,
            *BUSINESS_OBJECT_TERMS, *_ORDER_INTENT_TERMS, *_DESIGN_INTENT_TERMS,
            *_SUPPLEMENT_INTENT_TERMS, *_SUPPLEMENT_STOP_WORDS,
            *(trigger for triggers, _ in _QUERY_INTENT_MAP for trigger in triggers),
            *(term for _, mapped in _QUERY_INTENT_MAP for term in mapped),
        )
    }
    remainder = value
    for term in sorted(removable, key=len, reverse=True):
        if term:
            remainder = remainder.replace(term, " ")
    anchors: list[str] = list(nouns)
    for token in _SUPPLEMENT_TOKEN_RE.findall(remainder):
        if token.upper() in _MODEL_NOISE:
            continue
        anchors.append(token)
    anchors = list(dict.fromkeys(anchors))
    if not anchors:
        # 没有指向任何对象的锚点时不扩召（例如单独问“怎么算”）。
        return [], [], []
    return anchors[:3], list(dict.fromkeys(intents))[:3], lexical_object_anchors(anchors[:3])


def lexical_match_score(anchors: Iterable[str], intents: Iterable[str], chunk_text: str) -> int:
    """统计 Chunk 正文命中的锚点词与意图词数量，用于选择有限的词面补充候选。"""

    body = chunk_text.upper()
    return sum(1 for term in (*anchors, *intents) if term and term.upper() in body)


def conditions_for_object(conditions: list[dict], object_name: str) -> list[dict]:
    """只保留指定业务对象的会话条件，避免把旧对象条件带入新对象。"""

    return [item for item in conditions if item.get("object") == object_name]


def build_session_aware_query(topic: str, conditions: list[dict]) -> str:
    """构造会话条件感知的有效查询：原咨询主题 + 已确认会话条件。"""

    if not conditions:
        return topic
    labels = "、".join(
        f"{item.get('name', '')}{item.get('value', '')}{item.get('unit', '')}"
        for item in conditions
    )
    return f"{topic}；客户会话条件：{labels}"


__all__ = [
    "CATEGORY_LABELS", "category_key", "category_label", "consultation_allowed",
    "consultation_rank", "consultation_queries", "effective_consultation_query",
    "evidence_context_lines", "is_quote_query",
    "unique_preserving_order",
    "extract_object", "extract_pending_slots", "plan_pending_slots", "bind_short_reply", "is_short_numeric_reply",
    "slot_visible_in_answer", "align_visible_followup", "is_numeric_condition",
    "bind_short_reply_condition", "merge_session_conditions", "conditions_for_object",
    "build_session_aware_query", "is_session_follow_up",
    "bind_choice_reply", "is_change_reply", "plan_change_binding",
    "lexical_supplement_terms", "lexical_match_score", "lexical_object_anchors",
    "object_anchors",
    "is_supplier_rule_query", "SUPPLIER_RULE_TERMS",
    "BUSINESS_OBJECT_TERMS", "SUPPLIER_DATA_QUERY_TERMS",
]
