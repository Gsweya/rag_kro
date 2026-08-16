# services/ingestion — Centralized Knowledge Ingestion Pipeline

The **one place** documents and products become RAG knowledge. It is deliberately a
standalone deployment so ingestion happens **once, centrally**, for every tenant —
never repeated per user runtime (spec sections 6 + 6b).

```
upload (PDF/image) ──► chunk ──► embed ──► Qdrant (payload: tenant_id, type, doc_id)
product row        ──► text-doc ─► embed ──► Qdrant (payload: tenant_id, type=product)
```

## How it fits the architecture

- **Writes** to Qdrant (the shared index) and MinIO (raw files).
- **Does not** answer chat traffic; that is `services/rag`.
- **Does not** run inside the chat runtime — it is a separate container in the `dev`
  profile, reachable internally (`ingestion:8001`).
- The Celery worker (`services/worker`) schedules periodic reconciliation on top of the
  same endpoints (`sync_products`, `sync_documents`, hash-based change detection).

> **Reachability.** `ingestion` is internal-only. The browser uploads to `api`
> (`POST /documents/upload`, tenant-header authenticated) which proxies the file here
> with the shared `INTERNAL_API_KEY` — the tenant boundary is never bypassed from the UI.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| POST | `/ingest/document` | multipart `file` + `tenant_id` + `doc_type` (pdf\|image) → chunk+embed+store |
| POST | `/ingest/product` | form `product_id` + `tenant_id` → re-embed single row (6b) |

All endpoints require header `X-Internal-Key` equal to `INTERNAL_API_KEY`.

## Flow inside `/ingest/document`

1. Raw bytes saved to MinIO (`{tenant_id}/documents/{filename}`).
2. Text extracted:
   - PDF → `pdfplumber` (falls back to `pypdf`)
   - image → BLIP caption via HF Inference API, else local `transformers`, else a
     placeholder caption (raw image kept in MinIO regardless).
3. `RecursiveCharacterTextSplitter`-style chunking (`app/chunking.py`, no LangChain dep).
4. Embed with `EMBEDDINGS_BACKEND=local` (sentence-transformers) or `hf`.
5. Upsert into Qdrant with filters `{tenant_id, type, doc_id, chunk_index, source, storage_path}`.
6. Create a `documents` row (status `indexed`).

## Change detection (6b)

- `products` carry `emb_hash`; the worker compares a hash of
  `(id, name, price, stock, description, is_active)` and only re-embeds diffs.
- Delete/product removal → call `delete_by_metadata(tenant_id, type=..., doc_id=...)`
  in `rag_kro_shared.vectors.VectorStore` (Qdrant filtered delete).

## Configuration (from `.env`)

| Variable | Default | Notes |
|---|---|---|
| `INGESTION_API_URL` | `http://ingestion:8001` | self-reference for outbound calls |
| `EMBEDDINGS_BACKEND` | `local` | `local` = sentence-transformers ($0), `hf` = HF API |
| `HF_EMBEDDINGS_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | both backends |
| `CHUNK_SIZE`/`CHUNK_OVERLAP` | 1000/200 | splitter params |
| `MINIO_*` | — | object storage creds |
| `INTERNAL_API_KEY` | — | shared secret for X-Internal-Key |

## Deployment

Container `rag_kro_ingestion`, image built from `services/ingestion/Dockerfile`,
port **8001** (internal only). Include it with the `dev` profile:

```bash
docker compose --profile dev up -d --build ingestion
```

## Adding a new source type

1. Add a parser in `app/ingesters/` (e.g. `csv_ingester.py`).
2. Route `doc_type` to it in `app/main.py::ingest_document`.
3. Add the type constraint to `documents.type` CHECK in `infra/postgres/init/001_schema.sql`.

## Test

No committed tests yet — exercise via Swagger at `http://localhost:8001/docs`
or `curl -X POST -F file=@doc.pdf -F tenant_id=… -F doc_type=pdf http://localhost:8001/ingest/document -H "X-Internal-Key: …"`.