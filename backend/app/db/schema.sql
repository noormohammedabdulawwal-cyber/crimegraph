-- CrimeGraph Postgres schema (build step 6).
-- Applied idempotently by backend/app/db/migrate.py, and auto-run on a fresh
-- Postgres volume via docker-entrypoint-initdb.d (docker-compose mounts this).
--
-- users      — the MVP has exactly two seed users (investigator, admin),
--              password hashes generated in migrate.py with bcrypt.
-- audit_log  — every authenticated request appends user_id, role, action,
--              endpoint, created_at (PRD NFR 'Auditability'). user_id is TEXT
--              (the username) so rows stay readable and survive user changes;
--              role is snapshotted so a later role change doesn't rewrite
--              history — the row always shows what was true at query time.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('investigator', 'admin')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    action     TEXT NOT NULL,
    endpoint   TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_created_at_idx ON audit_log (created_at DESC);