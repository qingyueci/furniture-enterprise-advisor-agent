from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Product
from app.repositories.product_repository import ProductRepository
from app.schemas.product import ProductCreateRequest, ProductUpdateRequest


class ProductService:
    def __init__(self, products: ProductRepository | None = None):
        self.products = products or ProductRepository()

    def list_products(self, session: Session, *, keyword: str | None, category: str | None, brand: str | None,
                      product_type: str | None, page: int, page_size: int, include_deleted: bool = False) -> tuple[list[Product], int]:
        statement = (self.products.deleted_list_query if include_deleted else self.products.list_query)(keyword=keyword, category=category, brand=brand, product_type=product_type)
        total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
        items = list(session.scalars(statement.offset((page - 1) * page_size).limit(page_size)))
        return items, total

    def options(self, session: Session) -> tuple[list[str], list[str]]:
        return self.products.brands(session), self.products.categories(session)

    @staticmethod
    def _clean(payload: ProductCreateRequest | ProductUpdateRequest) -> dict:
        values = payload.model_dump()
        for key in ("product_name", "model", "brand", "category", "description"):
            if isinstance(values.get(key), str):
                values[key] = values[key].strip() or None
        if not values["product_name"] or not values["model"] or not values["brand"]:
            raise AppError(422, "VALIDATION_ERROR", "产品名称、型号和品牌不能为空")
        return values

    def create(self, session: Session, payload: ProductCreateRequest) -> Product:
        values = self._clean(payload)
        # 数据库现有唯一约束覆盖软删除记录；重复校验也覆盖已删除记录，避免落到 500。
        duplicate = session.scalar(select(Product).where(Product.brand == values["brand"], Product.model == values["model"]))
        if duplicate is not None:
            raise AppError(409, "PRODUCT_EXISTS", "相同品牌和型号的产品已存在")
        product = Product(id=self.products.next_id(session), **values)
        session.add(product)
        session.commit()
        session.refresh(product)
        return product

    def update(self, session: Session, product_id: int, payload: ProductUpdateRequest) -> Product:
        product = self.products.get_by_id_for_update(session, product_id)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
        values = self._clean(payload)
        duplicate = session.scalar(select(Product).where(Product.brand == values["brand"], Product.model == values["model"], Product.id != product_id))
        if duplicate is not None:
            raise AppError(409, "PRODUCT_EXISTS", "相同品牌和型号的产品已存在")
        for key, value in values.items():
            setattr(product, key, value)
        session.commit()
        session.refresh(product)
        return product

    def delete(self, session: Session, product_id: int) -> Product:
        product = self.products.soft_delete(session, product_id)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
        session.commit()
        return product

    def restore(self, session: Session, product_id: int) -> Product:
        product = self.products.restore(session, product_id)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
        session.commit()
        return product

    def permanent_delete(self, session: Session, product_id: int) -> None:
        existing = self.products.get_by_id_for_update(session, product_id, include_deleted=True)
        if existing is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
        if existing.deleted_at is None:
            raise AppError(409, "PRODUCT_NOT_DELETED", "永久删除仅适用于已删除产品")
        deleted, links = self.products.permanent_delete(session, product_id)
        if not deleted:
            if links:
                raise AppError(409, "PRODUCT_HAS_LINKS", f"产品仍关联 {links} 条价格或资料记录，先解除关联或使用可恢复删除")
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
        session.commit()

    def delete_many(self, session: Session, product_ids: list[int]) -> int:
        products = [self.products.get_by_id_for_update(session, product_id) for product_id in dict.fromkeys(product_ids)]
        if any(product is None for product in products):
            raise AppError(404, "PRODUCT_NOT_FOUND", "批量操作中包含不存在或已删除产品")
        for product in products:
            product.deleted_at = func.now()
        session.commit()
        return len(products)

    def get_product(self, session: Session, product_id: int) -> Product:
        product = self.products.get_by_id(session, product_id)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND", "未找到该产品，请检查产品信息。")
        return product
