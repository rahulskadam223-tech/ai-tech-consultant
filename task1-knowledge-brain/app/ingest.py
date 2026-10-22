"""Sitemap sync + crawl + image captions. Used by POST /ingest/refresh and `python -m app.ingest`."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .crawler import USER_AGENT, CrawlCounts, RateLimiter, crawl_pending, image_chunk, sync_sitemap
from .services import Services, build_services

log = logging.getLogger(__name__)


async def caption_images(svc: Services, counts: CrawlCounts) -> None:
    s = svc.settings
    budget = max(0, s.max_images - await svc.db.count_images("done"))
    todo = await svc.db.pending_images(budget, s.max_attempts)
    log.info("captions: %d images to describe (budget %d)", len(todo), budget)
    for img in todo:
        try:
            caption = await svc.llm.caption(img["url"], img["article_title"] or "")
            chunk = image_chunk(img["article_url"], img["article_title"] or "", img["url"], caption)
            await asyncio.to_thread(svc.store.upsert, [chunk])
            await svc.db.set_image_result(img["url"], "done", caption)
            counts.captioned += 1
        except Exception as e:  # noqa: BLE001
            log.warning("caption failed %s: %s", img["url"], e)
            await svc.db.set_image_result(img["url"], "failed", None)
            counts.errors.append(f"image {img['url']}: {e}")
        await svc.db.commit()


async def run_refresh(svc: Services) -> CrawlCounts:
    s = svc.settings
    counts = CrawlCounts()
    limiter = RateLimiter(s.crawl_delay_seconds)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
    ) as client:
        counts.removed = await sync_sitemap(svc.db, svc.store, client, s.sitemap_url, limiter)
        await crawl_pending(
            svc.db,
            svc.store,
            client,
            limiter,
            max_pages=s.max_pages,
            concurrency=s.crawl_concurrency,
            max_attempts=s.max_attempts,
            counts=counts,
        )
    await caption_images(svc, counts)
    return counts


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    svc = build_services()
    await svc.db.connect()
    try:
        counts = await run_refresh(svc)
    finally:
        await svc.db.close()
    print(
        f"added={counts.added} updated={counts.updated} unchanged={counts.unchanged} "
        f"removed={counts.removed} failed={counts.failed} captioned={counts.captioned} "
        f"chunks={svc.store.count()}"
    )
    for err in counts.errors[:10]:
        print("  !", err)


if __name__ == "__main__":
    asyncio.run(_main())
