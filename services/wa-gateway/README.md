# services/wa-gateway — WhatsApp Connectivity

Node microservice wrapping **Baileys** (@whiskeysockets/baileys, multi-device protocol).
Exposes a small HTTP API the dashboard and the API service use. One process can hold
multiple sockets (tenant → socket map) per spec section 2.

## Capabilities

- `POST /connect/:tenantId` — spawn a Baileys socket, generate a QR (returned as a
  `data:` URL for the dashboard). Socket streaming is done by polling `/status`.
- `GET /status/:tenantId` — `linking | connected | reconnecting | disconnected`.
- `POST /disconnect/:tenantId` — tear down the transport (admin control).
- `POST /send` — outbound message from the API service.
- Forward inbound messages to the API service webhook
  (`WA_API_CALLBACK_URL`, default `http://api:8000/webhook/message`).

## Session durability

Credentials persist via `useMultiFileAuthState` under `wa-sessions/{tenantId}`
(git-ignored). Spec note: this is the light path — swap to a DB-backed store for
durability; `wa_sessions` table exists for that purpose. **Keep sessions off the
public filesystem in production.**

## Inbound message handling

`messages.upsert` → downloads image media when present, then forwards a normalized
payload to the API service:

```json
{
  "tenant_id": "…",
  "platform": "whatsapp",
  "contact_identifier": "<remoteJid>",
  "body": "<text or caption>",
  "media_url": "<data-url or null>"
}
```

## Env

| Variable | Use |
|---|---|
| `WA_GATEWAY_PORT` | default 8100 |
| `WA_GATEWAY_INTERNAL_KEY` / `INTERNAL_API_KEY` | shared secret for `/send`, `/connect` |
| `WA_API_CALLBACK_URL` | webhook target (api service) |

## Deployment

```bash
docker compose --profile wa up -d --build wa-gateway
```

## ⚠️ ToS risk

Baileys uses the WhatsApp Web multi-device protocol — not the official Business API.
Accounts risk bans and this violates WhatsApp ToS. **Prototype only**; production
migration path is the WhatsApp Business Cloud API (paid/review-gated). See
`docs/SECURITY.md`.

## Test

```bash
npm install
npm test   # node --test once tests are added
```

Manual: `curl http://localhost:8100/status/<tenant>` to check state; connect via the
dashboard and scan the QR.