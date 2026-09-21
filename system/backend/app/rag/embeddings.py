from collections.abc import Sequence
import hashlib
import math
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from openai import OpenAI

from app.core.config import Settings, get_settings
from app.rag.types import EmbeddingInputError, RagProcessingError

QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


class EmbeddingProvider(Protocol):
    dimensions: int
    provider_name: str
    model_name: str
    revision: str
    max_seq_length: int | None

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def split_document_text(self, text: str) -> list[str]: ...


def validate_embeddings(
    vectors: Sequence[Sequence[float]], expected_count: int, dimensions: int,
) -> list[list[float]]:
    normalized = [list(map(float, vector)) for vector in vectors]
    if len(normalized) != expected_count:
        raise RagProcessingError("Embedding 返回数量与请求不一致")
    for vector in normalized:
        if len(vector) != dimensions:
            raise RagProcessingError(f"Embedding 向量维度不符合 {dimensions} 维要求")
        if any(not math.isfinite(value) for value in vector):
            raise RagProcessingError("Embedding 向量包含无效数值")
        if math.sqrt(sum(value * value for value in vector)) <= 0.0:
            raise RagProcessingError("Embedding 向量范数必须大于零")
    return normalized


class FakeEmbeddingProvider:
    """Deterministic test double. Production provider selection never returns this class."""

    provider_name = "fake_test"
    model_name = "fake-deterministic"
    revision = "test"
    max_seq_length = None

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []
        self.calls: list[list[str]] = []

    def _vectors(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [((digest[index % len(digest)] / 255.0) * 2.0 - 1.0) for index in range(self.dimensions)]
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return validate_embeddings(vectors, len(texts), self.dimensions)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        self.document_calls.append(batch)
        self.calls.append(batch)
        return self._vectors(batch)

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        self.calls.append([text])
        return self._vectors([text])[0]

    def split_document_text(self, text: str) -> list[str]:
        return [text]


_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_MODEL_LOAD_LOCK = RLock()
_ENCODE_LOCK = RLock()


def _clear_model_cache_for_tests() -> None:
    with _MODEL_LOAD_LOCK:
        _MODEL_CACHE.clear()


class LocalSentenceTransformerEmbeddingProvider:
    provider_name = "local_sentence_transformers"

    def __init__(self, settings: Settings, *, model_loader: Any | None = None):
        self.dimensions = settings.embedding_dimensions
        self.model_name = settings.embedding_model
        self.batch_size = settings.embedding_batch_size
        self.device = settings.embedding_device
        self.cache_dir = Path(settings.embedding_cache_dir).resolve()
        self.local_files_only = settings.embedding_local_files_only
        self.configured_revision = settings.embedding_model_revision
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            source, revision = self._resolve_source()
            key = (str(source), self.device)
            with _MODEL_LOAD_LOCK:
                model = _MODEL_CACHE.get(key)
                if model is None:
                    if model_loader is None:
                        from sentence_transformers import SentenceTransformer

                        model = SentenceTransformer(
                            str(source), device=self.device, cache_folder=str(self.cache_dir),
                            trust_remote_code=False, local_files_only=True,
                        )
                    else:
                        model = model_loader(str(source), self.device, self.cache_dir)
                    _MODEL_CACHE[key] = model
            dimension_getter = getattr(model, "get_embedding_dimension", None)
            if dimension_getter is None:
                dimension_getter = model.get_sentence_embedding_dimension
            actual_dimensions = int(dimension_getter())
            if actual_dimensions != self.dimensions:
                raise RagProcessingError(
                    f"本地 Embedding 模型维度为 {actual_dimensions}，与配置的 {self.dimensions} 维不一致"
                )
            self.model = model
            self.revision = revision
            self.max_seq_length = int(model.max_seq_length)
            if self.max_seq_length <= 0:
                raise RagProcessingError("本地 Embedding 模型的最大序列长度无效")
        except RagProcessingError:
            raise
        except Exception as exc:
            raise RagProcessingError("本地 Embedding 模型下载或加载失败，请检查模型缓存与网络设置") from exc

    def _resolve_source(self) -> tuple[Path, str]:
        configured = Path(self.model_name).expanduser()
        if configured.is_dir():
            source = configured.resolve()
            revision_file = source / ".model-revision"
            revision = self.configured_revision or (
                revision_file.read_text(encoding="utf-8").strip() if revision_file.is_file() else "local-unversioned"
            )
            return source, revision
        from huggingface_hub import snapshot_download

        snapshot = Path(snapshot_download(
            repo_id=self.model_name,
            revision=self.configured_revision,
            cache_dir=str(self.cache_dir),
            local_files_only=self.local_files_only,
        )).resolve()
        return snapshot, snapshot.name

    def _token_count(self, text: str) -> int:
        encoded = self.model.tokenizer(text, add_special_tokens=True, truncation=False)
        ids = encoded["input_ids"]
        return len(ids[0]) if ids and isinstance(ids[0], list) else len(ids)

    def split_document_text(self, text: str) -> list[str]:
        if self._token_count(text) <= self.max_seq_length:
            return [text]
        pieces: list[str] = []
        start = 0
        while start < len(text):
            low, high, best = start + 1, len(text), start
            while low <= high:
                middle = (low + high) // 2
                if self._token_count(text[start:middle]) <= self.max_seq_length:
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best == start:
                raise RagProcessingError("文档文本无法按本地模型 Token 上限安全拆分")
            pieces.append(text[start:best])
            start = best
        return pieces

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        if not values:
            return []
        try:
            with _ENCODE_LOCK:
                encoded = self.model.encode(
                    values, batch_size=self.batch_size, show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=True,
                )
            raw = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        except Exception as exc:
            raise RagProcessingError("本地 Embedding 编码失败，请检查模型与输入") from exc
        return validate_embeddings(raw, len(values), self.dimensions)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        if any(self._token_count(text) > self.max_seq_length for text in values):
            raise RagProcessingError("文档块超过本地模型 Token 上限，需先拆分后编码")
        return self._encode(values)

    def embed_query(self, text: str) -> list[float]:
        prepared = f"{QUERY_PREFIX}{text}"
        if self._token_count(prepared) > self.max_seq_length:
            raise EmbeddingInputError("检索问题超过本地模型 Token 上限")
        return self._encode([prepared])[0]


class OpenAICompatibleEmbeddingProvider:
    provider_name = "openai_compatible"
    revision = "api"
    max_seq_length = None

    def __init__(self, settings: Settings):
        if settings.embedding_api_key is None or not settings.embedding_api_key.get_secret_value().strip():
            raise RagProcessingError("Embedding 服务未配置，请配置后重新上传")
        self.dimensions = settings.embedding_dimensions
        self.model_name = settings.embedding_model
        self.batch_size = settings.embedding_batch_size
        self.client = OpenAI(api_key=settings.embedding_api_key.get_secret_value(), base_url=settings.embedding_base_url,
                             timeout=settings.embedding_timeout_seconds, max_retries=1)

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = list(texts)
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(values), self.batch_size):
                batch = values[start:start + self.batch_size]
                response = self.client.embeddings.create(model=self.model_name, input=batch, dimensions=self.dimensions)
                vectors.extend([list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)])
        except Exception as exc:
            raise RagProcessingError("Embedding 服务暂时不可用，请稍后重新上传") from exc
        return validate_embeddings(vectors, len(values), self.dimensions)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def split_document_text(self, text: str) -> list[str]:
        return [text]


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    current = settings or get_settings()
    if current.embedding_provider == "local_sentence_transformers":
        return LocalSentenceTransformerEmbeddingProvider(current)
    if current.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(current)
    raise RagProcessingError("Embedding Provider 配置不受支持")
