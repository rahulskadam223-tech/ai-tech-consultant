# AI Tech Consultant (capstone)

Three small Python 3.11 services that act as an AI consultant for a Brilliant Directories
website business: a documentation brain, an inbox agent that drafts replies, and a
meeting-to-scope pipeline that turns call transcripts into a proposal. They share one `.env`
and one set of versioned prompts in `prompts/v1/`.

| Folder | What | Port |
|---|---|---|
| `task1-knowledge-brain/` | FastAPI RAG over the Brilliant Directories support docs. SQLite tracks pages, Chroma holds chunks, Claude answers only from retrieved text and abstains otherwise. | 8001 |
| `task2-inbox-agent/` | Classifies customer emails, looks up product questions in Task 1 over HTTP, drafts replies, and learns per-category auto-send eligibility from human review. Streamlit UI. | 8502 |
| `task3-meeting-to-scope/` | Five agents: transcript -> requirements -> feasibility (via Task 1) -> scope -> estimate -> proposal, plus change reports for follow-up meetings. Streamlit UI. | 8503 |
| `evals/` | One eval script per task. Results are committed in `evals/<task>/results.csv`. | |
| `prompts/v1/` | Every prompt as a Markdown file, loaded from disk at runtime. | |

Docs: [DESIGN.md](DESIGN.md) (architecture and decisions), [EVALS.md](EVALS.md) (method and
results), [AI_LOG.md](AI_LOG.md) (how AI was used to build this and what went wrong).

## Quick start

```bash
cp .env.example .env   # ANTHROPIC_API_KEY, or AWS_BEARER_TOKEN_BEDROCK + AWS_REGION for Bedrock
make setup             # one venv per task, installs requirements
make ingest            # Task 1: crawl MAX_PAGES articles, embed, caption MAX_IMAGES screenshots (resumable)
make run               # task1 :8001, task2 UI :8502, task3 UI :8503   (or make run-task1 / run-task2 / run-task3)
make test              # pytest for all three tasks (43 tests)
make eval              # Task 1 -> evals/task1/results.csv  (run once per ANSWER_MODEL to compare models)
make eval-task2        # Task 2 -> evals/task2/results.csv  (40 emails, haiku vs sonnet)
make eval-task3        # Task 3 -> evals/task3/results.csv  (20 checks, analyst sonnet vs haiku)
make stop
```

Open http://localhost:8502 for the inbox agent and http://localhost:8503 for meeting-to-scope.
Task 1 API docs are at http://localhost:8001/docs.

Try Task 1 directly:

```bash
curl -s -X POST http://localhost:8001/query -H 'Content-Type: application/json' \
  -d '{"question":"Can I send a mass email campaign to an imported contact list?"}'
```

## Task 1 endpoints

| Endpoint | Purpose |
|---|---|
| `POST /query` | `{answer, status, sources, needs_human, model, usage}`. `status` is `answered` or `insufficient_evidence`. |
| `POST /escalations` | Save a question for a human expert. |
| `POST /escalations/{id}/resolve` | Expert answer is stored as a new chunk, so the next similar question is answered. |
| `POST /ingest/refresh` | Re-read the sitemap, re-process changed pages, mark removed pages inactive. Returns added/updated/removed/failed counts. |
| `GET /health` | Pages done and pending, chunk count, provider and model names. |

## Claude backend

If `AWS_BEARER_TOKEN_BEDROCK` is set, all tasks call Claude on Amazon Bedrock in `AWS_REGION`
(`global.anthropic.*` inference profiles). Otherwise they use the Anthropic API with
`ANTHROPIC_API_KEY`. Model names in `.env` stay short (`claude-haiku-4-5`, `claude-sonnet-4-5`)
and each task's `claude_client.py` maps them. `GET /health` on Task 1 shows the active provider.

## Requirements

Python 3.11, macOS or Linux. Docker is optional: `docker-compose.yml` runs Task 1. The first
`make ingest` downloads the `all-MiniLM-L6-v2` sentence-transformers model.
