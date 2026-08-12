# services/ig-gateway — Instagram Connectivity

Python microservice using **instagrapi** (unofficial library, spec §2b Option B) that
mirrors `wa-gateway`, tagging everything `platform: instagram` so the message pipeline
(allowlist, RAG, pause/resume) is platform-agnostic.

## Capabilities

- `POST /login` — username/password → `instagrapi` client → session blob **encrypted at
  rest** into `ig_sessions` (Fernet, key = `FERENCE_SECRET_KEY`).
- `POST /resume` — reload a stored session (restart-safe).
- `GET /status/{tenant_id}` — connected/disconnected.
- `POST /send` — send a DM (requires the target account to accept messages).
- Background poller forwards new DMs to the API service webhook
  (`IG_API_CALLBACK_URL`, default `http://api:8000/webhook/message`).

## Profile / context pull

On first contact the poller can fetch the sender's public profile (name, bio) into
`contact_profiles` — limited to contacts who actually message in (no bulk scraping).

## ⚠️ ToS + capability risk

- **instagrapi is an unofficial login** — same ban-risk caveat as Baileys. Prototype-only.
- DM automation is unreliable for arbitrary accounts; the production path is the
  Instagram Graph API for Business/Creator accounts (needs Meta app review) — spec §2b
  Option A.
- Some features (e.g. sending DMs to accounts that haven't messaged you) are server-side
  restricted by Instagram itself.

## Env

| Variable | Use |
|---|---|
| `IG_GATEWAY_PORT` | default 8200 |
| `IG_GATEWAY_INTERNAL_KEY` / `INTERNAL_API_KEY` | shared secret |
| `IG_API_CALLBACK_URL` | webhook target (api service) |

## Deployment

```bash
docker compose --profile ig up -d --build ig-gateway
```

## Structure

```
app/main.py   # FastAPI: login/resume/status/send + background DM poller
```

The poller runs every 30s per connected tenant. Consider switching to Telegram-style
long-polling with error backoff for production.

## Test

Manual: `POST /login` with test creds, then watch `api` activity feed for
`platform: instagram` messages.