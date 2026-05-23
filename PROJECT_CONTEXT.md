# PROJECT_CONTEXT

## Purpose
OpenSignal ITS is a Python-first traffic controller management platform built with Reflex.

## Canonical Architecture
- models/: Pydantic data contracts.
- devices/: Device drivers implementing Device base class.
- protocols/: Shared SNMP/Telnet/HTTP helpers (planned, not yet implemented).
- services/: Polling, command orchestration, logging (planned, not yet implemented).
- components/: Reusable Reflex UI components.
- states/: Reflex state classes (planned migration from app module).
- db/: Persistence layer (planned, SQLite first).

## Current Reality (2026-05-23)
- Implemented now: models/, devices/, protocols/, services/, db/, tests/, and state orchestration in opensignal_its/states/traffic_state.py.
- Siemens M60 connectivity behavior: SNMP v1 succeeds on current controller target; SNMP v2c times out.
- SNMP command wiring exists (SET path implemented), but OIDs are provisional and must be validated against Siemens/NTCIP docs before production use.
- Operational command safety is implemented with operator authentication, write unlock windows, and per-command confirmation tokens.
- Command/snapshot persistence is implemented in SQLite with correlation IDs and startup retention enforcement.
- Device plugin base is now production-oriented (auto-registration, factory creation, plugin metadata, background polling hooks).
- Current bottleneck: state layer remains large and carries Siemens-specific parsing plus orchestration/UI coupling.
- Device registry is implemented but not yet leveraged by state/services for dynamic multi-device operation.

## Operational Rules
- Use allowlisted command names and documented OIDs only.
- Log every command attempt and result.
- Prefer async methods and typed interfaces.
- Keep UI thin; business logic should move into states/services.
- In production-like environments, enforce preflight-required secrets and fail startup on invalid runtime configuration.
- Maintain and follow docs/operations-runbook.md for operational procedures and environment requirements.

## Immediate Development Focus
1. Slim state by moving Siemens-specific parsing/formatting out of TrafficState.
2. Make PollingService/CommandService use Device.create(...) and registry lookup.
3. Introduce normalized device-status adapters so UI consumes one shape for any driver.
4. Add multi-device state model (device list + selected device + aggregate health).
5. Shift polling ownership to device instances and have state aggregate updates.
6. Add service-level tests for registry-driven polling/command dispatch and multi-device state transitions.

## Agent Handoff
- Planning/research agent updates AGENT_CONTEXT.json.
- Coding agent reads PROJECT_CONTEXT.md and AGENT_CONTEXT.json before edits.
- Human validates on hardware and decides merges.
