from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Product, ProductPrice, User
from app.repositories.price_repository import PriceRepository
from app.security.rbac import has_permission

PUBLIC_TYPES = ("GUIDE", "SALES")
INTERNAL_TYPE = "INTERNAL_QUOTE"


class PriceService:
    def __init__(self, prices: PriceRepository | None = None):
        self.prices = prices or PriceRepository()

    def allowed_types(self, user: User) -> tuple[str, ...]:
        # user is fetched from the database by get_current_user on every protected request.
        if not has_permission(user, "price:public:read"):
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        if has_permission(user, "price:internal:read"):
            return (*PUBLIC_TYPES, INTERNAL_TYPE)
        return PUBLIC_TYPES

    def latest_prices(self, session: Session, *, product: Product, user: User,
                      requested_type: str | None) -> list[ProductPrice]:
        allowed_types = self.allowed_types(user)
        if requested_type is not None and requested_type not in allowed_types:
            raise AppError(403, "PERMISSION_DENIED", "当前账号没有执行此操作的权限")
        selected_types = (requested_type,) if requested_type else allowed_types
        # Each SQL statement has a permitted price_type predicate; sensitive rows never reach SALES.
        prices = [self.prices.latest_for_type(session, product_id=product.id, price_type=price_type)
                  for price_type in selected_types]
        visible_prices = [price for price in prices if price is not None]
        if not visible_prices:
            raise AppError(404, "PRICE_NOT_FOUND", "当前查询范围内没有价格数据。")
        return visible_prices
