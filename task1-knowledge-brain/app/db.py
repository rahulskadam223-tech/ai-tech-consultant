"""SQLite tracking for pages, images and escalations (aiosqlite)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    lastmod TEXT,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed | inactive | skipped
    attempts INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS images (
    url TEXT PRIMARY KEY,
    article_url TEXT NOT NULL,
    caption TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- open | resolved
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() not called"
        return self._conn

    async def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ---- pages -------------------------------------------------------------
    async def get_page(self, url: str) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM pages WHERE url = ?", (url,))

    async def all_page_urls(self) -> dict[str, dict[str, Any]]:
        return {r["url"]: r for r in await self._rows("SELECT * FROM pages")}

    async def upsert_page(self, url: str, lastmod: str | None, status: str) -> None:
        await self.conn.execute(
            "INSERT INTO pages (url, lastmod, status, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET lastmod = excluded.lastmod, status = excluded.status, "
            "updated_at = excluded.updated_at",
            (url, lastmod, status, now_iso()),
        )

    async def set_page_status(self, url: str, status: str, *, bump_attempts: bool = False) -> None:
        await self.conn.execute(
            "UPDATE pages SET status = ?, attempts = attempts + ?, updated_at = ? WHERE url = ?",
            (status, 1 if bump_attempts else 0, now_iso(), url),
        )

    async def mark_page_done(self, url: str, content_hash: str, title: str) -> None:
        await self.conn.execute(
            "UPDATE pages SET status = 'done', content_hash = ?, title = ?, attempts = attempts + 1, "
            "updated_at = ? WHERE url = ?",
            (content_hash, title, now_iso(), url),
        )

    async def pending_pages(self, limit: int, max_attempts: int) -> list[dict[str, Any]]:
        return await self._rows(
            "SELECT * FROM pages WHERE status IN ('pending', 'failed') AND attempts < ? "
            "ORDER BY rowid LIMIT ?",
            (max_attempts, limit),
        )

    async def count_pages(self, status: str) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM pages WHERE status = ?", (status,))
        return int(row["n"]) if row else 0

    # ---- images ------------------------------------------------------------
    async def add_images(self, article_url: str, urls: list[str]) -> None:
        for u in urls:
            await self.conn.execute(
                "INSERT OR IGNORE INTO images (url, article_url) VALUES (?, ?)", (u, article_url)
            )

    async def images_for_article(self, article_url: str) -> list[dict[str, Any]]:
        return await self._rows("SELECT * FROM images WHERE article_url = ?", (article_url,))

    async def pending_images(self, limit: int, max_attempts: int) -> list[dict[str, Any]]:
        return await self._rows(
            "SELECT i.*, p.title AS article_title FROM images i JOIN pages p ON p.url = i.article_url "
            "WHERE i.status IN ('pending', 'failed') AND i.attempts < ? AND p.status = 'done' ORDER BY i.rowid LIMIT ?",
            (max_attempts, limit),
        )

    async def count_images(self, status: str) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM images WHERE status = ?", (status,))
        return int(row["n"]) if row else 0

    async def set_image_result(self, url: str, status: str, caption: str | None) -> None:
        await self.conn.execute(
            "UPDATE images SET status = ?, caption = ?, attempts = attempts + 1 WHERE url = ?",
            (status, caption, url),
        )

    # ---- escalations -------------------------------------------------------
    async def create_escalation(self, question: str) -> int:
        cur = await self.conn.execute(
            "INSERT INTO escalations (question, created_at) VALUES (?, ?)", (question, now_iso())
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def get_escalation(self, esc_id: int) -> dict[str, Any] | None:
        return await self._one("SELECT * FROM escalations WHERE id = ?", (esc_id,))

    async def resolve_escalation(self, esc_id: int, answer: str) -> None:
        await self.conn.execute(
            "UPDATE escalations SET answer = ?, status = 'resolved', resolved_at = ? WHERE id = ?",
            (answer, now_iso(), esc_id),
        )
        await self.conn.commit()

    async def commit(self) -> None:
        await self.conn.commit()
