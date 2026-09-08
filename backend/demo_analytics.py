"""End-to-end manual verification for the analytics layer (build step 4).

Runs all four analytics against the REAL loaded graph + sample CDR:
  * GDS availability (gds.version)
  * degree baseline (sanity anchor for centrality)
  * PageRank — UNIFORM wildcard vs scoped SOCIAL projection
  * betweenness centrality — SOCIAL projection
  * Louvain community detection — SOCIAL projection
  * burst-call detection on data/sample_cdr.csv

Prints everything; a human (the integrator) reads the rankings against the
degree table and decides the OWNS-weighting judgment call for step 5.

Requires the isolated Neo4j running with the graph already written.
The one-command way to get there from a pristine state:

    python backend/demo_reset.py        # wipe + reseed graph AND Postgres

(Equivalently backend/demo_graph_write.py --reset first, but demo_reset.py
is the canonical reset and also re-seeds users + the audit trail.)

Usage:
    python backend/demo_analytics.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.analytics.anomaly_detection import detect_burst_call_clusters  # noqa: E402
from app.analytics.centrality import (  # noqa: E402
    SOCIAL_NODE_PROJECTION,
    SOCIAL_REL_PROJECTION,
    UNIFORM_NODE_PROJECTION,
    UNIFORM_REL_PROJECTION,
    compute_betweenness,
    compute_pagerank,
)
from app.analytics.community_detection import detect_communities  # noqa: E402
from app.graph.neo4j_client import Neo4jClient  # noqa: E402
from app.ingestion.cdr_loader import load_cdr_csv  # noqa: E402

DATA_DIR = BACKEND_DIR.parent / "data"


def gds_version(client: Neo4jClient) -> str:
    """GDS 2.x changed the version-proc output shape; probe candidates."""
    for query in (
        "RETURN gds.version() AS version",
        "CALL gds.version() YIELD version RETURN version",
        "CALL gds.version() YIELD gdsVersion RETURN gdsVersion",
    ):
        try:
            rows = client.run(query)
            if rows:
                row = rows[0]
                return str(row.get("version") or row.get("gdsVersion"))
        except Exception:
            continue
    return "PROBE FAILED"


def main() -> None:
    client = Neo4jClient()
    try:
        if not client.ping(timeout=120):
            raise SystemExit(
                "Neo4j not reachable on bolt://localhost:7688 — is "
                "'docker compose up -d neo4j' running? Re-seed with "
                "backend/demo_reset.py"
            )
        print("GDS version:", gds_version(client))

        print("\n=== degree baseline (sanity anchor) ===")
        degree = client.run(
            "MATCH (n)-[r]-() RETURN n.name AS name, labels(n)[0] AS label, "
            "count(r) AS degree ORDER BY degree DESC"
        )
        for row in degree:
            print(f"  {row['label']:<13} {row['name']:<22} degree={row['degree']}")
        top_degree = [row["name"] for row in degree]

        print("\n=== PageRank: UNIFORM ('*','*', directed) — scaffold baseline ===")
        pr_uniform = compute_pagerank(
            client, node_projection=UNIFORM_NODE_PROJECTION, rel_projection=UNIFORM_REL_PROJECTION
        )
        for row in pr_uniform:
            print(f"  {row['name']:<22} score={row['score']:.4f}")

        print("\n=== PageRank: SOCIAL (people+phones, undirected) ===")
        pr_social = compute_pagerank(
            client, node_projection=SOCIAL_NODE_PROJECTION, rel_projection=SOCIAL_REL_PROJECTION
        )
        for row in pr_social:
            print(f"  {row['name']:<22} score={row['score']:.4f}")

        print("\n=== sanity: top PageRank vs top degree ===")
        pr_top = pr_uniform[0]["name"]
        print(f"  uniform PageRank #1: {pr_top!r}")
        print(f"  highest-degree node: {top_degree[0]!r}")
        print(f"  match: {pr_top == top_degree[0]}")
        if pr_social:
            print(f"  social PageRank #1: {pr_social[0]['name']!r}")

        print("\n=== betweenness: SOCIAL (people+phones, undirected) ===")
        bw = compute_betweenness(
            client, node_projection=SOCIAL_NODE_PROJECTION, rel_projection=SOCIAL_REL_PROJECTION
        )
        for row in bw:
            print(f"  {row['name']:<22} score={row['score']:.4f}")

        print("\n=== Louvain communities: SOCIAL projection ===")
        communities = detect_communities(client)
        counts: dict[int, int] = {}
        for row in communities:
            counts[row["communityId"]] = counts.get(row["communityId"], 0) + 1
        print(f"  distinct communities: {len(counts)}")
        for cid, size in sorted(counts.items()):
            members = [r["name"] for r in communities if r["communityId"] == cid]
            print(f"  community {cid}: {size} members -> {members}")

        print("\n=== burst-call clusters on sample_cdr.csv ===")
        cdr = load_cdr_csv(str(DATA_DIR / "sample_cdr.csv"))
        flags = detect_burst_call_clusters(cdr.records)
        if not flags:
            print("  (none flagged)")
        for f in flags:
            print(f"  {f['pair']}  calls_in_window={f['call_count_in_window']} "
                  f"window_start={f['window_start']} confidence={f['confidence']:.2f} "
                  f"type={f['pattern_type']}")
    finally:
        client.close()


if __name__ == "__main__":
    main()