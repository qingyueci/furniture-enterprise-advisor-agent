import hashlib
from collections.abc import Callable

from app.rag.types import ChunkDraft, ParsedBlock, RagProcessingError

TARGET_CHARS = 650
MAX_CHARS = 800
OVERLAP_CHARS = 100
BOUNDARIES = "\n。！？；.!?;"


def _split_text(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    result: list[str] = []
    start = 0
    while start < len(text):
        limit = min(start + MAX_CHARS, len(text))
        if limit == len(text):
            cut = limit
        else:
            window_start = min(start + TARGET_CHARS, limit)
            positions = [text.rfind(mark, window_start, limit) for mark in BOUNDARIES]
            boundary = max(positions)
            cut = boundary + 1 if boundary >= window_start else limit
        piece = text[start:cut]
        if piece:
            result.append(piece)
        if cut >= len(text):
            break
        start = max(start + 1, cut - OVERLAP_CHARS)
    return result


def build_chunks(blocks: list[ParsedBlock]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    pending: ParsedBlock | None = None

    def emit(block: ParsedBlock) -> None:
        for piece in _split_text(block.text):
            if not piece:
                continue
            drafts.append(ChunkDraft(
                chunk_index=len(drafts), chunk_text=piece,
                page_start=block.page_start, page_end=block.page_end,
                section_title=block.section_title, row_start=block.row_start, row_end=block.row_end,
                content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
            ))

    for block in blocks:
        if not block.text:
            continue
        if pending is None:
            pending = block
            continue
        same_group = (pending.section_title == block.section_title and pending.page_start == block.page_start
                      and pending.page_end == block.page_end)
        combined = f"{pending.text}\n{block.text}"
        if same_group and len(combined) <= MAX_CHARS:
            pending = ParsedBlock(combined, pending.page_start, block.page_end, pending.section_title,
                                  pending.row_start, block.row_end, {"combined": True})
        else:
            emit(pending)
            pending = block
    if pending is not None:
        emit(pending)
    if not drafts:
        raise RagProcessingError("文档没有可写入的文本块")
    return drafts


def split_chunks_for_embedding(
    chunks: list[ChunkDraft], split_text: Callable[[str], list[str]],
) -> list[ChunkDraft]:
    """Split overlong chunks with the model tokenizer while preserving source location and order."""
    result: list[ChunkDraft] = []
    for chunk in chunks:
        pieces = split_text(chunk.chunk_text)
        if not pieces or any(not piece for piece in pieces) or "".join(pieces) != chunk.chunk_text:
            raise RagProcessingError("模型 Token 拆分未完整保留文档正文")
        for piece in pieces:
            result.append(ChunkDraft(
                chunk_index=len(result), chunk_text=piece,
                page_start=chunk.page_start, page_end=chunk.page_end,
                section_title=chunk.section_title, row_start=chunk.row_start, row_end=chunk.row_end,
                content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
            ))
    return result
