from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import User


class UserRepository:
    def get_by_id(self, session: Session, user_id: UUID, *, include_deleted: bool = False) -> User | None:
        # 受保护请求可能复用长生命周期 Session；每次认证都以数据库当前
        # 的状态和角色为准，不沿用身份映射中的旧 User 对象。
        statement = select(User).where(User.id == user_id)
        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))
        return session.scalar(statement.execution_options(populate_existing=True))

    def get_by_id_for_update(self, session: Session, user_id: UUID, *, include_deleted: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id).with_for_update()
        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))
        return session.scalar(
            statement
            .execution_options(populate_existing=True)
        )

    def get_by_username(self, session: Session, username: str) -> User | None:
        return session.scalar(select(User).where(User.username == username, User.deleted_at.is_(None)))

    def list_query(self, *, keyword: str | None, role: str | None, status: str | None) -> Select[tuple[User]]:
        statement = select(User).where(User.deleted_at.is_(None))
        if keyword:
            statement = statement.where(User.username.ilike(f"%{keyword.strip().lower()}%"))
        if role:
            statement = statement.where(User.role == role)
        if status:
            statement = statement.where(User.status == status)
        return statement.order_by(User.created_at.desc(), User.username.asc())

    def deleted_query(self, *, keyword: str | None, role: str | None, status: str | None) -> Select[tuple[User]]:
        statement = select(User).where(User.deleted_at.is_not(None))
        if keyword:
            statement = statement.where(User.username.ilike(f"%{keyword.strip().lower()}%"))
        if role:
            statement = statement.where(User.role == role)
        if status:
            statement = statement.where(User.status == status)
        return statement.order_by(User.deleted_at.desc(), User.username.asc())

    def soft_delete(self, session: Session, user_id: UUID) -> User | None:
        user = self.get_by_id_for_update(session, user_id)
        if user is not None:
            user.deleted_at = func.now()
            user.status = "DISABLED"
            user.token_version += 1
        return user

    def restore(self, session: Session, user_id: UUID) -> User | None:
        user = self.get_by_id_for_update(session, user_id, include_deleted=True)
        if user is not None and user.deleted_at is not None:
            user.deleted_at = None
            user.status = "ACTIVE"
            user.token_version += 1
        return user

    def active_admins_for_update(self, session: Session) -> list[User]:
        return list(session.scalars(select(User).where(User.role == "ADMIN", User.status == "ACTIVE").with_for_update()))

    def count_active_admins(self, session: Session) -> int:
        return session.scalar(select(func.count()).select_from(User).where(User.role == "ADMIN", User.status == "ACTIVE")) or 0
