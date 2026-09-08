# CLAUDE.md — Project Instructions for Claude Code

## Project

**CrimeGraph** — AI-Powered Criminal Network Analysis System
SIH 2026, Problem Statement ID **26189** (Ministry of Home Affairs / NCRB, Women Safety Division).
Full requirements: `docs/PRD_AI_Criminal_Network_Analysis_System.md` — read this first before making architectural decisions.

## What this system does

Ingests crime-related data (FIRs, CDRs, financial records, surveillance reports) → extracts entities
(people, phones, vehicles, locations, organizations) via NLP → builds a knowledge graph in Neo4j →
runs graph analytics to find key influencers and suspicious patterns → shows it all in an interactive
investigator dashboard.

## Tech stack (do not deviate without discussing first)

| Layer | Tech |
|---|---|
| Backend | Python 3.14 (the pinned venv resolves 3.14.4), FastAPI |
| NLP/NER | spaCy (`en_core_web_trf` or similar), regex for phone/vehicle patterns |
| Graph DB | Neo4j (Cypher, Graph Data Science library for PageRank/Louvain) |
| Relational | PostgreSQL (users, case metadata, audit logs) |
| Frontend | React + TypeScript + Tailwind CSS |
| Graph viz | Cytoscape.js |
| Auth | JWT + RBAC middleware |
| Dev environment | Docker Compose |

## Repo layout

```
backend/app/
  ingestion/     - loaders for CDR/FIR/financial CSV & text input
  extraction/    - NER, entity resolution/deduplication
  graph/         - Neo4j client, schema, graph-write logic
  analytics/     - centrality, community detection, anomaly detection
  api/           - FastAPI routes
  auth/          - RBAC, JWT
frontend/src/
  components/    - GraphView, SearchBar, InfluencerPanel
  api/           - typed API client
data/            - sample synthetic CDR/FIR data for local dev — never real case data
docs/            - PRD and design docs
```

## Build order (MVP — follow this sequence)

1. `backend/app/ingestion` — CSV loader for sample CDR data + plain-text loader for sample FIRs
2. `backend/app/extraction` — spaCy NER pipeline extracting person/phone/location/vehicle; simple
   fuzzy-match entity resolution to merge duplicate/alias entities
3. `backend/app/graph` — Neo4j schema (nodes: Person, Phone, Vehicle, Location, Organization, Event;
   relationships: CALLED, TRANSACTED_WITH, CO_LOCATED_WITH, ASSOCIATED_WITH) + write pipeline
4. `backend/app/analytics` — PageRank/betweenness centrality for "key influencer" ranking; one
   suspicious-pattern detector (start with burst-call clustering — simplest to demo)
5. `backend/app/api` — REST endpoints: upload data, search entity, get sub-graph (N-hop), get
   influencer ranking, get flagged patterns
6. `backend/app/auth` — basic JWT login + two roles (investigator, admin) + audit log on every query
7. `frontend` — search bar → sub-graph fetch → Cytoscape graph view → influencer panel

Do not build ahead of this order (e.g. don't build the frontend graph view before the API returns
real graph data) — each step should be demoable before moving to the next.

## Non-negotiables

- **Every AI-inferred relationship must carry a confidence score and source record ID(s).** Never
  present an inferred link as ground truth.
- **Use only synthetic/sample data in this repo.** No real case data, real names, or real phone
  numbers, ever — this is a hackathon prototype, not a production system handling real investigations.
- RBAC + audit logging are part of the MVP, not a "later" item — build them alongside the API, not
  after.
- Keep ingestion, extraction, graph, and analytics as separate modules with clean interfaces — the
  PRD's non-goals (real-time telecom integration, predictive risk-scoring) are explicitly out of
  scope; don't let scope creep in.

## Commands

```bash
docker compose up -d          # starts Postgres + an ISOLATED Neo4j (host bolt 7688, http 7475)
python backend/demo_reset.py  # wipe Neo4j+Postgres and re-load sample data + seed users (pristine demo state)
cd backend && uvicorn app.main:app --reload --port 8011
cd frontend && npm run dev
```

## Dev environment note — port isolation (this machine)

This machine already runs a separate, pre-existing SIH stack that owns the
standard ports (Neo4j bolt 7687/http 7474, backend 8000, Postgres 5432, and
frontend 3000 — "Network Intelligence"). To avoid collisions, CrimeGraph is
**isolated**:

| Service | Host port |
|---|---|
| Neo4j bolt | **7688** (container 7687) |
| Neo4j http/browser | **7475** (container 7474) |
| FastAPI backend | **8011** |
| Postgres | **5433** (container 5432) |
| Frontend dev | **3003** |

Why: this repo needs its own graph so entity-resolution tuning and GDS
projections don't collide with the other stack. `neo4j_client.py` defaults to
`bolt://localhost:7688` (override with `NEO4J_URI`); `app/db/db.py` defaults
`DATABASE_URL` to `postgresql://crimegraph:crimegraph_dev@localhost:5433/crimegraph`
(override with `DATABASE_URL`); the backend must run with `--port 8011`; the
frontend dev server runs on `--port 3003` (3000 is the SIH stack's) and the
frontend API client targets `http://localhost:8011/api`. The backend's CORS
allow-list is `localhost:3003` only (see `app/main.py`). Do not "fix" these
back to standard ports.

Postgres users/audit schema: schema.sql is applied idempotently by
`cd backend && ../.venv/bin/python -m app.db.migrate` (also auto-runs on a
fresh postgres volume via the docker-entrypoint-initdb.d mount). Seed users are
admin/admin123 and investigator/invest123 (synthetic, for the demo only).
