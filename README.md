<h1 align="center">rag_kro</h1>
<p align="center">
  <strong>WhatsApp + Instagram RAG Assistant</strong> — RAG-grounded auto-responder with
  allowlist, pause/resume, order handling and cross-platform memory. Zero-cost stack.
</p>

<p align="center">
  <img alt="python" src="https://img.shields.io/badge/python-3.12-blue" />
  <img alt="node" src="https://img.shields.io/badge/node-20-green" />
  <img alt="license" src="https://img.shields.io/badge/license-MIT-lightgrey" />
  <img alt="docker" src="https://img.shields.io/badge/docker-compose-blue" />
</p>

---

## What this is

A multi-tenant (no-login for now) tool that connects WhatsApp (and optionally Instagram),
lets you define an allowlist of senders, and uses an LLM **grounded on your own documents,
products and prior chat history** to auto-respond while adapting its tone per contact.
You can **pause/resume the bot per conversation**.

The whole thing runs on free/OSS pieces: Baileys, instagrapi, Qdrant, Postgres, Redis,
MinIO, and the HuggingFace Inference API free tier (or a self-hosted Ollama).

> **⚠️ ToS / production risk.** Baileys (WhatsApp multi-device protocol) and unofficial
> Instagram access violate platform ToS and accounts risk action. This is a **prototype**.
> See [docs/SECURITY.md](docs/SECURITY.md) before anything public.

---

## Screenshot-free quick tour of the layout

```
rag_kro/
├── docker-compose.yml              # one command to run the whole stack
├── .env.example                    # copy → .env, tweak secrets
├── Makefile                        # make up / make logs / make key …
├── docs/                           # architecture, deployment, security guides
├── packages/
│   └── python/rag_kro_shared/      # shared lib (config, db, crypto, llm, vectors)
├── services/                       # every deployable unit has its own home
│   ├── api/                        # orchestration: webhooks, allowlist, pause/resume
│   ├── rag/                        # RAG: retrieval + generation (HF/Ollama)
│   ├── ingestion/                  # CENTRALIZED ingestion: pdf/image/product → Qdrant
│   ├── worker/                     # Celery + beat: sync, summarize, reminders, notify
│   ├── wa-gateway/                 # WhatsApp connectivity (Node + Baileys)
│   ├── ig-gateway/                 # Instagram connectivity (Python + instagrapi)
│   └── web/                        # Next.js dashboard (Geist font)
└── infra/
    └── postgres/init/001_schema.sql # schema (tenant-scoped everywhere)
```

Each service has its **own Dockerfile, its own README, and its own responsibility**.
Every module is documented in `docs/` and inside its folder — no monolith dump.

---

## How ingestion is centralized (not per-user)

Unlike naive setups where every running instance ingests its own copy of knowledge,
**ingestion runs once, centrally**, in [`services/ingestion`](services/ingestion):

- **One shared Qdrant collection** + one embedding model cache.
- Tenants upload PDFs/images/products; the ingestion service chunks, embeds, and
  writes vectors tagged with `tenant_id`.
- Every tenant's RAG runtime queries that **same shared index**.
- The Celery worker continuously reconciles the index via hash-based change detection
  (`services/worker/app/tasks/embeddings_sync.py`) — no one re-ingests per runtime.

Your instance picks up knowledge instantly because retrieval is shared, not duplicated.

---

## Quick start (local dev)

```bash
cp .env.example .env        # set POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, a Fernet key…
make key                    # generate FERENCE_SECRET_KEY, paste into .env
make up                     # full stack: core + API + ingestion + RAG + worker + WA gateway (no IG)
```

| Service | URL |
|---|---|
| Dashboard (Next.js) | http://localhost:3000 |
| API (FastAPI) | http://localhost:8000/docs |
| Ingestion | http://localhost:8001 |
| RAG | http://localhost:8002 |
| Qdrant | http://localhost:6333/dashboard |
| MinIO console | http://localhost:9001 |

Then: **Products** → add a few → **Documents** → upload a PDF → **Allowlist** → add a
phone number → **Connect WhatsApp** → scan the QR → message from an allowed number.

> For dev file-watching the `api`, `ingestion`, `rag`, `worker` and `web` services
> mount their sources read-write; a restart picks up changes.

---

## LLM backend (free tier)

Default: **HuggingFace Inference API** (`LLM_BACKEND=hf`).

| Backend | Env config | Cost |
|---|---|---|
| HF Inference API | `LLM_BACKEND=hf`, `HF_INFERENCE_MODEL=Qwen/Qwen2.5-7B-Instruct` | $0, rate-limited |
| Ollama (self-hosted) | `LLM_BACKEND=ollama`, `OLLAMA_MODEL=llama3.2` + `make up-ollama` | $0, private |
| Any openAI-compatible | `LLM_BACKEND=openai_compatible` + base URL + key | depends |

Embeddings: `EMBEDDINGS_BACKEND=local` (sentence-transformers, $0, no API limits)
or `hf` (HF `all-MiniLM-L6-v2`).

---

## Repository map / docs

| Doc | What it covers |
|---|---|
| [README.md](README.md) | this file |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | containers, data flow, message pipeline |
| [docs/SETUP.md](docs/SETUP.md) | full setup, env reference, first-run checklist |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | docker compose profiles, TLS, production hardening |
| [docs/SECURITY.md](docs/SECURITY.md) | auth-less exposure, session encryption, ToS risk |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | dev loop, testing, adding a module |
| [services/ingestion/README.md](services/ingestion/README.md) | the centralized ingestion pipeline |
| [services/rag/README.md](services/rag/README.md) | the RAG module and its deployment |
| [services/api/README.md](services/api/README.md) | message orchestration |
| [services/worker/README.md](services/worker/README.md) | async jobs |
| [services/wa-gateway/README.md](services/wa-gateway/README.md) | WhatsApp gateway |
| [services/ig-gateway/README.md](services/ig-gateway/README.md) | Instagram gateway |
| [services/web/README.md](services/web/README.md) | dashboard |

---

## Feature status

| Feature | Status |
|---|---|
| Postgres schema, tenant-scoped | ✅ |
| Docker Compose skeleton + profiles | ✅ |
| Centralized ingestion (PDF/image/product) | ✅ |
| RAG chain with HF Inference / Ollama | ✅ |
| Message flow: allowlist → context → reply | ✅ |
| Pause/resume per conversation | ✅ |
| Product DB sync (hash change detection) | ✅ |
| Contact-profile summarization (worker) | ✅ |
| Reminders + SMS/email/webhook notifications | ✅ |
| WhatsApp Gateway (Baileys QR connect + webhook) | ✅ |
| Instagram Gateway (instagrapi) | ✅ (prototype risk) |
| Next.js dashboard | ✅ |
| Cross-platform identity resolution | partial (manual + same-identifier merge) |
| Image captioning | partial (needs HF token, else placeholder) |

---

## License

MIT — see [LICENSE](LICENSE). Use commercially at your own platform-ToS risk.