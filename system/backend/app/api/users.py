from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth import response
from app.api.dependencies import DbSession
from app.core.exceptions import AppError
from app.models import User
from app.schemas.audit import AuditAction, AuditResourceType, AuditResult
from app.schemas.common import ApiSuccess, CurrentUser, Pagination
from app.schemas.user import BulkUserDeleteRequest, CreateUserRequest, Role, Status, UpdateUserRequest, UserListData
from app.security.rbac import require_permission
from app.services.user_service import UserService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/users", tags=["users"])
AdminUser = Annotated[User, Depends(require_permission("user:manage"))]


@router.get("", response_model=ApiSuccess[UserListData])
def list_users(
    request: Request, session: DbSession, _: AdminUser,
    keyword: str | None = Query(default=None, max_length=50), role: Role | None = None, status: Status | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), include_deleted: bool = False,
):
    items, total = UserService().list_users(session, keyword=keyword, role=role, status=status, page=page, page_size=page_size, include_deleted=include_deleted)
    data = UserListData(items=[CurrentUser.model_validate(item) for item in items],
                        pagination=Pagination(page=page, page_size=page_size, total=total))
    return response(data, request)


@router.post("", response_model=ApiSuccess[CurrentUser], status_code=201)
def create_user(payload: CreateUserRequest, request: Request, session: DbSession, user: AdminUser):
    try:
        created = UserService().create_user(session, payload)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(
            request, action=AuditAction.USER_CREATE, exc=exc, user=user,
            resource_type=AuditResourceType.USER,
        )
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(
            request, action=AuditAction.USER_CREATE, result=AuditResult.FAILED,
            user=user, resource_type=AuditResourceType.USER, error_code="DATABASE_ERROR",
        )
        raise
    AuditService().record_request(
        request, action=AuditAction.USER_CREATE, result=AuditResult.SUCCESS,
        user=user, resource_type=AuditResourceType.USER, resource_id=created.id,
    )
    return response(CurrentUser.model_validate(created), request)


@router.put("/{user_id}", response_model=ApiSuccess[CurrentUser])
def update_user(user_id: UUID, payload: UpdateUserRequest, request: Request, session: DbSession, user: AdminUser):
    try:
        updated = UserService().update_user(session, user_id, payload)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(
            request, action=AuditAction.USER_UPDATE, exc=exc, user=user,
            resource_type=AuditResourceType.USER, resource_id=user_id,
        )
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(
            request, action=AuditAction.USER_UPDATE, result=AuditResult.FAILED,
            user=user, resource_type=AuditResourceType.USER, resource_id=user_id,
            error_code="DATABASE_ERROR",
        )
        raise
    AuditService().record_request(
        request, action=AuditAction.USER_UPDATE, result=AuditResult.SUCCESS,
        user=user, resource_type=AuditResourceType.USER, resource_id=updated.id,
    )
    return response(CurrentUser.model_validate(updated), request)


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_users(payload: BulkUserDeleteRequest, request: Request, session: DbSession, user: AdminUser):
    try:
        UserService().delete_many(session, user_ids=payload.ids, current_user=user)
    except AppError as exc:
        session.rollback(); AuditService().record_failure(request, action=AuditAction.USER_DELETE, exc=exc, user=user, resource_type=AuditResourceType.USER); raise
    except SQLAlchemyError:
        session.rollback(); AuditService().record_request(request, action=AuditAction.USER_DELETE,
                                                          result=AuditResult.FAILED, user=user,
                                                          resource_type=AuditResourceType.USER,
                                                          error_code="DATABASE_ERROR"); raise
    AuditService().record_request(request, action=AuditAction.USER_DELETE, result=AuditResult.SUCCESS, user=user, resource_type=AuditResourceType.USER, note="批量删除用户")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, request: Request, session: DbSession, user: AdminUser):
    try:
        UserService().delete(session, user_id=user_id, current_user=user)
    except AppError as exc:
        session.rollback(); AuditService().record_failure(request, action=AuditAction.USER_DELETE, exc=exc, user=user, resource_type=AuditResourceType.USER, resource_id=user_id); raise
    AuditService().record_request(request, action=AuditAction.USER_DELETE, result=AuditResult.SUCCESS, user=user, resource_type=AuditResourceType.USER, resource_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/restore", response_model=ApiSuccess[CurrentUser])
def restore_user(user_id: UUID, request: Request, session: DbSession, user: AdminUser):
    try:
        restored = UserService().restore(session, user_id=user_id)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.USER_UPDATE, exc=exc, user=user,
                                      resource_type=AuditResourceType.USER, resource_id=user_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.USER_UPDATE, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.USER, resource_id=user_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.USER_UPDATE, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.USER, resource_id=user_id,
                                  note="恢复已删除用户")
    return response(CurrentUser.model_validate(restored), request)


@router.delete("/{user_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanent_delete_user(user_id: UUID, request: Request, session: DbSession, user: AdminUser):
    try:
        UserService().permanent_delete(session, user_id=user_id, current_user=user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.USER_DELETE, exc=exc, user=user,
                                      resource_type=AuditResourceType.USER, resource_id=user_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.USER_DELETE, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.USER, resource_id=user_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.USER_DELETE, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.USER, resource_id=user_id,
                                  note="永久删除用户")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
