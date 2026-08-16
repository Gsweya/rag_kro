# Security Notes

There is no login yet (spec section 0/11: static default tenant + optional admin token).
This file is honest about what that means and how to reduce risk.

## 1. The no-auth window

- **Dashboard** is reachable by anyone who can reach `web`.
- **WA/IG connect, allowlist, document upload, pause/resume, orders** are all behind that
  unprotected UI.
- Unless bound to localhost/VPN, the dashboard must not be exposed. If you plan public
  deployment, enforce auth first (see DEPLOYMENT.md §3).

Recommended minimum before any public exposure:
1. Static bearer token check in the Next.js middleware reading `ADMIN_TOKEN`.
2. Reverse proxy basic-auth as belt and braces.
3. Do not publish internal service ports.

## 1b. Tenant isolation (multi-tenancy with no real login)

The retrieval pipeline is tenant-scoped **by design**: every Qdrant query filters
`tenant_id` (vectors.py), every vector payload carries `tenant_id` (ingestion), and every
Postgres read is `.filter_by(tenant_id=...)`. Company B's products cannot match company
A's RAG search. But isolation-by-convention is not enough once a second real tenant
exists — so `rag_kro` layers real enforcement:

1. **Per-tenant API keys (on by default).** Every tenant-scoped route requires an
   `X-Tenant-Id` + `X-Tenant-Key` pair, checked against the `tenant_keys` table
   (`rag_kro_shared/tenant_auth.py`). The authenticated header tenant is authoritative;
   a `tenant_id` inside a request body that differs is rejected with 403
   (`ensure_matching_tenant`). A caller can no longer read or write another tenant's data
   by editing the body. The default tenant key (`TENANT_DEFAULT_KEY`) is seeded into
   `tenant_keys` at API startup.
2. **Postgres RLS (opt-in, for the 2nd tenant).** `infra/postgres/rls/002_rls.sql`
   enables row-level security keyed on `current_setting('app.tenant_id')`. The shared
   `session_scope(tenant_id=...)` helper sets it per transaction, so the **database**
   enforces isolation even if an app query later forgets its WHERE clause.
3. **Qdrant per-tenant collections (opt-in).** Set `QDRANT_PER_TENANT_COLLECTIONS=true`
   and each tenant gets its own collection (`rag_kro_vectors__{tenant_id}`) — Qdrant-level
   isolation on top of the payload filter. Flip both on together when the second real
   tenant goes live.

Browser uploads go through `api` (`POST /documents/upload` with tenant headers), never
straight to the ingestion service, so the tenant boundary isn't bypassable from the UI.

## 2. Session credential encryption at rest

WA/IG session blobs stored in `wa_sessions` / `ig_sessions` are encrypted with Fernet
(`packages/python/rag_kro_shared/rag_kro_shared/crypto.py`). The key comes from
`FERENCE_SECRET_KEY`. Without it set, a deterministic **dev-only** key is used — fine for
a laptop, **not** for anything real. Generate a real key with `make key`.

## 3. Internal service-to-service auth

All Python services share one secret (`INTERNAL_API_KEY`) sent as `X-Internal-Key`.
The gateways and web use the same pattern. On the public internet this secret must be
random and rotated. This is a shared-secret scheme — acceptable for the prototype,
replace with mTLS/signed tokens for stronger needs.

## 4. Data scoping (tenant_id)

Every Postgres query and every Qdrant vector is scoped by `tenant_id` even though there
is only one tenant today. This keeps re-adding real auth a **config change, not a rewrite**.
Audit every new endpoint for a `tenant_id` filter.

## 5. Platform ToS risk (flag to reviewers)

- **Baileys (WhatsApp)**: unofficial multi-device protocol. Accounts can be banned.
  Prototype-only. Production path: WhatsApp Business Cloud API (paid/review-gated).
- **Instagram**: this repo uses `instagrapi` (unofficial login). Same ban risk,
  prototype-only. Production path: Instagram Graph API for Business/Creator with app review.
- IG profile harvesting is limited to contacts who actually message in (no bulk scrape).

## 6. Email/webhook notifications

SMTP creds (Gmail/Brevo free tiers) live in `.env`; they are used only to send
notifications. Do not log them. If using Gmail, use an app-specific password.

## 7. Ingestion safety

PDF text extraction and image captioning can be adversarial (zip bombs / huge files).
Add size and type limits to the ingestion upload endpoint before public use (currently
only basic type checks). Rate-limit inbound webhooks so one contact can't starve others.

## 8. Supply chain

Pulling `~6` Python + Node images plus Org You are pinned reasonably in the compose file;
edit pins conservatively. Run `docker compose config` to review effective config after
any change.