"""Split a long transcript into ~N-word chunks with overlap."""
from __future__ import annotations


def chunk_words(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("need size > 0 and 0 <= overlap < size")
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)] if words else []
    chunks: list[str] = []
    step = size - overlap
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step
    return chunks
