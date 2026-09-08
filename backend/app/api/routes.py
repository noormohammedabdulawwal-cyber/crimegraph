"""
REST endpoints for CrimeGraph (PRD section 7 — Functional Requirements).

Build step 5 (see CLAUDE.md). Wires the real ingestion / extraction / graph /
analytics modules behind the HTTP surface.

Auth (step 6): /auth/login is open; every other endpoint requires a Bearer
token via Depends (404/503 and 422 as before):
  401  — missing/invalid/expired token, or bad credentials at login
  403  — valid token but wrong role (uploads are admin-only)
  503  — Neo4j OR Postgres unreachable (connection-level failure)
"""
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from neo4j.exceptions import DriverError, ServiceUnavailable
from pydantic import BaseModel

from app.analytics.anomaly_detection import detect_burst_call_clusters
from app.analytics.community_detection import detect_communities
from app.analytics.centrality import (
    SOCIAL_NODE_PROJECTION,
    SOCIAL_REL_PROJECTION,
    UNIFORM_NODE_PROJECTION,
    UNIFORM_REL_PROJECTION,
    compute_pagerank,
)
from app.auth.rbac import (
    Role,
    create_access_token,
    get_current_user,
    require_admin,
    verify_password,
)
from app.db.db import DbUnavailable, get_user_by_username
from app.extraction.entity_resolution import resolve_entities
from app.extraction.ner import extract_entities
from app.graph.neo4j_client import Neo4jClient
from app.ingestion.cdr_loader import load_cdr_csv

logger = logging.getLogger(__name__)
router = APIRouter()

# Reject oversized uploads with a 413 before reading any bytes into memory —
# a stray multi-GB file must not wedge the worker (PRD Reliability NFR).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB cap for demo CDR/FIR uploads


def _check_upload_size(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )

# Projection presets exposed to /influencers. "social" is the product default
# (people + phones, undirected, real edges); "uniform" is kept for internal
# comparison/debugging only — it is NOT surfaced in the demo UI (it measures a
# scaffold artifact, not influence).
PROJECTIONS = {
    "social": (SOCIAL_NODE_PROJECTION, SOCIAL_REL_PROJECTION),
    "uniform": (UNIFORM_NODE_PROJECTION, UNIFORM_REL_PROJECTION),
}

_client: Neo4jClient | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


# ------------------------------------------------------------------- auth --
@router.post("/auth/login")
async def login(body: LoginRequest):
    """FR9: exchange username/password for a Bearer token. Open endpoint (no
    auth required — it IS the entry point)."""
    try:
        user = get_user_by_username(body.username.strip())
    except DbUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    role = Role(user["role"])
    token = create_access_token(user["username"], role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "username": user["username"],
    }


def _get_client() -> Neo4jClient:
    """Lazy shared client — created on first request so importing this module
    never forces a Neo4j connection."""
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client


def _graph(method, *args, **kwargs):
    """Run a graph call, translating connection-level failures to 503 so the
    caller never sees a driver stack trace."""
    try:
        return method(*args, **kwargs)
    except (ServiceUnavailable, DriverError) as exc:
        logger.error("Neo4j unreachable during %s: %s", getattr(method, "__name__", method), exc)
        raise HTTPException(
            status_code=503, detail="Graph database unavailable"
        ) from exc


def _source_from_filename(filename: str | None, fallback: str) -> str:
    """Derive a provenance id from an uploaded file's stem (e.g. 'sample_cdr')."""
    stem = Path(filename or "").stem.strip()
    return stem or fallback


# ------------------------------------------------------------------- upload --
@router.post("/upload/cdr")
async def upload_cdr(
    request: Request,
    file: UploadFile,
    _admin: dict = Depends(require_admin),
):
    """FR1: ingest a CDR CSV. Runs the real loader (Step 1), then pushes the
    valid records into the graph. Returns an ingestion-health summary in the
    CdrLoadResult shape: records loaded, rows skipped, per-row reasons."""
    _check_upload_size(request)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="uploaded file is empty")

    source = _source_from_filename(file.filename, "cdr_upload")

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            result = load_cdr_csv(tmp_path)
        except ValueError as exc:
            # Bad file — schema error, not a connection problem.
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        _graph(_get_client().write_cdr_records, result.records, source)
        return {
            "source": source,
            "records": len(result.records),
            "skipped_rows": result.skipped_rows,
            "errors": result.errors,  # [{"row": csv_line, "reason": str}]
            "written": True,
        }
    finally:
        if tmp_path:
            os.unlink(tmp_path)


