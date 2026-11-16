# Database Schema

PostgreSQL 16 + PostGIS 3.4. All timestamps `timestamptz` (UTC). Geometry is `POINT`, SRID 4326 (lon/lat).
Distances are computed with geography/haversine, never planar degrees.

## Implemented (migration 0001)

```mermaid
erDiagram
    data_sources ||--o{ aircraft_observations : "provenance"
    data_sources ||--o{ airports : "provenance"
    aircraft ||--o{ aircraft_observations : has
    data_sources { int id PK  string name UK  string kind  string terms_url  bool enabled  timestamptz last_success_at  timestamptz last_error_at  text last_error }
    aircraft { int id PK  string icao24 UK  string registration  string aircraft_type  string origin_country  timestamptz first_seen  timestamptz last_seen }
    aircraft_observations { bigint id PK  int aircraft_id FK  int data_source_id FK  timestamptz observed_at  timestamptz last_contact_at  string callsign  geometry position  float baro_altitude_m  float geo_altitude_m  bool on_ground  float velocity_ms  float heading_deg  float vertical_rate_ms  string squawk  smallint position_source  jsonb raw }
    airports { int id PK  string ident UK  string iata_code  string name  string airport_type  string iso_country  int elevation_ft  geometry position  int data_source_id FK }
    audit_logs { bigint id PK  timestamptz occurred_at  string actor  string action  string entity_type  string entity_id  jsonb details }
```

Design notes:
- **Identity vs time series:** `aircraft` holds one row per ICAO24 (CHECK `^[0-9a-f]{6}$`); observations are separate, append-only rows.
- **Idempotent ingestion:** `UNIQUE (aircraft_id, data_source_id, observed_at)` makes re-imports safe; duplicates are *also* a detection signal (DET-006), so ingestion must record rather than silently drop them (Phase 2 design item).
- **Indexes:** `(aircraft_id, observed_at)` for history/trajectory, `(observed_at)` for time windows, GiST on `position` for bounding-box and proximity queries.
- **Scale path:** if volume demands it, partition `aircraft_observations` by `observed_at` (monthly). Not done now to avoid premature complexity.
- **Nullable by design:** every provider-optional measurement is NULL when absent.
- `audit_logs` is append-only by convention; DB-level enforcement (revoked UPDATE/DELETE for the app role) is a Phase 8 hardening item.

## Implemented in migration 0002/0003

- `aircraft` gains `manufacturer`, `model`, `operator`, `metadata_source_id` (provenance of descriptive metadata) and a prefix-search index on `registration`; `aircraft_observations` gains a prefix-search index on `callsign`.
- `detection_rules(id PK 'DET-00x', name, description, version, enabled, config JSONB)`.
- `anomalies(id, rule_id FK, rule_version, aircraft_id FK | airport_ident, detection_type, title, description, severity, confidence, data_quality, status, event_start/end, detected_at, dedup_key, source_refs JSONB, summary JSONB)` with CHECK constraints (severity/status/data_quality enums, confidence 0..1, exactly-one-subject) and `UNIQUE(rule_id, rule_version, dedup_key)`.
- `evidence(id, anomaly_id FK CASCADE, ordinal, kind, observation_id FK SET NULL, payload JSONB)`.

## Planned (added with the phase that needs them)

| Table | Phase | Notes |
|---|---|---|
| `flights` | 3 | Derived segments, with documented inference method |
| `investigations`, `investigation_notes` | 5 | Status OPEN/INVESTIGATING/FALSE_POSITIVE/RESOLVED; every change audited |
| `ai_analyses` | 6 | Provider, model, prompt version, validated output, labelled AI-generated |
| `threat_intelligence` | 7 | Source name/URL, publication date, retrieval time, excerpt, reliability limits |
| `intelligence_reports` | 7 | Structured sections, export metadata |
