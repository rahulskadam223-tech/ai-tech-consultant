.PHONY: setup run run-task1 run-task2 ingest test eval eval-task2 stop

PY1 = task1-knowledge-brain/.venv/bin/python
PY2 = task2-inbox-agent/.venv/bin/python

setup:
	cd task1-knowledge-brain && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd task2-inbox-agent && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Start every service in parallel (Task 3 gets added when it exists).
run:
	$(MAKE) -j2 run-task1 run-task2

run-task1:
	cd task1-knowledge-brain && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001

run-task2:
	cd task2-inbox-agent && .venv/bin/streamlit run app.py --server.port 8502 --server.headless true

# First-time crawl + embed + captions (same code path as POST /ingest/refresh).
ingest:
	cd task1-knowledge-brain && .venv/bin/python -m app.ingest

test:
	cd task1-knowledge-brain && .venv/bin/python -m pytest -q
	cd task2-inbox-agent && .venv/bin/python -m pytest -q

eval:
	$(PY1) evals/eval_task1.py

eval-task2:
	$(PY2) evals/eval_task2.py

stop:
	-pkill -f "uvicorn app.main:app" || true
	-pkill -f "streamlit run app.py" || true
