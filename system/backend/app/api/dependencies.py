from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError
from app.models import User
from app.repositories.user_repository import UserRepository
from app.security.jwt import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    session: DbSession = None,  # type: ignore[assignment]
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(401, "AUTH_TOKEN_MISSING", "请先登录", {"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(claims["sub"])
    except (ValueError, TypeError, KeyError) as exc:
        raise AppError(401, "AUTH_TOKEN_INVALID", "登录状态无效，请重新登录", {"WWW-Authenticate": "Bearer"}) from exc
    user = UserRepository().get_by_id(session, user_id)
    request.state.business_session = session
    if user is None or user.token_version != claims["ver"]:
        raise AppError(401, "AUTH_TOKEN_INVALID", "登录状态无效，请重新登录", {"WWW-Authenticate": "Bearer"})
    if user.status != "ACTIVE":
        raise AppError(403, "ACCOUNT_DISABLED", "账号已被禁用")
    # 供统一异常处理记录一次权限拒绝；身份仍以当前数据库查询结果为准。
    request.state.audit_user = user
    return user
