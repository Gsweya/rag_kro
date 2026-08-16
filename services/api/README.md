# services/api — Orchestration

The coordination brain: ingests gateway webhooks, enforces policy, builds context,
calls the RAG service, sends replies, and records everything (spec sections 4–5).

## Responsibilities

- Receive inbound messages from `wa-gateway`/`ig-gateway` at `POST /webhook/message`.
- Enforce the **allowlist** (`allowed_senders`, incl. `'*'`).
- Respect **pause/resume** (`conversations.status`) — store only when paused.
- **Identity resolution** (`services/context_builder.resolve_contact`): link profiles
  across platforms when identifiers match; safe default = manual linking.
- Build RAG context: Redis short-term memory + Postgres long-term history (shared
  across a resolved contact's WA/IG threads) + `contact_profiles.notes`.
- Call `rag` `POST /chat` and forward the reply through the originating gateway.
- Log message pairs, activity events, orders, reminders (delegated to the worker).

## Tenant isolation (no-auth mode)

Every route below requires an `X-Tenant-Id` + `X-Tenant-Key` header pair validated
against the `tenant_keys` table (`rag_kro_shared/tenant_auth.py`). The header tenant is
authoritative; a body `tenant_id` that differs is rejected (403). The default tenant
key is seeded at startup (`TENANT_DEFAULT_KEY`). Deep-dive: `docs/SECURITY.md` §1b.

## Endpoints

All under `:8000` (internal only). Key ones:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB ping health |
| POST | `/webhook/message` | gateway inbound |
| GET | `/conversations` | list (dashboard) |
| PATCH | `/conversations/{id}` | pause/resume |
| GET/POST/DELETE | `/senders` | allowlist CRUD |
| GET/POST | `/products` | list/create (create triggers re-embed via ingestion) |
| GET | `/documents` | uploaded docs |
| GET | `/orders`, `/notifications`, `/activity` | admin reads |
| POST | `/reminders` | schedule reminder (worker fires it) |
| GET | `/sessions` | gateway statuses for dashboard |

## Message flow (code trace)

`app/main.py::webhook_message`:
1. allowlist check → reject + `allowlist_rejected` activity, if not allowed
2. upsert conversation + `resolve_contact`
3. store inbound message
4. if paused → log `paused_message`, return
5. `build_context()` → `services/context_builder.py`
6. `POST {RAG_API_URL}/chat` with history + contact context
7. `gateway_client.send_message(platform, contact, answer)` → `POST /send` on the gateway
8. store outbound + `bot_reply` activity with sources

## Configuration

| Variable | Use |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | stores |
| `RAG_API_URL`, `RAG_API_KEY` | internal rag call |
| `INGESTION_API_URL`, `INGEST_API_KEY` | product re-embed on create |
| `INTERNAL_API_KEY` | auth for gateway webhooks |
| `SMTP_*` | optional email notifications |

## Deployment

Container `rag_kro_api`, `services/api/Dockerfile`, port **8000** internal.
Stateless → scalable.

```bash
docker compose --profile dev up -d --build api
```

## Testing note

The webhook handler is the best place to start integration tests — mock the rag client
(httpx against `RAG_API_URL`) and assert allowlist/paused/replied branches, then
assert `messages` + `activity_log` rows.