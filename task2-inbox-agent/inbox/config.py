"""Settings from the repo-root .env (or environment)."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

TASK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TASK_DIR.parent
load_dotenv(REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: str | None = None
    task1_url: str = "http://localhost:8001"
    classify_model: str = "claude-haiku-4-5"
    draft_model: str = "claude-sonnet-4-5"
    prompt_version: str = "v1"
    auto_send_threshold: int = 20
    task2_db: Path = TASK_DIR / "data" / "inbox.sqlite"
    emails_file: Path = TASK_DIR / "data" / "emails.json"

    @property
    def prompts_dir(self) -> Path:
        return REPO_ROOT / "prompts" / self.prompt_version


def get_settings() -> Settings:
    return Settings()
