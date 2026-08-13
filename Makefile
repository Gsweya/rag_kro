.PHONY: up up-dev up-wa up-ig down logs ps schema qr key build test verify

# ---- environment ---------------------------------------------------
.env:
	cp .env.example .env
	@echo "=> created .env — edit the secrets before starting"

# ---- full stack (dev) ----------------------------------------------
up: .env
	docker compose --profile dev --profile wa up -d --build

up-dev: .env
	docker compose --profile dev up -d --build

up-wa: .env
	docker compose --profile dev --profile wa up -d --build

up-ig: .env
	docker compose --profile dev --profile ig up -d --build

up-ollama: .env
	docker compose --profile dev --profile ollama up -d --build
	docker compose exec ollama ollama pull llama3.2

down:
	docker compose down

# ---- ops -----------------------------------------------------------
logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

# generate a Fernet key for session encryption at rest
key:
	python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

build:
	docker compose build

test:
	@python3 -m pytest --version >/dev/null 2>&1 || echo "pytest not installed locally — run inside a service image"
	@echo "-> tenant isolation tests (needs Postgres + a seeded tenant key):"
	python3 -m pytest tests/test_isolation.py -v

verify:
	@echo "== syntax: python =="
	python3 -m compileall -q packages services/api services/rag services/ingestion services/worker services/ig-gateway
	@echo "== syntax: node =="
	node --check services/wa-gateway/src/index.js
	node --check services/wa-gateway/src/socket.js
	node --check services/wa-gateway/src/send.js
	@echo "== compose config =="
	docker compose config --quiet
	@echo "OK"