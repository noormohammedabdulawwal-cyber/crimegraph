"""End-to-end manual verification for the graph layer (build step 3).

Writes the sample CDR + FIR entities into the isolated Neo4j through the write
pipeline, then verifies by querying back: node/edge counts, a CALLED subgraph,
an ASSOCIATED_WITH subgraph, cross-world (CDR<->FIR) reachability, and
idempotency of re-ingesting the same source.

Requires the repo Neo4j on localhost:7688 (`docker compose up -d neo4j`).

Usage:
    python backend/demo_graph_write.py [--reset]   # --reset: wipe the graph first
    # To reset the WHOLE demo (graph + Postgres + seed users) in one command,
    # use backend/demo_reset.py — this script is just the graph stage.
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.extraction.entity_resolution import resolve_entities  # noqa: E402
from app.extraction.ner import extract_entities  # noqa: E402
from app.graph.neo4j_client import Neo4jClient  # noqa: E402
from app.ingestion.cdr_loader import load_cdr_csv  # noqa: E402
from app.ingestion.fir_loader import load_fir_text  # noqa: E402

DATA_DIR = BACKEND_DIR.parent / "data"

CDR_SOURCE = "sample_cdr"
FIR_CASE_ID = "sample_fir"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete all nodes/edges first")
    args = parser.parse_args()

    client = Neo4jClient()
    try:
        if not client.ping(timeout=240):
            raise SystemExit(
                "Neo4j not reachable on bolt://localhost:7688 — is "
                "'docker compose up -d neo4j' running?"
            )
        if args.reset:
            client.run("MATCH (n) DETACH DELETE n")
            print("--reset: graph wiped")

        client.init_schema()
        print("schema constraints + index created (idempotent)\n")

        # 1. CDR pipeline
        cdr = load_cdr_csv(str(DATA_DIR / "sample_cdr.csv"))
        print(f"CDR: {len(cdr.records)} records, {cdr.skipped_rows} skipped")
        client.write_cdr_records(cdr.records, CDR_SOURCE)

        # 2. FIR pipeline: text -> NER -> resolution -> graph write
        fir = load_fir_text(FIR_CASE_ID, str(DATA_DIR / "sample_fir.txt"))
        entities = extract_entities(fir.raw_text, FIR_CASE_ID)
        clusters = resolve_entities(entities)
        print(f"FIR: {len(entities)} raw entities -> {len(clusters)} clusters")
        client.write_fir_entities(clusters, FIR_CASE_ID)

        counts = client.counts()
        print("\ncounts:", counts)

        # 3. Idempotency: re-ingest the same sources, counts must not change
        client.write_cdr_records(cdr.records, CDR_SOURCE)
        client.write_fir_entities(clusters, FIR_CASE_ID)
        counts_after = client.counts()
        assert counts_after == counts, (
            f"re-ingest changed the graph!\n before={counts}\n after={counts_after}"
        )
        print("idempotency: re-ingesting the same sources left counts unchanged")

        # 4. Subgraph around a CDR phone (caller 9812345601) — must reach the
        #    FIR world via the Person-OWNS-Phone link (the cross-world demo story)
        g = client.get_subgraph_graph("9812345601", hops=1)
        names = sorted(n["name"] for n in g["nodes"])
        print(f"\nsubgraph('9812345601', 1 hop): {len(g['nodes'])} nodes {len(g['edges'])} edges")
        print("  nodes:", names)

        # 5. Subgraph around a FIR person
        g2 = client.get_subgraph_graph("Ramesh Patel", hops=1)
        names2 = sorted(n["name"] for n in g2["nodes"])
        assoc = sorted({e["type"] for e in g2["edges"]})
        print(f"subgraph('Ramesh Patel', 1 hop): {len(g2['nodes'])} nodes {len(g2['edges'])} edges")
        print("  nodes:", names2, f"  edge types: {assoc}")

        # ---- soft assertions (fail loudly if the demo story breaks) ----
        # Reachability invariants that hold regardless of graph history.
        assert "9823456712" in names and "9856789045" in names
        assert "Ramesh Patel" in names, "phone search should surface the FIR person (cross-world)"
        assert "Vikram" in names2 and "Suresh Chauhan" in names2
        assert "9812345601" in names2, "person search should surface their phone"

        # The exact node/edge counts only hold on a pristine graph — a single
        # ingest of each sample source, which --reset guarantees. Without --reset
        # the graph may already hold this data (a prior run, or API uploads), in
        # which case re-ingestion is idempotent and the totals are already at
        # steady state; assert the exact baseline only when we reset it.
        if args.reset:
            assert counts["nodes"].get("Phone") == 7, "expected 7 unique phones from CDR"
            assert counts["relationships"].get("CALLED") == 10, "expected 10 CALLED edges"
            assert counts["nodes"].get("Person") == 3, "expected 3 persons from FIR"
            assert counts["relationships"].get("ASSOCIATED_WITH") == 3, "expected 3 person pairs"
            assert counts["relationships"].get("OWNS") == 6, "expected 3 persons x 2 owned entities"
            print("\nALL GRAPH CHECKS PASSED (exact per-source counts, --reset)")
        else:
            print("\nALL GRAPH CHECKS PASSED (idempotency + reachability;"
                  "\n  exact-count asserts require --reset on a fresh graph)")
    finally:
        client.close()


if __name__ == "__main__":
    main()