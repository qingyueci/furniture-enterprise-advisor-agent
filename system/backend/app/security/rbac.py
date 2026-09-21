from collections.abc import Callable

from fastapi import Depends

from app.core.exceptions import AppError
from app.models import User

ALL_PERMISSIONS = frozenset({
    "agent:use", "product:read", "product:manage", "price:public:read", "price:internal:read", "document:read_allowed",
    "document:manage", "document:permission_manage", "user:manage", "audit:read", "system:config",
})
ROLE_PERMISSIONS = {
    "ADMIN": ALL_PERMISSIONS,
    "PRODUCT_MANAGER": frozenset({"agent:use", "product:read", "product:manage", "price:public:read", "price:internal:read", "document:read_allowed"}),
    "SALES": frozenset({"agent:use", "product:read", "price:public:read", "document:read_allowed"}),
}


def has_permission(user: User, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def require_roles(*roles: str) -> Callable:
    from app.api.dependencies import get_current_user

    def check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        return user
    return check


def require_permission(permission: str) -> Callable:
    from app.api.dependencies import get_current_user

    def check(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        return user
    return check
