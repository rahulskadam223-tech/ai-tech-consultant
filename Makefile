.PHONY: setup run run-task1 ingest test eval stop

PY1 = task1-knowledge-brain/.venv/bin/python

setup:
	cd task1-knowledge-brain && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Start every service. Task 2 and Task 3 lines get added when those tasks exist.
run: run-task1

run-task1:
	cd task1-knowledge-brain && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001

# First-time crawl + embed + captions (same code path as POST /ingest/refresh).
ingest:
	cd task1-knowledge-brain && .venv/bin/python -m app.ingest

test:
	cd task1-knowledge-brain && .venv/bin/python -m pytest -q

eval:
	$(PY1) evals/eval_task1.py

stop:
	-pkill -f "uvicorn app.main:app" || true
