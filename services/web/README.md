# services/web — Dashboard (Next.js)

The operator UI. Geist font (`geist` npm package), dark theme, no auth yet (guarded by
`ADMIN_TOKEN` in the roadmap — see `docs/SECURITY.md`).

## Pages

| Route | Purpose |
|---|---|
| `/` | dashboard: WhatsApp/IG connect + QR, conversations, session status |
| `/admin` | pause/resume per conversation + live activity feed |
| `/senders` | allowlist CRUD |
| `/documents` | upload PDF/image → centralized ingestion |
| `/products` | product CRUD (create triggers re-embed) |

## How it talks to the backend

All browser fetches go to proxy paths defined in `next.config.mjs` — internal services
are never exposed to the browser:

| Browser path | Internal target |
|---|---|
| `/api/back/*` | `api:8000` |
| `/api/wa/*` | `wa-gateway:8100` |
| `/api/ig/*` | `ig-gateway:8200` |
| `/api/rag/*` | `rag:8002` |
| `/api/ingest/*` | `ingestion:8001` |

Client helper: `src/lib/api.ts` (`api("/conversations", {...})` → `/api/back/...`).

## Structure

```
src/
├── app/            # route components (layout, page, admin, senders, documents, products)
│   ├── layout.tsx  # Geist + nav
│   ├── globals.css
│   └── …
└── lib/api.ts      # fetch wrapper
```

## Env (build/runtime)

| Variable | Use |
|---|---|
| `API_INTERNAL_URL` | default `http://api:8000` |
| `WA_GATEWAY_INTERNAL_URL` | default `http://wa-gateway:8100` |
| `IG_GATEWAY_INTERNAL_URL`, `RAG_INTERNAL_URL`, `INGESTION_INTERNAL_URL` | other proxies |
| `ADMIN_TOKEN` | future auth header (`NEXT_PUBLIC_ADMIN_TOKEN` for now) |
| `NEXT_PUBLIC_INTERNAL_KEY` | shared secret for proxied sensitive calls |

## Development

```bash
npm install
npm run dev        # http://localhost:3000
```

In the compose stack the `web` container mounts `./services/web:/app` and runs
`npm run dev`, so edits hot-reload.

## Production

```bash
npm run build && npm run start
# or via Dockerfile (multi-stage build)
```

Only this service should be published publicly (behind Caddy/Nginx for TLS — see
`docs/DEPLOYMENT.md`).