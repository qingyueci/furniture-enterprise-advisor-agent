from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import response
from app.api.dependencies import DbSession
from app.core.exceptions import AppError
from app.models import User
from app.schemas.audit import AuditAction, AuditResourceType, AuditResult
from app.schemas.common import ApiSuccess, Pagination
from app.schemas.product import (BulkProductDeleteRequest, PriceData, PriceProductData, PriceType, ProductCreateRequest, ProductData,
                                 ProductListData, ProductOptionsData, ProductPricesData, ProductType, ProductUpdateRequest)
from app.security.rbac import require_permission
from app.services.price_service import PriceService
from app.services.product_service import ProductService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/products", tags=["products"])
ProductReader = Annotated[User, Depends(require_permission("product:read"))]
ProductManager = Annotated[User, Depends(require_permission("product:manage"))]
PriceReader = Annotated[User, Depends(require_permission("price:public:read"))]


@router.get("", response_model=ApiSuccess[ProductListData])
def list_products(
    request: Request, session: DbSession, user: ProductReader,
    keyword: str | None = Query(default=None, max_length=50), category: str | None = Query(default=None, max_length=80),
    brand: str | None = Query(default=None, max_length=80), product_type: ProductType | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), include_deleted: bool = False,
):
    if include_deleted and user.role not in {"ADMIN", "PRODUCT_MANAGER"}:
        raise AppError(403, "PERMISSION_DENIED", "当前账号没有查看已删除产品的权限")
    try:
        items, total = ProductService().list_products(session, keyword=keyword, category=category, brand=brand,
                                                      product_type=product_type, page=page, page_size=page_size,
                                                      include_deleted=include_deleted)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.PRODUCT_QUERY, exc=exc,
                                      user=user, resource_type=AuditResourceType.PRODUCT)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.PRODUCT_QUERY, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.PRODUCT,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_QUERY, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.PRODUCT)
    return response(ProductListData(items=[ProductData.model_validate(item) for item in items],
                                    pagination=Pagination(page=page, page_size=page_size, total=total)), request)


@router.get("/options", response_model=ApiSuccess[ProductOptionsData])
def product_options(request: Request, session: DbSession, user: ProductReader):
    brands, categories = ProductService().options(session)
    return response(ProductOptionsData(brands=brands, categories=categories), request)


@router.post("", response_model=ApiSuccess[ProductData], status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreateRequest, request: Request, session: DbSession, user: ProductManager):
    try:
        product = ProductService().create(session, payload)
    except AppError as exc:
        session.rollback(); AuditService().record_failure(request, action=AuditAction.PRODUCT_CREATE, exc=exc, user=user, resource_type=AuditResourceType.PRODUCT); raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_CREATE, result=AuditResult.SUCCESS, user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product.id)
    return response(ProductData.model_validate(product), request)


@router.put("/{product_id}", response_model=ApiSuccess[ProductData])
def update_product(product_id: int, payload: ProductUpdateRequest, request: Request, session: DbSession, user: ProductManager):
    try:
        product = ProductService().update(session, product_id, payload)
    except AppError as exc:
        session.rollback(); AuditService().record_failure(request, action=AuditAction.PRODUCT_UPDATE, exc=exc, user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id); raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_UPDATE, result=AuditResult.SUCCESS, user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product.id)
    return response(ProductData.model_validate(product), request)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, request: Request, session: DbSession, user: ProductManager):
    try:
        ProductService().delete(session, product_id)
    except AppError as exc:
        session.rollback(); AuditService().record_failure(request, action=AuditAction.PRODUCT_DELETE, exc=exc, user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id); raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_DELETE, result=AuditResult.SUCCESS, user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_products(payload: BulkProductDeleteRequest, request: Request, session: DbSession, user: ProductManager):
    try:
        ProductService().delete_many(session, payload.ids)
    except AppError as exc:
        session.rollback(); AuditService().record_failure(request, action=AuditAction.PRODUCT_DELETE, exc=exc, user=user, resource_type=AuditResourceType.PRODUCT); raise
    except SQLAlchemyError:
        session.rollback(); AuditService().record_request(request, action=AuditAction.PRODUCT_DELETE,
                                                          result=AuditResult.FAILED, user=user,
                                                          resource_type=AuditResourceType.PRODUCT,
                                                          error_code="DATABASE_ERROR"); raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_DELETE, result=AuditResult.SUCCESS, user=user, resource_type=AuditResourceType.PRODUCT, note="批量删除产品")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{product_id}/restore", response_model=ApiSuccess[ProductData])
def restore_product(product_id: int, request: Request, session: DbSession, user: ProductManager):
    try:
        product = ProductService().restore(session, product_id)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.PRODUCT_UPDATE, exc=exc, user=user,
                                      resource_type=AuditResourceType.PRODUCT, resource_id=product_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.PRODUCT_UPDATE, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.PRODUCT,
                                      resource_id=product_id, error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_UPDATE, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id,
                                  note="恢复已删除产品")
    return response(ProductData.model_validate(product), request)


@router.delete("/{product_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanent_delete_product(product_id: int, request: Request, session: DbSession, user: ProductManager):
    try:
        ProductService().permanent_delete(session, product_id)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.PRODUCT_DELETE, exc=exc, user=user,
                                      resource_type=AuditResourceType.PRODUCT, resource_id=product_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.PRODUCT_DELETE, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.PRODUCT,
                                      resource_id=product_id, error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_DELETE, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id,
                                  note="永久删除产品")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{product_id}", response_model=ApiSuccess[ProductData])
def get_product(product_id: int, request: Request, session: DbSession, user: ProductReader):
    try:
        product = ProductService().get_product(session, product_id)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.PRODUCT_QUERY, exc=exc,
                                      user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.PRODUCT_QUERY, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.PRODUCT_QUERY, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.PRODUCT, resource_id=product.id)
    return response(ProductData.model_validate(product), request)


@router.get("/{product_id}/price", response_model=ApiSuccess[ProductPricesData])
def get_prices(product_id: int, request: Request, session: DbSession, user: PriceReader,
               price_type: PriceType | None = None):
    try:
        product = ProductService().get_product(session, product_id)
        prices = PriceService().latest_prices(session, product=product, user=user, requested_type=price_type)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.PRICE_QUERY, exc=exc,
                                      user=user, resource_type=AuditResourceType.PRICE, resource_id=product_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.PRICE_QUERY, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.PRICE, resource_id=product_id,
                                      error_code="DATABASE_ERROR")
        raise
    data = ProductPricesData(product=PriceProductData(id=product.id, product_name=product.product_name, model=product.model),
                             prices=[PriceData.model_validate(price) for price in prices])
    AuditService().record_request(request, action=AuditAction.PRICE_QUERY, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.PRICE, resource_id=product.id)
    return response(data, request)
