"""Match follow-up requirements to the approved baseline and build the change report."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Analysis, ChangeReport, Constraints, ModifiedItem, Requirement

MATCH_THRESHOLD = 0.45   # below this a requirement is treated as new
ID_MATCH_MIN = 0.20      # an id match is trusted only if the wording is at least this similar
SAME_THRESHOLD = 0.90    # above this (and same priority) it is unchanged
STOPWORDS = frozenset("a an the of to for and or in on by with is are be as at from that this it".split())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Blend of token overlap (robust to reordering) and sequence ratio (robust to paraphrase length)."""
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return round(max(jaccard, ratio), 3)


def match_to_baseline(req: Requirement, baseline: list[Requirement]) -> tuple[Requirement | None, float]:
    """Match by ID first (if the wording is not totally unrelated), then by description similarity."""
    for b in baseline:
        if b.id == req.id and similarity(req.description, b.description) >= ID_MATCH_MIN:
            return b, 1.0
    best, best_score = None, 0.0
    for b in baseline:
        score = similarity(req.description, b.description)
        if score > best_score:
            best, best_score = b, score
    if best is not None and best_score >= MATCH_THRESHOLD:
        return best, best_score
    return None, best_score


def next_id(existing: list[Requirement]) -> str:
    nums = [int(r.id.split("-")[1]) for r in existing if r.id.startswith("REQ-")]
    return f"REQ-{(max(nums) + 1 if nums else 1):03d}"


def build_change_report(
    baseline: list[Requirement], followup: Analysis, baseline_constraints: Constraints | None = None
) -> ChangeReport:
    report = ChangeReport()
    removed_ids = {rid for rid in followup.removed_requirement_ids}
    by_id = {b.id: b for b in baseline}
    report.removed = [by_id[r] for r in removed_ids if r in by_id]
    touched: set[str] = set()
    all_known: list[Requirement] = list(baseline)

    for new in followup.requirements:
        old, score = match_to_baseline(new, baseline)
        if old is not None and old.id in touched and old.id not in removed_ids:
            old = None  # that baseline item was already claimed by an earlier follow-up requirement
        if old is not None:
            if old.id in removed_ids:
                continue
            touched.add(old.id)
            adopted = new.model_copy(update={"id": old.id, "relation": "existing"})
            changes = []
            if similarity(old.description, new.description) < SAME_THRESHOLD:
                changes.append("description")
            if old.priority != new.priority:
                changes.append(f"priority {old.priority} -> {new.priority}")
            if changes:
                report.modified.append(
                    ModifiedItem(old=old, new=adopted, what_changed=", ".join(changes), similarity=score)
                )
            else:
                report.unchanged.append(old)
        else:
            fresh = new.model_copy(update={"id": next_id(all_known)})
            all_known.append(fresh)
            if new.relation == "out_of_scope":
                report.out_of_scope.append(fresh)
            else:
                report.added.append(fresh.model_copy(update={"relation": "new_in_scope"}))

    for b in baseline:  # not mentioned in the follow-up: carried over unchanged
        if b.id not in touched and b.id not in removed_ids:
            report.unchanged.append(b)

    if baseline_constraints is not None:
        for field in ("deadline", "budget"):
            old_v, new_v = getattr(baseline_constraints, field), getattr(followup.constraints, field)
            if new_v and new_v != old_v:
                report.constraint_changes.append(f"{field}: {old_v or 'none'} -> {new_v}")
    return report


def merged_requirements(report: ChangeReport) -> list[Requirement]:
    """The revised requirement set: unchanged + modified(new) + added. Removed and out-of-scope excluded."""
    return sorted(
        report.unchanged + [m.new for m in report.modified] + report.added, key=lambda r: r.id
    )
