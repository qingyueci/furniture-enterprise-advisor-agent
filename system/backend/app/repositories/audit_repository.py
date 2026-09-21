"""审计日志的参数化读写。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.schemas.audit import AuditLogFilters


class AuditRepository:
    """只负责 ``audit_logs`` 表，不承担身份或脱敏决策。"""

    def add(
        self,
        session: Session,
        *,
        user_id: UUID | None,
        username: str | None,
        action: str,
        resource_type: str | None,
        resource_id: str | None,
        request_ip: str | None,
        result: str,
        detail: dict,
    ) -> AuditLog:
        item = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_ip=request_ip,
            result=result,
            detail=dict(detail),
        )
        session.add(item)
        session.flush()
        return item

    def filtered_query(self, filters: AuditLogFilters) -> Select[tuple[AuditLog]]:
        statement = select(AuditLog)
        if filters.user_id is not None:
            statement = statement.where(AuditLog.user_id == filters.user_id)
        if filters.username is not None:
            statement = statement.where(AuditLog.username == filters.username)
        if filters.action is not None:
            statement = statement.where(AuditLog.action == filters.action.value)
        if filters.resource_type is not None:
            statement = statement.where(AuditLog.resource_type == filters.resource_type.value)
        if filters.result is not None:
            statement = statement.where(AuditLog.result == filters.result.value)
        if filters.start_time is not None:
            statement = statement.where(AuditLog.created_at >= filters.start_time)
        if filters.end_time is not None:
            statement = statement.where(AuditLog.created_at <= filters.end_time)
        return statement

    def list_logs(self, session: Session, filters: AuditLogFilters) -> tuple[list[AuditLog], int]:
        base = self.filtered_query(filters)
        total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
        items = list(
            session.scalars(
                base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .offset((filters.page - 1) * filters.page_size)
                .limit(filters.page_size)
            )
        )
        return items, total

    # 兼容服务层较短的自然命名；仍然复用同一组筛选条件。
    def list(self, session: Session, filters: AuditLogFilters) -> tuple[list[AuditLog], int]:
        return self.list_logs(session, filters)


__all__ = ["AuditRepository"]
