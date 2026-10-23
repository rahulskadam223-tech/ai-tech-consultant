"""Typed inputs/outputs shared by the five agents."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Priority = Literal["must", "should", "could"]
Status = Literal["confirmed", "unclear"]
Relation = Literal["existing", "new_in_scope", "out_of_scope"]
FeasClass = Literal["existing_setting", "partial", "custom_dev", "needs_clarification"]


class Requirement(BaseModel):
    id: str = Field(pattern=r"^REQ-\d{3}$")
    description: str = Field(min_length=1)
    source_quote: str = ""
    status: Status = "unclear"
    priority: Priority = "should"
    relation: Relation = "new_in_scope"  # follow-ups: existing | new_in_scope | out_of_scope


class Decision(BaseModel):
    text: str
    source_quote: str = ""


class Constraints(BaseModel):
    budget: str | None = None
    deadline: str | None = None
    other: list[str] = Field(default_factory=list)


class ChunkExtraction(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)


class Analysis(ChunkExtraction):
    removed_requirement_ids: list[str] = Field(default_factory=list)  # follow-ups only


class Source(BaseModel):
    title: str
    url: str
    score: float


class FeasibilityItem(BaseModel):
    requirement_id: str
    classification: FeasClass
    rationale: str
    kb_status: str  # answered | insufficient_evidence | skipped
    sources: list[Source] = Field(default_factory=list)


class Deliverable(BaseModel):
    name: str
    description: str
    requirement_ids: list[str] = Field(default_factory=list)


class ScopeDoc(BaseModel):
    objective: str
    problem: str
    requirements: list[str]
    solution: str
    deliverables: list[Deliverable]
    exclusions: list[str]
    assumptions: list[str]
    acceptance_criteria: list[str]
    client_responsibilities: list[str]
    open_questions: list[str]


class EstimateTask(BaseModel):
    requirement_id: str
    deliverable: str
    task: str
    low: float = Field(ge=0)
    likely: float = Field(ge=0)
    high: float = Field(ge=0)
    assumption: str = ""


class Estimate(BaseModel):
    tasks: list[EstimateTask]

    def totals(self) -> tuple[float, float, float]:
        return (
            sum(t.low for t in self.tasks),
            sum(t.likely for t in self.tasks),
            sum(t.high for t in self.tasks),
        )


class Proposal(BaseModel):
    markdown: str
    unverified_promises: list[str] = Field(default_factory=list)


class ModifiedItem(BaseModel):
    old: Requirement
    new: Requirement
    what_changed: str
    similarity: float


class ChangeReport(BaseModel):
    added: list[Requirement] = Field(default_factory=list)
    modified: list[ModifiedItem] = Field(default_factory=list)
    removed: list[Requirement] = Field(default_factory=list)
    out_of_scope: list[Requirement] = Field(default_factory=list)
    unchanged: list[Requirement] = Field(default_factory=list)
    constraint_changes: list[str] = Field(default_factory=list)

    def affected_ids(self) -> set[str]:
        return {r.id for r in self.added} | {m.new.id for m in self.modified}


# ---- JSON parsing of model output ---------------------------------------
class ParseError(ValueError):
    pass


def parse_json_object(text: str) -> dict[str, object]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ParseError(f"no JSON object in model output: {text[:120]!r}")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ParseError("not a JSON object")
    return data


def validate_as(schema: type, text: str):  # type: ignore[no-untyped-def]
    try:
        return schema.model_validate(parse_json_object(text))
    except ValidationError as e:
        raise ParseError(str(e)[:400]) from e
