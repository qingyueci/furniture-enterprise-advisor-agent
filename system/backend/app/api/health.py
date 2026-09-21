from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_engine
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
def health(response: Response, engine: Engine = Depends(get_engine)) -> HealthResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            vector = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')"))
    except SQLAlchemyError:
        response.status_code = 503
        return HealthResponse(status="degraded", database="error", pgvector="unknown")
    if not vector:
        response.status_code = 503
        return HealthResponse(status="degraded", database="ok", pgvector="missing")
    return HealthResponse(status="ok", database="ok", pgvector="ok")
