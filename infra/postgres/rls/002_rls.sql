-- =====================================================================
-- OPTIONAL: Postgres Row-Level Security for hard tenant isolation
--
-- This is NOT enabled by default. It's the second layer ("belt") you turn
-- on when a second REAL tenant goes live, so even a missed app-level
-- filter cannot leak rows across tenants.
--
-- How it works (Postgres native):
--   * RLS policies evaluate `current_setting('app.tenant_id', true)`.
--   * Your app connection must run, per request:
--         SET LOCAL app.tenant_id = '<uuid>';
--     inside the same transaction that runs the query.
--   * All rag_kro queries already go through session_scope() transactions,
--     so wiring the SET is a one-line change in rag_kro_shared/db.py.
--
-- Apply manually:  docker compose exec postgres psql -U rag_kro -d rag_kro -f -  < 002_rls.sql
-- =====================================================================

-- helper to read the session tenant
CREATE OR REPLACE FUNCTION current_tenant_uuid() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid;
$$ LANGUAGE sql;

-- !! DO NOT run the data-scoping pieces below until the app sets app.tenant_id.
-- Applying them without the SET will block ALL rows and break the dashboard.

DO $$
DECLARE
    t RECORD;
BEGIN
    -- tenant scope is only meaningful on tables that carry tenant_id
    FOR t IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename IN (
            'allowed_senders','conversations','contact_profiles','documents',
            'products','orders','reminders','notification_targets','activity_log',
            'wa_sessions','ig_sessions'
          )
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.tablename);
        EXECUTE format($pol$
            CREATE POLICY tenant_isolation ON %I
            USING (app.current_tenant_uuid() = tenant_id)
            WITH CHECK (app.current_tenant_uuid() = tenant_id)
        $pol$, t.tablename);
    END LOOP;
END $$;

-- tenants + tenant_keys are globally visible (auth lookup must work pre-SET)
ALTER TABLE tenants DISABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_keys DISABLE ROW LEVEL SECURITY;