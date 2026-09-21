from dataclasses import replace
from html import escape

from app.rag.types import Citation, ContextResult, KnowledgeSearchItem


def _location(item: KnowledgeSearchItem) -> list[str]:
    lines = [f"文件：{item.document_name}"]
    if item.page_start is not None:
        page = f"第{item.page_start}页" if item.page_end in (None, item.page_start) else f"第{item.page_start}–{item.page_end}页"
        lines.append(f"页码：{page}")
    if item.section_title:
        lines.append(f"章节：{item.section_title}")
    if item.row_start is not None:
        row = str(item.row_start) if item.row_end in (None, item.row_start) else f"{item.row_start}–{item.row_end}"
        lines.append(f"行号：{row}")
    return lines


class ContextBuilder:
    def __init__(self, max_chars: int = 8000, max_chunks: int = 8):
        self.max_chars = max_chars
        self.max_chunks = max_chunks

    def build(self, items: list[KnowledgeSearchItem]) -> ContextResult:
        sections: list[str] = []
        kept: list[KnowledgeSearchItem] = []
        citations: list[Citation] = []
        used = 0
        for item in items[:self.max_chunks]:
            citation_id = len(kept) + 1
            body = escape(item.chunk_text, quote=False)
            header = "\n".join([f"[来源 {citation_id}]", *_location(item)])
            available = self.max_chars - used - len(header) - len("\n<enterprise_document>\n\n</enterprise_document>\n")
            if available <= 0:
                break
            body = body[:available]
            if not body:
                break
            section = f"{header}\n<enterprise_document>\n{body}\n</enterprise_document>"
            citation = replace(item.citation, citation_id=citation_id, quote=item.chunk_text[:240])
            kept.append(replace(item, citation=citation))
            citations.append(citation)
            sections.append(section)
            used += len(section) + (2 if sections else 0)
        return ContextResult(context="\n\n".join(sections), citations=citations, items=kept)
