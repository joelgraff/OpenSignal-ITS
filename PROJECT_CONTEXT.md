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

## Operational Rules
- Use allowlisted command names and documented OIDs only.
- Log every command attempt and result.
- Prefer async methods and typed interfaces.
- Keep UI thin; business logic should move into states/services.
- In production-like environments, enforce preflight-required secrets and fail startup on invalid runtime configuration.
- Maintain and follow docs/operations-runbook.md for operational procedures and environment requirements.

## Immediate Development Focus
1. Stabilize state updates and dashboard telemetry.
2. Migrate state orchestration to opensignal_its/states/traffic_state.py.
3. Add shared SNMP protocol helper module.
4. Add command history + status snapshot persistence in opensignal_its/db/.
5. Add baseline tests for connect/poll/command flows.

## Agent Handoff
- Planning/research agent updates AGENT_CONTEXT.json.
- Coding agent reads PROJECT_CONTEXT.md and AGENT_CONTEXT.json before edits.
- Human validates on hardware and decides merges.
