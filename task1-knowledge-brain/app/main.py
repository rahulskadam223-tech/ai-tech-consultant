"""FastAPI app: /query, /escalations, /ingest/refresh, /health."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

import anthropic
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .chunker import Chunk, make_chunk_id
from .claude_client import provider_name
from .ingest import run_refresh
from .services import Services, build_services


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)


class Source(BaseModel):
    title: str
    url: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_evidence"]
    sources: list[Source]
    needs_human: bool


class EscalationRequest(BaseModel):
    question: str = Field(min_length=1)


class ResolveRequest(BaseModel):
    answer: str = Field(min_length=1)


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = services or build_services()
        await svc.db.connect()
        app.state.svc = svc
        try:
            yield
        finally:
            await svc.db.close()

    app = FastAPI(title="AI Tech Consultant - Knowledge Brain", lifespan=lifespan)

    def svc_of(request: Request) -> Services:
        return request.app.state.svc

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        svc = svc_of(request)
        return {
            "status": "ok",
            "pages_done": await svc.db.count_pages("done"),
            "pages_pending": await svc.db.count_pages("pending"),
            "chunks": svc.store.count(),
            "provider": provider_name(),
            "answer_model": svc.settings.answer_model,
            "caption_model": svc.settings.caption_model,
        }

    @app.post("/query", response_model=QueryResponse)
    async def query(req: QueryRequest, request: Request) -> QueryResponse:
        svc = svc_of(request)
        hits = await asyncio.to_thread(svc.store.search, req.question, svc.settings.top_k)
        relevant = [h for h in hits if h.score >= svc.settings.score_threshold]
        best: dict[str, Source] = {}
        for h in relevant:
            if h.url not in best:
                best[h.url] = Source(title=h.title, url=h.url, score=h.score)
        sources = list(best.values())
        if not relevant:
            return QueryResponse(
                answer="I couldn't find this in the documentation. Escalating to a human expert.",
                status="insufficient_evidence",
                sources=sources,
                needs_human=True,
            )
        try:
            answer = await svc.llm.answer(req.question, relevant)
        except anthropic.AuthenticationError as e:
            raise HTTPException(502, f"Anthropic auth failed, check ANTHROPIC_API_KEY in .env: {e.message}")
        except anthropic.APIError as e:
            raise HTTPException(502, f"Anthropic API error: {e.message}")
        except TypeError as e:  # SDK raises this when no credentials are configured at all
            raise HTTPException(502, f"No Anthropic credentials, set ANTHROPIC_API_KEY in .env: {e}")
        if answer is None:
            return QueryResponse(
                answer="The documentation I found doesn't answer this. Escalating to a human expert.",
                status="insufficient_evidence",
                sources=sources,
                needs_human=True,
            )
        return QueryResponse(answer=answer, status="answered", sources=sources, needs_human=False)

    @app.post("/escalations", status_code=201)
    async def create_escalation(req: EscalationRequest, request: Request) -> dict[str, object]:
        esc_id = await svc_of(request).db.create_escalation(req.question)
        return {"id": esc_id, "question": req.question, "status": "open"}

    @app.post("/escalations/{esc_id}/resolve")
    async def resolve_escalation(esc_id: int, req: ResolveRequest, request: Request) -> dict[str, object]:
        svc = svc_of(request)
        esc = await svc.db.get_escalation(esc_id)
        if esc is None:
            raise HTTPException(404, "escalation not found")
        chunk = Chunk(
            id=make_chunk_id(f"escalation://{esc_id}", "Expert answer", 0),
            text=f"Question: {esc['question']}\nExpert answer: {req.answer}",
            title=f"Expert answer: {esc['question'][:80]}",
            url=f"escalation://{esc_id}",
            section="Expert answer",
            kind="escalation",
        )
        await asyncio.to_thread(svc.store.upsert, [chunk])
        await svc.db.resolve_escalation(esc_id, req.answer)
        return {"id": esc_id, "status": "resolved", "chunk_id": chunk.id}

    @app.post("/ingest/refresh")
    async def ingest_refresh(request: Request) -> dict[str, object]:
        counts = await run_refresh(svc_of(request))
        return {
            "added": counts.added,
            "updated": counts.updated,
            "removed": counts.removed,
            "failed": counts.failed,
            "unchanged": counts.unchanged,
            "captioned": counts.captioned,
            "errors": counts.errors[:20],
        }

    return app


app = create_app()
