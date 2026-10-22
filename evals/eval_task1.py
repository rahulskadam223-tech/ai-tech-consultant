"""Eval for Task 1: asks fixed questions via POST /query and writes evals/task1/results.csv.

Usage: task1-knowledge-brain/.venv/bin/python evals/eval_task1.py [TASK1_URL]
Checks (a) answered questions mention an expected keyword and (b) off-topic questions abstain.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TASK1_URL", "http://localhost:8001")
OUT = Path(__file__).parent / "task1" / "results.csv"

# (question, expected_status, keyword that should appear in an answered reply)
CASES: list[tuple[str, str, str]] = [
    ("Can I send a mass email campaign to an imported contact list?", "answered", "spam"),
    ("How do I add a new member manually from the admin?", "answered", "member"),
    ("How do I change my site's logo?", "answered", "logo"),
    ("What payment gateways are supported?", "answered", "pay"),
    ("How do I set up a custom domain?", "answered", "domain"),
    ("What is the capital of France?", "insufficient_evidence", ""),
    ("Write me a poem about databases.", "insufficient_evidence", ""),
    ("How do I configure Kubernetes ingress for my cluster?", "insufficient_evidence", ""),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    health = httpx.get(f"{BASE_URL}/health", timeout=30).json()
    rows: list[dict[str, object]] = []
    passed = 0
    with httpx.Client(timeout=120) as client:
        for question, expected, keyword in CASES:
            t0 = time.perf_counter()
            body = client.post(f"{BASE_URL}/query", json={"question": question}).json()
            latency = round(time.perf_counter() - t0, 2)
            top = max((s["score"] for s in body["sources"]), default=0.0)
            ok = body["status"] == expected and (
                not keyword or keyword.lower() in body["answer"].lower()
            )
            passed += int(ok)
            rows.append(
                {
                    "question": question,
                    "expected_status": expected,
                    "status": body["status"],
                    "needs_human": body["needs_human"],
                    "top_score": top,
                    "n_sources": len(body["sources"]),
                    "keyword": keyword,
                    "pass": ok,
                    "latency_s": latency,
                    "answer_model": health.get("answer_model"),
                    "answer": body["answer"].replace("\n", " ")[:300],
                }
            )
            print(f"{'PASS' if ok else 'FAIL'} [{body['status']:>22}] {question}")
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{passed}/{len(CASES)} passed -> {OUT}")


if __name__ == "__main__":
    main()
