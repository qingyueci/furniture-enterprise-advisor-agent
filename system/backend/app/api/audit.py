from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.auth import response
from app.api.dependencies import DbSession
from app.models import User
from app.schemas.audit import AuditAction, AuditLogFilters, AuditLogListData, AuditResourceType, AuditResult
from app.schemas.common import ApiSuccess
from app.security.rbac import require_permission
from app.services.audit_service import AuditService


router = APIRouter(prefix="/api/audit-logs", tags=["audit"])
AdminAuditor = Annotated[User, Depends(require_permission("audit:read"))]


def audit_filters(
    user_id: UUID | None = Query(default=None),
    username: str | None = Query(default=None),
    action: AuditAction | None = Query(default=None),
    resource_type: AuditResourceType | None = Query(default=None),
    result: AuditResult | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AuditLogFilters:
    """把查询参数显式转成统一契约，并把范围错误归入 422 响应。"""

    try:
        return AuditLogFilters(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            result=result,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise RequestValidationError([{
            "type": "value_error",
            "loc": ("query",),
            "msg": "时间范围不符合要求",
            "input": {"start_time": start_time, "end_time": end_time},
        }]) from exc


@router.get("", response_model=ApiSuccess[AuditLogListData])
def list_audit_logs(
    request: Request,
    session: DbSession,
    _: AdminAuditor,
    filters: Annotated[AuditLogFilters, Depends(audit_filters)],
):
    data = AuditService().list_logs(session, filters=filters)
    return response(data, request)


__all__ = ["router"]
