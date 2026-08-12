# rag_kro documentation

Landing page for all documentation.

## Top-level guides

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | containers, message flow, centralized ingestion, scaling |
| [SETUP.md](SETUP.md) | prerequisites, env config, first-run checklist, troubleshooting |
| [DEPLOYMENT.md](DEPLOYMENT.md) | compose profiles, reverse proxy/TLS, hardening, backups |
| [SECURITY.md](SECURITY.md) | no-auth exposure, session encryption, ToS risk, scoping |
| [CONTRIBUTING.md](CONTRIBUTING.md) | dev loop, conventions, testing, adding a module |
| [SPEC.md](SPEC.md) | the original implementation spec this repo implements |

## Per-module docs

| Service | README |
|---|---|
| Centralized ingestion pipeline | [services/ingestion/README.md](../services/ingestion/README.md) |
| RAG module (retrieval + generation) | [services/rag/README.md](../services/rag/README.md) |
| API orchestration (webhooks, allowlist, pause/resume) | [services/api/README.md](../services/api/README.md) |
| Worker (Celery + beat async jobs) | [services/worker/README.md](../services/worker/README.md) |
| WhatsApp gateway (Baileys) | [services/wa-gateway/README.md](../services/wa-gateway/README.md) |
| Instagram gateway (instagrapi) | [services/ig-gateway/README.md](../services/ig-gateway/README.md) |
| Dashboard (Next.js) | [services/web/README.md](../services/web/README.md) |

## Shared library

- `packages/python/rag_kro_shared` — config, DB/session, crypto, LLM client, embeddings,
  Qdrant vector store, internal HTTP client. Every Python service depends on it.