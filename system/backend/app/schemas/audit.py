"""阶段 9 审计日志契约。

审计查询是只读的；本模块只允许 PRD 规定的动作、资源和结果。``detail``
刻意采用白名单字段，任何 Token、完整提示词、文档正文、服务器路径或异常
堆栈都不会进入可序列化模型。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from ipaddress import ip_address
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, ConfigDict, Field, field_validator, model_validator

from app.agent.contracts import StrictContract, sanitize_message
from app.schemas.common import Pagination


class AuditAction(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    USER_CREATE = "USER_CREATE"
    USER_UPDATE = "USER_UPDATE"
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
    DOCUMENT_PARSE_SUCCESS = "DOCUMENT_PARSE_SUCCESS"
    DOCUMENT_PARSE_FAILED = "DOCUMENT_PARSE_FAILED"
    DOCUMENT_PERMISSION_UPDATE = "DOCUMENT_PERMISSION_UPDATE"
    DOCUMENT_DELETE = "DOCUMENT_DELETE"
    DOCUMENT_READ = "DOCUMENT_READ"
    PRODUCT_QUERY = "PRODUCT_QUERY"
    PRODUCT_CREATE = "PRODUCT_CREATE"
    PRODUCT_UPDATE = "PRODUCT_UPDATE"
    PRODUCT_DELETE = "PRODUCT_DELETE"
    USER_DELETE = "USER_DELETE"
    PRICE_QUERY = "PRICE_QUERY"
    AGENT_CHAT = "AGENT_CHAT"
    AGENT_CONVERSATION_DELETE = "AGENT_CONVERSATION_DELETE"
    AGENT_TOOL_CALL = "AGENT_TOOL_CALL"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class AuditResourceType(str, Enum):
    AUTH = "AUTH"
    USER = "USER"
    DOCUMENT = "DOCUMENT"
    PRODUCT = "PRODUCT"
    PRICE = "PRICE"
    AGENT = "AGENT"


class AuditResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DENIED = "DENIED"


class AuditStrictModel(StrictContract):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


def _trim(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


_SENSITIVE_WORDS = re.compile(
    r"(?i)(?:access[_ -]?token|authorization|bearer|password|passwd|api[_ -]?key|secret|"
    r"完整提示词|系统提示|文档正文|异常堆栈|traceback|stack trace)"
)


def _redact_detail(value: Any) -> Any:
    """把备注稳定地压缩为脱敏文本；非字符串交给 Pydantic 类型校验。"""

    if value is None or not isinstance(value, str):
        return value
    cleaned = sanitize_message(value)
    if cleaned is None:
        return None
    # sanitize_message 已处理常见赋值形式；敏感语义仍只保留通用占位符。
    if _SENSITIVE_WORDS.search(cleaned):
        return "[已脱敏]"
    return cleaned


class AuditDetail(AuditStrictModel):
    """审计 detail 的白名单字段。"""

    error_code: str | None = Field(default=None, max_length=80)
    tool: str | None = Field(default=None, max_length=80)
    duration_ms: int | None = Field(default=None, ge=0)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    note: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("note", "redacted_note"),
    )

    _trim_text = field_validator("error_code", "tool", "request_id", mode="before")(_trim)
    _sanitize_note = field_validator("note", mode="before")(_redact_detail)

    @field_validator("request_id")
    @classmethod
    def request_id_format(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
            raise ValueError("request_id 格式无效")
        return value

    @field_validator("error_code")
    @classmethod
    def error_code_format(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Z][A-Z0-9_.-]{0,79}", value):
            raise ValueError("error_code 格式无效")
        return value

    @field_validator("tool")
    @classmethod
    def tool_name_format(cls, value: str | None) -> str | None:
        if value is not None and value not in {
            "search_product_knowledge", "read_document", "query_product_price", "compare_products",
        }:
            raise ValueError("tool 不在允许范围内")
        return value


class AuditLogData(AuditStrictModel):
    """管理员只读列表中的一条日志。"""

    id: int = Field(gt=0)
    user_id: UUID | None = None
    username: str | None = Field(default=None, max_length=64)
    action: AuditAction
    resource_type: AuditResourceType | None = None
    resource_id: str | None = Field(default=None, max_length=64)
    request_ip: str | None = Field(default=None, max_length=45)
    result: AuditResult
    detail: AuditDetail = Field(default_factory=AuditDetail)
    created_at: datetime

    _trim_enum = field_validator("action", "resource_type", "result", mode="before")(_trim)
    _trim_text = field_validator("username", "resource_id", "request_ip", mode="before")(_trim)

    @field_validator("resource_id", mode="before")
    @classmethod
    def normalize_resource_id(cls, value: object) -> object:
        if isinstance(value, (int, UUID)):
            return str(value)
        return value

    @field_validator("request_ip")
    @classmethod
    def validate_ip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ip_address(value)
        except ValueError as exc:
            raise ValueError("request_ip 必须是合法 IP 地址") from exc
        return value


class AuditLogFilters(AuditStrictModel):
    """审计查询参数；字段与 ``GET /api/audit-logs`` 保持一致。"""

    user_id: UUID | None = None
    username: str | None = Field(default=None, min_length=1, max_length=64)
    action: AuditAction | None = None
    resource_type: AuditResourceType | None = None
    result: AuditResult | None = None
    start_time: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("start_time", "start", "from_time"),
    )
    end_time: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("end_time", "end", "to_time"),
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    _trim_text = field_validator("username", mode="before")(_trim)
    _trim_enum = field_validator("action", "resource_type", "result", mode="before")(_trim)

    @field_validator("start_time", "end_time", mode="after")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_time_range(self) -> "AuditLogFilters":
        if self.start_time is not None and self.end_time is not None and self.end_time < self.start_time:
            raise ValueError("end_time 不得早于 start_time")
        return self


class AuditLogListData(AuditStrictModel):
    items: list[AuditLogData] = Field(default_factory=list, max_length=100)
    pagination: Pagination


# 语义别名，便于 API 采用更短的名称且不产生第二份契约。
AuditLog = AuditLogData
AuditFilter = AuditLogFilters
AuditQuery = AuditLogFilters
AuditListData = AuditLogListData
AuditDetailData = AuditDetail
AuditEvent = AuditAction
AuditResource = AuditResourceType
AuditOutcome = AuditResult
AuditLogFilter = AuditLogFilters
AuditQueryParams = AuditLogFilters
AuditQueryRequest = AuditLogFilters
AuditPagination = Pagination

AUDIT_ACTIONS = tuple(action.value for action in AuditAction)
AUDIT_RESOURCE_TYPES = tuple(resource.value for resource in AuditResourceType)
AUDIT_RESULTS = tuple(result.value for result in AuditResult)


__all__ = [
    "AUDIT_ACTIONS",
    "AUDIT_RESOURCE_TYPES",
    "AUDIT_RESULTS",
    "AuditAction",
    "AuditEvent",
    "AuditDetail",
    "AuditDetailData",
    "AuditFilter",
    "AuditListData",
    "AuditLog",
    "AuditLogData",
    "AuditLogFilters",
    "AuditLogFilter",
    "AuditLogListData",
    "AuditQuery",
    "AuditQueryParams",
    "AuditQueryRequest",
    "AuditPagination",
    "AuditOutcome",
    "AuditResource",
    "AuditResourceType",
    "AuditResult",
]
