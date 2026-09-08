"""End-to-end manual verification for the auth layer (build step 6).

Boots (or reuses) a uvicorn on :8011 and proves the auth contract against
the live Postgres:

  login as admin + investigator            -> 200, bearer tokens
  unauthenticated read "/search"           -> 401
  expired + malformed tokens               -> clean 401 (no JWT exception)
  investigator on upload (admin-only)      -> 403
  admin upload                             -> 200 (the write actually lands)
  audit rows                               -> query back from Postgres audit_log
                                             after a few authenticated calls,
                                             proving user/role/action/endpoint landed
  503 on a server pointed at a dead DB     -> /auth/login returns 503, no traceback

Usage:
    python backend/demo_auth.py [--reset-db]   # --reset-db: drop/rebuild tables first
    # To reset the WHOLE demo (graph + Postgres + audit trail + seed users) in
    # one command, use backend/demo_reset.py — this script is just the auth stage.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR.parent / "data"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

API = "http://localhost:8011/api"
DEAD_API = "http://localhost:8012/api"

SERVER_PROC: subprocess.Popen | None = None
DEAD_SERVER_PROC: subprocess.Popen | None = None

ADMIN = ("admin", "admin123")
INVESTIGATOR = ("investigator", "invest123")


def _wait_health(base: str, timeout: float = 60.0) -> bool:
    u = urlparse(base)
    root = f"{u.scheme}://{u.hostname}:{u.port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(root, timeout=2.0).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def boot_server(base: str, env_extra: dict | None = None) -> subprocess.Popen | None:
    if _wait_health(base, timeout=3.0):
        return None  # reuse an already-running server
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--port", str(urlparse(base).port)],
        cwd=BACKEND_DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if not _wait_health(base):
        proc.kill()
        raise SystemExit(f"uvicorn on {base} failed to boot")
    return proc


def login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    return client.post(f"{API}/auth/login", json={"username": username, "password": password})


def expired_token(username: str = "investigator") -> str:
    """Mint a token whose exp is 1 hour in the past (same SECRET/ALGO as the
    server's default) — proves expired tokens get a clean 401."""
    from jose import jwt
    from app.auth.rbac import ALGORITHM, SECRET_KEY
    return jwt.encode(
        {"sub": username, "role": "investigator",
         "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-db", action="store_true", help="drop + recreate tables first")
    args = parser.parse_args()

    global SERVER_PROC, DEAD_SERVER_PROC

    if args.reset_db:
        from app.db.db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS audit_log")
            cur.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        conn.close()
        subprocess.run(
            [sys.executable, "-m", "app.db.migrate"], cwd=BACKEND_DIR, check=True,
            stdout=subprocess.DEVNULL,
        )
        print("--reset-db: tables rebuilt + reseeded")

    SERVER_PROC = boot_server(API)

    checks = 0
    failures = []
    headers = {}
    with httpx.Client(timeout=30.0) as client:

        def check(label: str, ok: bool, detail: str = "") -> None:
            nonlocal checks
            checks += 1
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
            if not ok:
                failures.append(label)

        # ------------------------------------------------------------ unauth
        print("\n=== unauthenticated requests -> 401 ===")
        r = client.get(f"{API}/search", params={"query": "9812"})
        check("read without token -> 401", r.status_code == 401, f"status={r.status_code}")
        r = client.get(f"{API}/influencers")
        check("analytics without token -> 401", r.status_code == 401, f"status={r.status_code}")
        r = client.post(f"{API}/upload/cdr", files={"file": ("x.csv", b"a,b", "text/csv")})
        check("upload without token -> 401", r.status_code == 401, f"status={r.status_code}")

        # ------------------------------------------------------------- login
        print("\n=== /auth/login ===")
        r = login(client, *INVESTIGATOR)
        check("investigator login -> 200 + bearer token",
              r.status_code == 200 and r.json().get("token_type") == "bearer"
              and r.json().get("role") == "investigator", f"status={r.status_code}")
        inv_token = r.json()["access_token"]

        r = login(client, *ADMIN)
        check("admin login -> 200 + admin role",
              r.status_code == 200 and r.json().get("role") == "admin", f"status={r.status_code}")
        admin_token = r.json()["access_token"]

        r = login(client, "admin", "wrongpassword")
        check("wrong password -> 401", r.status_code == 401, f"status={r.status_code}")
        r = login(client, "nosuchuser", "whatever")
        check("unknown user -> 401", r.status_code == 401, f"status={r.status_code}")

        # --------------------------------------------------- valid read path
        print("\n=== authenticated reads (investigator) ===")
        h_inv = {"Authorization": f"Bearer {inv_token}"}
        r = client.get(f"{API}/search", params={"query": "9812"}, headers=h_inv)
        check("investigator read /search -> 200 + data",
              r.status_code == 200 and any(x["name"] == "9812345601" for x in r.json()["results"]),
              f"status={r.status_code}")
        r = client.get(f"{API}/influencers", headers=h_inv)
        check("investigator read /influencers -> 200", r.status_code == 200)

        # ------------------------------------------------------ token failures
        print("\n=== expired + malformed tokens -> clean 401 ===")
        r = client.get(f"{API}/search", params={"query": "9812"},
                       headers={"Authorization": f"Bearer {expired_token()}"})
        check("expired token -> 401", r.status_code == 401, f"status={r.status_code} body={r.text[:80]}")
        r = client.get(f"{API}/search", params={"query": "9812"},
                       headers={"Authorization": "Bearer not.a.real.jwt"})
        check("malformed token -> 401", r.status_code == 401, f"status={r.status_code} body={r.text[:80]}")
        r = client.get(f"{API}/search", params={"query": "9812"}, headers={"Authorization": "Bearer"})
        check("bearer with no token -> 401", r.status_code == 401, f"status={r.status_code}")

        # ------------------------------------------------------------- RBAC
        print("\n=== RBAC: uploads are admin-only ===")
        h_admin = {"Authorization": f"Bearer {admin_token}"}
        with open(DATA_DIR / "sample_cdr.csv", "rb") as f:
            r = client.post(f"{API}/upload/cdr",
                            files={"file": ("sample_cdr.csv", f, "text/csv")},
                            headers=h_inv)
            check("investigator upload -> 403 (not 401/200)", r.status_code == 403, f"status={r.status_code}")
        with open(DATA_DIR / "sample_cdr.csv", "rb") as f:
            r = client.post(f"{API}/upload/cdr",
                            files={"file": ("sample_cdr.csv", f, "text/csv")},
                            headers=h_admin)
            check("admin upload /upload/cdr -> 200 + written",
                  r.status_code == 200 and r.json().get("written"), f"status={r.status_code}")
        with open(DATA_DIR / "sample_fir.txt", "rb") as f:
            r = client.post(f"{API}/upload/fir",
                            files={"file": ("sample_fir.txt", f, "text/plain")},
                            headers=h_admin)
            check("admin upload /upload/fir -> 200 + clusters",
                  r.status_code == 200 and r.json().get("clusters", 0) >= 3, f"status={r.status_code}")
        r = client.get(f"{API}/subgraph/9812345601", headers=h_inv)
        check("investigator read /subgraph still 200", r.status_code == 200, f"status={r.status_code}")

        # -------------------------------------------------- audit trail proof
        print("\n=== audit_log rows land in Postgres ===")
        from app.db.db import get_connection
        conn = get_connection()
        rows = []
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, role, action, endpoint FROM audit_log ORDER BY id"
            )
            rows = cur.fetchall()
        conn.close()
        print(f"  {len(rows)} audit rows: {rows[-6:]}")
        actions = {(u, r, a, e) for u, r, a, e in rows}
        check("investigator read audited (GET /api/search)",
              ("investigator", "investigator", "GET", "/api/search") in actions, str(actions))
        check("admin upload audited (POST /api/upload/cdr)",
              ("admin", "admin", "POST", "/api/upload/cdr") in actions, str(actions))
        check("403 attempt audited (investigator blocked on upload)",
              ("investigator", "investigator", "POST", "/api/upload/cdr") in actions,
              "the auth dependency logs before the role check")

        # ---------------------------------------------------- dead-DB -> 503
        print("\n=== Postgres unreachable -> 503 (isolated :8012) ===")
        DEAD_SERVER_PROC = boot_server(
            DEAD_API, env_extra={"DATABASE_URL": "postgresql://crimegraph:x@localhost:59998/crimegraph"}
        )
        with httpx.Client(timeout=30.0) as dead:
            r = dead.post(f"{DEAD_API}/auth/login", json={"username": "admin", "password": "admin123"})
            check("login with dead Postgres -> 503",
                  r.status_code == 503, f"status={r.status_code} body={r.text[:100]}")
            r = dead.get(f"{DEAD_API}/search", params={"query": "9812"},
                         headers={"Authorization": f"Bearer {admin_token}"})
            check("read with dead Postgres (audit write fails) -> 503",
                  r.status_code == 503, f"status={r.status_code} body={r.text[:100]}")

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("FAILED:", *failures, sep="\n  ")
        sys.exit(1)
    print("ALL AUTH CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        for proc in (SERVER_PROC, DEAD_SERVER_PROC):
            if proc is not None:
                proc.kill()