"""Prompt-file driven Claude calls with pydantic validation and usage tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .claude_client import make_async_client, request_kwargs, resolve_model
from .models import ParseError, validate_as

T = TypeVar("T", bound=BaseModel)

PRICES: dict[str, tuple[float, float]] = {  # USD per 1M tokens (input, output)
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}


@dataclass
class Usage:
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        pi, po = PRICES.get(self.model, (0.0, 0.0))
        return self.input_tokens / 1e6 * pi + self.output_tokens / 1e6 * po


@dataclass
class LLM:
    prompts_dir: Path
    api_key: str | None = None
    usage: list[Usage] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.client = make_async_client(self.api_key)

    def load_prompt(self, name: str, **values: str) -> str:
        text = (self.prompts_dir / f"{name}.md").read_text(encoding="utf-8")
        for k, v in values.items():
            text = text.replace("{" + k + "}", v)
        return text

    async def ask_text(self, model: str, prompt: str, max_tokens: int) -> str:
        msg = await self.client.messages.create(
            model=resolve_model(model), max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}], **request_kwargs(),
        )
        self.usage.append(Usage(model, msg.usage.input_tokens, msg.usage.output_tokens))
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    async def ask_json(self, model: str, prompt_name: str, schema: type[T], max_tokens: int = 4000, **values: str) -> T:
        prompt = self.load_prompt(prompt_name, **values)
        try:
            return validate_as(schema, await self.ask_text(model, prompt, max_tokens))
        except ParseError as e:
            retry = prompt + f"\n\nYour previous output was invalid ({e}). Return only a valid JSON object."
            return validate_as(schema, await self.ask_text(model, retry, max_tokens))

    def total_cost(self) -> float:
        return sum(u.cost_usd for u in self.usage)

    def reset_usage(self) -> None:
        self.usage.clear()
