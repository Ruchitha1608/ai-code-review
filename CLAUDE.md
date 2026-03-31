# AI Code Review Bot

## Architecture

A GitHub webhook-driven bot that reviews pull requests using Claude (claude-sonnet-4-6) and improves over time via developer feedback.

```
GitHub Webhook → POST /webhook → Celery task → GitHub Diff → Claude API → GitHub Review
                                                                              ↓
                                                                         Postgres (Review, Comment)
                                                                              ↓
Developer feedback → POST /feedback → Celery task → Postgres (Feedback)
                                                          ↓
                                              Nightly beat task → few-shot prompt file
                                                                       ↓
                                                              Next review uses new prompt
```

## Services

| Service | Command | Purpose |
|---------|---------|---------|
| `api` | `uvicorn app.main:app` | FastAPI HTTP server |
| `worker` | `celery worker` | Runs `review_pr` and `ingest_feedback` tasks |
| `beat` | `celery beat` | Schedules nightly `update_prompt_version` |
| `postgres` | postgres:16 | Stores reviews, comments, feedback, prompt versions |
| `redis` | redis:7 | Celery broker and result backend |

## Endpoints

- `POST /webhook` — GitHub webhook receiver (validates HMAC-SHA256)
- `POST /feedback` — Record accepted/rejected/ignored signal for a comment
- `GET /health` — Checks Postgres and Redis connectivity
- `GET /metrics` — Prometheus metrics

## Database Models

- `Review` — one record per PR review run
- `Comment` — individual LLM-generated comments (file, line, severity, body)
- `Feedback` — developer signals (accepted / rejected / ignored)
- `PromptVersion` — versioned prompt files written by the nightly task

## Feedback Loop

1. LLM posts inline comments → persisted as `Comment` rows
2. Developer calls `POST /feedback` with signal → `Feedback` row created
3. Nightly Celery beat task (2 AM UTC) queries accepted comments from past 30 days
4. Builds few-shot prompt from their `diff_snippet` + `body`
5. Writes `prompts/prompt_vYYYYMMDD_HHMMSS.txt`, marks it active in `prompt_versions`
6. Next `review_pr` call loads the active prompt file

## Development

```bash
# Copy env and fill in secrets
cp .env.example .env

# Start core services
docker compose up -d

# Start with Grafana + Prometheus
docker compose --profile observability up -d

# Run tests
pip install -r requirements.txt
pytest tests/

# Tail worker logs
docker compose logs -f worker
```

## Metrics (Prometheus)

| Metric | Labels | Description |
|--------|--------|-------------|
| `webhook_received_total` | event_type, action | Webhooks received |
| `review_posted_total` | repo | Reviews posted to GitHub |
| `llm_latency_seconds` | — | LLM call duration histogram |
| `feedback_signal_total` | signal | Feedback signals by type |

## Environment Variables

See `.env.example` for all required variables.
