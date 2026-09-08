import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, {
  type Core,
  type EdgeSingular,
  type ElementDefinition,
  type NodeSingular,
} from "cytoscape";
import fcose from "cytoscape-fcose";
import type { SubgraphEdge, SubgraphNode, SubgraphResponse } from "../api/client";

// Register the fcose extension once at module load — it must be registered
// before any Cytoscape instance is created with layout: "fcose".
cytoscape.use(fcose);

const TYPE_COLORS: Record<string, string> = {
  Person: "#dc2626", // red
  Phone: "#2563eb", // blue
  Vehicle: "#7c3aed", // violet
  Location: "#059669", // green
  Organization: "#d97706", // amber
  Event: "#0f766e", // teal
  default: "#64748b", // slate
};

function colorFor(type: string): string {
  return TYPE_COLORS[type] ?? TYPE_COLORS.default;
}

// Community ring palette — high-contrast OUTLINE colors so they stay distinct
// from the node type fill (Person red / Phone blue / …). One color per
// distinct Louvain community, assigned in stable community-id order.
const COMMUNITY_COLORS = [
  "#f59e0b", // amber
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#84cc16", // lime
  "#8b5cf6", // violet
  "#f97316", // orange
  "#14b8a6", // teal
  "#eab308", // yellow
];

/** Assign each distinct community id a stable ring color. */
function communityColorFor(communityId: number | null, order: Map<number, number>): string {
  if (communityId === null) return "transparent";
  const idx = order.get(communityId) ?? 0;
  return COMMUNITY_COLORS[idx % COMMUNITY_COLORS.length];
}

/** Degree -> radius scale for "importance" sizing: the graph's most-connected
 * node renders at MAX_SIZE, leaves at MIN_SIZE. */
const MIN_SIZE = 20;
const MAX_SIZE = 60;

/** Local degree of each node (number of edges incident to it). */
function degreeByNode(nodes: SubgraphNode[], edges: SubgraphEdge[]): Map<string, number> {
  const degree = new Map<string, number>();
  for (const n of nodes) degree.set(n.id, 0);
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  return degree;
}

/**
 * Build human-readable "cell discovery" findings from the current view.
 *
 * For each Louvain community present, if it holds 2+ people and none of those
 * people are directly connected by a CALLED (phone) record, we surface the
 * finding: the system grouped them via case co-occurrence, not communication.
 * This is the headline demo fact — surfaced in plain language, not just as
 * colored rings the judge has to decode.
 */
function communityFindings(data: SubgraphResponse): string[] {
  const personIdsByCommunity = new Map<number, SubgraphNode[]>();
  for (const n of data.nodes) {
    if (n.communityId === null || n.label !== "Person") continue;
    const list = personIdsByCommunity.get(n.communityId) ?? [];
    list.push(n);
    personIdsByCommunity.set(n.communityId, list);
  }

  const calledPersonPairs = new Set<string>();
  for (const e of data.edges) {
    if (e.type !== "CALLED") continue;
    const src = data.nodes.find((n) => n.id === e.source);
    const tgt = data.nodes.find((n) => n.id === e.target);
    if (src?.label === "Person" && tgt?.label === "Person") {
      calledPersonPairs.add([src.id, tgt.id].sort().join("|"));
    }
  }

  const findings: string[] = [];
  for (const [cid, persons] of [...personIdsByCommunity.entries()].sort((a, b) => a[0] - b[0])) {
    if (persons.length < 2) continue;
    const names = persons.map((p) => p.name);
    // Do any two of these people have a direct call record between them?
    const hasDirectCall = persons.some((a) =>
      persons.some((b) => a !== b && calledPersonPairs.has([a.id, b.id].sort().join("|"))),
    );
    if (!hasDirectCall) {
      findings.push(
        `Community ${cid} groups ${persons.length} people (${names.join(", ")}) with no direct ` +
          `call record between them — the link is inferred from case co-occurrence, not communication.`,
      );
    }
  }
  return findings;
}

type Details =
  | { kind: "node"; name: string; type: string; degree: number; sourceCases: string[] }
  | { kind: "edge"; type: string; confidence: number | null; sourceCaseId: string | null }
  | null;

interface GraphViewProps {
  data: SubgraphResponse | null;
  /** True while a sub-graph fetch is in flight — drives the loading states. */
  loading?: boolean;
}

