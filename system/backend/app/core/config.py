from pathlib import Path

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    demo_admin_password: SecretStr | None = None
    demo_pm_password: SecretStr | None = None
    demo_sales_password: SecretStr | None = None
    embedding_provider: str = "local_sentence_transformers"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = None
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_model_revision: str | None = None
    embedding_dimensions: int = Field(default=512, ge=1)
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    embedding_cache_dir: Path = Path(__file__).resolve().parents[3] / "data" / "models"
    embedding_local_files_only: bool = True
    embedding_timeout_seconds: float = Field(default=30, gt=0, le=120)
    rag_top_k_default: int = Field(default=5, ge=1, le=8)
    rag_top_k_max: int = Field(default=8, ge=1, le=8)
    rag_min_similarity: float = Field(default=0.30, ge=-1, le=1)
    rag_context_max_chars: int = Field(default=8000, ge=1000, le=20000)
    parsing_stale_minutes: int = Field(default=10, ge=1, le=1440)
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: SecretStr | None = None
    llm_router_model: str = "deepseek-v4-flash"
    llm_generation_model: str = "deepseek-v4-pro"
    llm_timeout_seconds: float = Field(default=30, gt=0, le=60)
    llm_max_output_tokens: int = Field(default=1500, ge=100, le=8000)
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8", extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
            valid = url.drivername == "postgresql+psycopg" and bool(url.database)
        except Exception:
            valid = False
        if not valid:
            raise ValueError("DATABASE_URL must use postgresql+psycopg and specify a database")
        return value

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> "Settings":
        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        if len(self.jwt_secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        if self.embedding_provider not in {"local_sentence_transformers", "openai_compatible"}:
            raise ValueError("EMBEDDING_PROVIDER is not supported")
        if self.embedding_dimensions != 512:
            raise ValueError("EMBEDDING_DIMENSIONS must match vector(512)")
        if self.embedding_provider == "local_sentence_transformers":
            if self.embedding_device != "cpu":
                raise ValueError("local sentence-transformers must use CPU")
            if not self.embedding_model.strip():
                raise ValueError("EMBEDDING_MODEL must specify a model ID or local directory")
        if self.rag_top_k_default > self.rag_top_k_max:
            raise ValueError("RAG_TOP_K_DEFAULT must not exceed RAG_TOP_K_MAX")
        if not self.llm_base_url.startswith(("https://", "http://")):
            raise ValueError("LLM_BASE_URL must use HTTP or HTTPS")
        if not self.llm_router_model.strip() or not self.llm_generation_model.strip():
            raise ValueError("LLM router and generation models must not be empty")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
