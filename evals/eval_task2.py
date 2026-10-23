"""Eval for Task 2: classify the 40 non-holdout emails with Haiku and Sonnet.

Usage: task2-inbox-agent/.venv/bin/python evals/eval_task2.py
Writes evals/task2/results.csv and prints accuracy per model.
"""
from __future__ import annotations

import asyncio
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "task2-inbox-agent"))

from inbox.config import get_settings  # noqa: E402
from inbox.llm import Claude  # noqa: E402
from inbox.models import Email, ParseError  # noqa: E402
from inbox.pipeline import load_emails  # noqa: E402

MODELS = ["claude-haiku-4-5", "claude-sonnet-4-5"]
# USD per 1M tokens (input, output)
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}
OUT = ROOT / "evals" / "task2" / "results.csv"


async def one(llm: Claude, sem: asyncio.Semaphore, email: Email, model: str) -> dict[str, object]:
    async with sem:
        t0 = time.perf_counter()
        try:
            cls = await llm.classify(email, model=model)
            predicted = cls.category
        except ParseError as e:
            predicted = f"PARSE_ERROR: {str(e)[:40]}"
        latency_ms = round((time.perf_counter() - t0) * 1000)
        inp, out = llm.last_usage
        price_in, price_out = PRICES.get(model, (0.0, 0.0))
        return {
            "email_id": email.id,
            "model": model,
            "expected": email.expected_category,
            "predicted": predicted,
            "correct": predicted == email.expected_category,
            "latency_ms": latency_ms,
            "cost_usd": round(inp / 1e6 * price_in + out / 1e6 * price_out, 6),
        }


async def main() -> None:
    s = get_settings()
    llm = Claude(s.prompts_dir, s.classify_model, s.draft_model, s.anthropic_api_key)
    emails = [e for e in load_emails(s.emails_file) if not e.holdout]
    sem = asyncio.Semaphore(4)
    rows = await asyncio.gather(*(one(llm, sem, e, m) for m in MODELS for e in emails))
    rows.sort(key=lambda r: (str(r["model"]), int(r["email_id"])))  # type: ignore[call-overload]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for m in MODELS:
        mine = [r for r in rows if r["model"] == m]
        acc = sum(bool(r["correct"]) for r in mine) / len(mine)
        cost = sum(float(r["cost_usd"]) for r in mine)
        lat = sum(int(r["latency_ms"]) for r in mine) / len(mine)
        print(f"{m:<22} accuracy {acc:.1%} ({sum(bool(r['correct']) for r in mine)}/{len(mine)})  avg {lat:.0f} ms  total ${cost:.4f}")
        wrong = [r for r in mine if not r["correct"]]
        for r in wrong:
            print(f"   #{r['email_id']}: expected {r['expected']}, got {r['predicted']}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
