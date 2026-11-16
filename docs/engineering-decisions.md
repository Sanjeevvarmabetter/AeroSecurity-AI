# Engineering Decisions

Why the platform is built the way it is, phase by phase, including what real data and real providers taught us.
Each entry states the decision, the reason, and the evidence.

## Cross-cutting principles
- **Deterministic detection, AI explains.** Detections come from versioned, unit-tested rules. The AI layer has no write path to detections, statuses or evidence. Test: after an "obedient" (prompt-injected) model response, anomaly state and audit log are unchanged.
- **Absent stays absent.** Registration, type, operator and every provider-optional field are NULL unless a registered source supplied them (with provenance), and render as an em dash.
- **Reported vs derived are different quantities.** Provider-reported velocity and displacement-derived speed are separate fields and separate chart lines.
- **No accuracy claims.** Nothing has been validated against labelled attack data, and the documentation says so.
- **Fail loudly.** Unknown config keys are rejected, invalid AI output is recorded rather than shown, and provider errors map to specific, secret-free messages.

## Phase 1: Foundation
- **Modular monolith** (FastAPI + PostgreSQL/PostGIS + React/nginx). No Kubernetes, Kafka, Redis or vector DB: no requirement justified them.
- **Secrets by construction:** `DATABASE_URL` has no default and is a `SecretStr`; wildcard CORS is rejected at startup; logs redact URL credentials and key/token patterns; containers run as non-root.
- **Migrations own the schema.** Alembic autogenerate is limited to tables we own (the PostGIS image ships tiger-geocoder tables).
- **Health:** liveness never touches the database; the health endpoint returns 503 with a valid body when a dependency is down and never leaks connection details.

## Phase 2: Real data ingestion
- **Provider abstraction + one validator** shared by the CSV and REST adapters. The detection engine only reads stored observations.
- **Validation policy:** impossible-as-numbers values (NaN, negative speed, latitude > 90) are stored NULL with the original preserved as evidence; merely implausible values are stored unchanged so detection rules can see them.
- **`observed_at` is the position-fix time**, so re-emitted copies of one fix collapse (idempotent import).
- **Live OpenSky API is disabled by default** (its terms restrict operational use); enabling is an explicit operator action. Backoff, token refresh and credit-aware polling are implemented and tested against a mock transport, and verified live with an authenticated poll.
- **Auth + rate limiting arrived with the first data endpoint:** role tokens compared in constant time, unset token disables the role (fail closed).
- **Hermetic tests:** an isolated `<db>_test` database, and no real credentials read from a developer's `.env` (a real leak into unit tests was found and fixed).

## Phase 3: Aircraft intelligence
- **Analytics are pure functions** (haversine, derived speed/vertical rate, gap detection) and return numbers, never verdicts.
- **Search is injection-safe by construction:** patterns exclude LIKE wildcards, all SQL is parameterised, prefix matching uses `text_pattern_ops` indexes.
- **"Live" means latest stored position per aircraft in a freshness window** ending at `at`; `at` replays historical moments, and the response says explicitly when data is stale.
- **Bundled Natural Earth basemap** (no API keys or third-party requests). Found by testing: the free tile service started returning "API KEY REQUIRED" watermarks.
- **Real-data findings that shaped later design:** position timestamps jitter by up to ~1 s (16 segments implied 300-1,182 m/s for a ~230 m/s aircraft); the dataset README's gap figures disagreed with its own tables, so the code asserts what the data shows.

## Phase 4: Detection engineering
- **Rules are pure** (`Obs` in, `Finding` out). A cross-rule contract test enforces: evidence present, alternatives listed, exactly one subject, JSON-serialisable evidence, no wording that asserts intent or cause.
- **Tolerances measured from data,** configurable, and recorded in evidence: lower-bound speed = `max(0, d - 2*position_unc) / (dt + timestamp_unc)`.
- **Confidence means confidence in the data pattern,** not probability of malice.
- **Idempotent persistence** keyed on rule + version + dedup key. Analyst-closed findings are never rewritten by the engine.
- **Thresholds were not tuned to manufacture findings:** DET-007 produced none on real data and that is documented.

## Phase 5: Security dashboard
- **Audit identity without user accounts:** the actor is `role:token-fingerprint` (never the token); a display name is stored but labelled self-asserted.
- **Workflow integrity:** explicit transition table, validate-then-mutate, row lock, audit row in the same transaction, closed findings immutable to the engine. A real bug (state changed before validation) was caught by a test and fixed.
- **Notes are untrusted plain text,** rendered as React text nodes; an end-to-end test confirms a hostile `<img onerror>` note neither executes nor creates an element.
- **UI honesty:** the data-pattern-not-maliciousness disclaimer is visible text, not a tooltip.

## Phase 6: AI integration
- **Local-first:** Ollama is the default provider; cloud use is an explicit, visible per-request choice.
- **Validation over trust:** JSON schema, evidence-reference check, one repair attempt; failures are recorded as `INVALID_OUTPUT`.
- **Prompt injection:** data goes in one delimited block with angle brackets neutralised; the model has no tools in this phase.
- **Found by testing real providers:** reasoning models spend the whole token budget thinking and return nothing (now an explicit, actionable error); httpx timeouts are per read, so a wall-clock deadline is enforced; nginx cut off long AI calls at 30 s; the UI showed a previous result after a failed request (now hidden).

## Phase 7: Assistant, correlation, reports
- **Capability minimisation:** nine read-only tools, validated and capped, no write or free-form query path. Citations must be ids that tools returned.
- **Unverified absence claims are flagged** after a real failure where a model asserted "no HIGH detections" without querying them; a fleet-wide search tool was added because the model could not express that query.
- **Four layers kept apart** in correlation (verified observations / document statements / hypotheses / AI interpretation), strict where misattribution is dangerous, graceful elsewhere.
- **No scraping:** external intelligence comes from arXiv's documented API (XML parsed with `defusedxml`, tested against entity-expansion and file-read payloads) or manual registration with mandatory reliability statements.
- **Reports** keep platform facts and AI content in separately labelled sections; the whole report is marked UNREVIEWED.
- **Known limit:** citation validation proves an id exists, not that it supports the claim; a small local model produced semantically wrong but structurally valid output.

## Live data
- The OpenSky adapter was enabled only on explicit instruction. Polling is deliberately slow (anonymous credits are scarce) and the loop survives transient failures but stops after five in a row.
