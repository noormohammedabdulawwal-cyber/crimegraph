# Frontend Manual Test Checklist (Build Step 7)

Verify the full authenticated investigator flow against the live stack.
Stack must already be up (see CLAUDE.md "Commands"):

```bash
docker compose up -d                          # Neo4j :7688/:7475, Postgres :5433
cd backend && python -m app.db.migrate        # once, to seed users (admin/investigator)
cd backend && uvicorn app.main:app --reload --port 8011
cd frontend && npm install && npm run dev     # Vite on :3003 (isolated — :3000 is the SIH stack's)
```

Each row is a manual step. Mark ✅ when it behaves as described; if a step
breaks, stop — the failure is a bug to fix before going further.

## Auth first (401 / login gate)

| # | Step | Expect |
|---|---|---|
| 1 | Open http://localhost:3003 | **Login screen** renders (no dashboard) |
| 2 | Sign in with wrong password (`admin` / `nope`) | "Incorrect username or password" — no crash |
| 3 | Sign in as `investigator` / `invest123` | Dashboard renders, header shows `role: investigator` |
| 4 | Reload the page | Back to login (token is in-memory only — expected) |
| 5 | Sign in as `admin` / `admin123` | Dashboard renders, header shows `role: admin` |

## Search → subgraph render

| # | Step | Expect |
|---|---|---|
| 6 | Type `9812` in search, press Enter | A result row appears: `9812345601`, label `Phone` |
| 7 | Non-matching query (e.g. `zzzznope`) | "No entities match" notice — app does not crash (backend 404 handled) |
| 8 | Empty query + Enter | Nothing happens (client-side guard) |
| 9 | Click `9812345601` | Graph renders: the call-hub phone renders noticeably larger than the leaves (degree-scaled sizing); edges are unlabeled until clicked |
| 10 | Search `Ramesh`, click `Ramesh Patel` | Graph renders the FIR person (red) ± cross-world phone/person links |
| 11 | Hover header "Sub-graph" corner | Comma count `<name> · N nodes / M edges` matches the drawn graph |

## Node type color-coding + legend

| # | Step | Expect |
|---|---|---|
| 12 | Open the **Legend ▸** toggle (top-right of the canvas) | Person/Phone/Vehicle/Location/Organization swatches present in the collapsible panel |
| 13 | Colored nodes match legend | e.g. all phones blue `#2563eb`, persons red `#dc2626` |

## Influencer panel

| # | Step | Expect |
|---|---|---|
| 14 | Right-hand "Key Influencers" panel (any logged-in role) | Loads top 5 under auth: calls /influencers, shows `name — score 0.xxx` |
| 15 | Top influencer | `9812345601` (the call hub) — SOCIAL projection default, not a sink artifact |

## Admin-gated upload

| # | Step | Expect |
|---|---|---|
| 16 | Logged in as **investigator** → "Upload Data" panel | Message: uploads require the admin role; **no file picker** |
| 17 | Logged in as **admin** → "Upload Data" panel | File picker + CDR/FIR selector shown |
| 18 | Pick `data/sample_cdr.csv` | "CDR uploaded — 10 records ingested." |
| 19 | After upload, refresh "Key Influencers" (re-run search) | Graph/analytics reflect the new data — backend write actually landed |

## Logout / expired-redirect

| # | Step | Expect |
|---|---|---|
| 20 | Click "Sign out" in the header | Bounce to the login screen; dashboard unmounts |
| 21 | Sign in again, wait for a 401 to fire (or manually set an expired token in devtools: a JWT with past `exp`) | Any request returning 401 kicks the user back to login (axios interceptor → context clear) |

---

## Post-hardening additions (demo-hardening pass)

| # | Step | Expect |
|---|---|---|
| 22 | Search `ramesh` (lowercase) | Finds **Ramesh Patel** — `/search` is now case-insensitive (was 404) |
| 23 | Before any sub-graph is loaded | "No sub-graph loaded" placeholder + hint in the graph panel — not a blank box |
| 24 | Search `zzzznope` **after** a successful search | The "No entities match" notice shows AND the previous result list disappears (no stale rows alongside the notice) |
| 25 | Re-verify rows 1–21 at least once per reset (`python backend/demo_reset.py` between runs) | The one-command reset wipes Neo4j + Postgres, re-seeds sample data + users; influencer #1 is the call hub `9812345601` |
| 26 | Use the **+ / − / fit** toolbar (top-left of the canvas) | View zooms in/out and re-fits to screen after panning — view is never stuck |
| 27 | Click a node, then an edge | Details card under the canvas shows: node → name, type, degree, source cases; edge → relationship type, confidence, source case |
| 28 | Click empty canvas | Details card resets to the "click a node or an edge" hint |
| 29 | Look at repeated caller↔callee pairs (e.g. `9812345601 ↔ 9823456712`) | Parallel CALLED edges fan out (control-point-step-size) instead of stacking into one line |
| 30 | Search `Suresh`, click `Suresh Chauhan` (after a full `demo_reset.py`) | Node type colors unchanged; the three-person cell (Suresh, Ramesh, Vikram) carries a shared **community ring** (border in the same palette color) that the phone nodes do **not** share |
| 31 | Toggle `communities on/off` in the graph toolbar | Rings appear/disappear **in place** — nodes do NOT re-layout or jump |
| 32 | Check the "Cell discovery" note under the graph for the Suresh view | Reads "Community 8 groups 3 people (Suresh Chauhan, Ramesh Patel, Vikram) with no direct call record between them" — the plain-language headline finding |

**Cleanup:** Ctrl-C the uvicorn + vite processes when done.

**Return to the report:** a checklist where rows 1–25 are all ✅.