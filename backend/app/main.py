"""
CrimeGraph API entrypoint.

Wires up the ingestion / extraction / graph / analytics modules behind a
FastAPI app. See CLAUDE.md for the build order this scaffold follows.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router

app = FastAPI(
    title="CrimeGraph API",
    description="AI-Powered Criminal Network Analysis System — SIH 2026 (PS 26189)",
    version="0.1.0",
)

# CORS (build step 7): the Vite dev server on :3003 is a different origin than
# the API on :8011, so the browser preflights every call (Authorization header
# trips it even on GETs). Scoped to the CrimeGraph frontend origin(s) only —
# auth is bearer-token based (no cookies), so no credentials=True needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3003",
        "http://127.0.0.1:3003",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
