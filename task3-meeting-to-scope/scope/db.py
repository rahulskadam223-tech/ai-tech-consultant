"""SQLite: projects, meetings, requirement versions, approved baseline."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client TEXT NOT NULL,
    baseline_version_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    transcript TEXT NOT NULL,
    kind TEXT NOT NULL,            -- initial | followup
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    meeting_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    analysis TEXT NOT NULL,        -- JSON of Analysis
    feasibility TEXT NOT NULL,     -- JSON list of FeasibilityItem
    scope TEXT NOT NULL,           -- JSON ScopeDoc
    estimate TEXT NOT NULL,        -- JSON Estimate
    proposal TEXT NOT NULL,        -- JSON Proposal
    change_report TEXT,            -- JSON ChangeReport (follow-ups)
    models TEXT NOT NULL,
    status TEXT NOT NULL,          -- draft | approved | superseded
    created_at TEXT NOT NULL,
    approved_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectDB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- projects ----------------------------------------------------------
    def create_project(self, name: str, client: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO projects (name, client, created_at) VALUES (?, ?, ?)", (name, client, now_iso())
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def list_projects(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM projects ORDER BY id")]

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    # ---- meetings ----------------------------------------------------------
    def add_meeting(self, project_id: int, filename: str, transcript: str, kind: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO meetings (project_id, filename, transcript, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, filename, transcript, kind, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def meetings(self, project_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM meetings WHERE project_id = ? ORDER BY id", (project_id,))]

    # ---- versions ----------------------------------------------------------
    def save_version(self, project_id: int, meeting_id: int, payload: dict[str, Any], models: str) -> int:
        n = self.conn.execute("SELECT COALESCE(MAX(version_no), 0) + 1 FROM versions WHERE project_id = ?", (project_id,)).fetchone()[0]
        cur = self.conn.execute(
            "INSERT INTO versions (project_id, meeting_id, version_no, analysis, feasibility, scope, estimate, proposal, "
            "change_report, models, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
            (
                project_id, meeting_id, n,
                json.dumps(payload["analysis"]), json.dumps(payload["feasibility"]), json.dumps(payload["scope"]),
                json.dumps(payload["estimate"]), json.dumps(payload["proposal"]),
                json.dumps(payload["change_report"]) if payload.get("change_report") else None,
                models, now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("analysis", "feasibility", "scope", "estimate", "proposal", "change_report"):
            d[key] = json.loads(d[key]) if d.get(key) else None
        return d

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
        return self._decode(row) if row else None

    def versions(self, project_id: int) -> list[dict[str, Any]]:
        return [self._decode(r) for r in self.conn.execute("SELECT * FROM versions WHERE project_id = ? ORDER BY version_no", (project_id,))]

    def latest_version(self, project_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM versions WHERE project_id = ? ORDER BY version_no DESC LIMIT 1", (project_id,)).fetchone()
        return self._decode(row) if row else None

    def baseline(self, project_id: int) -> dict[str, Any] | None:
        p = self.get_project(project_id)
        if not p or not p["baseline_version_id"]:
            return None
        return self.get_version(int(p["baseline_version_id"]))

    def approve_version(self, version_id: int) -> None:
        """Human approval: this version becomes the project's approved baseline."""
        v = self.get_version(version_id)
        if v is None:
            raise KeyError(f"version {version_id} not found")
        self.conn.execute("UPDATE versions SET status = 'superseded' WHERE project_id = ? AND status = 'approved'", (v["project_id"],))
        self.conn.execute("UPDATE versions SET status = 'approved', approved_at = ? WHERE id = ?", (now_iso(), version_id))
        self.conn.execute("UPDATE projects SET baseline_version_id = ? WHERE id = ?", (version_id, v["project_id"]))
        self.conn.commit()
