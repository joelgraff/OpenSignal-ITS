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

## Current Reality (2026-05-21)
- Implemented now: models/, devices/, components/, single-state orchestration in opensignal_its.py.
- Not implemented yet: protocols/, services/, db/, tests/.
- Siemens M60 connectivity behavior: SNMP v1 succeeds on current controller target; SNMP v2c times out.
- SNMP command wiring exists (SET path implemented), but OIDs are provisional and must be validated against Siemens/NTCIP docs before production use.

## Operational Rules
- Use allowlisted command names and documented OIDs only.
- Log every command attempt and result.
- Prefer async methods and typed interfaces.
- Keep UI thin; business logic should move into states/services.

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
