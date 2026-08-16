-- =====================================================================
-- rag_kro — Postgres schema (init on first boot, idempotent-ish)
-- tenant_id scoping everywhere so auth can be re-added later without rewrite
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---- tenants ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- single implicit tenant while no-auth mode is active
INSERT INTO tenants (id, name)
VALUES ('00000000-0000-0000-0000-000000000001', 'default')
ON CONFLICT DO NOTHING;

-- ---- per-tenant API keys (auth boundary while login is absent) -------------
-- Callers must present a valid (tenant_id, api_key) pair via headers:
--   X-Tenant-Id, X-Tenant-Key
-- The pair is validated against this table before ANY route trusts a tenant_id.
CREATE TABLE IF NOT EXISTS tenant_keys (
    tenant_id  UUID PRIMARY KEY REFERENCES tenants(id),
    api_key    TEXT NOT NULL,
    label      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- seeded by the api service at startup from TENANT_DEFAULT_KEY (see auth.py)

-- ---- platform sessions (wa / ig) --------------------------------------
CREATE TABLE IF NOT EXISTS wa_sessions (
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    session_blob TEXT NOT NULL,          -- fernet-encrypted Baileys creds
    status       TEXT NOT NULL DEFAULT 'disconnected', -- connected|disconnected
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id)
);

CREATE TABLE IF NOT EXISTS ig_sessions (
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    session_blob TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'disconnected',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id)
);

-- ---- allowlist ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS allowed_senders (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    platform    TEXT NOT NULL CHECK (platform IN ('whatsapp','instagram','*')),
    identifier  TEXT NOT NULL,          -- phone | username | '*'
    label       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, platform, identifier)
);

-- ---- conversations --------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id          UUID NOT NULL REFERENCES tenants(id),
    platform           TEXT NOT NULL CHECK (platform IN ('whatsapp','instagram')),
    contact_identifier TEXT NOT NULL,          -- phone | username
    resolved_contact_id UUID,                  -- combined identity (section 4.4)
    status             TEXT NOT NULL DEFAULT 'bot_active'
                       CHECK (status IN ('bot_active','paused')),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, platform, contact_identifier)
);

-- ---- messages -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    direction       TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
    body            TEXT,
    media_url       TEXT,
    meta            JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages (conversation_id, created_at);

-- ---- contact profiles -------------------------------------------------------
CREATE TABLE IF NOT EXISTS contact_profiles (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id          UUID NOT NULL REFERENCES tenants(id),
    platform           TEXT NOT NULL CHECK (platform IN ('whatsapp','instagram')),
    contact_identifier TEXT NOT NULL,
    name               TEXT,
    bio                TEXT,
    notes              TEXT,                -- running relationship summary (worker re-summarizes)
    last_synced_at     TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, platform, contact_identifier)
);

-- ---- documents (ingested source files) --------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    type         TEXT NOT NULL CHECK (type IN ('pdf','image','csv','product','contact_profile')),
    title        TEXT,
    storage_path TEXT,                      -- minio object key
    source_hash  TEXT,                      -- for change detection (6b)
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','indexed','failed')),
    ingested_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- products -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    name        TEXT NOT NULL,
    price       NUMERIC(12,2),
    stock       INTEGER DEFAULT 0,
    description TEXT,
    image_url   TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    emb_hash    TEXT,                        -- change detection for vector sync (6b)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- orders ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    conversation_id UUID REFERENCES conversations(id),
    product_id      UUID REFERENCES products(id),
    qty             INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'placed'
                    CHECK (status IN ('placed','confirmed','shipped','completed','cancelled','needs_human')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- reminders (worker fires on schedule) ---------------------------------------
CREATE TABLE IF NOT EXISTS reminders (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id),
    conversation_id  UUID REFERENCES conversations(id),
    platform         TEXT NOT NULL DEFAULT 'whatsapp',
    contact_identifier TEXT NOT NULL,
    remind_at        TIMESTAMPTZ NOT NULL,
    message          TEXT NOT NULL,
    fired            BOOLEAN NOT NULL DEFAULT false,
    fired_at         TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (fired, remind_at);

-- ---- notification targets --------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_targets (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    type        TEXT NOT NULL CHECK (type IN ('email','webhook','sms')),
    destination TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- activity log (feeds admin panel) ---------------------------------------------
CREATE TABLE IF NOT EXISTS activity_log (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id  UUID NOT NULL REFERENCES tenants(id),
    event_type TEXT NOT NULL,
    payload    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_activity_log ON activity_log (tenant_id, created_at DESC);