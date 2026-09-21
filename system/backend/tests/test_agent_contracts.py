"""阶段 6 前置：Agent 契约和工具白名单专项测试。"""

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agent.contracts import (
    CompareProductsInput,
    DocumentType,
    PriceType,
    QueryProductPriceInput,
    ReadDocumentInput,
    RoutingDecision,
    SearchProductKnowledgeInput,
    TaskType,
    ToolCallRecord,
    ToolStatus,
)
from app.agent.tool_registry import (
    TOOL_NOT_ALLOWED,
    ToolRegistry,
    ToolRegistryError,
)


def test_all_task_types_parse_and_unknown_is_rejected():
    for task_type in TaskType:
        decision = RoutingDecision(task_type=task_type, normalized_query="产品资料")
        assert decision.task_type is task_type
    with pytest.raises(ValidationError):
        RoutingDecision(task_type="NOT_A_TASK", normalized_query="产品资料")


def test_routing_decision_is_strict_and_rejects_identity_role_path_and_tool_fields():
    for field in ("user_id", "username", "role", "permissions", "file_path", "tool", "tools"):
        with pytest.raises(ValidationError):
            RoutingDecision(
                task_type=TaskType.KNOWLEDGE_QUERY,
                normalized_query="查询产品",
                **{field: "injected"},
            )
    assert RoutingDecision.model_config["extra"] == "forbid"


def test_routing_strings_are_trimmed_and_lists_dedupe_in_order():
    decision = RoutingDecision(
        task_type="KNOWLEDGE_QUERY",
        normalized_query="  X100 的功能  ",
        product_mentions=[" X100 ", "Y200", "X100"],
        focus_dimensions=[" 续航 ", "材料", "续航"],
    )
    # The input list is capped before deduplication; two unique mentions remain.
    assert decision.normalized_query == "X100 的功能"
    assert decision.product_mentions == ["X100", "Y200"]
    assert decision.focus_dimensions == ["续航", "材料"]


def test_routing_lengths_currency_and_budget_boundaries():
    with pytest.raises(ValidationError):
        RoutingDecision(task_type="KNOWLEDGE_QUERY", normalized_query="")
    with pytest.raises(ValidationError):
        RoutingDecision(task_type="KNOWLEDGE_QUERY", normalized_query="q", product_mentions=["a", "b", "c"])
    with pytest.raises(ValidationError):
        RoutingDecision(task_type="KNOWLEDGE_QUERY", normalized_query="q", focus_dimensions=["x1", "x2", "x3", "x4", "x5", "x6"])
    decision = RoutingDecision(
        task_type="PRICE_QUERY", normalized_query="q", budget=Decimal("0.00"), currency="USD"
    )
    assert decision.budget == Decimal("0.00")
    with pytest.raises(ValidationError):
        RoutingDecision(task_type="PRICE_QUERY", normalized_query="q", budget=Decimal("-0.01"))
    with pytest.raises(ValidationError):
        RoutingDecision(task_type="PRICE_QUERY", normalized_query="q", currency="cny")


def test_search_input_constraints_and_extra_forbid():
    item = SearchProductKnowledgeInput(
        query="  续航  ", product_ids=[1, 2], top_k=8, document_types=["PDF", "DOCX"]
    )
    assert item.query == "续航"
    assert item.product_ids == [1, 2]
    assert item.document_types == [DocumentType.PDF, DocumentType.DOCX]
    with pytest.raises(ValidationError):
        SearchProductKnowledgeInput(query="q", top_k=0)
    with pytest.raises(ValidationError):
        SearchProductKnowledgeInput(query="q", top_k=9)
    with pytest.raises(ValidationError):
        SearchProductKnowledgeInput(query="q", product_ids=[1, 0])
    with pytest.raises(ValidationError):
        SearchProductKnowledgeInput(query="q", product_ids=[1, 2, 3, 4, 5, 6])
    with pytest.raises(ValidationError):
        SearchProductKnowledgeInput(query="q", document_types=["TXT"])
    with pytest.raises(ValidationError):
        SearchProductKnowledgeInput(query="q", file_path="C:/secret/manual.pdf")


def test_read_document_page_range_and_path_boundary():
    document_id = UUID("00000000-0000-0000-0000-000000000001")
    assert ReadDocumentInput(document_id=document_id, page_start=1, page_end=10).max_chunks == 8
    for payload in (
        {"document_id": document_id, "page_start": 1},
        {"document_id": document_id, "page_end": 2},
        {"document_id": document_id, "page_start": 3, "page_end": 2},
        {"document_id": document_id, "page_start": 1, "page_end": 11},
        {"document_id": document_id, "file_path": "C:/secret/manual.pdf"},
    ):
        with pytest.raises(ValidationError):
            ReadDocumentInput(**payload)
    assert ReadDocumentInput(document_id=document_id, query="  ").query is None
    with pytest.raises(ValidationError):
        ReadDocumentInput(document_id=document_id, max_chunks=13)


