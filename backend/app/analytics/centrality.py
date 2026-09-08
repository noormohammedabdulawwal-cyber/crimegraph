"""
Key-influencer ranking via graph centrality (PRD FR5 / section 10).

Runs Neo4j Graph Data Science (GDS) PageRank + betweenness over the REAL
loaded graph. The GDS projection is configurable so the API layer can choose
what counts toward "influence":

  UNIFORM ('*','*', directed)  — the scaffold baseline. Simple, but it treats
      every label and relationship type identically: Vehicle/Location/Org
      leaves become PageRank sinks, and ASSOCIATED_WITH/OWNS directions are
      write-order artifacts, so rankings skew away from the true hubs.

  SOCIAL  — people + communications devices, undirected, real-world edges
      (CALLED, ASSOCIATED_WITH, OWNS). This is the recommended default once a
      product decision on OWNS weighting is made (see demo_analytics.py).

Requires the graph-data-science plugin (see docker-compose.yml). Every result
carries the node name only; provenance (source_cases) lives on the nodes.
"""
import re

from app.graph.neo4j_client import Neo4jClient

PAGERANK_GRAPH = "crimegraph_pagerank"
BETWEENNESS_GRAPH = "crimegraph_betweenness"

# Wildcard baselines — what the scaffold used (everything, directed, unweighted).
UNIFORM_NODE_PROJECTION = "*"
UNIFORM_REL_PROJECTION = "*"

# Scoped "social influence" projection: the actors that can actually wield
# influence (people + phones), with edges that model communication or
# association, all undirected (direction on ASSOC/OWNS is a write artifact).
# OWNS is intentionally kept so a person stays reachable from their phone.
SOCIAL_NODE_PROJECTION = {"Person": {}, "Phone": {}}
SOCIAL_REL_PROJECTION = {
    "CALLED": {"orientation": "UNDIRECTED"},
    "ASSOCIATED_WITH": {"orientation": "UNDIRECTED"},
    "OWNS": {"orientation": "UNDIRECTED"},
}


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _cypher_map(obj) -> str:
    """Render a dict as a Cypher map literal — bare identifier keys (string
    keys are not accepted here), single-quoted string values."""
    parts = []
    for key, value in obj.items():
        key = str(key)
        if not _IDENT_RE.match(key):
            key = f"`{key}`"
        if isinstance(value, dict):
            rendered = _cypher_map(value)
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            rendered = f"'{value}'"
        parts.append(f"{key}: {rendered}")
    return "{" + ", ".join(parts) + "}"


def _projection_literal(spec) -> str:
    """Serialize a GDS node/relationship projection to a Cypher literal:
    string specs like '*' are single-quoted ('*'); dicts become a Cypher map
    literal with bare keys (e.g. {Person: {}, Phone: {}})."""
    if isinstance(spec, dict):
        return _cypher_map(spec)
    return f"'{spec}'"


def compute_pagerank(
    client: Neo4jClient,
    top_n: int = 5,
    node_projection=UNIFORM_NODE_PROJECTION,
    rel_projection=UNIFORM_REL_PROJECTION,
) -> list[dict]:
    """Top_n nodes by PageRank over the chosen projection.

    Returns [{"name": ..., "score": ...}, ...] ordered by score DESC.
    """
    node_spec = _projection_literal(node_projection)
    rel_spec = _projection_literal(rel_projection)
    client.run(
        f"CALL gds.graph.project($graph, {node_spec}, {rel_spec})",
        graph=PAGERANK_GRAPH,
    )
    try:
        return client.run(
            f"""
            CALL gds.pageRank.stream('{PAGERANK_GRAPH}', {{tolerance: $tol}})
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS name, score
            ORDER BY score DESC
            LIMIT $top_n
            """,
            tol=1e-7,
            top_n=top_n,
        )
    finally:
        client.run(f"CALL gds.graph.drop('{PAGERANK_GRAPH}', false)")


def compute_betweenness(
    client: Neo4jClient,
    top_n: int = 5,
    node_projection=UNIFORM_NODE_PROJECTION,
    rel_projection=UNIFORM_REL_PROJECTION,
) -> list[dict]:
    """Top_n 'bridge' nodes by betweenness centrality — intermediaries/couriers
    connecting otherwise-separate clusters."""
    node_spec = _projection_literal(node_projection)
    rel_spec = _projection_literal(rel_projection)
    client.run(
        f"CALL gds.graph.project($graph, {node_spec}, {rel_spec})",
        graph=BETWEENNESS_GRAPH,
    )
    try:
        return client.run(
            f"""
            CALL gds.betweenness.stream('{BETWEENNESS_GRAPH}')
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).name AS name, score
            ORDER BY score DESC
            LIMIT $top_n
            """,
            top_n=top_n,
        )
    finally:
        client.run(f"CALL gds.graph.drop('{BETWEENNESS_GRAPH}', false)")