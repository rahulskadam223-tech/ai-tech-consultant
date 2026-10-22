"""POST /query must abstain (insufficient_evidence, needs_human) instead of guessing."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.chunker import Chunk
from app.config import Settings
from app.db import Database
from app.main import create_app
from app.services import Services
from app.store import Hit, VectorStore

DIM = 8


class FakeEmbedder:
    """'cats' -> axis 0, anything else -> axis 1, so unrelated texts score ~0."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * DIM
            v[0 if "cats" in t.lower() else 1] = 1.0
            out.append(v)
        return out


class FakeLLM:
    def __init__(self, reply: str | None) -> None:
        self.reply = reply
        self.calls = 0

    async def caption(self, image_url: str, article_title: str) -> str:
        return "caption"

    async def answer(self, question: str, hits: list[Hit]) -> str | None:
        self.calls += 1
        return self.reply


def make_client(tmp_path: Path, llm: FakeLLM) -> tuple[TestClient, VectorStore]:
    settings = Settings(data_dir=tmp_path, prompts_dir=tmp_path, score_threshold=0.35, top_k=5)
    store = VectorStore(settings.chroma_path, FakeEmbedder())
    svc = Services(settings=settings, db=Database(settings.db_path), store=store, llm=llm)
    return TestClient(create_app(svc)), store


def test_empty_index_abstains(tmp_path: Path) -> None:
    llm = FakeLLM(reply="should never be used")
    client, _ = make_client(tmp_path, llm)
    with client:
        r = client.post("/query", json={"question": "How do I reset my password?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "insufficient_evidence"
    assert body["needs_human"] is True
    assert body["sources"] == []
    assert llm.calls == 0  # we never asked the model to guess


def test_low_score_hits_abstain(tmp_path: Path) -> None:
    llm = FakeLLM(reply="should never be used")
    client, store = make_client(tmp_path, llm)
    store.upsert([Chunk(id="c1", text="Dogs bark loudly.", title="Dogs", url="u1", section="Intro")])
    with client:
        r = client.post("/query", json={"question": "Tell me about cats"})
    body = r.json()
    assert body["status"] == "insufficient_evidence"
    assert body["needs_human"] is True
    assert llm.calls == 0


def test_model_says_insufficient(tmp_path: Path) -> None:
    llm = FakeLLM(reply=None)  # model answered INSUFFICIENT_EVIDENCE
    client, store = make_client(tmp_path, llm)
    store.upsert([Chunk(id="c1", text="Cats purr.", title="Cats", url="u1", section="Intro")])
    with client:
        r = client.post("/query", json={"question": "Do cats like water?"})
    body = r.json()
    assert body["status"] == "insufficient_evidence"
    assert body["needs_human"] is True
    assert body["sources"][0]["url"] == "u1"
    assert llm.calls == 1


def test_relevant_hit_is_answered(tmp_path: Path) -> None:
    llm = FakeLLM(reply="Cats purr when content. [Cats]")
    client, store = make_client(tmp_path, llm)
    store.upsert([Chunk(id="c1", text="Cats purr.", title="Cats", url="u1", section="Intro")])
    with client:
        r = client.post("/query", json={"question": "Why do cats purr?"})
    body = r.json()
    assert body["status"] == "answered"
    assert body["needs_human"] is False
    assert body["sources"] == [{"title": "Cats", "url": "u1", "score": pytest.approx(1.0)}]