def test_price_and_compare_inputs_preserve_decimal_and_reject_same_product():
    assert QueryProductPriceInput(product_id=1001, price_type="GUIDE").price_type is PriceType.GUIDE
    with pytest.raises(ValidationError):
        QueryProductPriceInput(product_id=0)
    compared = CompareProductsInput(
        product_a_id=1,
        product_b_id=2,
        focus_dimensions=["续航", "续航", "材料"],
        budget=Decimal("3000.10"),
    )
    assert compared.focus_dimensions == ["续航", "材料"]
    assert compared.budget == Decimal("3000.10")
    with pytest.raises(ValidationError):
        CompareProductsInput(product_a_id=1, product_b_id=1)
    with pytest.raises(ValidationError):
        CompareProductsInput(product_a_id=1, product_b_id=2, budget=Decimal("-1"))
    with pytest.raises(ValidationError):
        CompareProductsInput(product_a_id=1, product_b_id=2, focus_dimensions=["x1", "x2", "x3", "x4", "x5", "x6"])


def test_registry_has_exactly_four_tools_and_rejects_unknown_tool():
    registry = ToolRegistry()
    expected = {
        "search_product_knowledge",
        "read_document",
        "query_product_price",
        "compare_products",
    }
    assert set(registry.allowed_tool_names()) == expected
    assert registry.tools == frozenset(expected)
    assert len(registry.allowed_tools()) == 4
    assert registry.is_allowed("search_product_knowledge")
    assert not registry.is_allowed("run_shell")
    with pytest.raises(ToolRegistryError) as captured:
        registry.get_input_schema("run_shell")
    assert captured.value.error_code == TOOL_NOT_ALLOWED
    assert TOOL_NOT_ALLOWED in str(captured.value)


def test_registry_validates_each_input_schema_and_does_not_use_runtime_dependencies():
    registry = ToolRegistry()
    document_id = UUID("00000000-0000-0000-0000-000000000001")
    cases = {
        "search_product_knowledge": {"query": "q"},
        "read_document": {"document_id": document_id},
        "query_product_price": {"product_id": 1},
        "compare_products": {"product_a_id": 1, "product_b_id": 2},
    }
    for tool, params in cases.items():
        validated = registry.validate_input(tool, params)
        assert validated.__class__.__name__.endswith("Input")
    assert not hasattr(registry, "session")


def test_registry_exposes_only_whitelisted_tools_without_runtime_state():
    """白名单保持四工具且不随任务类型漂移；计划表已移除，改由 Service 分支编排。"""

    registry = ToolRegistry()
    assert registry.tools == {
        "search_product_knowledge", "read_document", "query_product_price", "compare_products",
    }
    for tool_name in registry.tools:
        schema = registry.get_input_schema(tool_name)
        assert schema.__name__.endswith("Input")
    assert not hasattr(registry, "plan_for")
    assert not hasattr(registry, "_plans")


def test_tool_call_record_rejects_negative_duration_and_redacts_sensitive_message():
    with pytest.raises(ValidationError):
        ToolCallRecord(tool="read_document", status="FAILED", duration_ms=-1)
    with pytest.raises(ValidationError):
        ToolCallRecord(tool="read_document", status="FAILED", duration_ms=1, message=123)
    record = ToolCallRecord(
        tool="read_document",
        status="FAILED",
        duration_ms=12,
        error_code="TOKEN_ERROR",
        message="token=secret password=hunter2 file_path=C:/private/a.pdf",
    )
    assert record.duration_ms == 12
    assert "secret" not in (record.message or "")
    assert "hunter2" not in (record.message or "")
    assert "C:/private" not in (record.message or "")
    assert "file_path" not in (record.message or "")
    assert "TOKEN_ERROR" in (record.error_code or "")


def test_all_contracts_generate_json_schema():
    models = [
        RoutingDecision,
        SearchProductKnowledgeInput,
        ReadDocumentInput,
        QueryProductPriceInput,
        CompareProductsInput,
        ToolCallRecord,
    ]
    for model in models:
        schema = model.model_json_schema()
        assert schema["type"] == "object"
        assert schema.get("additionalProperties") is False
