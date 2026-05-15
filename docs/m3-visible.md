# M3 — Visible

## 1. One-line summary

M3 ships the web UI: a React + Sigma.js frontend that renders the M2 graph as navigable flows, exposes per-node confidence and provenance on hover, and lets any senior engineer answer cross-service questions without reading a diagram legend first.

---

## 2. Why M3 ships last

**UI without query power is just diagrams.** CAST Imaging's core failure mode is exactly this: a beautiful force-directed graph over a deterministically-incomplete substrate, requiring an architect to interpret what the tool could not infer. M3 avoids that failure by shipping after M1 (deterministic graph), M1.5 (LLM extraction), and M2 (agent query layer) are validated.

Three things must be true before a UI is worth building: the graph schema must be stable, the query layer fast enough that a click returns in under two seconds, and the confidence model populated enough that the coverage dashboard shows real signal. None of those are true before M2 ships.

The sequencing also protects the product positioning. If M3 had shipped alongside M1, every demo would be evaluated as "a diagramming tool." By the time M3 ships, the substrate is already proven as a machine-queryable artifact — the UI is a rendering layer, not the product.

---

## 3. UI design principles

**Engineer-first, not architect-first.** CAST's UI is optimised for an architect who already knows what a "transaction scope" or "architecture layer" means and has spent a week in onboarding. Cartograph's UI is optimised for a senior engineer who has ten minutes and a specific question — "what services does the permit-approval flow touch?" — and needs an answer before standup.

Four principles govern every design decision:

- **Flow as default view.** When you open a service, the Flow view is the first tab, not a menu item three clicks deep. Engineers think in flows; they navigate by question, not by taxonomy.
- **Confidence visible everywhere.** Every node and every edge carries a confidence badge. There is no part of the UI where you are looking at a claim without knowing whether it came from a deterministic pack rule, an LLM extraction, or an agent traversal. Opaque graphs are the enemy of trust.
- **No hidden state.** Filters are always visible in the URL and as a chip bar above the graph. There is no "active session state" that makes two engineers see different graphs from the same URL.
- **Source always one click away.** Clicking any flow node opens the source file at the correct line. Clicking any edge shows the rule or model run that produced it. The graph is not a summary — it is a navigable index of the actual code.

---

## 4. Core views

### Flow view

**The differentiated view.** Services are rendered as vertical swimlanes. Kafka topics appear as labelled async edges between swimlanes — dashed lines with the topic name and a delivery arrow. HTTP calls appear as solid sync edges with the method and path. The layout is left-to-right by default, following the direction of a request through the system.

