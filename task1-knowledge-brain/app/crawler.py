"""Polite, resumable crawl of sitemap pages into SQLite + Chroma."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from .chunker import Chunk, chunk_article, make_chunk_id
from .db import Database
from .parser import parse_article
from .store import VectorStore

log = logging.getLogger(__name__)
USER_AGENT = "ai-tech-consultant-capstone/0.1 (+polite crawler)"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class SitemapEntry:
    url: str
    lastmod: str | None


@dataclass
class CrawlCounts:
    added: int = 0
    updated: int = 0
    removed: int = 0
    failed: int = 0
    unchanged: int = 0
    captioned: int = 0
    errors: list[str] = field(default_factory=list)


class RateLimiter:
    """Guarantees at least `gap` seconds between request starts across all workers."""

    def __init__(self, gap: float) -> None:
        self._gap = gap
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self._gap


def is_article_url(url: str) -> bool:
    return "/solutions/articles/" in url


def parse_sitemap(xml_text: str) -> list[SitemapEntry]:
    root = ET.fromstring(xml_text)
    entries: list[SitemapEntry] = []
    for node in root.iter(f"{SITEMAP_NS}url"):
        loc = node.findtext(f"{SITEMAP_NS}loc")
        if loc:
            entries.append(SitemapEntry(url=loc.strip(), lastmod=node.findtext(f"{SITEMAP_NS}lastmod")))
    return entries


async def fetch_text(client: httpx.AsyncClient, url: str, limiter: RateLimiter, tries: int = 3) -> str:
    """GET with retry + exponential backoff on network errors, 429 and 5xx."""
    for attempt in range(tries):
        await limiter.wait()
        try:
            resp = await client.get(url)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                raise  # not retryable (404 etc.)
            if attempt == tries - 1:
                raise
        except httpx.HTTPError:
            if attempt == tries - 1:
                raise
        await asyncio.sleep(2**attempt)
    raise RuntimeError("unreachable")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def image_chunk(article_url: str, title: str, image_url: str, caption: str) -> Chunk:
    return Chunk(
        id=make_chunk_id(article_url, f"image:{image_url}", 0),
        text=f"Screenshot ({image_url.rsplit('/', 1)[-1]}): {caption}",
        title=title,
        url=article_url,
        section="Screenshot",
        kind="image",
    )


async def sync_sitemap(
    db: Database, store: VectorStore, client: httpx.AsyncClient, sitemap_url: str, limiter: RateLimiter
) -> int:
    """Insert new urls, flag changed lastmod as pending, mark removed urls inactive. Returns removed count."""
    entries = parse_sitemap(await fetch_text(client, sitemap_url, limiter))
    known = await db.all_page_urls()
    seen: set[str] = set()
    for e in entries:
        seen.add(e.url)
        row = known.get(e.url)
        if not is_article_url(e.url):
            if row is None:
                await db.upsert_page(e.url, e.lastmod, "skipped")
            continue
        if row is None:
            await db.upsert_page(e.url, e.lastmod, "pending")
        elif row["status"] in ("done", "inactive") and (row["lastmod"] != e.lastmod or row["status"] == "inactive"):
            await db.upsert_page(e.url, e.lastmod, "pending")  # re-check; hash decides if re-embed
    removed = 0
    for url, row in known.items():
        if url not in seen and row["status"] not in ("inactive", "skipped"):
            await db.set_page_status(url, "inactive")
            await asyncio.to_thread(store.delete_by_url, url)
            removed += 1
    await db.commit()
    return removed


async def process_page(
    url: str, db: Database, store: VectorStore, client: httpx.AsyncClient, limiter: RateLimiter
) -> str:
    """Fetch, parse, chunk, embed one page. Returns added | updated | unchanged."""
    html = await fetch_text(client, url, limiter)
    article = parse_article(html, url)
    new_hash = content_hash(article.title + "\n" + article.body_text)
    row = await db.get_page(url)
    old_hash = row["content_hash"] if row else None
    if old_hash == new_hash:
        await db.mark_page_done(url, new_hash, article.title)
        return "unchanged"

    chunks = chunk_article(article, url)
    # Keep captions already paid for when an article changes.
    for img in await db.images_for_article(url):
        if img["status"] == "done" and img["caption"] and img["url"] in article.image_urls:
            chunks.append(image_chunk(url, article.title, img["url"], img["caption"]))

    def write() -> None:
        store.delete_by_url(url)
        store.upsert(chunks)

    await asyncio.to_thread(write)
    await db.add_images(url, [u for u in article.image_urls if u.startswith("http") and not u.lower().endswith(".svg")])
    await db.mark_page_done(url, new_hash, article.title)
    return "added" if old_hash is None else "updated"


async def crawl_pending(
    db: Database,
    store: VectorStore,
    client: httpx.AsyncClient,
    limiter: RateLimiter,
    *,
    max_pages: int,
    concurrency: int,
    max_attempts: int,
    counts: CrawlCounts,
) -> None:
    done = await db.count_pages("done")
    budget = max(0, max_pages - done)
    todo = await db.pending_pages(budget, max_attempts)
    log.info("crawl: %d done, %d pending within budget of %d", done, len(todo), max_pages)
    sem = asyncio.Semaphore(concurrency)

    async def worker(url: str) -> None:
        async with sem:
            try:
                result = await process_page(url, db, store, client, limiter)
                setattr(counts, result, getattr(counts, result) + 1)
            except Exception as e:  # noqa: BLE001 - record and move on, retried next run
                log.warning("failed %s: %s", url, e)
                await db.set_page_status(url, "failed", bump_attempts=True)
                counts.failed += 1
                counts.errors.append(f"{url}: {e}")
            await db.commit()

    await asyncio.gather(*(worker(r["url"]) for r in todo))
