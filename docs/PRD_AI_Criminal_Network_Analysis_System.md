# Product Requirements Document (PRD)
## AI-Powered Criminal Network Analysis System

| Field | Detail |
|---|---|
| Problem Statement ID | 26189 |
| Problem Statement Title | AI-Powered Criminal Network Analysis System |
| Organization | Ministry of Home Affairs |
| Department | National Crime Records Bureau (NCRB), Women Safety Division |
| Category | Software |
| Theme | Blockchain & Cybersecurity |
| Document Version | 1.1 |
| Status | Draft — SIH 2026 (reconciled with the built implementation; see §16) |

---

## 1. Executive Summary

Criminal networks today are rarely the work of a single actor — they span associates, financiers, intermediaries, locations, and communication channels, with evidence scattered across FIRs, CDRs, financial records, surveillance reports, social media, and criminal history databases. Investigators must currently piece these fragments together manually, which is slow and prone to missing non-obvious connections.

This PRD defines **CrimeGraph**, an AI-powered investigation-support platform that ingests structured and unstructured crime-related data, extracts entities and relationships using NLP and ML, builds a unified knowledge graph, and surfaces key influencers, hidden links, and suspicious patterns through graph analytics and an interactive visual interface — giving investigators actionable intelligence rather than raw data.

---

## 2. Problem Statement (as given)

Modern criminal activities are increasingly organized and interconnected, operating through networks of associates, intermediaries, financial channels, communication links, locations, and events. Law enforcement collects large volumes of data from FIRs, CDRs, financial transaction records, surveillance reports, social media intelligence, criminal history databases, and intelligence agency reports — but this data is fragmented, unstructured, and spread across multiple systems, making manual analysis slow and error-prone.

The goal is an AI system that automatically discovers relationships, detects patterns, and generates insights to help investigators understand criminal networks — extracting entities (people, locations, vehicles, phone numbers, organizations), building relationship maps, identifying key influencers, detecting suspicious activity, and presenting visual/analytical insights.

---

## 3. Goals & Objectives

| Goal | Description |
|---|---|
| G1 | Ingest and normalize multi-source, multi-format crime data (structured + unstructured) into one pipeline |
| G2 | Extract entities (people, phone numbers, vehicles, locations, organizations, events) using NLP/NER tuned for law-enforcement text |
| G3 | Automatically construct and continuously update a knowledge graph of entity relationships |
| G4 | Identify influential/key individuals using graph centrality and community-detection algorithms |
| G5 | Detect suspicious patterns and anomalies (e.g., unusual call clusters, layered transactions, repeated co-location) |
| G6 | Present findings through an investigator-friendly visual interface with search, filters, and drill-down |
| G7 | Ensure data security, access control, auditability, and chain-of-custody appropriate for law-enforcement use |

### Non-Goals (out of scope for MVP/hackathon build)
- Real-time live wiretap ingestion or telecom-operator integration
- Legal-grade evidentiary certification of AI-derived conclusions
- Predictive policing / individual risk-scoring of persons not already linked to a case
- Nationwide production deployment / integration with live NCRB systems

---

## 4. Target Users & Personas

| Persona | Needs |
|---|---|
| **Field Investigator / Sub-Inspector** | Quickly see who a suspect is connected to, across cases, without manually cross-referencing files |
| **Case Supervisor / SP-level Officer** | Bird's-eye view of a network, identify key influencers/kingpins to prioritize action against |
| **Intelligence Analyst (NCRB/State CID)** | Cross-case, cross-jurisdiction pattern detection; link seemingly unrelated FIRs |
| **Women Safety Cell Officer** | Detect networks behind trafficking/organized crimes against women, spot repeat-offender clusters |
| **System Administrator** | Manage data ingestion, user roles, and audit access to sensitive intelligence |

---

## 5. Data Sources & Inputs

| Source | Format | Extraction Challenge |
|---|---|---|
| FIRs / Police Reports | Unstructured text (scanned/typed) | OCR + NER on informal, regional-language text |
| Call Detail Records (CDRs) | Structured (CSV/DB) | High volume, needs graph-scale linking |
| Financial Transaction Records | Structured | Layered/obfuscated transaction chains |
| Surveillance Reports | Semi-structured text | Ambiguous entity references |
| Social Media Intelligence | Unstructured (text/images/metadata) | Noise, aliases, fake profiles |
| Criminal History Databases | Structured | Entity resolution across spelling variants |
| Intelligence Agency Reports | Unstructured text | Classification/sensitivity handling |

