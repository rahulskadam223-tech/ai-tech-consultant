"""Agent 3: scope of work."""
from __future__ import annotations

import json

from pydantic import BaseModel

from scope.llm import LLM
from scope.models import Analysis, FeasibilityItem, ScopeDoc


class ScopeInput(BaseModel):
    client: str
    project: str
    analysis: Analysis
    feasibility: list[FeasibilityItem]
    model: str


async def run(inp: ScopeInput, llm: LLM) -> ScopeDoc:
    return await llm.ask_json(
        inp.model, "scope", ScopeDoc, max_tokens=6000,
        client=inp.client, project=inp.project,
        analysis=inp.analysis.model_dump_json(indent=1),
        feasibility=json.dumps([f.model_dump(exclude={"sources"}) for f in inp.feasibility], indent=1),
    )
