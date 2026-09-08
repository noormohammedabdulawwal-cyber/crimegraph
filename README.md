# CrimeGraph

AI-Powered Criminal Network Analysis System 

See `docs/PRD_AI_Criminal_Network_Analysis_System.md` for the full requirements
and `CLAUDE.md` for build instructions / conventions used by Claude Code.

## Quick start

```bash
docker compose up -d              # Neo4j (bolt 7688) + Postgres (5433)
python backend/demo_reset.py      # wipe + re-load sample data and seed users
cd backend && ../.venv/bin/uvicorn app.main:app --port 8011   # http://localhost:8011
cd frontend && npm run dev        # http://localhost:3003 (3000/5173 taken by SIH)
```

## Status

**MVP complete** — ingestion, extraction, graph, analytics, API, auth (JWT + RBAC
+ audit), and the investigator dashboard all working end-to-end. Sample data
loaded; demo users: `admin/admin123`, `investigator/invest123`.