@router.post("/upload/fir")
async def upload_fir(
    request: Request,
    file: UploadFile,
    _admin: dict = Depends(require_admin),
):
    """FR1: ingest an FIR text file. Text -> NER -> entity resolution -> graph
    write (the full extraction chain from Steps 2/3)."""
    _check_upload_size(request)
    data = await file.read()
    if not data or not data.strip():
        raise HTTPException(status_code=422, detail="uploaded file is empty")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"not valid UTF-8 text: {exc}"
        ) from exc

    case_id = _source_from_filename(file.filename, "fir_upload")
    entities = extract_entities(text, case_id)
    clusters = resolve_entities(entities)
    _graph(_get_client().write_fir_entities, clusters, case_id)

    return {
        "case_id": case_id,
        "raw_entities": len(entities),
        "clusters": len(clusters),
        "entities": [
            {"name": name, "mentions": len(members)}
            for name, members in clusters.items()
        ],
        "written": True,
    }


# ------------------------------------------------------------------- search --
@router.get("/search")
async def search_entity(
    query: str,
    limit: int = 50,
    _user: dict = Depends(get_current_user),
):
    """FR8: substring search over canonical entity names (the de-duplicated
    names from entity resolution, not raw mentions). Case-insensitive so a
    judge typing "ramesh" finds "Ramesh Patel" — at demo scale a toLower()
    scan is cheap (no index needed)."""
    query = query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must not be empty")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")

    rows = _graph(
        _get_client().run,
        """
        MATCH (n)
        WHERE toLower(n.name) CONTAINS toLower($q)
        RETURN n.name AS name, labels(n)[0] AS label,
               coalesce(n.source_cases, []) AS source_cases
        ORDER BY n.name
        LIMIT $limit
        """,
        q=query,
        limit=limit,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"no entities match {query!r}")
    return {"query": query, "results": rows}


@router.get("/subgraph/{entity_name}")
async def get_subgraph(
    entity_name: str,
    hops: int = 2,
    include_communities: bool = False,
    _user: dict = Depends(get_current_user),
):
    """FR7/FR8: N-hop neighborhood shaped for the frontend Cytoscape consumer
    ({nodes, edges} with provenance + confidence on every element).

    ?include_communities=true runs Louvain over the SOCIAL projection and
    stamps each returned node with its community id, so the frontend can draw
    the "cell" grouping without a second round-trip."""
    if hops < 1 or hops > 5:
        raise HTTPException(status_code=422, detail="hops must be between 1 and 5")

    g = _graph(_get_client().get_subgraph_graph, entity_name, hops)
    if not g["nodes"]:
        raise HTTPException(status_code=404, detail=f"entity {entity_name!r} not found in graph")

    if include_communities:
        communities = _graph(detect_communities, _get_client())
        cid_by_name = {row["name"]: row["communityId"] for row in communities}
        for node in g["nodes"]:
            node["communityId"] = cid_by_name.get(node["name"])
    return g


# ------------------------------------------------------------------ analytics --
@router.get("/influencers")
async def get_influencers(
    top_n: int = 5,
    projection: str = "social",
    _user: dict = Depends(get_current_user),
):
    """FR5: top-N key influencers by PageRank. Defaults to the approved SOCIAL
    projection; ?projection=uniform is exposed for internal comparison only."""
    if projection not in PROJECTIONS:
        raise HTTPException(
            status_code=422, detail=f"projection must be one of {sorted(PROJECTIONS)}"
        )
    if top_n < 1 or top_n > 50:
        raise HTTPException(status_code=422, detail="top_n must be between 1 and 50")

    node_spec, rel_spec = PROJECTIONS[projection]
    rows = _graph(
        compute_pagerank,
        _get_client(),
        top_n=top_n,
        node_projection=node_spec,
        rel_projection=rel_spec,
    )
    return {"projection": projection, "top_n": top_n, "influencers": rows}


@router.get("/patterns/flagged")
async def get_flagged_patterns(
    _user: dict = Depends(get_current_user),
):
    """FR6: suspicious patterns over whatever CDR data is currently in the
    graph (so a new upload via /upload/cdr is reflected here on the next call).
    Every pattern carries a confidence + the evidence window (FR12)."""
    records = _graph(_get_client().get_all_call_records)
    flags = detect_burst_call_clusters(records)
    return {"call_records_analyzed": len(records), "patterns": flags}
