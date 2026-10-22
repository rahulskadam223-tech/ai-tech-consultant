"""Load prompt templates from prompts/<version>/*.md at runtime."""
from __future__ import annotations

from pathlib import Path


def load_prompt(prompts_dir: Path, name: str, **values: str) -> str:
    text = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text
