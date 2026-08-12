# Contributing

Thanks for helping with `rag_kro`. Keep the structure conventions in mind.

## Structure rules

- One clear home per responsibility (a service folder for a deployable unit).
- Python services import the shared lib (`packages/python/rag_kro_shared`) instead of
  vendoring duplicated code.
- Every service has its own `Dockerfile`, `requirements.txt`/`package.json` and README.
- New env vars go in `.env.example` **and** into `config.py` defaults + the READMEs.
- Internal calls use `X-Internal-Key`; never hardcode secrets.

## Adding a module

1. Create `services/<name>/` with `Dockerfile`, deps manifest, `app/` (or `src/`), README.
2. Add a profile line in `docker-compose.yml` + an entry in the root README table.
3. Add a `docs/` page updated and cross-linked.
4. Follow naming: Python packages under `app/`, endpoints snake_case, models in shared lib.

## Dev loop

```bash
make up          # run everything
make logs        # follow logs
docker compose restart api   # pick up changes (sources are mounted in dev)
```

## Testing

Tests live inside each service. Python services: `pytest` in the container
(no test suite committed yet — add one with your change). Node: `node --test`.

When you add a feature, add a minimum test that exercises the new boundary:
- `ingestion` → a chunking test
- `rag` → a retriever/prompt-building test with fake embeddings
- `api` → allowlist + webhook-order tests with a mocked RAG client

## Before opening a PR

- [ ] `python3 -m py_compile` on touched python
- [ ] `docker compose config` is valid
- [ ] `.env.example` updated
- [ ] READMEs updated if behaviour changed
- [ ] No secrets in the diff