# WhatsApp RAG Assistant — Implementation Spec

## 0. Goal
Single/multi-tenant tool (no login for now): connect WhatsApp (and Instagram), define an allowlist of senders, and an LLM (RAG-grounded on own docs/products + prior chat/social history) auto-responds and adapts tone/flow per contact. User can pause/resume the bot per-conversation. Zero-cost stack using free-tier/OSS components.

**No-auth mode**: skip NextAuth entirely for now — single implicit "default tenant" (or a static admin token in `.env` guarding the dashboard). `tenant_id` scoping in the schema stays as-is so auth can be dropped back in later without a rewrite.

---

## 1. High-Level Architecture

```
Next.js (frontend + API routes, no auth for now)
        |
        v
FastAPI (Python) — orchestration, RAG, agent logic
        |
   +--------+--------------+------------------+------------------+
   |                       |                  |                  |
Baileys (WhatsApp)   IG scraper/API      Vector DB (Qdrant)  Postgres (metadata, orders)
Node microservice    (Node/Python)       (self-hosted,        (self-hosted, Docker)
                                          Docker)
        |
        v
Redis (session state, pause/resume flags, queues)
        |
        v
LangChain (Python) -> HF Inference API / OSS LLM
```

All containerized via `docker-compose`: `web` (Next.js), `api` (FastAPI), `wa-gateway` (Node), `ig-gateway` (Node/Python), `postgres`, `redis`, `qdrant`, `worker` (Celery/RQ for async jobs).

---

## 2. WhatsApp Connectivity (the free part)
- **No official WhatsApp Business API** (costs money, needs Meta approval). Use **Baileys** (Node, multi-device WA Web protocol) as a separate microservice — exposes REST/WebSocket to FastAPI.
- Flow: user clicks "Connect WhatsApp" → wa-gateway generates QR → frontend polls/streams it → user scans → session (auth creds) stored encrypted in Postgres, keyed by tenant_id.
- One Baileys process can hold multiple sessions (map tenant_id → socket instance); persist auth state via `useMultiFileAuthState` (swap to DB-backed store for durability).
- **Caveat to flag to your reviewer**: Baileys use violates WhatsApp ToS and accounts risk banning — acceptable for prototype, must be disclosed as a production risk.

## 2b. Instagram Connectivity
- No official cost-free Instagram Graph API path for DMs on personal accounts (Graph API DM access requires a Business/Creator account + app review). Two realistic options:
  - **Option A (compliant, free tier)**: Instagram Graph API for a Business/Creator-linked page — works for DM automation, requires Meta app review (slower to set up, but ToS-safe, still $0).
  - **Option B (scraping, same risk profile as Baileys)**: unofficial libraries (e.g. `instagrapi` for Python) to log in and pull DMs/profile data — fast to build, same ban-risk caveat as WhatsApp, must be flagged as prototype-only.
- Recommend Option B for MVP speed (mirrors the Baileys approach) with Option A noted as the production migration path.
- `ig-gateway` service mirrors `wa-gateway`: login session stored encrypted, polls/streams DMs to FastAPI webhook, tagged with `platform: instagram` so the rest of the pipeline (allowlist, RAG, pause/resume) is platform-agnostic.
- **Profile/context pull**: on first contact, `ig-gateway` fetches the sender's public IG profile (bio, name, recent public posts if accessible) and stores it as a `contact_profile` doc — feeds into RAG context so the LLM can reference who it's talking to.

---

## 3. Data Model (Postgres)

- `tenants` (id, name) — single default row while no-auth mode is active
- `wa_sessions` (tenant_id, session_blob, status: connected/disconnected)
- `ig_sessions` (tenant_id, session_blob, status: connected/disconnected)
- `allowed_senders` (tenant_id, platform: whatsapp/instagram, identifier (phone|username) | '*', label)
- `conversations` (id, tenant_id, platform, contact_identifier, status: bot_active/paused, updated_at)
- `messages` (id, conversation_id, direction, body, media_url, created_at)
- `contact_profiles` (id, tenant_id, platform, contact_identifier, bio/name/notes, last_synced_at) — external profile + running summary of the relationship
- `documents` (id, tenant_id, type: pdf/image/product, storage_path, ingested_at)
- `products` (id, tenant_id, name, price, stock, description, image_url)
- `orders` (id, tenant_id, conversation_id, product_id, qty, status, created_at)
- `notification_targets` (tenant_id, type: email/webhook/sms, destination)
- `activity_log` (id, tenant_id, event_type, payload jsonb, created_at) — feeds the admin activity panel

---

## 4. Message Flow (Runtime)

