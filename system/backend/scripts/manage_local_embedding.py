import argparse
import json
from pathlib import Path

from app.core.config import get_settings


def _download() -> dict:
    from huggingface_hub import snapshot_download

    settings = get_settings()
    configured = Path(settings.embedding_model).expanduser()
    if configured.is_dir():
        snapshot = configured.resolve()
    else:
        snapshot = Path(snapshot_download(
            repo_id=settings.embedding_model,
            revision=settings.embedding_model_revision,
            cache_dir=str(Path(settings.embedding_cache_dir).resolve()),
            local_files_only=False,
        )).resolve()
    return {"model": settings.embedding_model, "revision": snapshot.name, "cache_ready": True}


def _check() -> dict:
    from app.rag.embeddings import LocalSentenceTransformerEmbeddingProvider

    provider = LocalSentenceTransformerEmbeddingProvider(get_settings())
    document_vector = provider.embed_documents(["X100 产品文档编码检查"])[0]
    query_vector = provider.embed_query("X100 的核心参数是什么？")
    return {
        "provider": provider.provider_name,
        "model": provider.model_name,
        "revision": provider.revision,
        "device": provider.device,
        "dimensions": len(document_vector),
        "query_dimensions": len(query_vector),
        "max_seq_length": provider.max_seq_length,
        "local_files_only": provider.local_files_only,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="下载或检查本地 sentence-transformers Embedding")
    parser.add_argument("action", choices=("download", "check"))
    args = parser.parse_args()
    result = _download() if args.action == "download" else _check()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