---

## 6. Proposed Solution — System Overview

CrimeGraph is composed of five layers:

1. **Ingestion Layer** — connectors/upload interfaces for each data source; normalizes into a common schema.
2. **Extraction Layer (NLP/ML)** — Named Entity Recognition, relationship extraction, entity resolution/deduplication (same person, different spellings/aliases).
3. **Knowledge Graph Layer** — stores entities (nodes) and relationships (edges) with metadata (source, timestamp, confidence score).
4. **Analytics Layer** — graph algorithms (centrality, community detection, shortest path, temporal pattern mining) to surface key influencers and anomalies.
5. **Presentation Layer** — interactive graph visualization, search, case linking, alerts, and reporting for investigators.

### High-Level Architecture

```
 ┌────────────────────────────────────────────────────────────┐
 │                      Presentation Layer                    │
 │  React + TypeScript UI · Graph Visualization (Cytoscape/D3) │
 │  Search · Filters · Case Dashboard · Alerts · Report Export │
 └───────────────────────────▲──────────────────────────────────┘
                              │ REST/GraphQL API
 ┌───────────────────────────┴──────────────────────────────────┐
 │                       Analytics Layer                        │
 │  Centrality (PageRank/Betweenness) · Community Detection      │
 │  Anomaly Detection · Link Prediction · Temporal Pattern Mining│
 └───────────────────────────▲──────────────────────────────────┘
                              │
 ┌───────────────────────────┴──────────────────────────────────┐
 │                     Knowledge Graph Layer                    │
 │             Neo4j Graph DB (entities + relationships)         │
 └───────────────────────────▲──────────────────────────────────┘
                              │
 ┌───────────────────────────┴──────────────────────────────────┐
 │                      Extraction Layer                        │
 │  NER (spaCy/transformers) · Relation Extraction · OCR         │
 │  Entity Resolution/Deduplication · Confidence Scoring         │
 └───────────────────────────▲──────────────────────────────────┘
                              │
 ┌───────────────────────────┴──────────────────────────────────┐
 │                       Ingestion Layer                        │
 │  FIRs · CDRs · Financial Records · Surveillance · Social Media│
 │  Criminal DB · Intel Reports  →  ETL / Upload / Connectors    │
 └────────────────────────────────────────────────────────────┘
```

---

## 7. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR1 | System shall ingest CSV/PDF/text uploads for CDRs, financial records, and FIRs | Must |
| FR2 | System shall extract named entities (person, phone, vehicle, location, organization) from unstructured text | Must |
| FR3 | System shall resolve duplicate/alias entities into a single canonical node | Must |
| FR4 | System shall build a graph linking entities via relationships (calls, transactions, co-location, association) with source provenance | Must |
| FR5 | System shall compute centrality scores to rank "key influencer" nodes | Must |
| FR6 | System shall detect suspicious patterns (e.g., burst-call clusters, circular financial transfers, repeated co-location) | Must |
| FR7 | System shall provide an interactive graph UI: zoom, filter by entity type/date/case, expand/collapse neighbors | Must |
| FR8 | System shall allow investigators to search by name/phone/vehicle number and retrieve the connected sub-graph | Must |
| FR9 | System shall support role-based access control and log all queries/views (audit trail) | Must |
| FR10 | System shall allow exporting a case sub-graph and findings as a report (PDF) | Should |
| FR11 | System shall support cross-case linking (same entity appearing in multiple FIRs) | Should |
| FR12 | System shall flag confidence levels on AI-inferred relationships (not auto-assert as fact) | Should |
| FR13 | System shall support multilingual text input (Hindi/regional languages) for NER | Could |

---

## 8. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Security** | End-to-end encryption at rest and in transit; strict RBAC; sensitive data access logging |
| **Privacy/Legal** | Compliance-oriented design — audit trails, data retention policy, no unauthorized profiling |
| **Scalability** | Graph DB must handle 100K+ nodes / 1M+ edges without significant query degradation |
| **Performance** | Sub-graph queries (2–3 hop) should return in under 3 seconds for demo-scale data |
| **Reliability** | Ingestion pipeline should handle malformed/partial records gracefully (no pipeline crash) |
| **Usability** | Graph UI must be understandable to non-technical investigators, not just analysts |
| **Auditability** | Every AI-inferred link must be traceable back to its source record(s) |

