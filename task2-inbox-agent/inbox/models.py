"""Pydantic schemas for emails, classifier output, draft output and DB rows."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Category = Literal[
    "how_to", "troubleshooting", "project_request", "refund_cancel",
    "complaint", "quote_request", "follow_up", "legal",
]
Level = Literal["low", "medium", "high"]

PRODUCT_QUESTION_CATEGORIES: frozenset[str] = frozenset({"how_to", "troubleshooting", "follow_up"})
ALWAYS_HUMAN_CATEGORIES: frozenset[str] = frozenset({"refund_cancel", "complaint", "quote_request", "legal"})
NEVER_AUTO: frozenset[str] = frozenset({"refund_cancel", "complaint", "quote_request"})


class Email(BaseModel):
    id: int
    from_: str = Field(alias="from")
    subject: str
    body: str
    expected_category: str
    risk: Level
    should_escalate: bool
    holdout: bool = False

    model_config = {"populate_by_name": True}


class Classification(BaseModel):
    category: Category
    urgency: Level
    risk: Level
    summary: str = Field(min_length=1)


class KBResult(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_evidence"]
    sources: list[dict[str, object]] = Field(default_factory=list)
    needs_human: bool


class Draft(BaseModel):
    reply: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    needs_human: bool
    next_action: str = Field(min_length=1)


class ParseError(ValueError):
    pass


def parse_json_object(text: str) -> dict[str, object]:
    """Extract the first JSON object from model output, tolerating ``` fences and prose."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ParseError(f"no JSON object in model output: {text[:120]!r}")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON from model: {e}") from e
    if not isinstance(data, dict):
        raise ParseError("model output is not a JSON object")
    return data


def validate_classification(text: str) -> Classification:
    try:
        return Classification.model_validate(parse_json_object(text))
    except ValidationError as e:
        raise ParseError(str(e)) from e


def validate_draft(text: str) -> Draft:
    try:
        return Draft.model_validate(parse_json_object(text))
    except ValidationError as e:
        raise ParseError(str(e)) from e
