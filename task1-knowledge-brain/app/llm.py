"""Claude calls: image captions (Haiku) and grounded answers (Sonnet)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import asyncio
import base64

import httpx

from .claude_client import make_async_client, request_kwargs, resolve_model
from .prompts import load_prompt
from .store import Hit

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


def sniff_image_type(data: bytes) -> str | None:
    """Detect the media type from magic bytes; CDN content-type headers are often wrong."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class LLM(Protocol):
    async def caption(self, image_url: str, article_title: str) -> str: ...
    async def answer(self, question: str, hits: list[Hit]) -> str | None: ...


def format_context(hits: list[Hit]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[{i}] Title: {h.title}\nSection: {h.section}\nURL: {h.url}\n{h.text}")
    return "\n\n".join(parts)


class ClaudeLLM:
    def __init__(
        self, prompts_dir: Path, answer_model: str, caption_model: str, api_key: str | None = None
    ) -> None:
        self.prompts_dir = prompts_dir
        self.answer_model = answer_model
        self.caption_model = caption_model
        self.client = make_async_client(api_key)

    async def _fetch_image(self, image_url: str) -> tuple[str, str]:
        """Download the image and return (media_type, base64). Bedrock does not accept URL sources."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ai-tech-consultant-capstone/0.1)"}
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as http:
            for attempt in range(3):
                try:
                    r = await http.get(image_url)
                    r.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
        media_type = sniff_image_type(r.content) or r.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type not in IMAGE_TYPES:
            raise ValueError(f"unsupported image type {media_type!r} for {image_url}")
        return media_type, base64.standard_b64encode(r.content).decode("ascii")

    async def caption(self, image_url: str, article_title: str) -> str:
        prompt = load_prompt(self.prompts_dir, "image_caption", title=article_title)
        media_type, data = await self._fetch_image(image_url)
        resp = await self.client.messages.create(
            model=resolve_model(self.caption_model),
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            **request_kwargs(),
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def answer(self, question: str, hits: list[Hit]) -> str | None:
        prompt = load_prompt(
            self.prompts_dir, "answer", context=format_context(hits), question=question
        )
        resp = await self.client.messages.create(
            model=resolve_model(self.answer_model),
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            **request_kwargs(),
        )
        self.last_usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text or INSUFFICIENT in text:
            return None
        return text
