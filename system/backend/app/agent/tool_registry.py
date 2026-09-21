"""阶段 6 前置的静态 Agent 工具白名单。

``ToolRegistry`` 只做两件事：列出允许工具、校验工具输入。它不持有数据库
Session，也不执行 Service、RAG 或外部 API；每个任务类型实际调用哪些工具
由 ``AgentService`` 的确定性分支编排，不再保留第二套静态计划表。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, ClassVar, Mapping

from pydantic import BaseModel

from app.agent.contracts import (
    CompareProductsInput,
    QueryProductPriceInput,
    ReadDocumentInput,
    SearchProductKnowledgeInput,
    ToolName,
)


TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
TOOL_NOT_ALLOWED_MESSAGE = "请求的工具不在系统允许范围内"


class ToolRegistryError(ValueError):
    """Registry 校验失败时的稳定、脱敏错误。"""

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.code = error_code  # 兼容 API 层常用的 code 命名
        self.message = message
        super().__init__(f"{error_code}: {message}")


_SCHEMAS: dict[str, type[BaseModel]] = {
    ToolName.SEARCH_PRODUCT_KNOWLEDGE.value: SearchProductKnowledgeInput,
    ToolName.READ_DOCUMENT.value: ReadDocumentInput,
    ToolName.QUERY_PRODUCT_PRICE.value: QueryProductPriceInput,
    ToolName.COMPARE_PRODUCTS.value: CompareProductsInput,
}

# 模块级只读快照便于后续 API 层生成工具说明；调用方无法通过它注册新工具。
ALLOWED_TOOLS = frozenset(_SCHEMAS)
TOOL_SCHEMAS = MappingProxyType(_SCHEMAS)


class ToolRegistry:
    """固定四工具注册表；实例无运行时资源和可变状态。"""

    _schemas: ClassVar[Mapping[str, type[BaseModel]]] = MappingProxyType(_SCHEMAS)
    # 公开只读视图，方便 API/测试展示白名单；不会暴露可修改字典。
    tools: ClassVar[frozenset[str]] = ALLOWED_TOOLS

    @classmethod
    def allowed_tools(cls) -> tuple[ToolName, ...]:
        """返回按固定顺序排列的四个工具。"""

        return tuple(ToolName(name) for name in cls._schemas)

    @classmethod
    def allowed_tool_names(cls) -> tuple[str, ...]:
        return tuple(name.value for name in cls.allowed_tools())

    @classmethod
    def get_allowed_tools(cls) -> tuple[str, ...]:
        """``allowed_tool_names`` 的兼容别名。"""

        return cls.allowed_tool_names()

    @classmethod
    def is_allowed(cls, tool_name: str | ToolName) -> bool:
        key = tool_name.value if isinstance(tool_name, ToolName) else tool_name
        return isinstance(key, str) and key.strip() in cls._schemas

    @classmethod
    def _normalize_tool_name(cls, tool_name: str | ToolName) -> str:
        key = tool_name.value if isinstance(tool_name, ToolName) else tool_name
        return key.strip() if isinstance(key, str) else ""

    @classmethod
    def get_input_schema(cls, tool_name: str | ToolName) -> type[BaseModel]:
        key = cls._normalize_tool_name(tool_name)
        schema = cls._schemas.get(key)
        if schema is None:
            raise ToolRegistryError(TOOL_NOT_ALLOWED, TOOL_NOT_ALLOWED_MESSAGE)
        return schema

    @classmethod
    def schema_for(cls, tool_name: str | ToolName) -> type[BaseModel]:
        return cls.get_input_schema(tool_name)

    @classmethod
    def get_schema(cls, tool_name: str | ToolName) -> type[BaseModel]:
        return cls.get_input_schema(tool_name)

    @classmethod
    def input_schema_for(cls, tool_name: str | ToolName) -> type[BaseModel]:
        return cls.get_input_schema(tool_name)

    @classmethod
    def validate_input(cls, tool_name: str | ToolName, params: Mapping[str, Any]) -> BaseModel:
        """校验并返回对应输入模型；未知工具使用稳定错误码。"""

        schema = cls.get_input_schema(tool_name)
        return schema.model_validate(params)

    @classmethod
    def validate_tool_input(cls, tool_name: str | ToolName, params: Mapping[str, Any]) -> BaseModel:
        return cls.validate_input(tool_name, params)

    @classmethod
    def validate(cls, tool_name: str | ToolName, params: Mapping[str, Any]) -> BaseModel:
        return cls.validate_input(tool_name, params)


__all__ = [
    "ALLOWED_TOOLS",
    "TOOL_NOT_ALLOWED",
    "TOOL_NOT_ALLOWED_MESSAGE",
    "TOOL_SCHEMAS",
    "ToolRegistry",
    "ToolRegistryError",
]
