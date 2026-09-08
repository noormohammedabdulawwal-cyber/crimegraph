"""
Postgres connection layer (build step 6).

Owns the DATABASE_URL and the two database operations the API actually needs
(get a user by username; insert audit rows). Every call opens a fresh
connection and closes it — in the uvicorn threadpool a shared connection
would need a pool or a lock, and for MVP request volume per-call connections
are the simple, correct choice.

Failure semantics (Reliability NFR — no stack traces to the client):
  * connection failures (refused / unreachable) -> DbUnavailable -> HTTP 503
  * genuine query/programming errors bubble up as HTTP 500 (that's a bug in
    our SQL, not an outage)
"""
import os

import psycopg2
import psycopg2.extras

# Host port 5433, not the Postgres default 5432: the repo's compose maps
# 5433->5432 so it runs isolated from the SIH stack's Postgres on this machine.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://crimegraph:crimegraph_dev@localhost:5433/crimegraph",
)


class DbUnavailable(Exception):
    """The database is unreachable. Map to HTTP 503."""


def get_connection() -> psycopg2.extensions.connection:
    """Open a new connection with a short timeout. Raises DbUnavailable when
    Postgres can't be reached (OperationalError), so callers translate it to
    an HTTP 503 instead of leaking a driver traceback."""
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except psycopg2.OperationalError:
        raise DbUnavailable("postgres not reachable") from None


def get_user_by_username(username: str) -> dict | None:
    """Return the seed user row for `username`, or None."""
    try:
        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, username, password_hash, role FROM users WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()
    except DbUnavailable:
        raise
    except psycopg2.OperationalError:
        raise DbUnavailable("postgres unreachable during query") from None


def insert_audit_event(user_id: str, role: str, action: str, endpoint: str) -> None:
    """Append one audit_log row. Raises DbUnavailable on connection failure."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_log (user_id, role, action, endpoint) "
                    "VALUES (%s, %s, %s, %s)",
                    (user_id, role, action, endpoint),
                )
            conn.commit()
        finally:
            conn.close()
    except DbUnavailable:
        raise
    except psycopg2.OperationalError:
        raise DbUnavailable("postgres unreachable during audit write") from None