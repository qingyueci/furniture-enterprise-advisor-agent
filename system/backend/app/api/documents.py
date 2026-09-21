from collections.abc import Callable
import inspect
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import response
from app.api.dependencies import DbSession
from app.core.exceptions import AppError
from app.models import User
from app.schemas.audit import AuditAction, AuditResourceType, AuditResult
from app.schemas.common import ApiSuccess, Pagination
from app.schemas.document import (DocumentData, DocumentListData, DocumentPermissionUpdate,
                                  DocumentUploadData, FileType, ParseStatus, SecurityLevel)
from app.security.rbac import require_permission
from app.services.document_service import DocumentService
from app.services.audit_service import AuditService, request_ip
from app.services.file_storage_service import MIME_TYPES
from app.rag.processor import process_document_background

router = APIRouter(prefix="/api/documents", tags=["documents"])
DocumentReader = Annotated[User, Depends(require_permission("document:read_allowed"))]
DocumentManager = Annotated[User, Depends(require_permission("document:manage"))]
PermissionManager = Annotated[User, Depends(require_permission("document:permission_manage"))]


def get_document_service() -> DocumentService:
    return DocumentService()


def get_document_processor() -> Callable[[UUID], None]:
    return process_document_background


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
DocumentProcessorDep = Annotated[Callable[..., None], Depends(get_document_processor)]


@router.get("", response_model=ApiSuccess[DocumentListData])
def list_documents(request: Request, session: DbSession, user: DocumentReader, service: DocumentServiceDep,
                   keyword: str | None = Query(default=None, max_length=50), file_type: FileType | None = None,
                   parse_status: ParseStatus | None = None, product_id: int | None = None,
                   page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)):
    items, total = service.list_documents(session, user=user, keyword=keyword, file_type=file_type,
                                          parse_status=parse_status, product_id=product_id,
                                          page=page, page_size=page_size)
    return response(DocumentListData(items=items, pagination=Pagination(page=page, page_size=page_size, total=total)), request)


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, response_model=ApiSuccess[DocumentUploadData])
async def upload_document(request: Request, background_tasks: BackgroundTasks, session: DbSession,
                          user: DocumentManager, service: DocumentServiceDep, processor: DocumentProcessorDep,
                          file: UploadFile = File(...), document_name: str = Form(..., min_length=1, max_length=255),
                          security_level: SecurityLevel = Form(...), allowed_roles: list[str] = Form(...),
                          product_ids: list[int] = Form(default=[])):
    try:
        document = await service.upload(session, upload=file, document_name=document_name, security_level=security_level,
                                        allowed_roles=allowed_roles, product_ids=product_ids, user=user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.DOCUMENT_UPLOAD, exc=exc,
                                      user=user, resource_type=AuditResourceType.DOCUMENT)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.DOCUMENT_UPLOAD, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.DOCUMENT,
                                      error_code="DATABASE_ERROR")
        raise
    # 正式处理器继承上传请求的关联 ID；测试/替换处理器若仍保持旧的
    # 单参数契约，则不强行传入关键字参数。
    try:
        parameters = inspect.signature(processor).parameters.values()
        accepts_context = (
            "audit_request_id" in inspect.signature(processor).parameters
            or any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters)
        )
    except (TypeError, ValueError):
        accepts_context = False
    if accepts_context:
        background_tasks.add_task(
            processor,
            document.id,
            audit_request_id=request.state.request_id,
            audit_request_ip=request_ip(request),
        )
    else:
        background_tasks.add_task(processor, document.id)
    AuditService().record_request(request, action=AuditAction.DOCUMENT_UPLOAD, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document.id)
    return response(DocumentUploadData(document_id=document.id, file_type=document.file_type, parse_status="PARSING"), request)


@router.get("/{document_id}", response_model=ApiSuccess[DocumentData])
def get_document(document_id: UUID, request: Request, session: DbSession, user: DocumentReader, service: DocumentServiceDep):
    try:
        data = service.detail(session, document_id=document_id, user=user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.DOCUMENT_READ, exc=exc,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.DOCUMENT_READ, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.DOCUMENT_READ, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=data.id)
    return response(data, request)


@router.get("/{document_id}/download")
def download_document(document_id: UUID, request: Request, session: DbSession, user: DocumentReader, service: DocumentServiceDep):
    try:
        item = service.download(session, document_id=document_id, user=user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.DOCUMENT_READ, exc=exc,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.DOCUMENT_READ, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.DOCUMENT_READ, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
    media_type = MIME_TYPES[f".{item.file_type.lower()}"][1]
    return FileResponse(item.path, media_type=media_type, filename=item.original_name)


@router.put("/{document_id}/permissions", response_model=ApiSuccess[DocumentData])
def update_permissions(document_id: UUID, payload: DocumentPermissionUpdate, request: Request, session: DbSession,
                       user: PermissionManager, service: DocumentServiceDep):
    try:
        data = service.update_permissions(session, document_id=document_id, payload=payload, user=user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.DOCUMENT_PERMISSION_UPDATE, exc=exc,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.DOCUMENT_PERMISSION_UPDATE,
                                      result=AuditResult.FAILED, user=user,
                                      resource_type=AuditResourceType.DOCUMENT, resource_id=document_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.DOCUMENT_PERMISSION_UPDATE,
                                  result=AuditResult.SUCCESS, user=user,
                                  resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
    return response(data, request)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: UUID, request: Request, session: DbSession, user: DocumentManager, service: DocumentServiceDep):
    try:
        service.delete(session, document_id=document_id, user=user)
    except AppError as exc:
        session.rollback()
        AuditService().record_failure(request, action=AuditAction.DOCUMENT_DELETE, exc=exc,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
        raise
    except SQLAlchemyError:
        session.rollback()
        AuditService().record_request(request, action=AuditAction.DOCUMENT_DELETE, result=AuditResult.FAILED,
                                      user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id,
                                      error_code="DATABASE_ERROR")
        raise
    AuditService().record_request(request, action=AuditAction.DOCUMENT_DELETE, result=AuditResult.SUCCESS,
                                  user=user, resource_type=AuditResourceType.DOCUMENT, resource_id=document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
