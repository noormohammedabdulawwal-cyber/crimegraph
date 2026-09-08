import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// CrimeGraph frontend — dev server on :3003. Port isolation (CLAUDE.md):
// the pre-existing SIH stack owns :3000, so CrimeGraph uses its own port same
// as it does everywhere else (neo4j 7688, postgres 5433, backend 8011).
// API calls go to http://localhost:8011/api (see src/api/client.ts).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3003,
    strictPort: true,
  },
});