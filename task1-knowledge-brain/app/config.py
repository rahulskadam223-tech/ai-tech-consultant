"""Settings loaded from the repo-root .env (or the environment)."""
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
    answer_model: str = "claude-sonnet-4-5"
    caption_model: str = "claude-haiku-4-5"

    sitemap_url: str = "https://support.brilliantdirectories.com/support/sitemap.xml"
    max_pages: int = 150
    max_images: int = 40
    crawl_concurrency: int = 3
    crawl_delay_seconds: float = 0.5
    max_attempts: int = 3
    score_threshold: float = 0.35
    top_k: int = 6
    embedding_model: str = "all-MiniLM-L6-v2"
    data_dir: Path = TASK_DIR / "data"
    prompts_dir: Path = REPO_ROOT / "prompts" / "v1"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pages.sqlite"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"


def get_settings() -> Settings:
    s = Settings()
    s.data_dir = (TASK_DIR / s.data_dir).resolve() if not s.data_dir.is_absolute() else s.data_dir
    s.prompts_dir = (TASK_DIR / s.prompts_dir).resolve() if not s.prompts_dir.is_absolute() else s.prompts_dir
    return s