---

## 9. Suggested Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Tailwind CSS |
| Graph Visualization | Cytoscape.js or D3.js (force-directed graph) |
| Backend / API | Python + FastAPI |
| NLP / Entity Extraction | spaCy, HuggingFace Transformers (NER), regex for phone/vehicle patterns |
| OCR (for scanned FIRs) | Tesseract OCR — deferred beyond the MVP (see §16.5) |
| Graph Database | Neo4j (Cypher queries for centrality, community detection) |
| Relational/Doc Store | PostgreSQL (case metadata, users, audit logs) |
| Search | OpenSearch / Elasticsearch (entity & full-text search) — not in the MVP; built entity search is a case-insensitive Neo4j substring query over canonical names (FR8), see §16.5 |
| Analytics | Neo4j Graph Data Science library (PageRank, Louvain community detection) |
| Auth | JWT-based auth with RBAC middleware — passwords stored as bcrypt hashes, hashed directly with the `bcrypt` library (passlib 1.7.4 is incompatible with modern bcrypt — see §16.3) |
| Deployment | Docker Compose (hackathon demo) → Kubernetes (production path). The hackathon build mounts isolated host ports because this machine also runs a separate SIH stack — see §16.2 |

---

## 10. Key Algorithms & Analytics Approach

| Task | Approach |
|---|---|
| Key influencer identification | Betweenness centrality + PageRank on the knowledge graph — high-centrality nodes act as bridges/hubs |
| Hidden network discovery | Community detection (Louvain/Label Propagation) to cluster tightly-connected sub-groups |
| Suspicious pattern detection | Rule-based + ML anomaly scoring: burst communication windows, circular/layered fund transfers, repeated co-location without known relationship |
| Entity resolution | Fuzzy matching (name/alias similarity) + shared attribute matching (phone, address) to merge duplicate nodes |
| Cross-case linking | Shared-entity join across case graphs to reveal an individual's presence in multiple, seemingly unrelated FIRs |

**Influencer-ranking projection policy (as implemented).** The GDS PageRank /
betweenness projection is configurable, and the build ships **SOCIAL** as the
product default with **UNIFORM** kept only as an internal baseline:

- *UNIFORM* — `('*', '*', directed)`: every node label and relationship type
  counted identically. This was the scaffold baseline, but Vehicle / Location /
  Organization leaves become PageRank sinks, and the directionality of
  `ASSOCIATED_WITH` / `OWNS` is a write-order artifact — so rankings skew away
  from the true hubs.
- *SOCIAL* — nodes `{Person, Phone}`, edges `CALLED / ASSOCIATED_WITH / OWNS`
  treated **undirected** (direction on ASSOC/OWNS is a write artifact; `OWNS` is
  kept so a person stays reachable from their phone). This is what
  `/api/influencers` returns by default; `?projection=uniform` exists for
  internal comparison only and is **not** surfaced in the demo UI. Verified
  against the sample data: SOCIAL #1 is the call hub `9812345601`, which matches
  the degree baseline rather than a sink artifact.

---

## 11. MVP Scope (Hackathon Build)

**In scope for MVP:**
1. Upload interface for sample CDR (CSV) + FIR (text) datasets
2. NER pipeline extracting person/phone/location/vehicle entities
3. Graph construction into Neo4j with relationship edges
4. Interactive graph visualization with search + filter
5. Centrality-based "top 5 key influencers" panel
6. One suspicious-pattern detector (e.g., burst-call clustering)
7. Basic RBAC login (investigator vs. admin role)

**Deferred beyond MVP:**
- Multilingual NLP, OCR pipeline for scanned documents
- Full cross-agency data connectors
- Advanced anomaly-detection models (deep learning based)
- Production-grade audit/compliance certification

---

## 12. Expected Deliverables

