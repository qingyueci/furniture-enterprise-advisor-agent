from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Conversation, Document, User
from app.repositories.user_repository import UserRepository
from app.schemas.user import CreateUserRequest, UpdateUserRequest
from app.security.passwords import hash_password


class UserService:
    def __init__(self, users: UserRepository | None = None):
        self.users = users or UserRepository()

    def list_users(self, session: Session, *, keyword: str | None, role: str | None, status: str | None,
                   page: int, page_size: int, include_deleted: bool = False) -> tuple[list[User], int]:
        statement = self.users.deleted_query(keyword=keyword, role=role, status=status) if include_deleted else self.users.list_query(keyword=keyword, role=role, status=status)
        total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
        items = list(session.scalars(statement.offset((page - 1) * page_size).limit(page_size)))
        return items, total

    @staticmethod
    def _protected(user: User, current_user: User) -> str | None:
        if user.id == current_user.id:
            return "当前登录账号不能删除"
        if user.username in {"admin_demo", "pm_demo", "sales_demo"}:
            return "演示账号受保护"
        return None

    def delete(self, session: Session, *, user_id, current_user: User) -> User:
        user = self.users.get_by_id_for_update(session, user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "用户不存在")
        if reason := self._protected(user, current_user):
            raise AppError(409, "USER_PROTECTED", reason)
        if user.role == "ADMIN" and user.status == "ACTIVE":
            session.execute(text("SELECT pg_advisory_xact_lock(927215)"))
            if len(self.users.active_admins_for_update(session)) <= 1:
                raise AppError(409, "LAST_ACTIVE_ADMIN_REQUIRED", "系统必须保留至少一个启用的管理员")
        user.deleted_at = func.now()
        user.status = "DISABLED"
        user.token_version += 1
        session.commit()
        return user

    def restore(self, session: Session, *, user_id) -> User:
        user = self.users.restore(session, user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "用户不存在")
        session.commit()
        return user

    def permanent_delete(self, session: Session, *, user_id, current_user: User) -> None:
        user = self.users.get_by_id_for_update(session, user_id, include_deleted=True)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "用户不存在")
        if user.deleted_at is None:
            raise AppError(409, "USER_NOT_DELETED", "永久删除仅适用于已删除用户")
        if reason := self._protected(user, current_user):
            raise AppError(409, "USER_PROTECTED", reason)
        links = (session.scalar(select(func.count()).select_from(Document).where(Document.upload_user_id == user_id)) or 0)
        links += session.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)) or 0
        if links:
            raise AppError(409, "USER_HAS_LINKS", f"用户仍关联 {links} 条资料或会话记录，先使用可恢复删除")
        session.delete(user)
        session.commit()

    def delete_many(self, session: Session, *, user_ids, current_user: User) -> int:
        unique_ids = list(dict.fromkeys(user_ids))
        users = [self.users.get_by_id_for_update(session, user_id) for user_id in unique_ids]
        if any(item is None for item in users):
            raise AppError(404, "USER_NOT_FOUND", "批量操作中包含不存在或已删除用户")
        for item in users:
            if reason := self._protected(item, current_user):
                raise AppError(409, "USER_PROTECTED", reason)
        session.execute(text("SELECT pg_advisory_xact_lock(927215)"))
        active_admins = self.users.active_admins_for_update(session)
        removing_admins = sum(item.role == "ADMIN" and item.status == "ACTIVE" for item in users)
        if len(active_admins) - removing_admins < 1:
            raise AppError(409, "LAST_ACTIVE_ADMIN_REQUIRED", "系统必须保留至少一个启用的管理员")
        for item in users:
            item.deleted_at = func.now()
            item.status = "DISABLED"
            item.token_version += 1
        session.commit()
        return len(users)

    def create_user(self, session: Session, payload: CreateUserRequest) -> User:
        if self.users.get_by_username(session, payload.username):
            raise AppError(409, "USERNAME_EXISTS", "用户名已存在")
        user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role, status=payload.status)
        session.add(user)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise AppError(409, "USERNAME_EXISTS", "用户名已存在") from exc
        session.refresh(user)
        return user

    def update_user(self, session: Session, user_id, payload: UpdateUserRequest) -> User:
        user = self.users.get_by_id_for_update(session, user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND", "用户不存在")
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise AppError(400, "VALIDATION_ERROR", "至少需要提供一个更新字段")
        if "username" in values and values["username"] != user.username:
            existing = self.users.get_by_username(session, values["username"])
            if existing is not None and existing.id != user.id:
                raise AppError(409, "USERNAME_EXISTS", "用户名已存在")
        leaves_active_admin = user.role == "ADMIN" and user.status == "ACTIVE" and (
            values.get("role", user.role) != "ADMIN" or values.get("status", user.status) != "ACTIVE"
        )
        if leaves_active_admin:
            # Serialize active-admin changes and lock the relevant rows before checking their count.
            session.execute(text("SELECT pg_advisory_xact_lock(927215)"))
            active_admins = self.users.active_admins_for_update(session)
            if len(active_admins) <= 1:
                raise AppError(409, "LAST_ACTIVE_ADMIN_REQUIRED", "系统必须保留至少一个启用的管理员")
        changed = False
        for field in ("username", "role", "status"):
            if field in values and values[field] != getattr(user, field):
                setattr(user, field, values[field])
                changed = True
        if values.get("new_password"):
            user.password_hash = hash_password(values["new_password"])
            changed = True
        if changed:
            user.token_version += 1
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise AppError(409, "USERNAME_EXISTS", "用户名已存在") from exc
        session.refresh(user)
        return user
