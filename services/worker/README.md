# services/worker — Celery Async Jobs

Background execution for everything that isn't a request/response: embedding sync,
summarization, reminders and external notifications (spec sections 4.7, 5, 6b, 8).

## What it runs

| Beat schedule | Task | What it does |
|---|---|---|
| every 60s | `sync_products` | hash-based change detection on `products` → re-embed diffs via ingestion |
| every 60m | `sync_documents` | sweep `documents` stuck in `pending` |
| every 30m | `summarize_contacts` | condense last 30 msgs per contact into `contact_profiles.notes` |
| every 60s | `notify_reminders` | fire due `reminders` through the right gateway |
| every 5m | `health_beat` | writes `worker:last_beat` to Redis for the admin panel |

The beat scheduler is baked into the same process for MVP simplicity
(`celery -A app.celery_app.app worker -B …`). Split the scheduler later if needed.

## Why Celery

Redis-backed queue means bursts of uploads, reminders and summaries queue cleanly and
never block the chat pipeline (the API service enqueues work rather than doing it inline).

## Structure

```
app/
├── celery_app.py            # Celery app + beat_schedule
└── tasks/
    ├── embeddings_sync.py   # product-sync + doc-sweep (6b change detection)
    ├── summarize.py         # contact profile re-summarization
    ├── reminders.py         # due-reminder firing + health_beat
    └── notifications.py     # (task registry wiring)
```

## Configuration

| Variable | Use |
|---|---|
| `CELERY_BROKER_URL` | redis db 1 |
| `CELERY_RESULT_BACKEND` | redis db 2 |
| `INGESTION_API_URL`/`INGEST_API_KEY` | product re-embed calls |
| `INTERNAL_API_KEY` | authenticating gateway `/send` calls |
| `LLM_*` | summarization model |

## Deployment

```bash
docker compose --profile dev up -d --build worker
```

One worker container runs both consumers and the scheduler. If queues grow:
`celery -A app.celery_app.app worker -Q default --concurrency=4`.

## Adding a task

1. Add a function decorated `@app.task(name="app.tasks.<module>.<name>")` in `app/tasks/`.
2. Reference it in `include=[...]` in `celery_app.py`.
3. Add a `beat_schedule` entry if periodic.
4. Trigger it from `api` with `.delay(...)` through Celery's shared client
   (`rag_kro_shared` provides broker URL config).