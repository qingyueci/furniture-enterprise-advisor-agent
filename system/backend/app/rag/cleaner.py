from collections import Counter
from dataclasses import replace
import re

from app.rag.types import ParsedBlock

INVISIBLE_SPACES = re.compile(r"[\u00a0\u2000-\u200b\u202f\u205f\u3000\ufeff]")
HORIZONTAL_SPACE = re.compile(r"[ \t]+")
BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")


def clean_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = INVISIBLE_SPACES.sub(" ", text)
    text = "\n".join(HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.split("\n"))
    return BLANK_LINES.sub("\n\n", text).strip()


def _repeated_pdf_edges(blocks: list[ParsedBlock]) -> tuple[set[str], set[str]]:
    pages = [block for block in blocks if block.page_start is not None]
    if len(pages) < 3:
        return set(), set()
    firsts: Counter[str] = Counter()
    lasts: Counter[str] = Counter()
    for block in pages:
        lines = [line.strip() for line in block.text.splitlines() if line.strip()]
        if lines:
            firsts[lines[0]] += 1
            lasts[lines[-1]] += 1
    threshold = max(3, int(len(pages) * 0.6 + 0.999))
    return {text for text, count in firsts.items() if count >= threshold}, {
        text for text, count in lasts.items() if count >= threshold}


def clean_blocks(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
    headers, footers = _repeated_pdf_edges(blocks)
    result: list[ParsedBlock] = []
    for block in blocks:
        lines = block.text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        if block.page_start is not None:
            while lines and lines[0].strip() in headers:
                lines.pop(0)
            while lines and lines[-1].strip() in footers:
                lines.pop()
        text = clean_text("\n".join(lines))
        if text:
            result.append(replace(block, text=text))
    return result
