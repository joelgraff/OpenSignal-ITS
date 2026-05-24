# UI Release Notes Draft

## Scope

This draft covers user-visible dashboard changes introduced during the page-architecture and UX cleanup sprint.

## Highlights

- Replaced the long single-page scroll layout with page-style workspace navigation.
- Added tabbed workspace navigation: Monitor, Control, Operations, Analytics, Settings, Admin.
- Moved login and recovery controls to the Admin page so operational pages are not gated by auth UI.
- Enforced login-first access: without sign-in, only access/recovery controls are shown.
- Updated labels to traffic-signal language (for example: Sites and Status, Signal Control, System Maintenance, Active Site Sessions).
- Improved compact-screen behavior with responsive card/grid layouts.
- Refined wording for page subtitles, panel helper text, and key action labels.

## Workspace Changes

### Monitor

- Live status and polling controls are grouped into a dedicated monitor page.
- Runtime/session and site status panels now remain in a focused monitoring workflow.

### Control

- Write-mode safety controls and pending command confirmation are isolated on the Control page.
- Ring timer text view is colocated with command controls for rapid operator context.

### Operations

- Runtime health and maintenance actions are grouped into clear section cards.
- Warning and critical storage states are visually separated for faster triage.

### Analytics

- Events and alarm triage are grouped into three focused sections:
  - Active Alarms
  - Alarm History
  - Timeline Feed
- Action labels are clearer and more consistent for operator workflows.

### Settings

- Fleet profile configuration and selected device context are consolidated.

### Admin

- Operator sign-in/out and lockout recovery are isolated from routine operations.
- Sign-in is now required before operational pages become accessible.

## UX Consistency Updates

- Introduced shared workspace page framing for consistent title/subtitle layout.
- Introduced shared section-card composition for repeated panel patterns.
- Normalized action wording (for example: Refresh Health, Refresh Timeline).

## Validation Snapshot

- Python compile checks passed for app and workspace modules.
- Full regression suite passed: 91 tests.
- Manual runtime walkthrough validated tab navigation and page rendering on localhost.

## Known Follow-ups

- Add a map-first site selection workflow once real equipment topology/coordinates are available.
- Connect site selection to co-located ITS asset views (cameras, detectors, cabinets, comms) for each signal location.
