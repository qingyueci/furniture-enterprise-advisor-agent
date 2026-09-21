import math

import pytest

from app.core.config import Settings
from app.rag.chunker import split_chunks_for_embedding
from app.rag.embeddings import (
    QUERY_PREFIX,
    LocalSentenceTransformerEmbeddingProvider,
    _clear_model_cache_for_tests,
    create_embedding_provider,
)
from app.rag.types import ChunkDraft, EmbeddingInputError, RagProcessingError


class MockModel:
    def __init__(self, *, dimensions: int = 512, max_seq_length: int = 32):
        self.dimensions = dimensions
        self.max_seq_length = max_seq_length
        self.encoded: list[list[str]] = []
        self.tokenizer = self._tokenize

    @staticmethod
    def _tokenize(text: str, **_kwargs):
        return {"input_ids": list(range(len(text) + 2))}

    def get_sentence_embedding_dimension(self):
        return self.dimensions

    def encode(self, texts, **kwargs):
        assert kwargs["normalize_embeddings"] is True
        assert kwargs["batch_size"] == 16
        self.encoded.append(list(texts))
        value = 1.0 / math.sqrt(self.dimensions)
        return [[value] * self.dimensions for _ in texts]


def _settings(model_dir, **overrides):
    values = {
        "database_url": "postgresql+psycopg://local/test",
        "jwt_secret": "x" * 32,
        "embedding_provider": "local_sentence_transformers",
        "embedding_model": str(model_dir),
        "embedding_model_revision": None,
        "embedding_dimensions": 512,
        "embedding_device": "cpu",
        "embedding_batch_size": 16,
        "embedding_cache_dir": model_dir / "cache",
        "embedding_local_files_only": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_local_provider_document_query_prefix_cache_and_token_split(tmp_path):
    _clear_model_cache_for_tests()
    model = MockModel(max_seq_length=32)
    loads = []

    def loader(source, device, cache_dir):
        loads.append((source, device, cache_dir))
        return model

    settings = _settings(tmp_path)
    first = LocalSentenceTransformerEmbeddingProvider(settings, model_loader=loader)
    second = LocalSentenceTransformerEmbeddingProvider(settings, model_loader=loader)
    assert len(loads) == 1
    assert first.revision == "local-unversioned"
    assert len(first.embed_documents(["文档正文"])[0]) == 512
    assert model.encoded[-1] == ["文档正文"]
    assert len(second.embed_query("参数")) == 512
    assert model.encoded[-1] == [f"{QUERY_PREFIX}参数"]

    source = "甲" * 70
    pieces = first.split_document_text(source)
    assert len(pieces) > 1 and "".join(pieces) == source
    draft = ChunkDraft(9, source, 3, 3, "章节", 7, 7, "old")
    split = split_chunks_for_embedding([draft], first.split_document_text)
    assert [item.chunk_index for item in split] == list(range(len(split)))
    assert all((item.page_start, item.section_title, item.row_start) == (3, "章节", 7) for item in split)
    assert "".join(item.chunk_text for item in split) == source


def test_query_over_limit_is_parameter_error_and_load_failure_does_not_fallback(tmp_path):
    _clear_model_cache_for_tests()
    provider = LocalSentenceTransformerEmbeddingProvider(
        _settings(tmp_path), model_loader=lambda *_args: MockModel(max_seq_length=24),
    )
    with pytest.raises(EmbeddingInputError, match="Token"):
        provider.embed_query("超" * 100)

    _clear_model_cache_for_tests()
    with pytest.raises(RagProcessingError, match="下载或加载失败"):
        LocalSentenceTransformerEmbeddingProvider(
            _settings(tmp_path), model_loader=lambda *_args: (_ for _ in ()).throw(RuntimeError("secret path")),
        )


def test_provider_selection_and_dimension_configuration(tmp_path, monkeypatch):
    sentinel = object()
    monkeypatch.setattr(
        "app.rag.embeddings.LocalSentenceTransformerEmbeddingProvider", lambda _settings: sentinel,
    )
    assert create_embedding_provider(_settings(tmp_path)) is sentinel
    with pytest.raises(ValueError, match=r"vector\(512\)"):
        _settings(tmp_path, embedding_dimensions=1536)
    with pytest.raises(ValueError, match="CPU"):
        _settings(tmp_path, embedding_device="cuda")


@pytest.mark.local_embedding
def test_real_local_embedding_shape_norm_and_prefix():
    provider = LocalSentenceTransformerEmbeddingProvider(Settings())
    document = provider.embed_documents(["X100 支持 65W 供电"])[0]
    query = provider.embed_query("X100 支持多少瓦供电？")
    assert len(document) == len(query) == 512
    assert math.isfinite(sum(document)) and math.isfinite(sum(query))
    assert math.isclose(math.sqrt(sum(value * value for value in document)), 1.0, rel_tol=1e-4)
    assert math.isclose(math.sqrt(sum(value * value for value in query)), 1.0, rel_tol=1e-4)
