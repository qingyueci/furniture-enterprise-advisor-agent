from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProductPrice


class PriceRepository:
    def latest_for_type(self, session: Session, *, product_id: int, price_type: str) -> ProductPrice | None:
        # The caller supplies only types already permitted for the database-current role.
        return session.scalar(
            select(ProductPrice)
            .where(ProductPrice.product_id == product_id, ProductPrice.price_type == price_type)
            .order_by(ProductPrice.update_time.desc(), ProductPrice.id.desc())
            .limit(1)
        )

    def demo_price_exists(self, session: Session, *, product_id: int, price_type: str, source: str) -> bool:
        return session.scalar(
            select(ProductPrice.id).where(
                ProductPrice.product_id == product_id,
                ProductPrice.price_type == price_type,
                ProductPrice.source == source,
            ).limit(1)
        ) is not None
