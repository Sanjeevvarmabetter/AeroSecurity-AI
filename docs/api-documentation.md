# API Documentation

Base path `/api/v1`. Interactive OpenAPI docs at `/docs` (disabled when `ENVIRONMENT=production`).
Standard error envelope: `{"error": {"code", "message", "details"}}`. Timestamps are ISO 8601 UTC and **must carry a timezone** in requests.

## Authentication and authorisation
`Authorization: Bearer <token>`. Roles (hierarchy): `viewer` < `analyst` < `admin`, configured with
`API_TOKEN_VIEWER|ANALYST|ADMIN` (an unset token disables that role). Read endpoints need `viewer`; workflow writes need
`analyst`. 401 = missing/invalid token, 403 = role too low. Audit records identify the caller as `role:key_id` where
`key_id` is the first 8 hex chars of SHA-256(token): never the token. A request may carry a self-asserted
`claimed_name` (recorded and displayed as unauthenticated). Requests are rate limited (429 + `Retry-After`).

## Endpoints
| Method & path | Role | Purpose |
|---|---|---|
| `GET /system/health`, `GET /healthz` | public | Dependency health (503 body when down) / liveness |
| `GET /auth/me` | viewer | Caller's role and key fingerprint |
| `GET /data-sources` | viewer | Registered sources, enabled state, last success/error |
| `GET /aviation/aircraft?q=&sort=&limit=&offset=` | viewer | Prefix search: ICAO24, registration or callsign |
| `GET /aviation/aircraft/live?at=&max_age_s=&lamin=&lomin=&lamax=&lomax=` | viewer | Latest position per aircraft in a freshness window; `stale` flag |
| `GET /aviation/aircraft/{icao24}` · `/history?start=&end=&order=` | viewer | Details with provenance · observation history |
| `GET /aviation/airports?q=` · `/airports/{code}` | viewer | OurAirports search / detail |
| `GET /analytics/trajectories?icao24=&start=&end=&gap_s=` | viewer | Segments, derived vs reported speed, gaps |
| `GET /anomalies` | viewer | Filter: `severity`*, `status`*, `detection_type`, `rule_id`, `icao24` (prefix), `airport`, `min_confidence`, `start`/`end` (overlap); sort `severity|confidence|detected_at|event_start`; pagination |
| `GET /anomalies/stats` | viewer | Counts by severity / status / type / rule |
| `GET /anomalies/{ANM-0001}` | viewer | Detail: evidence, alternatives, rule, investigation, notes, timeline, allowed transitions |
| `POST /anomalies/{id}/investigate` | analyst | Open the investigation (OPEN -> INVESTIGATING), optional first note |
| `PATCH /anomalies/{id}/status` | analyst | Transition with `reason` (required to close) |
| `POST /anomalies/{id}/notes` | analyst | Plain-text note (1-5,000 chars) |
| `GET /emergencies?squawk=&status=` | viewer | DET-005 events: code, aircraft, callsign, times, last known position |
| `GET /investigations?status=` | viewer | Investigations with note counts and last activity |

| `POST /intelligence/anomaly-explanation` | analyst | AI explanation of a detection (`anomaly_id`, optional `provider`/`model`); 502 + recorded analysis if output is invalid |
| `POST /intelligence/aircraft-investigation` | analyst | AI investigation summary for an aircraft (`icao24`) |
| `GET /intelligence/analyses?anomaly_id=&icao24=` | viewer | Stored AI analyses (always `ai_generated: true`), beside the current detection |
| `GET /settings/ai?check=true` | viewer | Provider config, health and model lists (never secrets) |
| `PUT /settings/ai` | admin | Change default provider / model names (not keys or URLs) |

| `POST /intelligence/chat` | analyst | Assistant turn (`message`, optional `conversation_id`, `provider`, `model`) |
| `GET /intelligence/conversations`, `/{id}` | viewer | Your conversations (admins: all) |
| `POST /intelligence/threat-correlation` | analyst | AI correlation of an anomaly with stored documents |
| `POST /intelligence/reports` | analyst | Generate a report for `anomaly_id` xor `icao24`, `include_ai` uses existing analyses |
| `GET /intelligence/reports`, `/{id}`, `/{id}/export?format=md\|pdf` | viewer | List, read, download |
| `GET /threat-intel?q=`, `/{id}` | viewer | Search / read documents |
| `POST /threat-intel`, `POST /threat-intel/import/arxiv` | analyst | Register a document (provenance required) / import abstracts |

\* repeatable query parameter.

## Workflow rules (enforced server-side)
```
OPEN ──► INVESTIGATING ──► RESOLVED
 │  ▲        │   ▲             │
 │  └────────┘   └──(reopen)───┘
 └──► FALSE_POSITIVE ──(reopen)──► OPEN
```
Allowed: OPEN→INVESTIGATING/FALSE_POSITIVE; INVESTIGATING→OPEN/FALSE_POSITIVE/RESOLVED; FALSE_POSITIVE→OPEN; RESOLVED→OPEN.
Closing (FALSE_POSITIVE/RESOLVED) requires a non-blank reason. INVESTIGATING requires an opened investigation; notes
require one too. The anomaly row is locked during a transition, validation happens before any mutation, and every change
writes an `audit_logs` row in the same transaction (`investigation.opened`, `anomaly.status_changed` with from/to/reason,
`anomaly.note_added`). A rejected request writes nothing. The detection engine never rewrites a finding an analyst has
closed.

## Examples
```bash
T=$API_TOKEN_ANALYST; H="Authorization: Bearer $T"
curl -s -H "$H" 'localhost:8000/api/v1/anomalies?severity=HIGH&severity=CRITICAL&sort=severity'
curl -s -H "$H" -X POST localhost:8000/api/v1/anomalies/ANM-0056/investigate -H 'Content-Type: application/json' \
     -d '{"note":"Triage started","claimed_name":"A. Analyst"}'
curl -s -H "$H" -X PATCH localhost:8000/api/v1/anomalies/ANM-0056/status -H 'Content-Type: application/json' \
     -d '{"status":"RESOLVED","reason":"Crew confirmed medical diversion"}'
```
