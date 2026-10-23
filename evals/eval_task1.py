"""Eval for Task 1: 20 fixed questions via POST /query -> evals/task1/results.csv.

Usage: task1-knowledge-brain/.venv/bin/python evals/eval_task1.py [TASK1_URL]
The model is whatever the running server reports in /health (ANSWER_MODEL). Rows for that
model replace earlier rows for the same model, so run once per model to compare them.

Case kinds: direct (one article answers it), two_article (needs >= 2 sources), caption_only
(answer exists only in a screenshot caption), abstain (off-topic, must not guess),
malformed (bad input must be rejected or abstained, never a 5xx).
"""
from __future__ import annotations

import csv
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TASK1_URL", "http://localhost:8001")
OUT = Path(__file__).parent / "task1" / "results.csv"
PRICES: dict[str, tuple[float, float]] = {  # USD per 1M input / output tokens (Anthropic list price)
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}

# (id, kind, question, keywords any-of that must appear in an answered reply)
CASES: list[tuple[str, str, str, str]] = [
    ("D01", "direct", "Can I send a mass email campaign to an imported contact list?", "spam"),
    ("D02", "direct", "What are the recommended image sizes for the homepage background image, profile image and logo?", "image|px"),
    ("D03", "direct", "How do I install the Google Analytics tracking code?", "analytics"),
    ("D04", "direct", "How do I set up Verifone as my payment gateway?", "verifone"),
    ("D05", "direct", "How do I create a folder in the Media Manager?", "folder"),
    ("D06", "direct", "How do I edit the website email signature?", "signature"),
    ("D07", "direct", "How does search result ordering and distance sorting work?", "distance|sort"),
    ("D08", "direct", "How do I enable maps on my site with the Google Maps API?", "api"),
    ("D09", "direct", "How do I add custom tabs to member profile pages using HTML?", "tab"),
    ("D10", "direct", "How do I set up one time payments?", "payment"),
    ("T01", "two_article", "How do I connect a custom domain and get an SSL certificate for it?", "ssl|certificate"),
    ("T02", "two_article", "How do I import categories via a CSV file, and how do members then select their categories?", "categor"),
    ("T03", "two_article", "How do I create a new email template and edit the existing email templates?", "template"),
    ("C01", "caption_only", "What color is the lightbulb icon in the Brilliant Knowledge logo?", "yellow"),
    ("C02", "caption_only", "How many social media input fields are on the Social Media Links settings page?", "ten|10"),
    ("A01", "abstain", "What is the capital of France?", ""),
    ("A02", "abstain", "Write me a poem about databases.", ""),
    ("A03", "abstain", "How do I configure Kubernetes ingress for my cluster?", ""),
    ("M01", "malformed", "", ""),
    ("M02", "malformed", "asdf qwerty ;;; <<<>>> 12345 !!! ??? ~~~", ""),
]


def judge(kind: str, http_status: int, body: dict[str, object] | None, keywords: str) -> bool:
    if kind == "malformed":
        return http_status == 422 or (http_status == 200 and body is not None and body["status"] == "insufficient_evidence")
    if http_status != 200 or body is None:
        return False
    if kind == "abstain":
        return body["status"] == "insufficient_evidence" and body["needs_human"] is True
    answered = body["status"] == "answered"
    answer = str(body["answer"]).lower()
    has_kw = not keywords or any(k in answer for k in keywords.split("|"))
    if kind == "two_article":
        return answered and has_kw and len({s["url"] for s in body["sources"]}) >= 2  # type: ignore[index]
    return answered and has_kw


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    health = httpx.get(f"{BASE_URL}/health", timeout=30).json()
    model = str(health.get("answer_model"))
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    rows: list[dict[str, object]] = []
    with httpx.Client(timeout=180) as client:
        for case_id, kind, question, keywords in CASES:
            t0 = time.perf_counter()
            r = client.post(f"{BASE_URL}/query", json={"question": question})
            latency_ms = round((time.perf_counter() - t0) * 1000)
            body = r.json() if r.status_code == 200 else None
            usage = (body or {}).get("usage") or {}
            inp, out = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            ok = judge(kind, r.status_code, body, keywords)
            sources = (body or {}).get("sources") or []
            rows.append(
                {
                    "case_id": case_id,
                    "kind": kind,
                    "question": question,
                    "model": model,
                    "http_status": r.status_code,
                    "status": (body or {}).get("status", ""),
                    "n_sources": len({s["url"] for s in sources}),
                    "top_score": max((float(s["score"]) for s in sources), default=0.0),
                    "pass": ok,
                    "latency_ms": latency_ms,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cost_usd": round(inp / 1e6 * price_in + out / 1e6 * price_out, 6),
                    "answer": str((body or {}).get("answer", r.text)).replace("\n", " ")[:300],
                }
            )
            print(f"{'PASS' if ok else 'FAIL'} {case_id} [{kind:>12}] {(body or {}).get('status', r.status_code)}  {latency_ms} ms")

    # Merge with rows from other models already in the file.
    existing: list[dict[str, object]] = []
    if OUT.exists():
        with OUT.open(newline="", encoding="utf-8") as f:
            existing = [dict(r) for r in csv.DictReader(f) if r.get("model") != model]
    all_rows = sorted(existing + rows, key=lambda r: (str(r["model"]), str(r["case_id"])))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    passed = sum(1 for r in rows if r["pass"])
    med = statistics.median(int(r["latency_ms"]) for r in rows)
    cost = sum(float(r["cost_usd"]) for r in rows)
    print(f"\n{model}: {passed}/{len(rows)} passed, median {med:.0f} ms, ${cost:.4f} total -> {OUT}")


if __name__ == "__main__":
    main()
