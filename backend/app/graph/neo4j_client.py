"""
Neo4j connection + write pipeline for the knowledge graph.

Build step 3 (see CLAUDE.md). Node labels: Person, Phone, Vehicle, Location,
Organization, Event. Relationship types: CALLED, TRANSACTED_WITH,
CO_LOCATED_WITH, ASSOCIATED_WITH — every relationship carries `confidence`
and `source_case_id` (never assert a link without provenance; CLAUDE.md).

Write pipeline:
  write_cdr_records()   — Phone nodes + one CALLED edge per call from CDR
                          CallRecords. Calls are observed facts, so confidence
                          is 1.0 and each edge keeps its call (timestamp,
                          duration) for the step-4 burst-call detector.
  write_fir_entities()  — entity nodes from resolved extraction clusters, plus
                          ASSOCIATED_WITH edges between persons who appear in
                          the same FIR (co-occurrence inference: confidence =
                          the weaker of the two entity confidences).
"""
import logging
import os
import time
from datetime import datetime

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

logger = logging.getLogger(__name__)

from app.extraction.ner import EntityType
from app.graph.schema import NODE_LABELS
from app.ingestion.cdr_loader import CallRecord

# Host bolt port is 7688, not the Neo4j default 7687: the repo's compose maps
# 7688->7687 so it can run isolated from the other SIH stack on this machine.
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7688")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "crimegraph_dev")

# Map extraction entity types onto the schema's Neo4j node labels.
_ENTITY_LABEL = {
    EntityType.PERSON: "Person",
    EntityType.PHONE: "Phone",
    EntityType.VEHICLE: "Vehicle",
    EntityType.LOCATION: "Location",
    EntityType.ORGANIZATION: "Organization",
}

