"""Schema + seed migration for the CrimeGraph Postgres database.

Applies backend/app/db/schema.sql idempotently (CREATE TABLE IF NOT EXISTS /
ON CONFLICT DO NOTHING), then seeds the two demo users with bcrypt hashes.

Usage:
    python -m app.db.migrate        (from backend/)
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.db import DbUnavailable, get_connection  # noqa: E402
from app.auth.rbac import Role, hash_password  # noqa: E402

SEED_USERS = [
    # (username, password, role) — demo credentials, synthetic only (CLAUDE.md)
    ("admin", "admin123", Role.ADMIN),
    ("investigator", "invest123", Role.INVESTIGATOR),
]


def apply_schema(conn) -> None:
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with conn.cursor() as cur:
        cur.execute(schema_path.read_text(encoding="utf-8"))
    conn.commit()


def seed_users(conn) -> None:
    with conn.cursor() as cur:
        for username, password, role in SEED_USERS:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (username) DO NOTHING",
                (username, hash_password(password), role.value),
            )
    conn.commit()


def main() -> None:
    try:
        conn = get_connection()
    except DbUnavailable as exc:
        print(f"FATAL: {exc} — is 'docker compose up -d postgres' running on 5433?")
        sys.exit(1)
    try:
        apply_schema(conn)
        print("schema applied (users, audit_log)")
        seed_users(conn)
        print("seed users ensured (admin, investigator)")
    finally:
        conn.close()
    print("migrate OK")


if __name__ == "__main__":
    main()