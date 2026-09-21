from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.agent.contracts import ToolStatus
from app.agent.service import AgentService
from app.api.auth import response
from app.api.dependencies import DbSession, get_current_user
from app.core.exceptions import AppError
from app.models import User
from app.schemas.agent import AgentChatData, AgentChatRequest, BulkConversationDeleteRequest, ConversationData, ConversationListData, ProductComparisonData
from app.schemas.audit import AuditAction, AuditResourceType, AuditResult
from app.schemas.common import ApiSuccess
from app.services.audit_service import AuditService, request_ip, request_id

router = APIRouter(tags=["agent"])
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_agent_service() -> AgentService:
    return AgentService()


AgentServiceDependency = Annotated[AgentService, Depends(get_agent_service)]


@router.post("/api/agent/chat", response_model=ApiSuccess[AgentChatData])
def chat(payload: AgentChatRequest, request: Request, session: DbSession,
         current_user: CurrentUser, service: AgentServiceDependency):
    audit = AuditService()
    try:
        data = service.chat(
            session,
            payload=payload,
            current_user=current_user,
            audit_request_id=request_id(request),
            audit_request_ip=request_ip(request),
            audit_username=current_user.username,
        )
    except AppError as exc:
        session.rollback()
        result = AuditResult.DENIED if AuditService.is_access_denial(exc) else AuditResult.FAILED
        error_code = (
            "RESOURCE_NOT_ACCESSIBLE"
            if exc.code in {"DOCUMENT_NOT_ACCESSIBLE", "CONVERSATION_NOT_ACCESSIBLE"}
            else exc.code
        )
        audit.record_request(
            request,
            action=AuditAction.AGENT_CHAT,
            result=result,
            user=current_user,
            resource_type=AuditResourceType.AGENT,
            error_code=error_code,
        )
        raise
    except SQLAlchemyError:
        session.rollback()
        audit.record_request(
            request,
            action=AuditAction.AGENT_CHAT,
            result=AuditResult.FAILED,
            user=current_user,
            resource_type=AuditResourceType.AGENT,
            error_code="DATABASE_ERROR",
        )
        raise
    except Exception:
        session.rollback()
        audit.record_request(
            request,
            action=AuditAction.AGENT_CHAT,
            result=AuditResult.FAILED,
            user=current_user,
            resource_type=AuditResourceType.AGENT,
            error_code="AGENT_CHAT_FAILED",
        )
        raise

    partial = isinstance(data.structured_data, ProductComparisonData) and data.structured_data.overall_status is ToolStatus.PARTIAL
    audit.record_request(
        request,
        action=AuditAction.AGENT_CHAT,
        result=AuditResult.FAILED if partial else AuditResult.SUCCESS,
        user=current_user,
        resource_type=AuditResourceType.AGENT,
        resource_id=data.conversation_id,
        error_code="PARTIAL" if partial else None,
        note="部分成功" if partial else None,
        duration_ms=sum(service.last_run_stats.durations_ms),
    )
    return response(data, request)


@router.get("/api/conversations", response_model=ApiSuccess[ConversationListData])
def list_conversations(request: Request, session: DbSession, current_user: CurrentUser,
                       service: AgentServiceDependency,
                       page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=20, ge=1, le=100), include_deleted: bool = False):
    data = service.list_conversations(session, current_user=current_user, page=page, page_size=page_size, include_deleted=include_deleted)
    return response(data, request)


@router.get("/api/conversations/{conversation_id}", response_model=ApiSuccess[ConversationData])
def get_conversation(conversation_id: UUID, request: Request, session: DbSession,
                     current_user: CurrentUser, service: AgentServiceDependency,
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=50, ge=1, le=100)):
    data = service.get_conversation(
        session, conversation_id=conversation_id, current_user=current_user,
        page=page, page_size=page_size,
    )
    return response(data, request)


@router.post("/api/conversations/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_conversations(payload: BulkConversationDeleteRequest, request: Request, session: DbSession,
                              current_user: CurrentUser, service: AgentServiceDependency):
    try:
        service.delete_conversations(session, conversation_ids=payload.ids, current_user=current_user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.AGENT_CONVERSATION_DELETE, exc=exc,
                                      user=current_user, resource_type=AuditResourceType.AGENT)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                                      result=AuditResult.FAILED, user=current_user,
                                      resource_type=AuditResourceType.AGENT, error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                                  result=AuditResult.SUCCESS, user=current_user,
                                  resource_type=AuditResourceType.AGENT, note="批量删除会话")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/conversations/{conversation_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_conversation(conversation_id: UUID, request: Request, session: DbSession,
                         current_user: CurrentUser, service: AgentServiceDependency):
    try:
        service.restore_conversation(session, conversation_id=conversation_id, current_user=current_user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.AGENT_CONVERSATION_DELETE, exc=exc,
                                      user=current_user, resource_type=AuditResourceType.AGENT,
                                      resource_id=conversation_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                                      result=AuditResult.FAILED, user=current_user,
                                      resource_type=AuditResourceType.AGENT, resource_id=conversation_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                                  result=AuditResult.SUCCESS, user=current_user,
                                  resource_type=AuditResourceType.AGENT, resource_id=conversation_id,
                                  note="恢复已删除会话")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/api/conversations/{conversation_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_conversation(conversation_id: UUID, request: Request, session: DbSession,
                                    current_user: CurrentUser, service: AgentServiceDependency):
    try:
        service.permanently_delete_conversation(session, conversation_id=conversation_id, current_user=current_user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.AGENT_CONVERSATION_DELETE, exc=exc,
                                      user=current_user, resource_type=AuditResourceType.AGENT,
                                      resource_id=conversation_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                                      result=AuditResult.FAILED, user=current_user,
                                      resource_type=AuditResourceType.AGENT, resource_id=conversation_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                                  result=AuditResult.SUCCESS, user=current_user,
                                  resource_type=AuditResourceType.AGENT, resource_id=conversation_id,
                                  note="永久删除会话")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: UUID, request: Request, session: DbSession,
                        current_user: CurrentUser, service: AgentServiceDependency):
    audit = AuditService()
    try:
        service.delete_conversation(session, conversation_id=conversation_id, current_user=current_user)
    except AppError as exc:
        session.rollback()
        audit.record_failure(request, action=AuditAction.AGENT_CONVERSATION_DELETE, exc=exc,
                             user=current_user, resource_type=AuditResourceType.AGENT,
                             resource_id=conversation_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        audit.record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                             result=AuditResult.FAILED, user=current_user,
                             resource_type=AuditResourceType.AGENT, resource_id=conversation_id,
                             error_code="DATABASE_ERROR")
        raise
    audit.record_request(request, action=AuditAction.AGENT_CONVERSATION_DELETE,
                         result=AuditResult.SUCCESS, user=current_user,
                         resource_type=AuditResourceType.AGENT, resource_id=conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["get_agent_service", "router"]