| Deliverable | Description |
|---|---|
| Working prototype | End-to-end demo: data upload → entity extraction → graph → investigator dashboard |
| Source code repository | Modular, documented codebase (ingestion, extraction, graph, API, frontend) |
| Sample dataset | Synthetic/anonymized CDR, FIR, and transaction data for demonstration |
| Architecture & design document | System architecture, data flow, and algorithm documentation |
| Demo video / presentation | Walkthrough of the investigator workflow and key-influencer detection |

---

## 13. Success Metrics

| Metric | Target |
|---|---|
| Entity extraction accuracy (precision/recall on sample FIR text) | ≥ 80% F1 on demo dataset |
| Time to surface a hidden 2-hop connection vs. manual search | Significant reduction (demo comparison) |
| Key-influencer ranking relevance | Top-ranked nodes match manually-identified "kingpins" in test scenarios |
| UI usability | Investigator persona can find a suspect's network within a few clicks |

---

## 14. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Poor-quality/noisy real-world text (informal FIR language) | Start with cleaned/synthetic sample data for MVP; note production NLP fine-tuning as future work |
| False-positive relationships eroding investigator trust | Attach confidence scores and source provenance to every inferred edge |
| Data sensitivity/privacy concerns | Use synthetic data for demo; design RBAC + audit logging from the start |
| Graph scale performance | Limit demo dataset size; document scaling path (Neo4j clustering) for production |

---

## 15. Future Roadmap (Post-Hackathon)

1. Multilingual NER + OCR for scanned FIRs
2. Integration connectors for live CDR/financial-intelligence systems
3. Predictive link suggestion (probable undiscovered connections)
4. Mobile app for field investigators
5. Blockchain-backed audit trail for evidentiary chain-of-custody (aligns with the Blockchain & Cybersecurity theme)

---

## 16. Implementation Notes & Divergences from the Original Plan

*Retroactive (added during demo-hardening) — these notes reconcile the plan
above with what was actually built for the SIH 2026 demo. The canonical
one-command reset of the demo state is `python backend/demo_reset.py`
(see CLAUDE.md).*

1. **Influencer-ranking projection: SOCIAL chosen over UNIFORM (FR5, §10).**
   See the "Influencer-ranking projection policy" note in §10. Short version:
   `/api/influencers` defaults to the **SOCIAL** projection (Person + Phone,
   undirected `CALLED / ASSOCIATED_WITH / OWNS`); **UNIFORM** (`'*','*'`,
   directed) is retained only as an internal scaffold baseline and is not
   surfaced in the demo UI, because it ranks sink artifacts, not hubs.

2. **Port-isolation scheme.** This machine co-hosts a separate pre-existing SIH
   stack ("Network Intelligence") that owns the standard ports (Neo4j bolt 7687
   / http 7474, backend 8000, Postgres 5432, frontend 3000). To keep its own
   graph and GDS projections isolated, CrimeGraph mounts **non-default host
   ports**: Neo4j bolt **7688** / http **7475**, FastAPI **8011**, Postgres
   **5433**, Vite **3003**. The code defaults (`NEO4J_URI`, `DATABASE_URL`,
   frontend `API_BASE`, the backend CORS allow-list) all point at these; the
   native defaults are overridable via env vars. Do not "fix" them back.

3. **bcrypt swap (passlib replaced).** Passwords are hashed directly with the
   `bcrypt` library (≥ 4.2, pinned in `requirements.txt`). `passlib 1.7.4` is
   broken at runtime against the modern bcrypt resolved by this install, so
   `backend/app/auth/rbac.py` hashes and verifies directly instead of going
   through passlib. Seed-user hashes are generated at runtime by
   `app/db/migrate.py` / `demo_reset.py` — they cannot live in static SQL.

4. **Python 3.14 (up from the planned 3.11).** The fully-pinned virtualenv
   resolves **Python 3.14.4** (matching the machine's interpreter). No change
   to the demo surface; this PRD and CLAUDE.md now state 3.14.

5. **Other §9 stack deltas (as built).** Entity search (FR8) is a
   case-insensitive Neo4j substring query over canonical names — OpenSearch /
   Elasticsearch was not needed at demo scale and is deferred. Graph
   visualization is **Cytoscape.js** (the chosen option in §9). OCR (Tesseract)
   and HuggingFace Transformers remain deferred beyond the MVP per §11.

---

*End of Document*
