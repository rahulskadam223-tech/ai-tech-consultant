"""Claude calls: classify (Haiku) and draft (Sonnet), each validated with pydantic."""
from __future__ import annotations

import json
from pathlib import Path

from anthropic.types import Message

from .claude_client import make_async_client, request_kwargs, resolve_model

from .models import Classification, Draft, Email, KBResult, ParseError, validate_classification, validate_draft


def load_prompt(prompts_dir: Path, name: str, **values: str) -> str:
    text = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def text_of(msg: Message) -> str:
    return "".join(b.text for b in msg.content if b.type == "text").strip()


class Claude:
    def __init__(self, prompts_dir: Path, classify_model: str, draft_model: str, api_key: str | None = None) -> None:
        self.prompts_dir = prompts_dir
        self.classify_model = classify_model
        self.draft_model = draft_model
        self.client = make_async_client(api_key)
        self.last_usage: tuple[int, int] = (0, 0)  # input, output tokens of the last call

    async def _ask(self, model: str, prompt: str, max_tokens: int, retry_note: str | None = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        if retry_note:
            messages[0]["content"] = prompt + f"\n\nYour previous output was invalid: {retry_note}. Return only valid JSON."
        msg = await self.client.messages.create(
            model=resolve_model(model), max_tokens=max_tokens, messages=messages, **request_kwargs()
        )
        self.last_usage = (msg.usage.input_tokens, msg.usage.output_tokens)
        return text_of(msg)

    async def classify(self, email: Email, model: str | None = None) -> Classification:
        prompt = load_prompt(self.prompts_dir, "classify", **{"from": email.from_, "subject": email.subject, "body": email.body})
        model = model or self.classify_model
        try:
            return validate_classification(await self._ask(model, prompt, 400))
        except ParseError as e:
            return validate_classification(await self._ask(model, prompt, 400, retry_note=str(e)[:200]))

    async def draft(self, email: Email, cls: Classification, kb: KBResult | None) -> Draft:
        kb_text = kb.model_dump_json(indent=1) if kb else "none (not a product question)"
        prompt = load_prompt(
            self.prompts_dir, "draft",
            **{"from": email.from_, "subject": email.subject, "body": email.body,
               "classification": json.dumps(cls.model_dump()), "kb_result": kb_text},
        )
        try:
            return validate_draft(await self._ask(self.draft_model, prompt, 1200))
        except ParseError as e:
            return validate_draft(await self._ask(self.draft_model, prompt, 1200, retry_note=str(e)[:200]))
