"""Wires settings -> db, vector store, LLM. Tests build this with fakes."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Settings, get_settings
from .db import Database
from .llm import LLM, ClaudeLLM
from .store import SentenceTransformerEmbedder, VectorStore


@dataclass
class Services:
    settings: Settings
    db: Database
    store: VectorStore
    llm: LLM


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or get_settings()
    db = Database(settings.db_path)
    store = VectorStore(settings.chroma_path, SentenceTransformerEmbedder(settings.embedding_model))
    llm = ClaudeLLM(
        settings.prompts_dir, settings.answer_model, settings.caption_model, settings.anthropic_api_key
    )
    return Services(settings=settings, db=db, store=store, llm=llm)
