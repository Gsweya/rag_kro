# services/rag — RAG Module (retrieval + generation)

Standalone, stateless service that turns an incoming user message + conversation history
into a grounded answer, using the tenant-scoped index that `services/ingestion` maintains.

## Responsibilities

- **Retrieve**: Qdrant similarity search filtered by `tenant_id` (`RAG retrieves top_k`).
- **Context build**: latest conversation turns + `contact_context` notes (who the contact
  is, their tone, prior topics/orders) — passed in by the API service.
- **Generate**: calls the LLM backend abstraction with the grounded prompt.
- **Return** `answer` plus `sources` for the admin drill-in debug view.

It **owns no writes** to Qdrant and **owns no user data** of its own beyond what it reads —
ingestion is elsewhere by design so knowledge is indexed once for all tenants.

## LLM backends (swap with one env flag)

`LLM_BACKEND` values (see `rag_kro_shared.llm.LLMClient`):

| Value | Provider | Env additionally needed |
|---|---|---|
| `hf` (default) | HF Inference API (free tier) | `HF_INFERENCE_MODEL`, optional `HF_TOKEN` |
| `ollama` | self-hosted, fully private | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| `openai_compatible` | any OpenAI-shaped endpoint | `OPENAI_COMPATIBLE_*` |

Embeddings default to local `sentence-transformers` so retrieval never hits rate limits.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| POST | `/chat` | grounded answer; requires `X-Internal-Key: INTERNAL_API_KEY` |

Request body:

```json
{
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "conversation_history": [{"role": "user", "content": "do you sell X?"}],
  "contact_context": "Name: Ada. Notes: asks about pricing, likes short replies.",
  "system_prompt": "optional overrides default"
}
```

Response: `{ "answer": "…", "sources": [{title, doc_id, type, score}] }`.

## Flow

1. Last user message is embedded with the same embedder that created the index
   (must match — both default to `all-MiniLM-L6-v2`).
2. Qdrant search `{query, filter: tenant_id, limit: top_k}`.
3. System prompt + retrieved context + history are assembled into `messages`.
4. `LLMClient.chat()` dispatches to the configured backend.
5. Answer + source metadata returned; the API service logs it with the outbound message.

## Deployment

Container `rag_kro_rag`, built from `services/rag/Dockerfile`, port **8002** (internal
only). Included via the `dev` profile:

```bash
docker compose --profile dev up -d --build rag
```

Scale horizontally (it is stateless) behind a load balancer pointed at `:8002`.

## Configuration (from `.env`)

| Variable | Default | Notes |
|---|---|---|
| `LLM_BACKEND` | `hf` | see table above |
| `HF_INFERENCE_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | swap for current free-tier availability |
| `RETRIEVE_TOP_K` | 4 | number of chunks retrieved |
| `RAG_SYSTEM_PROMPT` | default persona | tenant persona can override per-request |
| `EMBEDDINGS_BACKEND` | must match ingestion | keep both `local` (or both `hf`) |

## Verification

```bash
curl -s http://localhost:8002/health
curl -s -X POST http://localhost:8002/chat \
  -H 'Content-Type: application/json' -H 'X-Internal-Key: <key>' \
  -d '{"tenant_id":"00000000-0000-0000-0000-000000000001","conversation_history":[{"role":"user","content":"what is your cheapest product?"}]}'
```

If retrieval returns nothing useful, check that the ingestion service has indexed
products/docs into the same collection.