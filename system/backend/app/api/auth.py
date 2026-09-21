from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import DbSession, get_current_user
from app.core.exceptions import AppError
from app.models import User
from app.schemas.auth import LoginData, LoginRequest, LogoutData
from app.schemas.common import ApiSuccess, CurrentUser
from app.schemas.audit import AuditAction, AuditResult, AuditResourceType
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def response(data, request: Request):
    return ApiSuccess(data=data, request_id=request.state.request_id)


@router.post("/login", response_model=ApiSuccess[LoginData])
def login(payload: LoginRequest, request: Request, session: DbSession):
    service = AuthService()
    candidate = None
    try:
        # 只读取已通过 LoginRequest 校验的用户名；密码永远不进入审计事件。
        candidate = service.users.get_by_username(session, payload.username)
        token, user = service.login(session, username=payload.username, password=payload.password)
    except AppError as exc:
        # 认证失败只读取业务数据，没有失败的写事务需要回滚；避免把
        # 调用方正在管理的外层事务一并回滚。
        AuditService().record_request(
            request,
            action=AuditAction.LOGIN_FAILED,
            result=AuditResult.FAILED,
            user=candidate,
            username=payload.username if candidate is None else None,
            resource_type=AuditResourceType.AUTH,
            error_code=exc.code,
            note="身份验证失败",
        )
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(
            request,
            action=AuditAction.LOGIN_FAILED,
            result=AuditResult.FAILED,
            username=payload.username,
            resource_type=AuditResourceType.AUTH,
            error_code="DATABASE_ERROR",
            note="身份验证失败",
        )
        raise
    AuditService().record_request(
        request,
        action=AuditAction.LOGIN_SUCCESS,
        result=AuditResult.SUCCESS,
        user=user,
        resource_type=AuditResourceType.AUTH,
    )
    data = LoginData(access_token=token, expires_in=AuthService().expires_in, user=CurrentUser.model_validate(user))
    return response(data, request)


@router.get("/me", response_model=ApiSuccess[CurrentUser])
def me(request: Request, user: Annotated[User, Depends(get_current_user)]):
    return response(CurrentUser.model_validate(user), request)


@router.post("/logout", response_model=ApiSuccess[LogoutData])
def logout(request: Request, session: DbSession, user: Annotated[User, Depends(get_current_user)]):
    try:
        AuthService().logout(session, user)
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(
            request,
            action=AuditAction.LOGOUT,
            result=AuditResult.FAILED,
            user=user,
            resource_type=AuditResourceType.AUTH,
            error_code="DATABASE_ERROR",
        )
        raise
    AuditService().record_request(
        request,
        action=AuditAction.LOGOUT,
        result=AuditResult.SUCCESS,
        user=user,
        resource_type=AuditResourceType.AUTH,
    )
    return response(LogoutData(), request)
