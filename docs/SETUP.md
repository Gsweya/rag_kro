# Setup Guide

## Prerequisites

- Docker + Docker Compose v2 (tested with Compose 5.x)
- `make` (optional; commands below work without it)

## 1. Clone and configure

```bash
git clone git@github.com:Gsweya/rag_kro.git
cd rag_kro

cp .env.example .env
```

Edit `.env` and at minimum set:

| Variable | Notes |
|---|---|
| `POSTGRES_PASSWORD` | any strong value |
| `MINIO_ROOT_PASSWORD` | any strong value (≥8 chars) |
| `FERENCE_SECRET_KEY` | Fernet key for DB session-credential encryption |
| `ADMIN_TOKEN` | static token guarding the dashboard (no-auth mode) |
| `INTERNAL_API_KEY` | shared secret for internal service calls |
| `HF_TOKEN` | optional, unlocks HF free-tier model availability |
| `SMTP_USER`/`SMTP_PASSWORD` | optional order/escalation emails |

Generate a Fernet key:

```bash
make key        # prints a 44-char key; paste into FERENCE_SECRET_KEY
```

## 2. Start the stack

```bash
make up         # core + dev services + wa-gateway
```

Equivalent raw form:

```bash
docker compose --profile dev --profile wa up -d --build
```

Ollama (self-hosted LLM) optional:

```bash
make up-ollama  # pulls llama3.2 into the ollama container
```

Instagram optional (use with ToS eyes open, see SECURITY.md):

```bash
make up-ig
```

## 3. First-run checklist

1. **Database** initialised automatically by `infra/postgres/init/001_schema.sql`
   (creates a default tenant).
2. **Products** → http://localhost:3000/products → add a couple of products.
   (This also enqueues a re-embed into Qdrant via the ingestion service.)
3. **Documents** → upload a PDF. Status should go `pending → indexed`.
4. **Allowlist** → add a phone number you'll test from.
5. **Connect WhatsApp** → scan the QR from the WhatsApp app
   (Settings → Linked Devices → Link a Device).
6. Message the number from the allowlisted phone. The bot replies grounded in your docs.

## 4. Verify pieces are healthy

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

Useful queries:

```bash
# check indexed vectors
curl -s http://localhost:6333/collections/rag_kro_vectors | python3 -m json.tool

# check the worker log
docker compose logs -f worker
```

## 5. Env reference (all variables)

`env | grep '^[A-Z]' | sort` — but in short, every variable in `.env.example` has a
`# comment` describing its purpose. Keep `.env` in sync with `.env.example`.

## 6. Local-only dev tips

- API docs: http://localhost:8000/docs (FastAPI Swagger), same for `:8001` and `:8002`.
- Services `api`, `ingestion`, `rag`, `worker`, `web` mount their source dirs read-write
  and run with reloaders, so edits apply without rebuild.
- Want to try HF Inference without a key? `HF_TOKEN` empty may still hit free
  serverless endpoints for popular models; set it if you hit 401/429.

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `POSTGRES_PASSWORD` error on `up` | `.env` missing or variable not set; copy `.env.example` |
| Qdrant collection missing | ingestion service creates it lazily on first upsert |
| RAG returns empty/off-topic | embeddings backend local not downloaded yet; watch ingestion logs |
| Worker task stuck | Redis not healthy yet; `docker compose restart worker` |
| WhatsApp QR never shown | no session yet; check wa-gateway logs, scan within re-connect window |
| HF 429/503 | free tier rate limit; set `LLM_BACKEND=ollama` and run `make up-ollama` |