"""Agent 2: ask Task 1 whether Brilliant Directories supports each requirement, then classify."""
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, Field

from scope.kb_client import KnowledgeBrain
from scope.llm import LLM
from scope.models import FeasClass, FeasibilityItem, Requirement


class FeasibilityInput(BaseModel):
    requirements: list[Requirement]
    model: str
    concurrency: int = 3


class FeasibilityOutput(BaseModel):
    items: list[FeasibilityItem] = Field(default_factory=list)


class _Verdict(BaseModel):
    classification: FeasClass
    rationale: str


async def classify_one(req: Requirement, kb: KnowledgeBrain, llm: LLM, model: str) -> FeasibilityItem:
    if req.relation == "out_of_scope":
        return FeasibilityItem(requirement_id=req.id, classification="needs_clarification",
                               rationale="Out of scope for this project; not assessed.", kb_status="skipped")
    result = await kb.query(f"Does Brilliant Directories support {req.description}")
    if result.status == "insufficient_evidence":
        return FeasibilityItem(
            requirement_id=req.id, classification="needs_clarification",
            rationale="The documentation search found no relevant evidence; feasibility must be confirmed, not assumed.",
            kb_status=result.status, sources=result.sources,
        )
    verdict = await llm.ask_json(
        model, "feasibility", _Verdict, max_tokens=400,
        requirement=req.description, kb_status=result.status, kb_answer=result.answer,
        sources=json.dumps([s.model_dump() for s in result.sources]),
    )
    return FeasibilityItem(requirement_id=req.id, classification=verdict.classification,
                           rationale=verdict.rationale, kb_status=result.status, sources=result.sources)


async def run(inp: FeasibilityInput, llm: LLM, kb: KnowledgeBrain) -> FeasibilityOutput:
    sem = asyncio.Semaphore(inp.concurrency)

    async def guarded(r: Requirement) -> FeasibilityItem:
        async with sem:
            return await classify_one(r, kb, llm, inp.model)

    return FeasibilityOutput(items=list(await asyncio.gather(*(guarded(r) for r in inp.requirements))))
