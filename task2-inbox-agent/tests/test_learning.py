from pathlib import Path

from inbox.db import InboxDB
from inbox.learning import CategoryState, apply_outcome, was_edited
from inbox.models import NEVER_AUTO


def test_was_edited_ignores_surrounding_whitespace() -> None:
    assert was_edited("Hello there", "  Hello there \n") is False
    assert was_edited("Hello there", "Hello there!") is True
    assert was_edited("", "anything") is True


def test_counter_increments_and_resets() -> None:
    s = CategoryState("how_to")
    for _ in range(5):
        s, _ = apply_outcome(s, "approved")
    assert s.consecutive_clean == 5
    s, _ = apply_outcome(s, "edited")
    assert s.consecutive_clean == 0 and s.consecutive_edits == 1
    for _ in range(3):
        s, _ = apply_outcome(s, "approved")
    s, _ = apply_outcome(s, "rejected")
    assert s.consecutive_clean == 0
    assert s.auto_send_eligible is False


def test_becomes_eligible_at_threshold_and_logs_reason() -> None:
    s = CategoryState("how_to")
    reasons = []
    for _ in range(20):
        s, r = apply_outcome(s, "approved", threshold=20)
        reasons.append(r)
    assert s.auto_send_eligible is True
    assert reasons[:19] == [None] * 19 and reasons[19] is not None


def test_two_edits_in_a_row_disable_eligibility() -> None:
    s = CategoryState("how_to", consecutive_clean=25, auto_send_eligible=True)
    s, r1 = apply_outcome(s, "edited")
    assert s.auto_send_eligible is True and r1 is None  # one edit is fine
    s, _ = apply_outcome(s, "approved")  # approve breaks the edit streak
    s, _ = apply_outcome(s, "edited")
    assert s.auto_send_eligible is True
    s, r2 = apply_outcome(s, "edited")
    assert s.auto_send_eligible is False and r2 == "2 edits in a row"


def test_never_auto_categories_never_become_eligible() -> None:
    assert NEVER_AUTO == {"refund_cancel", "complaint", "quote_request"}
    for cat in NEVER_AUTO:
        s = CategoryState(cat)
        for _ in range(50):
            s, r = apply_outcome(s, "approved", threshold=20)
            assert r is None
        assert s.auto_send_eligible is False
        assert s.consecutive_clean == 50  # counter still tracked, flag never flips


def test_db_record_decision_updates_state_and_log(tmp_path: Path) -> None:
    db = InboxDB(tmp_path / "t.sqlite", threshold=2)
    base = {"email_id": 1, "category": "how_to", "draft": "Draft text", "needs_human": 0,
            "prompt_version": "v1", "model": "m"}
    d1 = db.save_draft(base)
    state, reason = db.record_decision(d1, "edited", "Draft text  ")  # unchanged after strip
    assert state.consecutive_clean == 1 and reason is None
    assert db.latest_draft(1)["outcome"] == "approved" and db.latest_draft(1)["was_edited"] == 0
    d2 = db.save_draft(base)
    state, reason = db.record_decision(d2, "approved", "Draft text")
    assert state.auto_send_eligible is True and reason is not None
    assert db.eligibility_log()[0]["new_value"] == 1
    d3 = db.save_draft({**base, "category": "complaint"})
    for _ in range(3):
        db.record_decision(d3, "approved", "Draft text")
    assert db.get_state("complaint").auto_send_eligible is False
