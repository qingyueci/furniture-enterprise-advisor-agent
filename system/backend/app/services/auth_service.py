from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import User
from app.repositories.user_repository import UserRepository
from app.security.jwt import create_access_token
from app.security.passwords import verify_password


class AuthService:
    def __init__(self, users: UserRepository | None = None):
        self.users = users or UserRepository()

    def login(self, session: Session, *, username: str, password: str) -> tuple[str, User]:
        user = self.users.get_by_username(session, username)
        if user is None or not verify_password(password, user.password_hash):
            raise AppError(401, "AUTH_INVALID_CREDENTIALS", "用户名或密码错误", {"WWW-Authenticate": "Bearer"})
        if user.status != "ACTIVE":
            raise AppError(403, "ACCOUNT_DISABLED", "账号已被禁用")
        user.last_login_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(user)
        return create_access_token(user_id=user.id, username=user.username, role=user.role, token_version=user.token_version), user

    def logout(self, session: Session, user: User) -> None:
        user.token_version += 1
        session.commit()

    @property
    def expires_in(self) -> int:
        return get_settings().access_token_expire_minutes * 60
