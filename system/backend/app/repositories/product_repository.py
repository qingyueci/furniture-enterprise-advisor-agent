from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import DocumentChunk, DocumentProduct, Product, ProductPrice


class ProductRepository:
    def get_by_id(self, session: Session, product_id: int, *, include_deleted: bool = False) -> Product | None:
        statement = select(Product).where(Product.id == product_id)
        if not include_deleted:
            statement = statement.where(Product.deleted_at.is_(None))
        return session.scalar(statement)

    def get_by_id_for_update(self, session: Session, product_id: int, *, include_deleted: bool = False) -> Product | None:
        statement = select(Product).where(Product.id == product_id).with_for_update()
        if not include_deleted:
            statement = statement.where(Product.deleted_at.is_(None))
        return session.scalar(statement)

    def exact_matches(self, session: Session, mention: str) -> list[Product]:
        key = mention.strip().lower()
        return list(session.scalars(
            select(Product).where(Product.deleted_at.is_(None), or_(
                func.lower(Product.model) == key,
                func.lower(Product.product_name) == key,
            )).order_by(Product.id.asc())
        ))

    def fuzzy_matches(self, session: Session, mention: str, limit: int = 5) -> list[Product]:
        needle = f"%{mention.strip()}%"
        return list(session.scalars(
            select(Product).where(Product.deleted_at.is_(None), or_(Product.model.ilike(needle), Product.product_name.ilike(needle)))
            .order_by(Product.product_name.asc(), Product.id.asc()).limit(limit)
        ))

    def list_query(self, *, keyword: str | None, category: str | None, brand: str | None,
                   product_type: str | None) -> Select[tuple[Product]]:
        statement = select(Product).where(Product.deleted_at.is_(None))
        if keyword:
            needle = f"%{keyword.strip()}%"
            statement = statement.where(or_(Product.product_name.ilike(needle), Product.model.ilike(needle)))
        if category:
            category = category.strip()
            if category == "未分类":
                statement = statement.where(or_(Product.category.is_(None), func.trim(Product.category) == ""))
            else:
                statement = statement.where(func.trim(Product.category).ilike(f"%{category.strip()}%"))
        if brand:
            statement = statement.where(func.trim(Product.brand).ilike(f"%{brand.strip()}%"))
        if product_type:
            statement = statement.where(Product.product_type == product_type)
        return statement.order_by(Product.product_name.asc(), Product.id.asc())

    def deleted_list_query(self, *, keyword: str | None, category: str | None, brand: str | None,
                           product_type: str | None) -> Select[tuple[Product]]:
        statement = select(Product).where(Product.deleted_at.is_not(None))
        if keyword:
            needle = f"%{keyword.strip()}%"
            statement = statement.where(or_(Product.product_name.ilike(needle), Product.model.ilike(needle)))
        if category:
            category = category.strip()
            if category == "未分类":
                statement = statement.where(or_(Product.category.is_(None), func.trim(Product.category) == ""))
            else:
                statement = statement.where(func.trim(Product.category).ilike(f"%{category.strip()}%"))
        if brand:
            statement = statement.where(func.trim(Product.brand).ilike(f"%{brand.strip()}%"))
        if product_type:
            statement = statement.where(Product.product_type == product_type)
        return statement.order_by(Product.deleted_at.desc(), Product.product_name.asc(), Product.id.asc())

    def next_id(self, session: Session) -> int:
        return int(session.scalar(select(func.coalesce(func.max(Product.id), 0))) or 0) + 1

    def brands(self, session: Session) -> list[str]:
        values = session.scalars(select(Product.brand).where(Product.deleted_at.is_(None))).all()
        return sorted({value.strip() for value in values if value and value.strip()}, key=str.casefold)

    def categories(self, session: Session) -> list[str]:
        values = session.scalars(select(Product.category).where(Product.deleted_at.is_(None))).all()
        normalized = {value.strip() for value in values if value and value.strip()}
        if any(value is None or not value.strip() for value in values):
            normalized.add("未分类")
        return sorted(normalized, key=lambda value: (value != "未分类", value.casefold()))

    def soft_delete(self, session: Session, product_id: int) -> Product | None:
        product = self.get_by_id_for_update(session, product_id)
        if product is not None:
            product.deleted_at = func.now()
        return product

    def restore(self, session: Session, product_id: int) -> Product | None:
        product = self.get_by_id_for_update(session, product_id, include_deleted=True)
        if product is not None:
            product.deleted_at = None
        return product

    def permanent_delete(self, session: Session, product_id: int) -> tuple[bool, int]:
        product = self.get_by_id_for_update(session, product_id, include_deleted=True)
        if product is None:
            return False, 0
        price_count = session.scalar(select(func.count()).select_from(ProductPrice).where(ProductPrice.product_id == product_id)) or 0
        document_count = session.scalar(select(func.count()).select_from(DocumentProduct).where(DocumentProduct.product_id == product_id)) or 0
        chunk_count = session.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.product_id == product_id)) or 0
        if price_count or document_count or chunk_count:
            return False, int(price_count + document_count + chunk_count)
        session.delete(product)
        return True, 0
