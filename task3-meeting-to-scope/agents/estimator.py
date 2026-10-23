"""Agent 4: hours per task. existing_setting items get 0.5-1h configuration only."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from scope.llm import LLM
from scope.models import Estimate, EstimateTask, FeasibilityItem, Requirement, ScopeDoc

ESTIMABLE = {"existing_setting", "partial", "custom_dev"}


class EstimatorInput(BaseModel):
    requirements: list[Requirement]
    feasibility: list[FeasibilityItem]
    scope: ScopeDoc
    model: str
    only_ids: set[str] | None = None  # follow-ups: re-estimate only affected requirements


class EstimatorOutput(BaseModel):
    estimate: Estimate
    estimated_ids: list[str] = Field(default_factory=list)


def clamp_config_tasks(tasks: list[EstimateTask], existing_ids: set[str]) -> list[EstimateTask]:
    """Enforce the rule in code too: existing_setting -> one task, 0.5-1h."""
    out: list[EstimateTask] = []
    seen: set[str] = set()
    for t in tasks:
        if t.requirement_id in existing_ids:
            if t.requirement_id in seen:
                continue
            seen.add(t.requirement_id)
            t = t.model_copy(update={"low": 0.5, "likely": min(max(t.likely, 0.5), 1.0), "high": 1.0})
        out.append(t)
    return out


async def run(inp: EstimatorInput, llm: LLM) -> EstimatorOutput:
    feas = {f.requirement_id: f.classification for f in inp.feasibility}
    deliverable_of = {rid: d.name for d in inp.scope.deliverables for rid in d.requirement_ids}
    items = [
        {"requirement_id": r.id, "requirement": r.description, "feasibility": feas.get(r.id, "needs_clarification"),
         "deliverable": deliverable_of.get(r.id, "General")}
        for r in inp.requirements
        if feas.get(r.id) in ESTIMABLE and r.relation != "out_of_scope"
        and (inp.only_ids is None or r.id in inp.only_ids)
    ]
    if not items:
        return EstimatorOutput(estimate=Estimate(tasks=[]), estimated_ids=[])
    est = await llm.ask_json(inp.model, "estimator", Estimate, max_tokens=5000, items=json.dumps(items, indent=1))
    existing = {i["requirement_id"] for i in items if i["feasibility"] == "existing_setting"}
    est.tasks = clamp_config_tasks(est.tasks, existing)
    return EstimatorOutput(estimate=est, estimated_ids=[i["requirement_id"] for i in items])
