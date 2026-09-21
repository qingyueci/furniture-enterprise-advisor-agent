from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    application: Literal["enterprise-product-analysis-agent"] = "enterprise-product-analysis-agent"
    database: Literal["ok", "error"]
    pgvector: Literal["ok", "missing", "unknown"]
