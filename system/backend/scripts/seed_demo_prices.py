"""Insert stage 3 demonstration prices without changing non-demo price history."""
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_engine
from app.models import Product, ProductPrice
from app.repositories.price_repository import PriceRepository

DEMO_SOURCE = "阶段3演示价格数据，非真实报价"
DEMO_UPDATE_TIME = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
DEMO_PRICES = {
    ("DEMO_BRAND", "X100"): {"GUIDE": "3199.00", "SALES": "2999.00", "INTERNAL_QUOTE": "2699.00"},
    ("DEMO_BRAND", "X200"): {"GUIDE": "4299.00", "SALES": "3999.00", "INTERNAL_QUOTE": "3599.00"},
    ("DEMO_COMPETITOR", "Y200"): {"GUIDE": "3499.00", "SALES": "3299.00"},
}


def seed() -> dict:
    result = {"created": 0, "existing": 0, "prices_total": 0, "demo_only": True}
    with Session(get_engine()) as session:
        prices = PriceRepository()
        for (brand, model), entries in DEMO_PRICES.items():
            product = session.scalar(select(Product).where(Product.brand == brand, Product.model == model))
            if product is None:
                raise RuntimeError(f"Required demo product is missing: {brand}/{model}")
            for price_type, value in entries.items():
                if prices.demo_price_exists(session, product_id=product.id, price_type=price_type, source=DEMO_SOURCE):
                    result["existing"] += 1
                    continue
                session.add(ProductPrice(product_id=product.id, price=Decimal(value), currency="CNY", price_type=price_type,
                                         source=DEMO_SOURCE, update_time=DEMO_UPDATE_TIME))
                result["created"] += 1
        session.commit()
        result["prices_total"] = session.scalar(select(func.count()).select_from(ProductPrice)) or 0
    return result


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False))
