"""
JWT auth + role-based access control (PRD FR9) + audit logging.

Build step 6. Real implementations replace the step-0 scaffold:
  * passwords stored as bcrypt hashes (direct bcrypt lib — passlib 1.7.4 is
    broken at runtime against the modern bcrypt this Python 3.14 install
    resolved, so we hash directly rather than fighting the toolchain)
  * create/decode_access_token — HS256 JWT; decode returns None on any JWT
    error (expired, malformed, wrong signature) and the FastAPI dependency
    turns that into a clean 401
  * log_audit_event -> INSERT into Postgres audit_log (user_id, role, action,
    endpoint, timestamp); never stdout
  * get_current_user / require_admin are FastAPI Depends() — every protected
    route declares one of them and FastAPI enforces it; no hand-rolled checks.

Auditability is non-negotiable (CLAUDE.md): the auth dependency logs every
authenticated request before the handler runs. A Postgres outage surfaces as
HTTP 503 (Reliability NFR), never a stack trace.
"""
import os
from datetime import datetime, timedelta, timezone
from enum import Enum

import bcrypt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.db.db import DbUnavailable, insert_audit_event

SECRET_KEY = os.environ.get("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

bearer_scheme = HTTPBearer(auto_error=False)  # None credentials -> our clean 401


class Role(str, Enum):
    INVESTIGATOR = "investigator"
    ADMIN = "admin"


# ------------------------------------------------------------------ passwords
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False  # malformed stored hash — treat as a failed login, no crash


# ----------------------------------------------------------------------- JWT
def create_access_token(username: str, role: Role) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role.value, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Return the token payload, or None for any expired/malformed/invalid
    token — the caller (and the public API) never sees a JWT exception."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------- audit trail
def log_audit_event(user_id: str, role: str, action: str, endpoint: str) -> None:
    """Persist one audit_log row. Postgres unreachable -> 503, not stdout."""
    try:
        insert_audit_event(user_id, role, action, endpoint)
    except DbUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------- dependencies
def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Authenticate the Bearer token; audit the request. Every protected route
    declares `user: dict = Depends(get_current_user)`."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated — provide a Bearer token")
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    username = payload.get("sub")
    role = payload.get("role")
    if not username:
        raise HTTPException(status_code=401, detail="Token missing subject")

    # Action captures method + endpoint from the actual request (e.g.
    # "GET /api/search"); the audit row is written by every authenticated call.
    log_audit_event(username, role or "", request.method, str(request.url.path))
    return {"username": username, "role": role}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Compose with get_current_user: caller must hold the admin role."""
    if user.get("role") != Role.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin role required for this action")
    return user