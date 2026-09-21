from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import get_settings
from app.core.exceptions import AppError


def create_access_token(*, user_id: UUID, username: str, role: str, token_version: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id), "username": username, "role": role, "ver": token_version,
        "iat": now, "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"],
                            options={"require": ["sub", "username", "role", "ver", "iat", "exp"]})
        UUID(claims["sub"])
        if not isinstance(claims["username"], str) or not isinstance(claims["role"], str):
            raise ValueError("invalid string claims")
        if not isinstance(claims["ver"], int) or isinstance(claims["ver"], bool) or claims["ver"] < 0:
            raise ValueError("invalid version claim")
        return claims
    except ExpiredSignatureError as exc:
        raise AppError(401, "AUTH_TOKEN_EXPIRED", "登录状态已过期，请重新登录", {"WWW-Authenticate": "Bearer"}) from exc
    except (InvalidTokenError, ValueError, KeyError, TypeError) as exc:
        raise AppError(401, "AUTH_TOKEN_INVALID", "登录状态无效，请重新登录", {"WWW-Authenticate": "Bearer"}) from exc
