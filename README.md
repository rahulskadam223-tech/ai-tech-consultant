# AI Tech Consultant (capstone)

Three small Python 3.11 services sharing one `.env` and versioned prompts in `prompts/v1/`.

| Folder | What | Status |
|---|---|---|
| `task1-knowledge-brain/` | FastAPI RAG over the Brilliant Directories support docs (SQLite + Chroma + Claude) | done |
| `task2-inbox-agent/` | Inbox agent calling Task 1 over HTTP, Streamlit review UI on :8502 | done |
| `task3-meeting-to-scope/` | 5 agents turning meeting notes into a scope, Streamlit UI | todo |
| `evals/` | One script per task, each writes `evals/<task>/results.csv` | task1 |

## Quick start

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY, or AWS_BEARER_TOKEN_BEDROCK + AWS_REGION for Bedrock
make setup                      # venv + deps for task1
make ingest                     # crawl MAX_PAGES, embed, caption MAX_IMAGES screenshots (resumable)
make run                        # task1 on :8001 and task2 UI on :8502 (or run-task1 / run-task2)
make test                       # pytest
make eval                       # evals/eval_task1.py -> evals/task1/results.csv
make eval-task2                 # classify 40 emails with haiku+sonnet -> evals/task2/results.csv
```

Task 1 endpoints: `POST /query`, `POST /escalations`, `POST /escalations/{id}/resolve`,
`POST /ingest/refresh`, `GET /health`. Docs at http://localhost:8001/docs.

## Claude backend

If `AWS_BEARER_TOKEN_BEDROCK` is set, both tasks call Claude on Amazon Bedrock in `AWS_REGION` (legacy
`bedrock-runtime` endpoint, `global.anthropic.*` inference profiles, body version `bedrock-2023-05-31`).
Otherwise they use the Anthropic API with `ANTHROPIC_API_KEY`. Model names in `.env` stay short
(`claude-haiku-4-5`, `claude-sonnet-4-5`); `app/claude_client.py` maps them. `GET /health` shows the provider.
