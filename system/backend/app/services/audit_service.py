"""阶段 9 审计事件构造、同步尽力写入和管理员查询。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Callable
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.contracts import ToolName
from app.core.database import SessionLocal, get_engine
from app.core.exceptions import AppError
from app.models import User
from app.repositories.audit_repository import AuditRepository
from app.schemas.audit import (
    AuditAction,
    AuditDetail,
    AuditLogData,
    AuditLogFilters,
    AuditLogListData,
    AuditResourceType,
    AuditResult,
)
from app.schemas.common import Pagination


LOGGER = logging.getLogger(__name__)
AUDIT_WRITE_FAILED = "AUDIT_WRITE_FAILED"
_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_.-]{0,79}")
_TOOL_NAMES = frozenset(item.value for item in ToolName)
_FIXED_NOTES = frozenset({
    "身份验证失败",
    "资源不存在或当前无权访问",
    "部分成功",
})

# 审计 detail 只接受服务端已经定义的错误码。未知值不会把调用方输入
# 原样带入数据库或查询响应；``SERVICE_ERROR`` 是稳定的兜底码。
_AUDIT_ERROR_CODES = frozenset({
    "ACCOUNT_DISABLED", "AGENT_CHAT_FAILED", "AGENT_TIMEOUT", "AGENT_TOOL_FAILED",
    "AUDIT_WRITE_FAILED", "AUTH_INVALID_CREDENTIALS", "AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_INVALID", "AUTH_TOKEN_MISSING",
    "CONVERSATION_NOT_ACCESSIBLE", "DATABASE_ERROR", "DOCUMENT_NOT_ACCESSIBLE", "DOCUMENT_NOT_READY",
    "DOCUMENT_PARSE_FAILED", "DOCUMENT_TRUNCATED", "FILE_STORAGE_ERROR", "FILE_TOO_LARGE",
    "GENERATION_FALLBACK", "INVALID_COMPARISON_CONTEXT", "LAST_ACTIVE_ADMIN_REQUIRED", "MODEL_TIMEOUT",
    "PARTIAL", "PARTIAL_RESULT", "PERMISSION_CHANGED", "PERMISSION_DENIED", "PRICE_NOT_FOUND",
    "PRODUCT_NOT_FOUND", "RESOURCE_NOT_ACCESSIBLE", "ROUTING_FALLBACK", "SERVICE_ERROR",
    "TOOL_CALL_LIMIT", "TOOL_EXECUTION_FAILED", "TOOL_NOT_ALLOWED", "UNSUPPORTED_FILE_TYPE",
    "USERNAME_EXISTS", "USER_NOT_FOUND", "VALIDATION_ERROR",
})

_ACTION_RESOURCES: dict[AuditAction, AuditResourceType] = {
    AuditAction.LOGIN_SUCCESS: AuditResourceType.AUTH,
    AuditAction.LOGIN_FAILED: AuditResourceType.AUTH,
    AuditAction.LOGOUT: AuditResourceType.AUTH,
    AuditAction.USER_CREATE: AuditResourceType.USER,
    AuditAction.USER_UPDATE: AuditResourceType.USER,
    AuditAction.DOCUMENT_UPLOAD: AuditResourceType.DOCUMENT,
    AuditAction.DOCUMENT_PARSE_SUCCESS: AuditResourceType.DOCUMENT,
    AuditAction.DOCUMENT_PARSE_FAILED: AuditResourceType.DOCUMENT,
    AuditAction.DOCUMENT_PERMISSION_UPDATE: AuditResourceType.DOCUMENT,
    AuditAction.DOCUMENT_DELETE: AuditResourceType.DOCUMENT,
    AuditAction.DOCUMENT_READ: AuditResourceType.DOCUMENT,
    AuditAction.PRODUCT_QUERY: AuditResourceType.PRODUCT,
    AuditAction.PRICE_QUERY: AuditResourceType.PRICE,
    AuditAction.AGENT_CHAT: AuditResourceType.AGENT,
    AuditAction.AGENT_TOOL_CALL: AuditResourceType.AGENT,
    AuditAction.PERMISSION_DENIED: AuditResourceType.AUTH,
}

_ACCESS_ERROR_CODES = frozenset({
    "PERMISSION_DENIED",
    "DOCUMENT_NOT_ACCESSIBLE",
    "CONVERSATION_NOT_ACCESSIBLE",
    "RESOURCE_NOT_ACCESSIBLE",
})


@dataclass(frozen=True)
class AuditWriteResult:
    written: bool
    request_id: str
    error_code: str | None = None


def _audit_session_factory() -> Session:
    return SessionLocal(bind=get_engine())


def request_ip(request: Request | None) -> str | None:
    """读取服务端连接地址；不信任任意客户端 ``X-Forwarded-For``。"""

    client = getattr(request, "client", None) if request is not None else None
    host = getattr(client, "host", None)
    if not isinstance(host, str):
        return None
    try:
        return str(ip_address(host))
    except ValueError:
        return None


def request_id(request: Request | None) -> str:
    value = getattr(getattr(request, "state", None), "request_id", None)
    if isinstance(value, str) and _REQUEST_ID.fullmatch(value):
        return value
    return f"req_{uuid4()}"


def resource_for_request(request: Request) -> tuple[AuditResourceType, str | None]:
    """根据路由参数推断审计资源，不查询被隐藏的资源。"""

    path = str(getattr(getattr(request, "url", None), "path", ""))
    params = getattr(request, "path_params", {}) or {}
    if path.startswith("/api/auth/"):
        return AuditResourceType.AUTH, None
    if path.startswith("/api/audit-logs"):
        return AuditResourceType.AUTH, None
    if "document_id" in params or path.startswith("/api/documents"):
        return AuditResourceType.DOCUMENT, _resource_id(params.get("document_id"))
    if path.endswith("/price"):
        return AuditResourceType.PRICE, _resource_id(params.get("product_id"))
    if "product_id" in params or path.startswith("/api/products"):
        return AuditResourceType.PRODUCT, _resource_id(params.get("product_id"))
    if "user_id" in params or path.startswith("/api/users"):
        return AuditResourceType.USER, _resource_id(params.get("user_id"))
    if "conversation_id" in params or path.startswith("/api/conversations") or path.startswith("/api/agent"):
        return AuditResourceType.AGENT, _resource_id(params.get("conversation_id"))
    return AuditResourceType.AUTH, None


def _resource_id(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (UUID, int)):
        return str(value)
    if isinstance(value, str):
        value = value.strip()
        if value and len(value) <= 64 and not any(char in value for char in ("/", "\\", ":")):
            return value
    return None


class AuditService:
    """审计写入不提交调用方业务 Session。"""

    def __init__(
        self,
        repository: AuditRepository | None = None,
        session_factory: Callable[[], Session] | None = None,
    ):
        self.repository = repository or AuditRepository()
        self.session_factory = session_factory or _audit_session_factory

    @staticmethod
    def safe_username(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        clean = value.strip().lower()
        if (
            not 3 <= len(clean) <= 50
            or any(ord(char) < 32 for char in clean)
            or any(char in clean for char in ("/", "\\", ":"))
        ):
            return None
        return clean

    @staticmethod
    def safe_resource_id(value: object) -> str | None:
        return _resource_id(value)

    @staticmethod
    def safe_error_code(value: object, default: str = "SERVICE_ERROR") -> str:
        if isinstance(value, str):
            clean = value.strip()
            if _ERROR_CODE.fullmatch(clean) and clean in _AUDIT_ERROR_CODES:
                return clean
        return default

    @staticmethod
    def safe_tool(value: object) -> str | None:
        clean = value.value if isinstance(value, ToolName) else value
        return clean if isinstance(clean, str) and clean in _TOOL_NAMES else None

    @staticmethod
    def safe_result(value: AuditResult | str) -> AuditResult:
        return value if isinstance(value, AuditResult) else AuditResult(value)

    @staticmethod
    def safe_action(value: AuditAction | str) -> AuditAction:
        return value if isinstance(value, AuditAction) else AuditAction(value)

    @staticmethod
    def safe_resource_type(value: AuditResourceType | str | None) -> AuditResourceType | None:
        if value is None:
            return None
        return value if isinstance(value, AuditResourceType) else AuditResourceType(value)

    @staticmethod
    def _detail(
        *,
        request_id_value: str,
        error_code: object = None,
        tool: object = None,
        duration_ms: object = None,
        note: object = None,
    ) -> dict[str, Any]:
        duration = duration_ms if isinstance(duration_ms, int) and not isinstance(duration_ms, bool) and duration_ms >= 0 else None
        fixed_note = note if isinstance(note, str) and note in _FIXED_NOTES else None
        return AuditDetail(
            error_code=AuditService.safe_error_code(error_code) if error_code is not None else None,
            tool=AuditService.safe_tool(tool),
            duration_ms=duration,
            request_id=request_id_value,
            note=fixed_note,
        ).model_dump(mode="json", exclude_none=True)

    def record(
        self,
        *,
        action: AuditAction | str,
        result: AuditResult | str,
        user: User | None = None,
        user_id: UUID | None = None,
        username: str | None = None,
        resource_type: AuditResourceType | str | None = None,
        resource_id: object = None,
        request_ip_value: str | None = None,
        request_id_value: str | None = None,
        error_code: object = None,
        tool: object = None,
        duration_ms: object = None,
        note: object = None,
    ) -> AuditWriteResult:
        normalized_action = self.safe_action(action)
        normalized_result = self.safe_result(result)
        if user is not None:
            user_id = user.id
            username = user.username
        clean_request_id = request_id_value if isinstance(request_id_value, str) and _REQUEST_ID.fullmatch(request_id_value) else f"req_{uuid4()}"
        clean_username = self.safe_username(username)
        clean_ip = request_ip_value
        if clean_ip is not None:
            try:
                clean_ip = str(ip_address(clean_ip))
            except ValueError:
                clean_ip = None
        normalized_resource = self.safe_resource_type(resource_type) or _ACTION_RESOURCES[normalized_action]
        detail = self._detail(
            request_id_value=clean_request_id,
            error_code=error_code,
            tool=tool,
            duration_ms=duration_ms,
            note=note,
        )
        return self._write(
            user_id=user_id,
            username=clean_username,
            action=normalized_action.value,
            resource_type=normalized_resource.value if normalized_resource else None,
            resource_id=self.safe_resource_id(resource_id),
            request_ip=clean_ip,
            result=normalized_result.value,
            detail=detail,
            request_id_value=clean_request_id,
        )

    def _write(self, *, request_id_value: str, **values: Any) -> AuditWriteResult:
        session: Session | None = None
        try:
            session = self.session_factory()
            with session.begin():
                # 测试事务或进程重启期间身份行可能尚未对独立连接可见；
                # 保留用户名快照并将不可见外键降为 NULL，避免审计故障阻塞业务。
                if values["user_id"] is not None:
                    visible = session.scalar(select(User.id).where(User.id == values["user_id"]))
                    if visible is None:
                        values["user_id"] = None
                self.repository.add(session, **values)
            return AuditWriteResult(True, request_id_value)
        except Exception:
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    pass
            LOGGER.warning("AUDIT_WRITE_FAILED request_id=%s error_code=%s", request_id_value, AUDIT_WRITE_FAILED)
            return AuditWriteResult(False, request_id_value, AUDIT_WRITE_FAILED)
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def record_request(
        self,
        request: Request,
        *,
        action: AuditAction | str,
        result: AuditResult | str,
        user: User | None = None,
        user_id: UUID | None = None,
        username: str | None = None,
        resource_type: AuditResourceType | str | None = None,
        resource_id: object = None,
        error_code: object = None,
        tool: object = None,
        duration_ms: object = None,
        note: object = None,
    ) -> AuditWriteResult:
        if user is None:
            user = getattr(getattr(request, "state", None), "audit_user", None)
        return self.record(
            action=action,
            result=result,
            user=user,
            user_id=user_id,
            username=username,
            resource_type=resource_type,
            resource_id=resource_id,
            request_ip_value=request_ip(request),
            request_id_value=request_id(request),
            error_code=error_code,
            tool=tool,
            duration_ms=duration_ms,
            note=note,
        )

    def record_failure(
        self,
        request: Request,
        *,
        action: AuditAction | str,
        exc: Exception,
        user: User | None = None,
        resource_type: AuditResourceType | str | None = None,
        resource_id: object = None,
    ) -> AuditWriteResult | None:
        code = getattr(exc, "code", None)
        denied = self.is_access_denial(exc)
        if code in {"DOCUMENT_NOT_ACCESSIBLE", "CONVERSATION_NOT_ACCESSIBLE"}:
            code = "RESOURCE_NOT_ACCESSIBLE"
        return self.record_request(
            request,
            action=action,
            result=AuditResult.DENIED if denied else AuditResult.FAILED,
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
            error_code=self.safe_error_code(code),
        )

    def record_permission_denied(self, request: Request, exc: AppError) -> AuditWriteResult:
        resource_type, resource_id = resource_for_request(request)
        code = "RESOURCE_NOT_ACCESSIBLE" if exc.code in {"DOCUMENT_NOT_ACCESSIBLE", "CONVERSATION_NOT_ACCESSIBLE"} else "PERMISSION_DENIED"
        return self.record_request(
            request,
            action=AuditAction.PERMISSION_DENIED,
            result=AuditResult.DENIED,
            resource_type=resource_type,
            resource_id=resource_id,
            error_code=code,
            note="资源不存在或当前无权访问" if code == "RESOURCE_NOT_ACCESSIBLE" else None,
        )

    @staticmethod
    def is_access_denial(exc: Exception) -> bool:
        return isinstance(exc, AppError) and exc.code in _ACCESS_ERROR_CODES

    def list_logs(self, session: Session, *, filters: AuditLogFilters) -> AuditLogListData:
        items, total = self.repository.list_logs(session, filters)
        data: list[AuditLogData] = []
        for item in items:
            raw = item.detail if isinstance(item.detail, dict) else {}
            raw_error = raw.get("error_code")
            error_code = (
                raw_error.strip()
                if isinstance(raw_error, str)
                and _ERROR_CODE.fullmatch(raw_error.strip())
                and raw_error.strip() in _AUDIT_ERROR_CODES
                else None
            )
            raw_request_id = raw.get("request_id")
            clean_request_id = (
                raw_request_id.strip()
                if isinstance(raw_request_id, str) and _REQUEST_ID.fullmatch(raw_request_id.strip())
                else None
            )
            raw_duration = raw.get("duration_ms")
            duration_ms = (
                raw_duration
                if isinstance(raw_duration, int) and not isinstance(raw_duration, bool) and raw_duration >= 0
                else None
            )
            detail = AuditDetail(
                error_code=error_code,
                tool=self.safe_tool(raw.get("tool")),
                duration_ms=duration_ms,
                request_id=clean_request_id,
                note=raw.get("note") if raw.get("note") in _FIXED_NOTES else None,
            ).model_dump(mode="json", exclude_none=True)
            clean_ip = item.request_ip
            if clean_ip is not None:
                try:
                    clean_ip = str(ip_address(clean_ip))
                except ValueError:
                    clean_ip = None
            try:
                data.append(AuditLogData(
                    id=item.id,
                    user_id=item.user_id,
                    username=self.safe_username(item.username),
                    action=item.action,
                    resource_type=item.resource_type,
                    resource_id=self.safe_resource_id(item.resource_id),
                    request_ip=clean_ip,
                    result=item.result,
                    detail=detail,
                    created_at=item.created_at,
                ))
            except ValidationError:
                # 历史异常行不应让管理员查询回显未定义枚举或字段；total
                # 仍保持数据库筛选结果，当前服务写入的行不会进入此分支。
                continue
        return AuditLogListData(
            items=data,
            pagination=Pagination(page=filters.page, page_size=filters.page_size, total=total),
        )

    # 便于调用方按语义选择名称，不复制实现。
    write = record
    record_event = record
    query = list_logs


__all__ = [
    "AUDIT_WRITE_FAILED",
    "AuditService",
    "AuditWriteResult",
    "request_id",
    "request_ip",
    "resource_for_request",
]