class Neo4jClient:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            # Fail fast when the graph is unreachable instead of letting a
            # request hang on the driver's 30s default connect wait.
            connection_timeout=5.0,
        )

    def close(self):
        self._driver.close()

    def ping(self, timeout: float = 180.0) -> bool:
        """Wait (up to `timeout` s) until Bolt accepts a trivial query. Lets
        demos/scripts boot their own dependency without a separate poll step."""
        deadline = time.time() + timeout
        while True:
            try:
                with self._driver.session() as session:
                    session.run("RETURN 1")
                return True
            except ServiceUnavailable:
                if time.time() >= deadline:
                    return False
                time.sleep(5)

    # ------------------------------------------------------------- schema --
    def init_schema(self):
        """Idempotently create the schema: a unique-name constraint per node
        label (so entity resolution genuinely de-dupes at the DB level) and a
        CALLED.timestamp index for the burst-call detector (step 4). Safe to
        call on every boot."""
        with self._driver.session() as session:
            for label in NODE_LABELS:
                session.run(
                    f"CREATE CONSTRAINT entity_name_{label.lower()} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.name IS UNIQUE"
                )
            session.run(
                "CREATE INDEX call_timestamp IF NOT EXISTS "
                "FOR ()-[r:CALLED]-() ON (r.timestamp)"
            )

    # ------------------------------------------------------------- writers --
    def upsert_entity(self, label: str, name: str, source_case_id: str):
        """Create or match an entity node by name, tracking which case(s) it
        has appeared in. Re-upserting the same case is a no-op (idempotent)."""
        query = f"""
        MERGE (e:{label} {{name: $name}})
        ON CREATE SET e.first_seen_case = $source_case_id
        SET e.source_cases = CASE
            WHEN $source_case_id IN coalesce(e.source_cases, []) THEN e.source_cases
            ELSE coalesce(e.source_cases, []) + $source_case_id
        END
        RETURN e.name
        """
        with self._driver.session() as session:
            session.run(query, name=name, source_case_id=source_case_id)

    def upsert_relationship(
        self,
        from_label: str,
        from_name: str,
        to_label: str,
        to_name: str,
        rel_type: str,
        confidence: float,
        source_case_id: str,
    ):
        """Match or create a relationship of `rel_type` between the two named
        nodes. `source_case_id` records where the edge was first established
        (ON CREATE), so a later case re-asserting the same pair never
        misattributes the evidence to itself — it only appends to the growing
        source_cases list. Confidence is refreshed on every write (latest
        assessment of that link)."""
        query = f"""
        MATCH (a:{from_label} {{name: $from_name}})
        MATCH (b:{to_label} {{name: $to_name}})
        MERGE (a)-[r:{rel_type}]->(b)
        ON CREATE SET r.confidence = $confidence,
                      r.source_case_id = $source_case_id,
                      r.source_cases = [$source_case_id]
        ON MATCH SET r.confidence = $confidence,
                     r.source_cases = CASE
                         WHEN $source_case_id IN coalesce(r.source_cases, []) THEN r.source_cases
                         ELSE coalesce(r.source_cases, []) + $source_case_id
                     END
        RETURN r
        """
        with self._driver.session() as session:
            session.run(
                query,
                from_name=from_name,
                to_name=to_name,
                confidence=confidence,
                source_case_id=source_case_id,
            )

    def write_cdr_records(self, records, source: str):
        """Graph-write a batch of CDR CallRecords.

        One Phone node per unique number; one CALLED edge per call with its
        timestamp/duration retained. `source` is the provenance (e.g. the CSV
        stem "sample_cdr"). Re-running the same source is idempotent because
        call_id is a stable function of (source, caller, callee, timestamp).
        """
        unique_phones = {r.caller_number for r in records} | {
            r.callee_number for r in records
        }
        with self._driver.session() as session:
            for phone in unique_phones:
                session.run(
                    """
                    MERGE (p:Phone {name: $name})
                    ON CREATE SET p.first_seen_case = $source
                    SET p.source_cases = CASE
                        WHEN $source IN coalesce(p.source_cases, []) THEN p.source_cases
                        ELSE coalesce(p.source_cases, []) + $source
                    END
                    """,
                    name=phone,
                    source=source,
                )
            for rec in records:
                call_id = f"{source}|{rec.caller_number}|{rec.callee_number}|{rec.timestamp.isoformat()}"
                session.run(
                    """
                    MATCH (a:Phone {name: $caller})
                    MATCH (b:Phone {name: $callee})
                    MERGE (a)-[r:CALLED {call_id: $call_id}]->(b)
                    SET r.timestamp = $timestamp,
                        r.duration_seconds = $duration,
                        r.confidence = 1.0,
                        r.source_case_id = $source
                    """,
                    caller=rec.caller_number,
                    callee=rec.callee_number,
                    call_id=call_id,
                    timestamp=rec.timestamp.isoformat(),
                    duration=rec.duration_seconds,
                    source=source,
                )

    def write_fir_entities(self, clusters: dict[str, list], case_id: str):
        """Graph-write resolved entity clusters from one FIR.

        Creates/updates a node per cluster, and an ASSOCIATED_WITH edge between
        every pair of persons named together in this case — co-occurrence is
        *inference*, so confidence = the weaker of the two entity confidences.
        """
        persons: list[tuple[str, float]] = []
        owned: list[tuple[str, str, float]] = []  # (name, label, conf) Phone/Vehicle
        for name, members in clusters.items():
            entity_type = members[0].entity_type
            label = _ENTITY_LABEL.get(entity_type)
            if label is None:
                continue  # extraction doesn't produce Event entities yet
            self.upsert_entity(label, name, case_id)
            conf = max(m.confidence for m in members)  # most confident mention
            if entity_type is EntityType.PERSON:
                persons.append((name, conf))
            elif label in ("Phone", "Vehicle"):
                owned.append((name, label, conf))

        # People named together in one FIR are presumed associated.
        for i, (a_name, a_conf) in enumerate(persons):
            for b_name, b_conf in persons[i + 1 :]:
                self.upsert_relationship(
                    "Person", a_name, "Person", b_name,
                    "ASSOCIATED_WITH", min(a_conf, b_conf), case_id,
                )

        # People <-> phones/vehicles co-mentioned in the same FIR (e.g. "Phone
        # number X was reportedly used by Y"). Proximity inference, not proof,
        # so confidence = the weaker of the two sides.
        for p_name, p_conf in persons:
            for o_name, o_label, o_conf in owned:
                self.upsert_relationship(
                    "Person", p_name, o_label, o_name,
                    "OWNS", min(p_conf, o_conf), case_id,
                )

    # ------------------------------------------------------------- queries --
    def get_all_call_records(self) -> list[CallRecord]:
        """Reconstruct every CallRecord currently in the graph from CALLED
        edges. Lets the pattern detectors run over whatever CDR data has been
        ingested so far (not just the static sample file) — an upload via the
        API is reflected here on the next query."""
        rows = self.run(
            "MATCH (a:Phone)-[r:CALLED]->(b:Phone) "
            "RETURN a.name AS caller, b.name AS callee, "
            "r.timestamp AS timestamp, r.duration_seconds AS duration"
        )
        records: list[CallRecord] = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except (TypeError, ValueError):
                logger.warning("Skipping CALLED edge with bad timestamp %r", row.get("timestamp"))
                continue
            records.append(
                CallRecord(
                    caller_number=row["caller"],
                    callee_number=row["callee"],
                    timestamp=ts,
                    duration_seconds=int(row["duration"] or 0),
                )
            )
        return records

    def get_subgraph(self, entity_name: str, hops: int = 2) -> list[dict]:
        """Fetch the N-hop neighborhood of a given entity for the
        investigator UI (PRD FR7/FR8). Raw paths — see
        get_subgraph_graph() for the structured nodes/edges shape."""
        query = f"""
        MATCH path = (start {{name: $entity_name}})-[*1..{hops}]-(connected)
        RETURN path
        LIMIT 200
        """
        with self._driver.session() as session:
            result = session.run(query, entity_name=entity_name)
            return [record.data() for record in result]

    def get_subgraph_graph(
        self, entity_name: str, hops: int = 2, limit: int = 200
    ) -> dict:
        """Structured N-hop neighborhood": {{nodes:[...], edges:[...]}} shaped
        for the graph viz / API. Every node carries its provenance list and
        every edge its confidence + source — nothing asserted without evidence.
        """
        query = f"""
        MATCH path = (start {{name: $entity_name}})-[*1..{hops}]-(connected)
        RETURN path
        LIMIT {limit}
        """
        nodes: dict[str, dict] = {}
        edges: dict[str, dict] = {}
        with self._driver.session() as session:
            for record in session.run(query, entity_name=entity_name):
                path = record["path"]
                for node in path.nodes:
                    if node.element_id in nodes:
                        continue
                    nodes[node.element_id] = {
                        "id": node.element_id,
                        "label": next(iter(node.labels), "Node"),
                        "name": node.get("name"),
                        "source_cases": node.get("source_cases") or [],
                    }
                for rel in path.relationships:
                    if rel.element_id in edges:
                        continue
                    edges[rel.element_id] = {
                        "id": rel.element_id,
                        "source": rel.start_node.element_id,
                        "target": rel.end_node.element_id,
                        "type": rel.type,
                        "confidence": rel.get("confidence"),
                        "source_case_id": rel.get("source_case_id"),
                        "source_cases": rel.get("source_cases") or [],
                    }
        return {
            "entity": entity_name,
            "hops": hops,
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
        }

    def run(self, query: str, **params) -> list[dict]:
        """Raw Cypher passthrough for assertions/tests (or new detectors)."""
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    def counts(self) -> dict:
        """Per-label node counts + per-type relationship counts (demo/tests)."""
        return {
            "nodes": {
                row["label"]: row["c"]
                for row in self.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c")
            },
            "relationships": {
                row["type"]: row["c"]
                for row in self.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS c")
            },
        }