"""
Reference schema for the CrimeGraph knowledge graph.

Relationship shapes are documented here and are NOT enforced by Neo4j (which
is schema-less for edges) — this module is the source of truth for what the
writers emit and what the analytics/API layers should expect.

Two things ARE enforced, in `app/graph/neo4j_client.py::init_schema`:
  * unique `name` per node label (constraint), so entity resolution genuinely
    de-dupes at the DB level;
  * an index on CALLED.timestamp for the burst-call detector.

Current write pipeline emits: Phone + CALLED (from CDRs, conf 1.0), and
Person/Location/Organization/Vehicle nodes + ASSOCIATED_WITH (FIR
co-occurrence inference). TRANSACTED_WITH, CO_LOCATED_WITH, OWNS and
INVOLVED_IN are reserved for future source-pipelines (financial records,
surveillance, ...) — do not hand-wire them until a source exists.
"""

NODE_LABELS = [
    "Person",
    "Phone",
    "Vehicle",
    "Location",
    "Organization",
    "Event",
]

RELATIONSHIP_TYPES = [
    "CALLED",           # Person/Phone -> Person/Phone, from CDRs
    "TRANSACTED_WITH",  # Person/Organization -> Person/Organization, from financial records
    "CO_LOCATED_WITH",  # Person -> Person, from surveillance/location data
    "ASSOCIATED_WITH",  # Person -> Person/Organization, from FIR/social-media text
    "OWNS",             # Person -> Vehicle/Phone
    "INVOLVED_IN",       # Person/Organization -> Event
]

# Every relationship should carry these properties:
REQUIRED_RELATIONSHIP_PROPERTIES = [
    "confidence",       # float 0-1, per PRD FR12
    "source_case_id",   # traceability back to originating record, per PRD NFR "Auditability"
]
