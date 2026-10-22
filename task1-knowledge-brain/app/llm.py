"""Claude calls: image captions (Haiku) and grounded answers (Sonnet)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from anthropic import AsyncAnthropic

from .prompts import load_prompt
from .store import Hit

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


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
        self.client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()

    async def caption(self, image_url: str, article_title: str) -> str:
        prompt = load_prompt(self.prompts_dir, "image_caption", title=article_title)
        resp = await self.client.messages.create(
            model=self.caption_model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "url", "url": image_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def answer(self, question: str, hits: list[Hit]) -> str | None:
        prompt = load_prompt(
            self.prompts_dir, "answer", context=format_context(hits), question=question
        )
        resp = await self.client.messages.create(
            model=self.answer_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text or INSUFFICIENT in text:
            return None
        return text