1. Baileys/ig-gateway receives inbound message → posts to FastAPI `/webhook/message` with `platform` tag.
2. FastAPI checks `allowed_senders` (tenant_id, platform, identifier) — reject if not allowed and not `*`.
3. Check `conversations.status` — if `paused`, store message only, notify tenant dashboard (no LLM call), stop.
4. **Identity resolution**: try to match the incoming contact across platforms (same phone/username/name overlap, or manually linked in dashboard) so a WA and IG conversation with the same real person share one `contact_profile` and combined history where possible.
5. If active: build context for the RAG chain:
   - Recent turns: Redis short-term + Postgres long-term, **across all platforms for that resolved contact**, not just the current thread.
   - `contact_profiles` summary (who they are, prior topics/orders, tone they use) — this is what lets the bot "adapt to the flow" of the new incoming chat instead of restarting cold.
   - Retriever: Qdrant similarity search scoped to `tenant_id` (metadata filter) over business docs/products.
   - Agent/tool layer (LangChain agent or simple function-calling): tools = `search_products`, `place_order`, `create_reminder`, `escalate_to_human`.
6. LLM (via HF Inference API/Ollama) generates response, matching the register of the ongoing conversation → send back through the originating platform's gateway.
7. If order placed or human-escalation triggered → push to `notification_targets` (email via SMTP free tier like Gmail/Brevo, or webhook to external CRM).
8. Log everything to `messages`; periodically (worker job) re-summarize `contact_profiles.notes` from recent messages so the context stays compact instead of growing unbounded.

---

## 5. Pause/Resume Control
- Toggle stored in `conversations.status`, editable from Next.js dashboard (per-contact) or globally per-tenant.
- Simplest: a button per conversation thread; WhatsApp command fallback optional (e.g., tenant texts "STOP BOT" from their own linked device to self-pause — nice-to-have, not core).
- FastAPI checks this flag before invoking the RAG chain — already covered in step 3 above.

---

## 6. RAG Ingestion Pipeline
- Upload endpoint (Next.js → FastAPI) for PDFs/images/CSV product lists.
- **PDFs**: LangChain `PyPDFLoader` → `RecursiveCharacterTextSplitter` → embeddings → Qdrant, metadata `{tenant_id, doc_id, source}`.
- **Images**: store in object storage (self-hosted MinIO container, S3-compatible, free); optionally caption via a free HF vision model (e.g., BLIP) and embed the caption text for retrieval; keep raw image URL in metadata for sending back to customer.
- **Product DB**: structured rows → convert each product to a text doc ("Name: X, Price: Y, Stock: Z, Desc: ...") → embed, so RAG can naturally answer "do you have X in stock".
- **Embeddings model (free)**: HF Inference API `sentence-transformers/all-MiniLM-L6-v2` (or run locally via `sentence-transformers` in the worker container — literally $0, no API limits).

---

---

## 6b. Continuous Vector DB Update Pipeline
- Don't treat ingestion as one-off. Worker runs a scheduled job (Celery beat / RQ scheduler):
  - **Change detection**: hash each source doc/product row; only re-embed on diff (avoid full re-index every run).
  - **Product DB sync**: on any `products` insert/update/delete (Postgres trigger or app-level event), push a re-embed job for that single row into the worker queue — near-real-time instead of polling.
  - **Document sync**: new PDF/image uploads trigger immediate embedding job; periodic sweep (e.g. hourly) catches anything missed.
  - **Contact profile sync**: the summarization job from section 4 also re-embeds updated `contact_profiles.notes` so retrieval reflects the latest relationship context.
  - **Stale vector cleanup**: on delete (product removed, doc deleted), remove matching vectors by metadata filter (`tenant_id` + `doc_id`/`product_id`) — Qdrant supports filtered delete directly.
- Queue-based (Redis + RQ/Celery) rather than cron-only, so bursts of uploads don't block each other or the chat pipeline.

---

## 7. LLM Choice (Zero Cost)
- **Free options via HF Inference API**: rate-limited but free — e.g. `Qwen2.5-7B-Instruct`, `Meta-Llama-3.1-8B-Instruct`, `Mistral-7B-Instruct` (check current HF free-tier availability, it shifts).
- **Self-hosted alternative** (truly $0 recurring, more setup cost): Ollama container running Llama3/Qwen/Mistral, called via LangChain's `ChatOllama` — avoids any external API limits, keeps data private. Given you're already using Docker, this is worth strongly considering as the default, with HF API as fallback/dev option.
- Recommend: LangChain's model abstraction so you can swap HF API ↔ Ollama with one config flag.

---

