"""只插入演示产品，不创建账号、价格或真实产品事实。"""
import json

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import get_engine
from app.models import Product

DEMO_PRODUCTS = [
    {"product_name": "企业产品 X100", "model": "X100", "brand": "DEMO_BRAND", "product_type": "INTERNAL"},
    {"product_name": "企业产品 X200", "model": "X200", "brand": "DEMO_BRAND", "product_type": "INTERNAL"},
    {"product_name": "竞品 Y200", "model": "Y200", "brand": "DEMO_COMPETITOR", "product_type": "COMPETITOR"},
]


def seed() -> dict:
    with get_engine().begin() as connection:
        for product in DEMO_PRODUCTS:
            connection.execute(insert(Product).values(**product, description="演示数据，不代表真实企业产品事实。")
                               .on_conflict_do_nothing(index_elements=["brand", "model"]))
        count = connection.scalar(select(func.count()).select_from(Product))
    return {"products_total": count, "demo_only": True}


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False))
