# Implementation Plan

Repository state at start: empty (`LICENSE`, `.gitignore`). Greenfield.

| Phase | Scope | Gate to proceed |
|---|---|---|
| 1 Foundation | Backend skeleton, migrations 0001, frontend shell, compose, docs | Backend/frontend start, DB connects, migrations run, health works — **done** |
| 2 Ingestion (**done**) | `Provider` interface, OpenSky adapter (OAuth2, backoff, rate limits), public dataset importer, validation, persistence; **adds auth + rate limiting** | Real public observations in PostgreSQL |
| 3 Aircraft Intelligence (**done**) | Search, details, history, trajectory maths, MapLibre map, charts | Search an aircraft and inspect its real history |
| 4 Detection (**done**) | DET-001…008, registry, evidence, severity/confidence, persistence | Reproducible results on fixtures + documented historical data |
| 5 Security dashboard (**done**) | Anomaly Center, emergencies, investigations, notes, audit | Analyst can investigate an anomaly end to end |
| 6 AI (**done**) | `LLMProvider`, Ollama + OpenRouter, structured output validation | Same workflow works on either provider |
| 7 AI intel + reports (**done**) | Chat with allowlisted tools, threat-intel correlation, Markdown/PDF reports | Answers cite real records, separate fact from interpretation |
| 8 Hardening | Security review, coverage, SBOM, image scans, docs, screenshots | Documented clean-room setup works |

Phase 4 design input from real data: position timestamps jitter by up to ~1 s, so DET-001 must model timestamp uncertainty (see `data-sources.md`).

Open decision for Phase 2 (resolved: live API stays disabled by default): OpenSky API terms restrict operational/commercial use. Default plan is to develop against OpenSky's research datasets/historical files and keep live API access disabled (`data_sources.enabled=false`) until authorisation is confirmed.