## 8. LangChain Structure (Python/FastAPI side)
- `Retriever`: Qdrant vectorstore retriever, filtered by tenant_id.
- `Memory`: `ConversationBufferWindowMemory` or manual last-N messages from Postgres.
- `Chain`: `RetrievalQA` or custom LCEL chain combining retrieved context + conversation history + system prompt (tenant-specific persona/instructions, stored per tenant).
- `Agent tools` for order placement/reminders — implement as LangChain `Tool`s calling internal FastAPI service functions directly (not over HTTP, same process) for speed.
- Reminders: a Celery/RQ periodic worker checks an `orders`/`reminders` table and pushes WA messages or notifications on schedule.

---

## 9. Next.js Responsibilities
- No auth for now (see section 0/11) — dashboard reachable directly.
- Font: **Geist** (`next/font/google` → `Geist`, or `geist` npm package for Geist + Geist Mono) as the site-wide typeface.
- Dashboard: WA/IG connect (QR/login), allowed senders CRUD, conversation list + pause/resume toggle, document/product upload, order log, notification target config.
- Calls FastAPI via internal API routes (keep FastAPI not publicly exposed, proxy through Next.js API routes or a shared internal token).

---

## 9b. Admin Panel
Separate route in the same app (`/admin`), same Geist font, polling or WebSocket-fed for live data.
- **System health**: status cards per Docker service (Postgres, Redis, Qdrant, wa-gateway, ig-gateway, worker) — FastAPI exposes `/health` aggregating each dependency's ping; worker exposes queue depth/failed-job count.
- **Live chats**: real-time view of active conversations across WA + IG — WebSocket/SSE pushed from the message webhook handler, so messages stream into the admin UI as they happen, not just on refresh.
- **Activity/processing feed**: log of pipeline events — embedding jobs run, orders placed, reminders fired, allowlist rejections — sourced from an `activity_log` table (tenant_id, event_type, payload, created_at), written by each subsystem as it acts.
- **Per-conversation drill-in**: click a live chat to see full transcript + which RAG sources/tools were used for the last response (debugging aid).
- Given no-auth is temporary, `/admin` is the highest-value target if this ever gets exposed publicly — gate it hardest first if any auth is reintroduced early.

---

## 10. Docker Compose Skeleton

```yaml
services:
  web:        # Next.js
  api:        # FastAPI + LangChain
  wa-gateway: # Node + Baileys
  ig-gateway: # Node/Python + instagrapi
  worker:     # Celery/RQ for embeddings, reminders, notifications
  postgres:
  redis:
  qdrant:
  minio:      # object storage for PDFs/images
  ollama:     # optional local LLM
```
Each service has its own Dockerfile; shared `.env` for secrets; internal Docker network, only `web` exposed publicly (behind Nginx/Caddy for TLS — also free via Let's Encrypt).

---

## 11. Multi-Tenancy & Security Notes (flag these to the reviewing agent)
- **No-auth mode is a real exposure**: the dashboard (WA/IG connect, allowlist, documents, pause/resume) is unprotected. Minimum: bind to localhost/VPN or gate behind a static token/basic-auth at the reverse proxy until real auth returns.
- Every Qdrant query, Postgres query, and storage path should stay scoped by `tenant_id` even with one tenant — keeps re-adding auth a config change, not a rewrite.
- WA/IG session credentials are sensitive — encrypt at rest (e.g., Fernet with a key in `.env`).
- Rate-limit inbound webhook processing to avoid one contact's traffic starving others.
- HF Inference free tier has strict rate limits — design for graceful degradation (queue + retry, or fallback to Ollama).
- Only store scraped IG profile data for contacts who've actually messaged in, not bulk-scraped — stay within reasonable privacy bounds.

---

## 12. Suggested Build Order
1. Docker compose skeleton + Postgres schema (no auth — static default tenant).
2. Baileys gateway + QR connect flow + allowed_senders enforcement (no LLM yet, just echo).
3. Ingestion pipeline (PDF/product) + Qdrant + embeddings.
4. LangChain RAG chain wired to inbound messages (read-only Q&A), single-thread context only.
5. Pause/resume control.
6. Cross-conversation context: `contact_profiles` + history summarization + identity resolution.
7. ig-gateway + platform-tagged pipeline reuse.
8. Order-placement tool + Postgres orders table.
9. Reminders worker + external notification forwarding.
10. Image ingestion/captioning (lowest priority).

---

## 13. Open Decisions for the Reviewing Agent
- HF Inference API vs self-hosted Ollama as default LLM (cost/latency/quality tradeoff).
- Baileys/instagrapi ToS risk — acceptable for MVP, with official Graph/Cloud APIs (paid/review-gated) as v2 migration path?
- Single gateway process per server vs one per tenant (scaling ceiling), now relevant for both WA and IG.
- How aggressive should cross-platform identity resolution be (auto-match vs require manual linking)? False matches leak one contact's context into another's conversation.
- Should the no-auth window be strictly dev-only and never deployed publicly as-is?
