CREATE TABLE IF NOT EXISTS planning_sessions (
    token_hash text PRIMARY KEY,
    state jsonb NOT NULL,
    revision bigint NOT NULL DEFAULT 0,
    run_id text,
    lease_until timestamptz,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS planning_sessions_expiry ON planning_sessions (expires_at);
