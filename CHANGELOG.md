# Changelog

All notable changes to this project are documented here, organized by sprint.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [MVP academic closeout] — 2026-11-24

### Documentation
- Updated the README to describe the completed academic MVP, RAMI 4.0 design approach, current functionality, optional AI, analytical contracts and industrial limitations.
- Consolidated the agreed EXP-01–07 outcome, including adverse results and the unclocked scope of EXP-07; published selected report metrics with source hashes.
- Documented the 16-instrument pilot separately from the four-case demo, environment isolation and explicit snapshot refresh.
- Excluded the local rehearsal Compose override from version control. No application logic, database migration or data reset is part of this update.

The entries below are historical checkpoints, not the current delivery status.

## [Foundation] — Sprint 0

### Added
- Repository foundation structure (backend, frontend, ai, docs, infra, scripts, .github).
- `docker-compose.yml` skeleton (PostgreSQL/TimescaleDB, backend, frontend).
- Draft PostgreSQL schema (`infra/postgres/schema.sql`).
- Definition of Done, Contributing guide, Issue/PR templates.

<!-- Add a new "## [Sprint N]" section at the end of each sprint. -->