This is the default tab when opening any service or flow lens result. It is the closest analog to CAST's "Transaction" view, but it is driven by lens output from [M2's flow-lens](./m2-queryable.md#flow-lens) rather than by pre-computed transaction identification. Where CAST requires an architect to first configure transaction scopes and then run a deep analysis before a transaction view is available, Cartograph's Flow view is available the moment the M2 query layer can answer a flow question.

A flow query like `trace permit-approval` resolves to a set of services, endpoints, and message topics. The Flow view renders that result directly — swimlanes for each service, with the edges ordered top-to-bottom by the sequence in which they fire. Services with no pack coverage appear in the view with a low-confidence badge; engineers can see the gap before they trust the trace.

### Service view

The Service view scopes the graph to a single service. It shows the service's endpoints (inbound), its outbound HTTP calls, its Kafka producer topics, its Kafka consumer topics, and the inferred contracts on each edge. A dependency table below the graph lists every upstream and downstream service by name, with the edge count and the dominant confidence tier.

This view is the entry point for "what does this service depend on?" questions, and where engineers land when they click through from a search result or a coverage dashboard row.

### Coverage dashboard

**The confidence story made human-readable.** The coverage dashboard shows a per-service table with three columns: pack coverage percentage, LLM coverage percentage, and uncovered percentage. These map directly to the `source` field on graph nodes and edges — `pack:<rule-id>` nodes count toward pack coverage; `llm:<model>@<date>` and `agent:<tool-id>@<date>` nodes count toward LLM coverage; nodes with no source or an unresolved anchor are uncovered.

Each row is color-coded: green for services with pack coverage above 70% (consistent with the 70–90% pack coverage claim validated in [Spike B](../spike/real-repos/SPIKE-B-FINDINGS.md)), yellow for services with substantial LLM coverage, red for services with more than 30% uncovered. Engineers should be able to glance at this dashboard before running a flow query and know which parts of the answer to verify manually.

The dashboard makes an explicit, visible split between "what we know from deterministic rules" and "what the LLM inferred." This is not a detail panel — it is the first thing an engineer sees when they land on the coverage tab. CAST has no equivalent; it presents its graph as a single authoritative artifact with no epistemic gradient.

### Search and graph explorer

A top-of-page search bar accepts free-text and structured queries. Free-text queries run against node labels, service names, endpoint paths, and topic names. Structured queries use a small filter syntax: `service:permit-service confidence:high source:pack` narrows to pack-derived nodes in that service. Results render as a list with service badges and confidence indicators; clicking a result opens either the Flow view or the Service view depending on the node type.

The graph explorer is a secondary mode, not the primary entry point. Engineers who want to browse the full graph can switch to it, but the default experience is search-first — enter a question, get a scoped view, drill from there.

---

## 5. Confidence and provenance display

**Every node and edge has a hover state.** Hovering any node or edge opens a small popover with three fields:

- `source`: one of `pack:<rule-id>`, `llm:<model>@<date>`, or `agent:<tool-id>@<date>`
- `confidence`: `high`, `medium`, or `low`
- `anchor`: the file path and line number where the claim is grounded in source code

The confidence tier maps directly to the three-tier system defined in [SHARED-CONTEXT.md](./SHARED-CONTEXT.md): pack-derived nodes are `high`, LLM-derived nodes are `medium` by default (bumped to `high` if two-pass consensus confirmed them, per [Spike C](../spike/real-repos/SPIKE-C-FINDINGS.md)), agent-derived nodes are `low` unless the agent cites a pack-confirmed anchor.

Confidence is also rendered visually. High-confidence nodes have a solid border. Medium-confidence nodes have a dashed border. Low-confidence nodes have a dotted border and a faint opacity reduction. This means the confidence gradient is readable without hovering — an engineer can scan a Flow view and immediately see which edges are solid and which are inferred.

The visual treatment is not decorative. It answers the question "should I trust this?" at a glance, which is the core of the anti-CAST positioning.

---

## 6. Interaction patterns

**Interactions are consistent: click to navigate, hover to inspect.** No gesture does more than one thing.

Clicking a flow node opens the source file in a split panel on the right, scrolled to the line that produced the node — the same anchor stored in the `anchor` field of the node's provenance record. This is not a deep link to GitHub or a separate window; it is an inline source viewer scoped to the relevant function. The line is highlighted; the surrounding context is visible.

Clicking an edge opens a detail panel showing the rule or model run that produced it. For a pack-derived edge, this shows the Pack ID, the rule file, and the tree-sitter query that matched. For an LLM-derived edge, this shows the model, the prompt version, the extraction date, and the structured-output claim the model returned. For an agent-derived edge, this shows the agent tool ID, the traversal path, and the sub-nodes it visited to infer the edge.

Filtering is available at two levels. The chip bar above any graph view exposes confidence-tier filters (show only `high`, show `high + medium`, show all) and source filters (show only `pack:*`, show only `llm:*`, hide `agent:*`). These filters apply immediately without a reload and are reflected in the URL so they can be shared. The second level of filtering is the coverage dashboard: clicking a red row in the coverage dashboard navigates to that service's Flow view with uncovered nodes highlighted.

---

## 7. Tech stack

**Sigma.js renders the graph; React wraps everything; MCP provides all data.**

- **Graph rendering:** [Sigma.js](https://www.sigmajs.org) with Graphology as the underlying graph data structure. Sigma's WebGL renderer handles graphs up to ~100k nodes without layout degradation — well beyond the size of any service-scoped or flow-scoped view. For the full polyrepo graph explorer, the edge limit defaults to 5,000 edges; a "show more" control loads additional neighbours on demand.
- **Layout:** Graphology's `graphology-layout-forceatlas2` for force-directed; a custom swimlane layout for the Flow view. The swimlane layout is written as a Graphology layout plugin — it assigns x-positions based on service index and y-positions based on call order within the flow, with Kafka topic nodes placed at the midpoint of the source and target swimlanes.
- **Shell:** React 18, TypeScript. Routing via React Router. No Next.js — the UI is a static SPA deployed behind the MCP server's HTTP endpoint.
- **Styling:** Tailwind CSS with [shadcn/ui](https://ui.shadcn.com) for component primitives (buttons, popovers, tooltips, tables). The design token set is minimal: two brand colors, three confidence-state colors (green/yellow/red), one graph background.
- **Data layer:** All graph data comes from the MCP server over a thin HTTP+WebSocket API. The UI has no direct access to KuzuDB or any other storage layer. The MCP server exposes endpoints that mirror its tool surface: `GET /flows/{lens}` returns the flow graph for a lens query; `GET /services/{id}/coverage` returns the coverage breakdown; `GET /nodes/{id}/provenance` returns the source and confidence record. The UI is a consumer of the MCP server, not a co-owner of data.
- **Source viewer:** A lightweight code panel using [CodeMirror 6](https://codemirror.net) with syntax highlighting. Not a full IDE — no LSP, no editing. The sole purpose is "show me the line that produced this node."
- **State management:** React Query for server state (graph data, coverage data, search results). No global client-side store — URL parameters carry filter state.

Day-one scaffold: `pnpm create vite@latest cartograph-ui -- --template react-ts`, add Sigma.js, Graphology, shadcn/ui, React Query, React Router, and CodeMirror 6. A running MCP server pointed at a test repo is the only external dependency.

---

## 8. Optional enterprise tier

**Enterprise features are a monetisation layer, not a prerequisite for product-market fit.** The following deliverables are part of M3 but gate behind a paid SKU. The open-tier product is complete without them. A team of five engineers using Cartograph against their own repos does not need any of these features; they exist for organisations deploying Cartograph as shared infrastructure across many teams.

- **SSO.** SAML 2.0 and OIDC federation with the customer's identity provider. The MCP server ships with a basic username/password auth layer in the open tier; SSO replaces that with a configurable identity broker. Implementation: Keycloak realm configuration exported as a YAML template.
- **RBAC.** Role-based access control at the service level. An engineer can be granted read access to a subset of services in the graph. The coverage dashboard and flow views filter to the permitted services automatically. The MCP server enforces permissions at the data layer; the UI does not render nodes the user cannot see.
- **Multi-tenant graph isolation.** A single Cartograph deployment can host graphs for multiple organisations. Each organisation's graph is stored in a separate KuzuDB database. The UI routes to the correct tenant based on the authenticated identity. Tenant data never appears in another tenant's query results.
- **Audit log.** Every query, every flow trace, every source-file open is recorded with the user identity, the timestamp, and the parameters. The audit log is queryable from the admin panel and exportable as CSV. This is a compliance feature, not a product feature.
- **On-prem deployment.** A Helm chart and a Docker Compose file for air-gapped deployment. The MCP server, the graph database, and the UI are all containerised. The LLM layer can be pointed at an Ollama instance on local hardware. No external network calls are required after installation.

None of these features change the core graph, the flow view, or the confidence model. They are operational concerns for enterprise buyers. Building them after M3 core ships is the correct sequence — proving product-market fit with the open tier first avoids building enterprise plumbing for a product that has not yet found its users.

---

## 9. Out of scope

**Live runtime trace overlay is explicitly deferred.** M2 imports OTEL span data as a data source for the graph, but M3 does not render live trace streams. A live overlay would require a WebSocket subscription to an OTEL collector, a reconciliation layer between static graph nodes and dynamic span IDs, and a time-scrubber UI component. That is a substantial feature that belongs to a post-M3 milestone. The graph at M3 is a static index of code structure, not a runtime monitoring tool.

**Full graph editing is read-only at M3.** Engineers can filter, navigate, and inspect — but they cannot add nodes, delete edges, or override confidence scores through the UI. The graph is owned by the indexer and the MCP server. Editing through the UI would require a write path through the MCP server, conflict resolution for concurrent edits, and audit trail support — none of which are in scope for M3. Custom annotations (tagging a service, leaving a note on a flow) are a candidate for M3.1 or M4, not M3.

---

## 10. Success metrics

**The primary metric is task completion by a non-expert.** A senior engineer who has never used Cartograph before should be able to answer "what services does the permit-approval flow touch?" by clicking through the UI alone, in under ten minutes, without reading documentation.

Secondary metrics:

- A first-time user lands on the coverage dashboard and, without prompting, navigates to a flow view and identifies at least one low-confidence edge before making a decision based on the graph. This measures whether the confidence visibility design actually informs behaviour.
- A flow query covering three or more services renders in under two seconds on a laptop with the MCP server running locally against the CityPermits synthetic test repo from [Spike A](../spike/polyrepo/SPIKE-A-FINDINGS.md).
- An engineer asks a question in the search bar in natural language ("what calls the permit submission endpoint?") and arrives at a scoped Flow view with the correct anchor service highlighted, without needing to know the endpoint path in advance.
- The coverage dashboard correctly shows the 40% pack / 30% LLM / 30% uncovered split for a service that was deliberately indexed with a partial pack set. Engineers should trust the dashboard's accuracy before trusting the flows it surfaces.

---

## 11. Open questions

1. **Swimlane layout authorship.** The Flow view requires a custom swimlane layout plugin for Graphology. This is not a hard problem, but it is a design decision — how are services ordered left-to-right when there is no single root? The current plan is to order by call frequency (most-called service rightmost), but that heuristic fails for fan-out patterns like a BFF calling five downstream services. Owner: frontend lead, before first Flow view prototype.

2. **Source viewer scope.** The inline source viewer shows the function that contains the anchor line. For large files this may be hundreds of lines. Should the viewer show only the function, the full file with the anchor highlighted, or a configurable context window? A context-too-small design frustrates engineers who need surrounding context; a context-too-large design obscures the specific claim. Decision needed before source-viewer implementation begins.

3. **Enterprise tier sequencing.** The five enterprise features (SSO, RBAC, multi-tenant isolation, audit log, on-prem) are listed here as M3 deliverables but are explicitly optional. The question is whether to ship them in M3 proper or to cut them to M4 and treat M3 as open-tier only. The answer depends on whether an enterprise pilot customer is identified before M3 development begins. If yes, implement the specific features they require. If no, defer all five. Owner: product lead, by M2 GA.
