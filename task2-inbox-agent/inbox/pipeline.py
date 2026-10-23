"""One email -> classification -> (Task 1 lookup) -> draft -> saved row."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .db import InboxDB
from .kb_client import KnowledgeBrain
from .llm import Claude
from .models import ALWAYS_HUMAN_CATEGORIES, PRODUCT_QUESTION_CATEGORIES, Classification, Draft, Email, KBResult


@dataclass
class Processed:
    draft_id: int
    classification: Classification
    kb: KBResult | None
    draft: Draft


def load_emails(path: Path) -> list[Email]:
    return [Email.model_validate(e) for e in json.loads(path.read_text(encoding="utf-8"))]


def apply_guardrails(cls: Classification, kb: KBResult | None, draft: Draft) -> Draft:
    """Rules the model cannot override."""
    if cls.category in ALWAYS_HUMAN_CATEGORIES:
        return draft.model_copy(update={"needs_human": True})
    if cls.category in PRODUCT_QUESTION_CATEGORIES and (kb is None or kb.status == "insufficient_evidence"):
        return draft.model_copy(update={"needs_human": True})
    return draft


class Pipeline:
    def __init__(self, settings: Settings, db: InboxDB, llm: Claude, kb: KnowledgeBrain) -> None:
        self.settings, self.db, self.llm, self.kb = settings, db, llm, kb

    async def process(self, email: Email) -> Processed:
        cls = await self.llm.classify(email)
        kb: KBResult | None = None
        if cls.category in PRODUCT_QUESTION_CATEGORIES:
            kb = await self.kb.query(cls.summary)  # raises KBUnavailable if Task 1 is down
        draft = apply_guardrails(cls, kb, await self.llm.draft(email, cls, kb))
        draft_id = self.db.save_draft(
            {
                "email_id": email.id,
                "category": cls.category,
                "urgency": cls.urgency,
                "risk": cls.risk,
                "summary": cls.summary,
                "kb_status": kb.status if kb else None,
                "retrieved_sources": kb.sources if kb else [],
                "draft": draft.reply,
                "needs_human": int(draft.needs_human),
                "next_action": draft.next_action,
                "prompt_version": self.settings.prompt_version,
                "model": f"{self.settings.classify_model}+{self.settings.draft_model}",
            }
        )
        return Processed(draft_id=draft_id, classification=cls, kb=kb, draft=draft)


def build_pipeline(settings: Settings) -> Pipeline:
    db = InboxDB(settings.task2_db, settings.auto_send_threshold)
    llm = Claude(settings.prompts_dir, settings.classify_model, settings.draft_model, settings.anthropic_api_key)
    return Pipeline(settings, db, llm, KnowledgeBrain(settings.task1_url))
