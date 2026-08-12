# Deployment

This document describes how to deploy `rag_kro` beyond your laptop.

> **Read this first.** The default stack runs with **no authentication**. Everything in
> this doc that adds auth is **not optional** once the dashboard leaves localhost.

## 1. Compose profiles

`docker-compose.yml` splits services into profiles so you only bring up what you need:

| Profile | Services | When |
|---|---|---|
| *(core)* | postgres, redis, qdrant, minio | always |
| `dev` | web, api, rag, ingestion, worker | development + default production core |
| `wa` | wa-gateway | WhatsApp enabled |
| `ig` | ig-gateway | Instagram enabled |
| `ollama` | ollama | self-hosted LLM instead of HF API |

```bash
# production-ish (no reloaders): build without profile dev reload mounts
docker compose --profile dev --profile wa up -d --build
```

For production you generally **do not want** the dev volume mounts + `--reload` flags.
A future `docker-compose.prod.yml` will strip those; for now overlay is via
`docker compose -f docker-compose.yml -f docker-compose.prod.override.yml up -d`.

## 2. Reverse proxy + TLS (free)

Only `web` (Next.js) is exposed. Put Nginx or Caddy in front of it. Caddy example
(`caddy` can be added as a compose service):

```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports: ["443:443", "80:80"]
    volumes: ["./infra/caddy/Caddyfile:/etc/caddy/Caddyfile"]
    environment:
      DOMAIN: bot.example.com
      WEB_INTERNAL: web:3000
```

```nginx
{$DOMAIN} {
    reverse_proxy {$WEB_INTERNAL}
    header / Strict-Transport-Security "max-age=31536000"
}
```

Let's Encrypt is automatic with Caddy (free TLS). **Require `ADMIN_TOKEN`** before exposing.

## 3. Hardening BEFORE public exposure (mandatory)

1. **Gate the dashboard.** Options (increasing effort):
   - put the Next.js app behind a VPN/tailnet only, or
   - enforce a static bearer token (env `ADMIN_TOKEN`) in the `web` route handler, or
   - add basic-auth on the reverse proxy.
2. **Rotate `INTERNAL_API_KEY` / `ADMIN_TOKEN`** from the `.env.example` defaults.
3. **Encryption** — `FERENCE_SECRET_KEY` must be set; WA/IG session blobs are encrypted
   at rest in Postgres.
4. **Firewall** — never publish `8000/8001/8002`, `8100`, `8200`, `6379`, `5432`,
   `9000/9001`, `6333` to the internet. Only `443/80` (and `3000` for dev).
5. **Private LLM data** — if any of this data is sensitive, run `make up-ollama`
   (`LLM_BACKEND=ollama`) so nothing leaves your host.

## 4. Backup / restore

State lives in the named volumes `postgres-data`, `redis-data`, `qdrant-data`, `minio-data`:

```bash
docker compose stop
docker run --rm -v rag_kro_postgres-data:/data -v "$PWD/backups:/backup" \
  alpine tar czf /backup/postgres-$(date +%F).tgz -C /data .
# same pattern for the other volumes
docker compose start
```

## 5. Upgrades

The schema is applied idempotently via `docker-entrypoint-initdb.d`, which only runs on
a **fresh** Postgres volume. For subsequent schema changes use migrations (e.g. Alembic)
on the `api` container. Document any migration in `docs/` and the affected service README.

## 6. Monitoring (free-tier friendly)

- `worker` writes `worker:last_beat` into Redis every 5m — the admin panel can surface it.
- `activity_log` table records pipeline events for the dashboard.
- Export `api`, `rag`, `ingestion`, `worker` logs to your favourite collector.

## 7. Scaling notes

- Horizontally scale `api`, `rag`, `worker` behind a load balancer (they are stateless).
- Gateways keep state (Baileys sockets / IG sessions): pin tenants to a gateway
  instance (e.g. tenant id hash → gateway) rather than round-robin.
- Postgres/Redis/Qdrant are the single points of state — consider PG replication and
  Qdrant sharding only if throughput demands it (out of MVP scope).