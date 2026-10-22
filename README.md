# AI Tech Consultant (capstone)

Three small Python 3.11 services sharing one `.env` and versioned prompts in `prompts/v1/`.

| Folder | What | Status |
|---|---|---|
| `task1-knowledge-brain/` | FastAPI RAG over the Brilliant Directories support docs (SQLite + Chroma + Claude) | done |
| `task2-inbox-agent/` | Inbox agent calling Task 1 over HTTP, Streamlit review UI | todo |
| `task3-meeting-to-scope/` | 5 agents turning meeting notes into a scope, Streamlit UI | todo |
| `evals/` | One script per task, each writes `evals/<task>/results.csv` | task1 |

## Quick start

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY
make setup                      # venv + deps for task1
make ingest                     # crawl MAX_PAGES, embed, caption MAX_IMAGES screenshots (resumable)
make run                        # starts task1 on :8001
make test                       # pytest
make eval                       # evals/eval_task1.py -> evals/task1/results.csv
```

Task 1 endpoints: `POST /query`, `POST /escalations`, `POST /escalations/{id}/resolve`,
`POST /ingest/refresh`, `GET /health`. Docs at http://localhost:8001/docs.
