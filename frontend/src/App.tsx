import { useRef, useState } from "react";
import { AuthProvider, useAuth } from "./api/AuthContext";
import { getSubgraph, type SearchResult, type SubgraphResponse } from "./api/client";
import { Login } from "./components/Login";
import { SearchBar } from "./components/SearchBar";
import { GraphView } from "./components/GraphView";
import { InfluencerPanel } from "./components/InfluencerPanel";
import { UploadPanel } from "./components/UploadPanel";

/**
 * Investigation gate: with no bearer token (initial load, or after the axios
 * 401 handler clears it) the app renders the login screen. Everything else
 * renders only once authenticated.
 *
 * Flow: SearchBar -> /search (canonical names) -> click entity ->
 * /subgraph/{name} -> GraphView (Cytoscape) + InfluencerPanel + UploadPanel.
 */
function Dashboard() {
  const { role, logout } = useAuth();
  const [subgraph, setSubgraph] = useState<SubgraphResponse | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [subgraphLoading, setSubgraphLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // Bumped by UploadPanel on a successful upload so InfluencerPanel re-queries
  // and reflects the new data instead of staying stale from mount.
  const [influencerTick, setInfluencerTick] = useState(0);

  // Sequence guard for subgraph fetches: rapid entity clicks must not resolve
  // out of order (an earlier request landing after a later one would draw a
  // graph that doesn't match the selected entity / header count). Each fetch
  // captures the current counter and only applies its result if it is still
  // the latest selection.
  const subgraphReqId = useRef(0);

  /** A search that finds nothing (or fails) invalidates the older view — don't
   * leave a stale graph on screen alongside a "no match" notice. */
  function handleSearchError(message: string) {
    subgraphReqId.current++; // a search error also sidelined any in-flight subgraph
    setNotice(message);
    setSubgraph(null);
    setSelectedName(null);
  }

  async function handleSelectEntity(entity: SearchResult) {
    const reqId = ++subgraphReqId.current;
    setSelectedName(entity.name);
    setNotice(null);
    setSubgraphLoading(true);
    try {
      const g = await getSubgraph(entity.name, 2);
      if (reqId !== subgraphReqId.current) return; // superseded by a newer selection
      setSubgraph(g);
    } catch (err: unknown) {
      if (reqId !== subgraphReqId.current) return; // stale failure — ignore
      const status = (err as { response?: { status?: number } }).response?.status;
      setSubgraph(null);
      setNotice(
        status === 404 ? `Entity "${entity.name}" not in graph.` : "Failed to load subgraph.",
      );
    } finally {
      if (reqId === subgraphReqId.current) setSubgraphLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-800">
          CrimeGraph — Investigator Dashboard
        </h1>
        <div className="flex items-center gap-3">
          {role && (
            <span className="text-sm text-slate-500">
              role: <code>{role}</code>
            </span>
          )}
          <button
            onClick={logout}
            className="text-sm text-slate-600 hover:text-red-600"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="p-6 space-y-4">
        <SearchBar onSelectEntity={handleSelectEntity} onError={handleSearchError} />

        {notice && <p className="text-sm text-amber-700">{notice}</p>}

        <div className="grid grid-cols-4 gap-4">
          <section className="col-span-3 space-y-4">
            <div className="border rounded p-4 bg-white">
              <div className="flex items-baseline justify-between mb-2">
                <h2 className="font-semibold">Sub-graph</h2>
                {subgraph && (
                  <span className="text-xs text-slate-400">
                    {selectedName} · {subgraph.nodes.length} nodes /{" "}
                    {subgraph.edges.length} edges
                  </span>
                )}
              </div>
              <GraphView data={subgraph} loading={subgraphLoading} />
            </div>
            <UploadPanel onUploaded={() => setInfluencerTick((t) => t + 1)} />
          </section>
          <aside className="col-span-1">
            <InfluencerPanel refreshToken={influencerTick} />
          </aside>
        </div>
      </main>
    </div>
  );
}

function AppGate() {
  const { token } = useAuth();
  return token ? <Dashboard /> : <Login />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppGate />
    </AuthProvider>
  );
}