import axios from "axios";

const API_BASE = "http://localhost:8011/api";

const client = axios.create({
  baseURL: API_BASE,
});

// ---- auth interceptor: attach Bearer on every request ----
let _getToken: (() => string | null) | null = null;
let _onUnauthorized: (() => void) | null = null;

export function configureAuth(
  getToken: () => string | null,
  onUnauthorized: () => void,
) {
  _getToken = getToken;
  _onUnauthorized = onUnauthorized;
}

client.interceptors.request.use((config) => {
  const token = _getToken?.();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && _getToken?.()) {
      // Token exists but backend rejected it — expired/invalid.
      // Don't fire during login attempts (no token yet).
      _onUnauthorized?.();
    }
    return Promise.reject(err);
  },
);

// ---- types ----
export interface SearchResult {
  name: string;
  label: string;
  source_cases: string[];
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface SubgraphNode {
  /** Neo4j element id — edges reference these; use as the Cytoscape id. */
  id: string;
  /** Graph label = entity type (Person/Phone/Vehicle/Location). */
  label: string;
  /** Canonical display name. */
  name: string;
  source_cases: string[];
  /** Louvain community id (set when ?include_communities=true) — null otherwise. */
  communityId: number | null;
}

export interface SubgraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  /** Null when a relationship lacks the property (backend emits JSON null via
   * rel.get(), not 0/"" — consumers must guard before .toFixed()). */
  confidence: number | null;
  source_case_id: string | null;
  source_cases: string[];
}

export interface SubgraphResponse {
  entity: string;
  hops: number;
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}

export interface Influencer {
  name: string;
  score: number;
}

// ---- API calls ----
export async function searchEntities(
  query: string,
  limit = 50,
): Promise<SearchResponse> {
  const { data } = await client.get("/search", {
    params: { query, limit },
  });
  return data;
}

export async function getSubgraph(
  entityName: string,
  hops = 2,
  includeCommunities = true,
): Promise<SubgraphResponse> {
  const { data } = await client.get(`/subgraph/${encodeURIComponent(entityName)}`, {
    params: { hops, include_communities: includeCommunities },
  });
  return data;
}

export async function getInfluencers(
  topN = 5,
): Promise<{ projection: string; top_n: number; influencers: Influencer[] }> {
  const { data } = await client.get("/influencers", { params: { top_n: topN } });
  return data;
}

export async function getFlaggedPatterns(): Promise<{
  call_records_analyzed: number;
  patterns: unknown[];
}> {
  const { data } = await client.get("/patterns/flagged");
  return data;
}

export async function loginRequest(
  username: string,
  password: string,
): Promise<{ access_token: string; token_type: string; role: string; username: string }> {
  const { data } = await client.post("/auth/login", { username, password });
  return data;
}

export async function uploadFile(
  endpoint: "/upload/cdr" | "/upload/fir",
  file: File,
): Promise<unknown> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post(endpoint, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
