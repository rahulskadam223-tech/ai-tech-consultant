"""Embeddings (sentence-transformers) and the Chroma vector store."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import chromadb

from .chunker import Chunk


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Lazy-loads the model on first use; encodes under a lock (not thread-safe otherwise)."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [v.tolist() for v in vectors]


@dataclass
class Hit:
    text: str
    title: str
    url: str
    section: str
    kind: str
    score: float  # cosine similarity, higher is better


class VectorStore:
    def __init__(self, path: Path, embedder: Embedder) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self._client = chromadb.PersistentClient(
            path=str(path), settings=chromadb.Settings(anonymized_telemetry=False)
        )
        self._coll = self._client.get_or_create_collection(
            "chunks", metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self._coll.count()

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = self.embedder.embed([c.embed_text for c in chunks])
        self._coll.upsert(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )

    def delete_by_url(self, url: str) -> None:
        self._coll.delete(where={"url": url})

    def search(self, query: str, k: int) -> list[Hit]:
        n = min(k, self.count())
        if n == 0:
            return []
        qv = self.embedder.embed([query])[0]
        res = self._coll.query(
            query_embeddings=[qv], n_results=n, include=["documents", "metadatas", "distances"]
        )
        hits: list[Hit] = []
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            hits.append(
                Hit(
                    text=doc,
                    title=str(meta.get("title", "")),
                    url=str(meta.get("url", "")),
                    section=str(meta.get("section", "")),
                    kind=str(meta.get("kind", "text")),
                    score=round(1.0 - float(dist), 4),
                )
            )
        return hits
