"""Auto-send eligibility rules. Pure functions so they are easy to test."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .models import NEVER_AUTO

Outcome = Literal["approved", "edited", "rejected"]


@dataclass(frozen=True)
class CategoryState:
    category: str
    consecutive_clean: int = 0  # sends in a row without edit or reject
    consecutive_edits: int = 0  # edits in a row (approve resets)
    auto_send_eligible: bool = False


def was_edited(draft: str, final: str) -> bool:
    return draft.strip() != final.strip()


def apply_outcome(
    state: CategoryState, outcome: Outcome, threshold: int = 20
) -> tuple[CategoryState, str | None]:
    """Return the new state and a log reason if the eligibility flag changed.

    - approved: clean streak +1, edit streak reset. At `threshold` the category becomes
      eligible unless it is in NEVER_AUTO.
    - edited: clean streak reset, edit streak +1. Two edits in a row disable eligibility.
    - rejected: clean streak reset (edit streak unchanged).
    """
    reason: str | None = None
    if outcome == "approved":
        new = replace(state, consecutive_clean=state.consecutive_clean + 1, consecutive_edits=0)
        if (
            not new.auto_send_eligible
            and new.consecutive_clean >= threshold
            and new.category not in NEVER_AUTO
        ):
            new = replace(new, auto_send_eligible=True)
            reason = f"{threshold} consecutive sends without edit"
    elif outcome == "edited":
        new = replace(state, consecutive_clean=0, consecutive_edits=state.consecutive_edits + 1)
        if new.auto_send_eligible and new.consecutive_edits >= 2:
            new = replace(new, auto_send_eligible=False)
            reason = "2 edits in a row"
    else:  # rejected
        new = replace(state, consecutive_clean=0)
    return new, reason
