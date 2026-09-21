from contextlib import asynccontextmanager
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import agent, audit, auth, documents, health, products, users
from app.core.exceptions import AppError
from app.services.audit_service import AuditService
from app.schemas.common import ApiError, ErrorBody
from app.schemas.audit import AuditAction, AuditResult
from app.rag.processor import mark_stale_parsing_failed

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        mark_stale_parsing_failed()
    except SQLAlchemyError:
        # 启动恢复失败不阻断健康接口，但必须留下不含连接串的稳定诊断。
        LOGGER.warning("STALE_DOCUMENT_RECOVERY_FAILED error_code=DATABASE_ERROR")
    yield


app = FastAPI(title="家具企业顾问 Agent 系统", version="0.6.0", lifespan=lifespan)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = f"req_{uuid4()}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error_response(request: Request, *, status_code: int, code: str, message: str, headers: dict[str, str] | None = None):
    return JSONResponse(status_code=status_code, headers=headers,
                        content=ApiError(error=ErrorBody(code=code, message=message), request_id=request.state.request_id).model_dump())


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    if AuditService.is_access_denial(exc):
        business_session = getattr(request.state, "business_session", None)
        if business_session is not None:
            try:
                business_session.rollback()
            except Exception:
                pass
        if not getattr(request.state, "permission_audited", False):
            request.state.permission_audited = True
            AuditService().record_permission_denied(request, exc)
    return error_response(request, status_code=exc.status_code, code=exc.code, message=exc.message, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, _: RequestValidationError):
    # 请求体不读取、不落库；登录标识无法通过现有校验时保持匿名。
    if request.url.path == "/api/auth/login":
        AuditService().record_request(
            request,
            action=AuditAction.LOGIN_FAILED,
            result=AuditResult.FAILED,
            resource_type="AUTH",
            error_code="VALIDATION_ERROR",
        )
    return error_response(request, status_code=422, code="VALIDATION_ERROR", message="请求参数不符合要求")


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, _: SQLAlchemyError):
    return error_response(request, status_code=503, code="DATABASE_ERROR", message="数据库服务暂时不可用")


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(documents.router)
app.include_router(agent.router)
app.include_router(audit.router)
