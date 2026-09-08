"""
Community detection — clusters tightly-connected sub-groups to reveal hidden
networks/cells (PRD section 10). Uses Louvain via Neo4j GDS.

Louvain is designed for undirected graphs, so the default projection is the
scoped SOCIAL one from app/analytics/centrality.py (people + phones,
undirected, communication/association edges) — counting OWNS "device" links as
first-class social edges would distort the grouping. Pass the UNIFORM
projection explicitly if an all-graph layout is ever wanted.

IMPORTANT for the MVP: the sample graph is tiny (patient of the demo). Expect
(and don't over-read) a single community.
"""
from app.analytics.centrality import SOCIAL_NODE_PROJECTION, SOCIAL_REL_PROJECTION, _projection_literal
from app.graph.neo4j_client import Neo4jClient

COMMUNITY_GRAPH = "crimegraph_communities"


def detect_communities(
    client: Neo4jClient,
    node_projection=SOCIAL_NODE_PROJECTION,
    rel_projection=SOCIAL_REL_PROJECTION,
) -> list[dict]:
    """Return each node's assigned community id via Louvain.

    Returns [{"name": ..., "communityId": ...}, ...] ordered by communityId.
    """
    node_spec = _projection_literal(node_projection)
    rel_spec = _projection_literal(rel_projection)
    client.run(
        f"CALL gds.graph.project($graph, {node_spec}, {rel_spec})",
        graph=COMMUNITY_GRAPH,
    )
    try:
        return client.run(
            f"""
            CALL gds.louvain.stream('{COMMUNITY_GRAPH}')
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).name AS name, communityId
            ORDER BY communityId, name
            """
        )
    finally:
        client.run(f"CALL gds.graph.drop('{COMMUNITY_GRAPH}', false)")