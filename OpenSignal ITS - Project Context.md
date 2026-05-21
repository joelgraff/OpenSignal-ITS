# OpenSignal ITS - Project Context

## Project Purpose
Build a modern, lightweight, cross-platform **Traffic Controller Management Platform** inspired by Siemens TACTICS. 

Core goals:
- Real-time monitoring and control of traffic signal controllers (starting with Siemens M60 and Econolite).
- Support for video detection systems (Iteris, GridSmart, Autoscope, and others).
- Expandable to **any IP-addressable ITS device** (NTCIP, SNMP, HTTP APIs, RTSP streams, Telnet, etc.).
- Focus on robustness, modularity, and future extensibility without heavy legacy code.

Target users: Traffic engineers, DOTs, municipalities.

## Key Requirements
- **Platform independent** — Run natively on Ubuntu, Windows, macOS (no mandatory Docker).
- **No Java, prefer pure Python** stack.
- Lightweight and quick to deploy (`uv run reflex run` should work).
- Strong NTCIP 1202 support for controller timing, status, detectors, and commands.
- Real-time dashboards + historical logging.
- Video stream embedding with detector overlays.

## Architecture Principles (Follow These)
1. **Devices Layer** — Extensible driver system.
   - Abstract `Device` base class in `opensignal_its/devices/base.py`.
   - Concrete drivers (e.g. `SiemensM60`) in `devices/`.
   - Auto-registry + factory pattern.
   - Each device implements: `connect()`, `poll()`, `command()`, background polling.

2. **Layers** (Keep separation clear):
   - `models/` → Pydantic models (DeviceConfig, DeviceStatus, Events).
   - `protocols/` → Shared SNMP, Telnet, RTSP, HTTP helpers.
   - `devices/` → Device-specific logic.
   - `services/` → Polling scheduler, logging, alerting.
   - `components/` → Reusable Reflex UI pieces.
   - `states/` → Reflex State classes.
   - `db/` → SQLite (default) → PostgreSQL later.

3. **Tech Stack**
   - Reflex (pure Python full-stack) for UI + backend.
   - pysnmp for NTCIP/SNMP.
   - SQLAlchemy + SQLite for storage.
   - APScheduler / asyncio for background tasks.
   - Folium / Leaflet for maps, aiortc + RTSP for video.

4. **Extensibility Rules**
   - New device types should require minimal code (just inherit from `Device` and register).
   - Support both real-time polling and historical event logging (ATSPM-inspired).
   - IRIS-like device abstraction without the Java legacy.

## Current Status (as of your latest changes)
- Base Device + SiemensM60 driver implemented.
- Basic dashboard with status cards and timing control panel.
- Reflex app structure using `opensignal_its` module name.
- SNMP connectivity observed: v1 succeeds against current Siemens M60, v2c times out.
- Timing command path exists end-to-end (UI -> state -> device command -> SNMP SET), but command OIDs are still provisional and must be validated against Siemens documentation.

## Architecture Reality Check (Important)
- `devices/`, `models/`, and `components/` are active and usable.
- `protocols/`, `services/`, `db/`, and `tests/` are currently not implemented yet.
- Reflex state and orchestration currently live mostly in `opensignal_its.py`; migration to `states/` should be prioritized.

## Operational Safety Policy (Required)
- Treat all write commands as high-impact operations.
- Only allowlist known command names and validated OIDs.
- Require command logging (timestamp, target, parameters, result, error).
- Add user confirmation before high-risk actions (mode/pattern/state changes).
- Keep all command OIDs documented with source reference (MIB section/vendor doc).

## Near-Term Milestones
### M1 - State and UI Separation
- Move `TrafficState` from `opensignal_its.py` into `states/traffic_state.py`.
- Keep `opensignal_its.py` focused on page composition and routing.

### M2 - Protocol Layer
- Add `protocols/snmp_client.py` with shared async GET/SET helpers.
- Centralize retry/timeout/version fallback behavior.

### M3 - Service Layer and Polling
- Add `services/polling_service.py` for periodic refresh.
- Add `services/command_service.py` to validate and execute commands.

### M4 - Persistence and Audit
- Add SQLite models for command history and status snapshots.
- Persist every command and periodic status sample.

### M5 - Testing Baseline
- Add smoke tests for connect, poll, and command translation.
- Add regression tests for SNMP v1/v2c behavior and failure messaging.

## File-by-File Execution Checklist
- `opensignal_its/opensignal_its.py`: Reduce to app/page wiring and component assembly.
- `opensignal_its/states/traffic_state.py`: Main state actions (`connect`, `refresh`, `send_command`, UI state fields).
- `opensignal_its/protocols/snmp_client.py`: Shared SNMP primitives (get/set, target creation, error normalization).
- `opensignal_its/services/polling_service.py`: Realtime polling cadence and task lifecycle.
- `opensignal_its/services/command_service.py`: Allowlisted command schema and dispatch.
- `opensignal_its/db/`: Status/command persistence models and repository helpers.
- `opensignal_its/tests/`: Unit and smoke tests for state, device, and protocol paths.

## Coding Guidelines
- Use type hints everywhere.
- Prefer async where possible.
- Keep UI components reusable and clean.
- Safety-first on controller commands (log everything, add confirmations later).
- Document OIDs and vendor specifics clearly.

## Helpful References
- NTCIP 1202 standard (MIB objects for phases, patterns, detectors).
- Siemens M60 SNMP/Telnet documentation (you have access).
- Reflex docs for State, components, and dynamic UI.

## Canonical Agent Context Files
- `PROJECT_CONTEXT.md` is the concise execution source of truth.
- `AGENT_CONTEXT.json` is the machine-readable handoff contract between planning and coding agents.
- Update both files whenever runtime behavior, architecture status, or priorities materially change.

---

**Instructions for Copilot / AI Agents:**
Always read this file first. When adding new features, follow the modular device driver pattern. Ask for clarification if something conflicts with the architecture.

**Required startup read order for coding sessions:**
1. `PROJECT_CONTEXT.md`
2. `AGENT_CONTEXT.json`
3. This file (`OpenSignal ITS - Project Context.md`) for extended architecture rationale.