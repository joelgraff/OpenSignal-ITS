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

---

**Instructions for Copilot / AI Agents:**
Always read this file first. When adding new features, follow the modular device driver pattern. Ask for clarification if something conflicts with the architecture.