"""Eval for Task 3: 20 checks on meeting_a (initial) and meeting_c (follow-up), analyst = sonnet vs haiku.

Usage: task3-meeting-to-scope/.venv/bin/python evals/eval_task3.py
Writes evals/task3/results.csv (check, model, pass, latency_ms, cost_usd) and prints a summary per model.
Uses a throwaway SQLite DB so it never touches real projects.
"""
from __future__ import annotations

import asyncio
import csv
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task3-meeting-to-scope"))

from scope.config import get_settings  # noqa: E402
from scope.models import ChangeReport, Estimate  # noqa: E402
from scope.pipeline import build_pipeline  # noqa: E402

ANALYST_MODELS = ["claude-sonnet-4-5", "claude-haiku-4-5"]
OUT = ROOT / "evals" / "task3" / "results.csv"


def has(reqs: list[dict[str, Any]], *words: str) -> dict[str, Any] | None:
    for r in reqs:
        d = r["description"].lower()
        if any(w in d for w in words):
            return r
    return None


def feas_of(v: dict[str, Any], req: dict[str, Any] | None) -> str:
    if not req:
        return "missing"
    return next((f["classification"] for f in v["feasibility"] if f["requirement_id"] == req["id"]), "missing")


def checks_initial(v: dict[str, Any]) -> list[tuple[str, bool]]:
    reqs = v["analysis"]["requirements"]
    est = Estimate.model_validate(v["estimate"])
    custom_ids = {f["requirement_id"] for f in v["feasibility"] if f["classification"] == "custom_dev"}
    existing_ids = {f["requirement_id"] for f in v["feasibility"] if f["classification"] == "existing_setting"}
    cfg_tasks = [t for t in est.tasks if t.requirement_id in existing_ids]
    return [
        ("A1 at least 5 requirements extracted", len(reqs) >= 5),
        ("A2 location filter requirement found", has(reqs, "location", "locality", "city") is not None),
        ("A3 price filter requirement found", has(reqs, "price") is not None),
        ("A4 mobile view requirement found", has(reqs, "mobile") is not None),
        ("A5 AI search requirement found and marked unclear", (has(reqs, "ai ", "ai-", "natural language") or {}).get("status") == "unclear"),
        ("A6 deadline constraint captured (6 weeks)", "6" in (v["analysis"]["constraints"].get("deadline") or "") or "six" in (v["analysis"]["constraints"].get("deadline") or "").lower()),
        ("A7 location filter is existing_setting or partial", feas_of(v, has(reqs, "location", "locality", "city")) in {"existing_setting", "partial"}),
        ("A8 AI search is custom_dev or needs_clarification", feas_of(v, has(reqs, "ai ", "ai-", "natural language")) in {"custom_dev", "needs_clarification"}),
        ("A9 every requirement has a feasibility entry", {r["id"] for r in reqs} == {f["requirement_id"] for f in v["feasibility"]}),
        ("A10 scope has exclusions and acceptance criteria", bool(v["scope"]["exclusions"]) and bool(v["scope"]["acceptance_criteria"])),
        ("A11 estimate tasks have low <= likely <= high", bool(est.tasks) and all(t.low <= t.likely <= t.high for t in est.tasks)),
        ("A12 existing_setting items cost at most 1h config", all(0.5 <= t.likely <= 1.0 for t in cfg_tasks) if existing_ids else True),
        ("A13 every custom_dev item has 2+ tasks", all(sum(t.requirement_id == i for t in est.tasks) >= 2 for i in custom_ids) if custom_ids else True),
        ("A14 proposal has no unverified promise", v["proposal"]["unverified_promises"] == []),
        ("A15 proposal states currency and the Items To Confirm section", get_settings().currency in v["proposal"]["markdown"] and "## Items To Confirm" in v["proposal"]["markdown"]),
    ]


def checks_followup(v: dict[str, Any], base: dict[str, Any]) -> list[tuple[str, bool]]:
    cr = ChangeReport.model_validate(v["change_report"])
    added = " ".join(r.description.lower() for r in cr.added)
    removed = " ".join(r.description.lower() for r in cr.removed)
    oos = " ".join(r.description.lower() for r in cr.out_of_scope)
    base_est = Estimate.model_validate(base["estimate"])
    new_est = Estimate.model_validate(v["estimate"])
    untouched = {r.id for r in cr.unchanged}
    carried_same = all(
        [t.model_dump() for t in base_est.tasks if t.requirement_id == i] == [t.model_dump() for t in new_est.tasks if t.requirement_id == i]
        for i in untouched
    )
    return [
        ("C1 saved-search alert detected as ADDED", "alert" in added or "saved search" in added),
        ("C2 AI search detected as REMOVED", "ai" in removed or "natural language" in removed),
        ("C3 deadline change 6 -> 4 weeks detected", any("4" in c or "four" in c.lower() for c in cr.constraint_changes)),
        ("C4 logo redesign flagged OUT OF SCOPE", "logo" in oos),
        ("C5 unchanged items keep their baseline estimate (only affected re-estimated)", carried_same and v["proposal"]["unverified_promises"] == []),
    ]


async def run_model(model: str) -> list[dict[str, Any]]:
    s = get_settings()
    s.analyst_model = model
    s.task3_db = Path(tempfile.mkdtemp()) / "eval.sqlite"
    pipe = build_pipeline(s)
    pid = pipe.db.create_project("Search & mobile upgrade", "Ravi, Sunrise Property Listings")
    tdir = s.transcripts_dir
    rows: list[dict[str, Any]] = []

    def record(checks: list[tuple[str, bool]], latency_ms: int, cost: float) -> None:
        for name, ok in checks:  # latency/cost of the run are shared across its checks
            rows.append({"check": name, "model": model, "pass": ok, "latency_ms": latency_ms, "cost_usd": round(cost / len(checks), 5)})
            print(f"  {'PASS' if ok else 'FAIL'} {name}")

    print(f"\n=== analyst={model}: meeting_a (initial)")
    pipe.llm.reset_usage(); t0 = time.perf_counter()
    v1 = await pipe.run_initial(pid, "meeting_a.txt", (tdir / "meeting_a.txt").read_text())
    base = pipe.db.get_version(v1); assert base
    record(checks_initial(base), round((time.perf_counter() - t0) * 1000), pipe.llm.total_cost())
    pipe.db.approve_version(v1)

    print(f"=== analyst={model}: meeting_c (follow-up)")
    pipe.llm.reset_usage(); t0 = time.perf_counter()
    v2 = await pipe.run_followup(pid, "meeting_c.txt", (tdir / "meeting_c.txt").read_text())
    rev = pipe.db.get_version(v2); assert rev
    record(checks_followup(rev, base), round((time.perf_counter() - t0) * 1000), pipe.llm.total_cost())
    return rows


async def main() -> None:
    rows: list[dict[str, Any]] = []
    for m in ANALYST_MODELS:
        rows += await run_model(m)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print()
    for m in ANALYST_MODELS:
        mine = [r for r in rows if r["model"] == m]
        passed = sum(bool(r["pass"]) for r in mine)
        cost = sum(float(r["cost_usd"]) for r in mine)
        lat = {r["latency_ms"] for r in mine}
        print(f"analyst={m:<20} {passed}/{len(mine)} checks passed   total ${cost:.3f}   run latencies {sorted(lat)} ms")
    print(f"-> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