export function GraphView({ data, loading = false }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [details, setDetails] = useState<Details>(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [showCommunities, setShowCommunities] = useState(true);
  // Mirrors showCommunities into a ref so the graph-creation effect can read
  // the current value without re-running on every toggle (a full re-create
  // would re-run the fcose layout and lose node positions).
  const showCommunitiesRef = useRef(showCommunities);
  showCommunitiesRef.current = showCommunities;

  // Stable community-id -> palette index ordering for this view.
  const communityOrder = useMemo(() => {
    const order = new Map<number, number>();
    if (!data) return order;
    const ids = [...new Set(data.nodes.map((n) => n.communityId).filter((x): x is number => x !== null))].sort((a, b) => a - b);
    ids.forEach((id, i) => order.set(id, i));
    return order;
  }, [data]);

  const findings = useMemo(() => (data ? communityFindings(data) : []), [data]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !data) {
      setDetails(null); // a new (or cleared) graph resets the details panel
      return;
    }

    const degree = degreeByNode(data.nodes, data.edges);
    const sizes = [...degree.values()];
    const minDeg = sizes.length ? Math.min(...sizes) : 0;
    const maxDeg = sizes.length ? Math.max(...sizes) : 0;
    const span = maxDeg - minDeg;
    const nodeCaseById = new Map(data.nodes.map((n) => [n.id, n.source_cases]));

    const elements: ElementDefinition[] = [
      // Nodes carry their display name, type, local degree, a degree-scaled
      // size, and the community ring color.
      ...data.nodes.map((n) => {
        const d = degree.get(n.id) ?? 0;
        const size =
          span === 0 ? MIN_SIZE : MIN_SIZE + ((d - minDeg) / span) * (MAX_SIZE - MIN_SIZE);
        return {
          data: {
            id: n.id,
            label: n.name,
            type: n.label,
            degree: d,
            size: Math.round(size),
            communityId: n.communityId,
            ringColor: communityColorFor(n.communityId, communityOrder),
          },
        };
      }),
      // Edges keep type + confidence + provenance for the details panel.
      ...data.edges.map((e) => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          relType: e.type,
          confidence: e.confidence,
          source_case_id: e.source_case_id,
        },
      })),
    ];

    const cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": (ele) => colorFor(ele.data("type")),
            "border-color": (ele) => ele.data("ringColor"),
            "border-width": (ele) =>
              showCommunitiesRef.current && ele.data("communityId") !== null ? 4 : 0,
            "text-valign": "center",
            "text-halign": "center",
            color: "#0f172a",
            "font-size": 11,
            "text-wrap": "wrap",
            "text-max-width": "140px",
            width: "data(size)",
            height: "data(size)",
          },
        },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#0f172a" } },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#94a3b8",
            // bezier + control-point-step-size staggers parallel edges between
            // the same pair so overlapping relationships stay distinguishable.
            "curve-style": "bezier",
            "control-point-step-size": 30,
          },
        },
        { selector: "edge:selected", style: { "line-color": "#0f172a", width: 3 } },
      ],
      // fcose's options (animate, nodeSeparation) aren't in cytoscape's layout
      // union — cast since cytoscape-fcose ships no types (ambient any).
      layout: { name: "fcose", animate: true, nodeSeparation: 80 } as cytoscape.LayoutOptions,
    });
    cyRef.current = cy;

    // Details on click: node -> name/type/degree/sources; edge -> type/confidence/source.
    cy.on("tap", "node", (evt) => {
      const n = evt.target as NodeSingular;
      setDetails({
        kind: "node",
        name: n.data("label"),
        type: n.data("type"),
        degree: n.data("degree") ?? 0,
        sourceCases: nodeCaseById.get(n.id()) ?? [],
      });
    });
    cy.on("tap", "edge", (evt) => {
      const e = evt.target as EdgeSingular;
      const d = e.data();
      setDetails({
        kind: "edge",
        type: d.relType,
        confidence: d.confidence ?? null,
        sourceCaseId: d.source_case_id ?? null,
      });
    });
    // Tap on empty canvas clears the selection + details panel.
    cy.on("tap", (evt) => {
      if (evt.target === cy) setDetails(null);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, communityOrder]);

  // Toggling the community rings restyles in place — no full re-layout.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().style("border-width", (ele: NodeSingular) =>
        showCommunities && ele.data("communityId") !== null ? 4 : 0);
    });
  }, [showCommunities]);

  /** Floating-toolbar controls operate on the current Cytoscape instance. */
  function zoomIn() {
    const cy = cyRef.current;
    if (cy) cy.zoom(cy.zoom() * 1.25);
  }
  function zoomOut() {
    const cy = cyRef.current;
    if (cy) cy.zoom(cy.zoom() * 0.8);
  }
  function fitView() {
    const cy = cyRef.current;
    if (!cy) return;
    cy.fit(undefined, 30);
    cy.zoom(Math.min(cy.zoom(), 2.5)); // don't blow a tiny graph up to fill the canvas
  }
  function toggleCommunities() {
    setShowCommunities((s) => !s);
  }

  return (
    <div>
      {data ? (
        <div className="relative" style={{ height: "560px" }}>
          <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

          {/* Zoom / fit toolbar */}
          <div className="absolute left-2 top-2 flex overflow-hidden rounded border border-slate-200 bg-white/95 shadow-sm">
            <button
              onClick={zoomIn}
              title="Zoom in"
              className="border-r border-slate-200 px-2 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
            >
              +
            </button>
            <button
              onClick={zoomOut}
              title="Zoom out"
              className="border-r border-slate-200 px-2 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
            >
              −
            </button>
            <button
              onClick={fitView}
              title="Fit to screen"
              className="border-r border-slate-200 px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
            >
              fit
            </button>
            <button
              onClick={toggleCommunities}
              title="Toggle community ring highlighting"
              className={`px-2 py-1.5 text-xs ${showCommunities ? "bg-indigo-100 text-indigo-700" : "text-slate-600 hover:bg-slate-100"}`}
            >
              communities {showCommunities ? "on" : "off"}
            </button>
          </div>

          {/* Collapsible legend */}
          <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
            <button
              onClick={() => setLegendOpen((o) => !o)}
              className="rounded border border-slate-200 bg-white/95 px-2 py-1.5 text-xs text-slate-600 shadow-sm hover:bg-slate-100"
            >
              Legend {legendOpen ? "▾" : "▸"}
            </button>
            {legendOpen && (
              <div className="space-y-1 rounded border border-slate-200 bg-white/95 px-2.5 py-2 text-xs text-slate-600 shadow-sm">
                {Object.entries(TYPE_COLORS)
                  .filter(([k]) => k !== "default")
                  .map(([type, color]) => (
                    <div key={type} className="flex items-center gap-1.5">
                      <span
                        className="inline-block h-3 w-3 rounded-full"
                        style={{ backgroundColor: color }}
                      />
                      {type}
                    </div>
                  ))}
                <div className="border-t border-slate-200 pt-1 mt-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-3 w-3 rounded-full border-4"
                      style={{ borderColor: "#f59e0b" }}
                    />
                    Community ring (Louvain)
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* In-flight indicator when a newer graph replaces the current one */}
          {loading && (
            <div className="pointer-events-none absolute inset-x-0 top-2 flex justify-center">
              <span className="flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1 text-xs text-slate-500 shadow-sm">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
                Loading…
              </span>
            </div>
          )}
        </div>
      ) : loading ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded border border-dashed border-slate-300 bg-slate-50 text-slate-400" style={{ height: "240px" }}>
          <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          <span className="text-sm">Loading sub-graph…</span>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 text-slate-400" style={{ height: "240px" }}>
          <span className="text-sm">No sub-graph loaded</span>
          <span className="text-xs">Search an entity above, then click a result to render its network.</span>
        </div>
      )}

      <DetailsPanel details={details} onClose={() => setDetails(null)} />

      {findings.length > 0 && (
        <div className="mt-3 rounded border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
          <h3 className="font-semibold text-indigo-800">Cell discovery</h3>
          <ul className="mt-1 space-y-1">
            {findings.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Read-only card under the canvas showing what was clicked. Replaces the
 * always-on edge labels — inspect specifics only when you need them. */
function DetailsPanel({ details, onClose }: { details: Details; onClose: () => void }) {
  const empty = details === null;
  return (
    <div className="mt-3 rounded border border-slate-200 bg-white p-3 text-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-700">Details</h3>
        {!empty && (
          <button
            onClick={onClose}
            className="text-xs text-slate-400 hover:text-slate-700"
            aria-label="Close details"
          >
            ✕
          </button>
        )}
      </div>
      {empty ? (
        <p className="mt-1 text-xs text-slate-400">
          Click a node or an edge to inspect its type, confidence, and source case.
        </p>
      ) : details.kind === "node" ? (
        <dl className="mt-1 grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1 text-slate-700">
          <dt className="text-slate-500">Name</dt>
          <dd className="font-medium">{details.name}</dd>
          <dt className="text-slate-500">Type</dt>
          <dd>{details.type}</dd>
          <dt className="text-slate-500">Degree</dt>
          <dd>{details.degree}</dd>
          <dt className="text-slate-500">Source cases</dt>
          <dd>{details.sourceCases.length ? details.sourceCases.join(", ") : "—"}</dd>
        </dl>
      ) : (
        <dl className="mt-1 grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1 text-slate-700">
          <dt className="text-slate-500">Relationship</dt>
          <dd className="font-medium">{details.type}</dd>
          <dt className="text-slate-500">Confidence</dt>
          <dd>{details.confidence !== null ? details.confidence.toFixed(2) : "—"}</dd>
          <dt className="text-slate-500">Source case</dt>
          <dd>{details.sourceCaseId ?? "—"}</dd>
        </dl>
      )}
    </div>
  );
}
