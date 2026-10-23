"""Agent 1: transcript -> requirements, decisions, open questions, constraints."""
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, Field

from scope.chunking import chunk_words
from scope.llm import LLM
from scope.models import Analysis, ChunkExtraction, Requirement


class AnalystInput(BaseModel):
    transcript: str
    baseline: list[Requirement] = Field(default_factory=list)  # approved requirements, for follow-ups
    model: str
    chunk_size: int = 800
    overlap: int = 100


class AnalystOutput(BaseModel):
    analysis: Analysis
    chunk_count: int


def renumber(reqs: list[Requirement], keep_ids: set[str]) -> list[Requirement]:
    """Keep baseline ids; give everything else sequential ids after the highest known id."""
    used = {r.id for r in reqs if r.id in keep_ids}
    nums = [int(i.split("-")[1]) for i in (keep_ids | used)]
    nxt = (max(nums) + 1) if nums else 1
    out: list[Requirement] = []
    for r in reqs:
        if r.id in keep_ids and r.id not in {o.id for o in out}:
            out.append(r)
            continue
        out.append(r.model_copy(update={"id": f"REQ-{nxt:03d}"}))
        nxt += 1
    return out


async def run(inp: AnalystInput, llm: LLM) -> AnalystOutput:
    chunks = chunk_words(inp.transcript, inp.chunk_size, inp.overlap)
    extractions = await asyncio.gather(
        *(
            llm.ask_json(
                inp.model, "analyst_extract", ChunkExtraction,
                chunk=c, chunk_index=str(i + 1), chunk_count=str(len(chunks)),
            )
            for i, c in enumerate(chunks)
        )
    )
    baseline_text = (
        json.dumps([r.model_dump(include={"id", "description", "priority", "status"}) for r in inp.baseline], indent=1)
        if inp.baseline else "none (this is the first meeting)"
    )
    merged = await llm.ask_json(
        inp.model, "analyst_merge", Analysis, max_tokens=6000,
        extractions=json.dumps([e.model_dump() for e in extractions], indent=1),
        baseline=baseline_text,
    )
    keep = {r.id for r in inp.baseline}
    merged.requirements = renumber(merged.requirements, keep)
    if not inp.baseline:
        merged.removed_requirement_ids = []
    return AnalystOutput(analysis=merged, chunk_count=len(chunks))
