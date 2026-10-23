"""Agent 5: client-ready Markdown proposal, checked for unverified promises."""
from __future__ import annotations

import re

from pydantic import BaseModel

from scope.llm import LLM
from scope.models import Estimate, FeasibilityItem, Proposal, ScopeDoc

PROMISE_SECTIONS = {"Proposed Solution", "Deliverables", "Timeline", "Investment", "Acceptance Criteria"}


class ProposalInput(BaseModel):
    client: str
    project: str
    scope: ScopeDoc
    estimate: Estimate
    feasibility: list[FeasibilityItem]
    hourly_rate: float
    currency: str
    model: str


def sections(markdown: str) -> dict[str, str]:
    parts = re.split(r"^## +(.+?)\s*$", markdown, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


HEDGES = ("confirm", "clarif", "not included", "not part", "exclud", "pending", "subject to", "to be", "once verified", "separate")


def unverified_promises(markdown: str, unclear_ids: set[str]) -> list[str]:
    """Return 'REQ-xxx in <section>' for any needs_clarification id that a committing section mentions
    on a line with no hedge (e.g. an Investment table row with a price, or a deliverable bullet)."""
    found: list[str] = []
    for title, body in sections(markdown).items():
        if title not in PROMISE_SECTIONS:
            continue
        for line in body.splitlines():
            low = line.lower()
            if any(h in low for h in HEDGES):
                continue
            for rid in sorted(unclear_ids):
                if rid in line and f"{rid} in {title}" not in found:
                    found.append(f"{rid} in {title}")
    return found


async def run(inp: ProposalInput, llm: LLM) -> Proposal:
    unclear = {f.requirement_id for f in inp.feasibility if f.classification == "needs_clarification"}
    values = dict(
        client=inp.client, project=inp.project, rate=f"{inp.hourly_rate:g}", currency=inp.currency,
        scope=inp.scope.model_dump_json(indent=1), estimate=inp.estimate.model_dump_json(indent=1),
        needs_clarification_ids=", ".join(sorted(unclear)) or "none",
    )
    prompt = llm.load_prompt("proposal", **values)
    md = await llm.ask_text(inp.model, prompt, 6000)
    bad = unverified_promises(md, unclear)
    if bad:
        retry = prompt + "\n\nYour previous draft promised items that are not confirmed: " + "; ".join(bad) + \
            ". Move those ids to Items To Confirm only and rewrite."
        md = await llm.ask_text(inp.model, retry, 6000)
        bad = unverified_promises(md, unclear)
    return Proposal(markdown=md, unverified_promises=bad)
