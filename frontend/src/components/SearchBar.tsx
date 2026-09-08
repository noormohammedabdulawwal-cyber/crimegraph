import { useState } from "react";
import { searchEntities, type SearchResult } from "../api/client";

interface SearchBarProps {
  onSelectEntity: (entity: SearchResult) => void;
  onError: (message: string) => void;
}

/**
 * Search bar (FR8). Typing a query hits /search (canonical names only — not
 * raw mentions), renders the matched entities as clickable rows, and the
 * caller fetches /subgraph/{name} when one is chosen.
 */
export function SearchBar({ onSelectEntity, onError }: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    try {
      const res = await searchEntities(q);
      setResults(res.results);
      if (res.results.length === 0) {
        setResults(null); // defensive — the backend 404s on no match anyway
        onError(`No entities match "${q}"`);
      }
    } catch (err: unknown) {
      // 404 (no match) and 422 surface as non-fatal messages. Drop the
      // previous result list too — showing yesterday's matches next to a
      // "no match" notice would look broken.
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) {
        setResults(null);
        onError(`No entities match "${q}"`);
      } else if (status === 422) {
        onError("Empty or invalid query");
      } else {
        onError("Search failed — check the backend.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          className="flex-1 border rounded px-3 py-2"
          placeholder="Search canonical entities (e.g. 9812 or Ramesh)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="submit"
          disabled={busy}
          className="bg-indigo-600 text-white rounded px-4 py-2 font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Searching…" : "Search"}
        </button>
      </form>

      {results && results.length > 0 && (
        <ul className="mt-2 border rounded divide-y">
          {results.map((r) => (
            <li key={r.name}>
              <button
                className="w-full text-left px-3 py-2 hover:bg-indigo-50 flex items-baseline justify-between"
                onClick={() => onSelectEntity(r)}
              >
                <span className="font-medium">{r.name}</span>
                <span className="text-xs text-slate-500">
                  {r.label}
                  {r.source_cases.length > 0 && ` · ${r.source_cases.length} case(s)`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
