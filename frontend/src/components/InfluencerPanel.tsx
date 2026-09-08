import { useEffect, useState } from "react";
import { getInfluencers, type Influencer } from "../api/client";

/**
 * Shows the top-N key influencers by PageRank over the SOCIAL projection
 * (PRD FR5 — the product-approved default). Calls /influencers with the
 * bearer token attached by the axios interceptor.
 *
 * `refreshToken`: a counter App bumps after an admin upload, so the panel
 * re-queries and reflects the new data instead of staying stale from mount.
 */
export function InfluencerPanel({ refreshToken = 0 }: { refreshToken?: number }) {
  const [influencers, setInfluencers] = useState<Influencer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInfluencers(null); // drop the stale list while re-loading (loading state shows)
    setError(null);
    getInfluencers(5)
      .then((res) => {
        if (!cancelled) setInfluencers(res.influencers);
      })
      .catch((err: unknown) => {
        const status = (err as { response?: { status?: number } }).response?.status;
        if (!cancelled)
          setError(
            status === 503 ? "Graph unavailable — is Neo4j running?" : "Failed to load influencers.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  return (
    <div className="border rounded p-4 bg-white">
      <h2 className="font-semibold mb-2">Key Influencers</h2>
      {error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : influencers === null ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <ol className="list-decimal list-inside space-y-1">
          {influencers.map((inf) => (
            <li key={inf.name}>
              <span className="font-medium">{inf.name}</span>{" "}
              <span className="text-slate-500 text-sm">score {inf.score.toFixed(3)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
