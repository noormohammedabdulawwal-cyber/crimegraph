#!/usr/bin/env python
"""One-command state reset for the judged demo.

Consolidates the scattered --reset flags (demo_graph_write --reset, demo_api
--reset, demo_auth --reset-db) into a single command so a practice run or the
judged demo always starts from the same pristine state:

  Graph  : DETACH DELETE all nodes/edges -> init_schema() -> re-ingest
           sample_cdr.csv + sample_fir.txt through the real pipelines
           (identical to demo_graph_write.py's seed path).
  DB     : DROP users/audit_log -> re-apply schema.sql -> re-seed admin/
           investigator (identical to demo_auth --reset-db).

Both are direct-to-Neo4j / direct-to-Postgres — they do NOT go through the
running HTTP API, so the reset works whether uvicorn is up or not. Servers on
8011 will pick up the new state on their next request (the graph client is
lazy and Postgres connections are per-request).

Usage:
    python backend/demo_reset.py            # reset graph + database (default)
    python backend/demo_reset.py --graph-only
    python backend/demo_reset.py --db-only

If the containers themselves are so corrupted that even this fails, the
nuclear option is:
    docker compose down -v && docker compose up -d
then re-run this script (schema.sql + seed users auto-apply on the fresh
Postgres volume).
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR.parent / "data"

CDR_SOURCE = "sample_cdr"
FIR_CASE_ID = "sample_fir"
FIR2_CASE_ID = "sample_fir_2"

# Demo seed users — keep in sync with app/db/migrate.py.
SEED_USERS = ("admin", "investigator")


def reset_graph() -> None:
    from app.extraction.entity_resolution import resolve_entities
    from app.extraction.ner import extract_entities
    from app.graph.neo4j_client import Neo4jClient

    client = Neo4jClient()
    try:
        if not client.ping(timeout=240):
            raise SystemExit(
                "Neo4j not reachable on bolt://localhost:7688 — is "
                "'docker compose up -d neo4j' running?"
            )

        client.run("MATCH (n) DETACH DELETE n")
        print("[graph] wiped all nodes + edges")
        client.init_schema()
        print("[graph] schema constraints created (idempotent)")

        # CDR through the real ingestion + write pipeline.
        from app.ingestion.cdr_loader import load_cdr_csv
        cdr = load_cdr_csv(str(DATA_DIR / "sample_cdr.csv"))
        if cdr.skipped_rows:
            print(f"[graph] WARNING: {cdr.skipped_rows} CDR rows skipped: {cdr.errors}")
        client.write_cdr_records(cdr.records, CDR_SOURCE)
        print(f"[graph] CDR ingested: {len(cdr.records)} CallRecords (source={CDR_SOURCE})")

        # FIR through the real NER + resolution + write pipeline.
        from app.ingestion.fir_loader import load_fir_text, FIRDocument
        fir: FIRDocument = load_fir_text(FIR_CASE_ID, str(DATA_DIR / "sample_fir.txt"))
        entities = extract_entities(fir.raw_text, FIR_CASE_ID)
        clusters = resolve_entities(entities)
        client.write_fir_entities(clusters, FIR_CASE_ID)
        print(f"[graph] FIR ingested: {len(entities)} raw entities -> "
              f"{len(clusters)} clusters (case_id={FIR_CASE_ID})")

        # Second FIR: a separate case whose people are NOT linked to the CDR
        # phone network — creates a distinct Louvain community for the demo.
        fir2: FIRDocument = load_fir_text(FIR2_CASE_ID, str(DATA_DIR / "sample_fir_2.txt"))
        entities2 = extract_entities(fir2.raw_text, FIR2_CASE_ID)
        clusters2 = resolve_entities(entities2)
        client.write_fir_entities(clusters2, FIR2_CASE_ID)
        print(f"[graph] FIR ingested: {len(entities2)} raw entities -> "
              f"{len(clusters2)} clusters (case_id={FIR2_CASE_ID})")

        counts = client.counts()
        print(f"[graph] final counts: {counts}")
    finally:
        client.close()


def reset_db() -> None:
    from app.db.migrate import apply_schema, seed_users
    from app.db.db import DbUnavailable, get_connection
    from app.auth.rbac import Role, hash_password  # noqa: F401  (seed_users uses it)

    try:
        conn = get_connection()
    except DbUnavailable as exc:
        raise SystemExit(
            f"Postgres not reachable — is 'docker compose up -d postgres' running "
            f"on 5433? ({exc})"
        )
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS audit_log")
            cur.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        print("[db] dropped users + audit_log (clean audit trail for the demo)")

        apply_schema(conn)
        seed_users(conn)
        print(f"[db] schema applied + seed users ensured: {', '.join(SEED_USERS)}")
    finally:
        conn.close()


def verify() -> None:
    from app.graph.neo4j_client import Neo4jClient
    from app.db.db import get_connection

    # Sanity: influencer #1 must be the call hub, not a sink artifact — this
    # is the single most likely thing to be "off" after a bad reset.
    from app.analytics.centrality import (
        SOCIAL_NODE_PROJECTION, SOCIAL_REL_PROJECTION, compute_pagerank,
    )

    client = Neo4jClient()
    try:
        counts = client.counts()
        total = sum(counts["nodes"].values())
        print(f"[verify] graph nodes: {total} "
              f"({', '.join(f'{k}={v}' for k, v in counts['nodes'].items())})")
        top = compute_pagerank(
            client, top_n=1, node_projection=SOCIAL_NODE_PROJECTION,
            rel_projection=SOCIAL_REL_PROJECTION,
        )
        print(f"[verify] top influencer (SOCIAL): {top[0]['name']} "
              f"score={top[0]['score']:.3f}")
    finally:
        client.close()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audit_log")
            audit = cur.fetchone()[0]
            cur.execute("SELECT username, role FROM users ORDER BY username")
            users = cur.fetchall()
        print(f"[verify] audit_log rows: {audit} (expect 0 — pristine)")
        print(f"[verify] users: {users}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-only", action="store_true",
                        help="reset only the Neo4j graph + re-seed sample data")
    parser.add_argument("--db-only", action="store_true",
                        help="reset only Postgres (users + audit_log) + re-seed")
    args = parser.parse_args()

    if args.graph_only and args.db_only:
        parser.error("--graph-only and --db-only are mutually exclusive")
    do_graph = not args.db_only
    do_db = not args.graph_only

    print("CrimeGraph demo reset")
    print("--------------------")
    if do_graph:
        reset_graph()
    if do_db:
        reset_db()
    print("--------------------")
    verify()
    print("Reset complete — state is pristine. Start the stack with:")
    print("  cd backend && uvicorn app.main:app --port 8011")
    print("  cd frontend && npm run dev   # http://localhost:3003")


if __name__ == "__main__":
    main()