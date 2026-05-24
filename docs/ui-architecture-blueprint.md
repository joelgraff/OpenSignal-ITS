# OpenSignal ITS UI Architecture Blueprint

This blueprint defines a scalable UI shell for current dashboard workflows and future multi-application growth.

## Goals

1. Keep operator-critical workflows fast and obvious.
2. Support growth into multiple applications/modules without page rewrites.
3. Isolate high-risk actions in explicit guarded zones.
4. Standardize layout and interaction patterns across modules.

## Target Shell Model

### Global App Shell

1. Header rail:
- Core status badges (online/offline, write mode, role, active alarm count, selected device).
- Quick refresh actions.

2. Primary navigation (mode-based):
- Monitor
- Control
- Operations
- Analytics
- Configuration

3. Workspace body:
- Main module canvas
- Optional context side panel (selection detail, notices, quick actions)

4. Global notice stack:
- Prioritized notices (error > warning > info)
- Consistent placement and dismiss behavior

## Module Map

### Monitor

Purpose: read-only situational awareness.

Contains:
1. Device health and summary metrics.
2. Fleet status list and runtime registry view.
3. Ring/phase timer consoles.

### Control

Purpose: intentional command workflows.

Contains:
1. Command safety state.
2. Write confirmation flow.
3. Timing plan controls/actions.

### Operations

Purpose: maintenance and administrative tasks.

Contains:
1. Runtime health/retention controls.
2. Audit export controls.
3. Lockout recovery/admin maintenance actions.

### Analytics

Purpose: incident triage and historical analysis.

Contains:
1. Active alarms panel.
2. Alarm action/history panel.
3. Event timeline feed.

### Configuration

Purpose: setup and advanced editing.

Contains:
1. Connection/polling defaults.
2. Fleet profile management.
3. Advanced JSON editors and import/export.

## Information Architecture Rules

1. One section, one primary purpose.
2. Dangerous actions are never mixed with routine monitoring controls.
3. Selection context (device, alarm) remains visible in any module where actions depend on it.
4. Advanced/raw editors are collapsed by default.

## Shared UI Patterns

1. Panel header:
- Title
- One-line purpose text
- Optional actions (right-aligned)

2. Action bars:
- Grouped by workflow step.
- Minimal button set; secondary actions moved into overflow or advanced sections.

3. Lists/feeds:
- Scrollable fixed-height regions.
- Severity/color semantics consistent across modules.

4. Notices:
- Error (red), Warning (amber), Info (gray/blue).
- No inline duplicate notices for the same event.

## State and Service Boundaries

1. UI shell state:
- Current workspace mode
- Current selection context (device_id, alarm_key)

2. Module adapter functions:
- Map service DTOs into module-ready UI field payloads.
- Keep testable outside Reflex state instantiation.

3. Service contracts:
- Continue typed DTO usage (FleetRefreshView, RuntimeRegistryView, etc.).
- Add DTOs for alarms/operations module mapping where practical.

## Migration Plan

### Phase 1: Shell Scaffold (non-breaking)

1. Add workspace mode selector to dashboard shell.
2. Add explicit module section containers.
3. Keep existing actions wired; move presentation only.

Exit criteria:
- App compiles.
- Existing tests pass.
- No backend behavior changes.

### Phase 2: Module Extraction

1. Move Monitor/Control/Operations/Analytics into dedicated component builders.
2. Keep shared layout primitives for panel headers and action bars.
3. Reduce page-file complexity by moving section markup into component files.

Exit criteria:
- Full regression green.
- Reduced dashboard file complexity and duplication.

### Phase 3: UX Polish and Density Pass

1. Improve visual hierarchy and spacing scale.
2. Normalize typography and color semantics.
3. Tune compact-width behavior for laptop-first layouts.

Exit criteria:
- Operator top tasks require fewer context switches.
- Compact layout remains usable without horizontal overflow.

## Acceptance Metrics

1. Time-to-action for top operator tasks (connect/poll, triage alarm, execute command, run maintenance).
2. Number of visible controls above the fold in each module.
3. Error rate on high-risk actions after layout changes.
4. Regression status and test coverage changes.

## Immediate Next Pass Scope

1. Implement shell mode selector and module containers.
2. Move fleet JSON editor into Configuration/Advanced area.
3. Finish triage-oriented Analytics panel cleanup with clearer action sequencing.
