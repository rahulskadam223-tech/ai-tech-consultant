"""SQLite: drafts, per-category learning state, eligibility change log."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .learning import CategoryState, Outcome, apply_outcome, was_edited

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    urgency TEXT,
    risk TEXT,
    summary TEXT,
    kb_status TEXT,
    retrieved_sources TEXT,   -- JSON list of {title,url,score}
    draft TEXT NOT NULL,
    needs_human INTEGER NOT NULL,
    next_action TEXT,
    final_reply TEXT,
    outcome TEXT,             -- approved | edited | rejected | NULL (pending)
    was_edited INTEGER,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS category_stats (
    category TEXT PRIMARY KEY,
    consecutive_clean INTEGER NOT NULL DEFAULT 0,
    consecutive_edits INTEGER NOT NULL DEFAULT 0,
    auto_send_eligible INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS eligibility_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    old_value INTEGER NOT NULL,
    new_value INTEGER NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InboxDB:
    def __init__(self, path: Path, threshold: int = 20) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.threshold = threshold

    # ---- drafts ------------------------------------------------------------
    def save_draft(self, row: dict[str, Any]) -> int:
        row = {**row, "retrieved_sources": json.dumps(row.get("retrieved_sources", [])), "created_at": now_iso()}
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self.conn.execute(f"INSERT INTO drafts ({cols}) VALUES ({marks})", tuple(row.values()))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def latest_draft(self, email_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM drafts WHERE email_id = ? ORDER BY id DESC LIMIT 1", (email_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["retrieved_sources"] = json.loads(d["retrieved_sources"] or "[]")
        return d

    def decided_email_ids(self) -> dict[int, str]:
        rows = self.conn.execute(
            "SELECT email_id, outcome FROM drafts WHERE outcome IS NOT NULL"
        ).fetchall()
        return {int(r["email_id"]): str(r["outcome"]) for r in rows}

    def record_decision(self, draft_id: int, outcome: Outcome, final_reply: str) -> tuple[CategoryState, str | None]:
        """Store the human decision, then update the category counters. Returns new state + log reason."""
        row = self.conn.execute("SELECT draft, category FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise KeyError(f"draft {draft_id} not found")
        edited = was_edited(row["draft"], final_reply)
        if outcome == "edited" and not edited:
            outcome = "approved"  # text unchanged, treat as a clean send
        self.conn.execute(
            "UPDATE drafts SET final_reply = ?, outcome = ?, was_edited = ?, decided_at = ? WHERE id = ?",
            (final_reply, outcome, int(edited), now_iso(), draft_id),
        )
        state, reason = apply_outcome(self.get_state(row["category"]), outcome, self.threshold)
        self._save_state(state)
        if reason is not None:
            self.conn.execute(
                "INSERT INTO eligibility_log (category, old_value, new_value, reason, at) VALUES (?, ?, ?, ?, ?)",
                (state.category, int(not state.auto_send_eligible), int(state.auto_send_eligible), reason, now_iso()),
            )
            print(f"[eligibility] {state.category}: auto_send_eligible -> {state.auto_send_eligible} ({reason})")
        self.conn.commit()
        return state, reason

    # ---- learning state ----------------------------------------------------
    def get_state(self, category: str) -> CategoryState:
        row = self.conn.execute("SELECT * FROM category_stats WHERE category = ?", (category,)).fetchone()
        if row is None:
            return CategoryState(category=category)
        return CategoryState(
            category=category,
            consecutive_clean=int(row["consecutive_clean"]),
            consecutive_edits=int(row["consecutive_edits"]),
            auto_send_eligible=bool(row["auto_send_eligible"]),
        )

    def all_states(self) -> list[CategoryState]:
        rows = self.conn.execute("SELECT category FROM category_stats ORDER BY category").fetchall()
        return [self.get_state(str(r["category"])) for r in rows]

    def _save_state(self, s: CategoryState) -> None:
        self.conn.execute(
            "INSERT INTO category_stats (category, consecutive_clean, consecutive_edits, auto_send_eligible) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(category) DO UPDATE SET consecutive_clean = excluded.consecutive_clean, "
            "consecutive_edits = excluded.consecutive_edits, auto_send_eligible = excluded.auto_send_eligible",
            (s.category, s.consecutive_clean, s.consecutive_edits, int(s.auto_send_eligible)),
        )

    def eligibility_log(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM eligibility_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
