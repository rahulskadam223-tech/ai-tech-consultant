"""Split a parsed article into chunks at headings, carrying title/url/section."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .parser import ParsedArticle

MAX_CHUNK_CHARS = 1500


@dataclass
class Chunk:
    id: str
    text: str
    title: str
    url: str
    section: str
    kind: str = "text"  # text | image | escalation

    @property
    def embed_text(self) -> str:
        return f"{self.title}\n{self.section}\n{self.text}"

    @property
    def metadata(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "section": self.section, "kind": self.kind}


def make_chunk_id(url: str, section: str, index: int) -> str:
    return hashlib.sha1(f"{url}|{section}|{index}".encode()).hexdigest()


def _split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for para in text.split("\n"):
        if current and len(current) + len(para) + 1 > limit:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current:
        parts.append(current)
    return parts


def chunk_article(article: ParsedArticle, url: str, limit: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    position = 0  # running index: headings can repeat within one article
    for section in article.sections:
        for piece in _split_long(section.text, limit):
            chunks.append(
                Chunk(
                    id=make_chunk_id(url, section.heading, position),
                    text=piece,
                    title=article.title,
                    url=url,
                    section=section.heading,
                )
            )
            position += 1
    return chunks
