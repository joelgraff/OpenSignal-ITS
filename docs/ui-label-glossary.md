# OpenSignal ITS UI Label Glossary

This glossary defines user-facing labels in the web UI using traffic-signal operations language.

## Final Label Decisions (Authoritative)

Use these labels as the canonical set for current UI and documentation.

| Area | Final Label |
|---|---|
| Monitor tab | Overview |
| Control tab | Signal Control |
| Operations tab | Maintenance |
| Analytics tab | Alarms & Events |
| Configuration tab | Controllers |
| Admin tab | Access |
| Monitor page title | Network Overview |
| Monitor detail title | Intersection Detail |
| Configuration page title | Controllers |
| Access page title | Access |
| Selected target field | Selected Controller |
| Inventory summary | Controllers total / online / offline |

## Grok Recommendation Disposition

| Grok Suggestion | Decision | Notes |
|---|---|---|
| Use Controllers instead of Site/Fleet terminology | Adopted | Implemented across tabs, page titles, and notices. |
| Keep Alarms visible and operator-focused | Adopted | Alarms & Events remains a primary tab. |
| Intersection Detail page as primary screen | Partially adopted | Overview remains the landing workspace; selecting a controller opens an Intersection Detail view within the same workflow. |
| Dashboard map as first screen | Partially adopted | The Overview landing workspace now includes a map-style controller panel that can be upgraded later to full GIS mapping. |
| Cabinet equipment section (video, battery, power) | Deferred | Requires new data model/integrations. |
| Raw Data and Advanced separation | Deferred | Planned for future UX simplification phase. |
| Replace write-mode wording with Unlock Controls | Deferred | Current safety model preserved to avoid operational ambiguity during hardening. |

## Label Renames (Legacy -> Current)

- Events -> Alarms & Events
- Configuration -> Controllers
- Access -> Access
- Analytics (page title) -> Alarms & Events
- Settings (page title) -> Controllers
- Fleet Profiles -> Controller Profiles
- Refresh Fleet -> Refresh Controllers
- Selected device_id (optional) -> Selected controller ID (optional)
- Refresh Runtime Registry -> Refresh Active Poll Sessions
- Selected: -> Selected Controller:
- Fleet N total -> Controllers N total

## Top Bar

- OpenSignal ITS Controller Console:
Main application header for traffic operations.
- ONLINE / OFFLINE:
Whether the selected signal controller is currently reachable.
- PROBE MODE:
Safety mode where write actions are blocked; operator can observe status only.
- WRITE MODE:
Control mode where write actions are allowed after unlock and confirmation.
- WRITE UNLOCKED / WRITE LOCKED:
Whether the temporary write-control window is active.
- ROLE <value>:
Current permission role for the active session (viewer/operator/admin).
- ALARMS <count>:
Count of currently active alarms.
- Selected Controller:
Current controller target selected in the UI.
- Updated:
Timestamp of the most recent status refresh.
- Pattern / Unit / SNMP / Controllers:
Compact summary of active pattern, unit state, protocol mode, and inventory totals.

## Workspace Tabs

- Overview:
Choose target controllers, review fleet-level status, and open intersection detail.
- Signal Control:
Perform command operations with safety guardrails.
- Maintenance:
Inspect runtime health and run maintenance actions.
- Alarms & Events:
Review event timeline and alarm lifecycle actions.
- Controllers:
Manage configured controller profile records.
- Access:
Sign in, sign out, and run admin lockout recovery actions.

## Overview Workspace

- Network Overview:
Landing page for fleet summary, controller map, and controller list.
- Intersection Detail:
Drill-in page for one selected controller, including live phase state and command-adjacent diagnostics.
- Controller Connection & Polling:
Connection and polling controls for selected controller targets.
- Controller IP:
IP address of a traffic signal controller.
- Port:
Controller SNMP port, typically 161.
- Community:
SNMP community string for v1/v2c access.
- Timeout sec:
Request timeout in seconds.
- Retries:
Number of retries before poll failure.
- Auto Refresh:
Enable/disable periodic status refresh.
- Auto Reconnect:
Enable/disable automatic reconnect when communication drops.
- Selected controller ID (optional):
Optional controller identifier to scope actions.
- Selected Controller:
Current polling/action target summary card.
- Refresh Controllers:
Reload configured controller inventory and current status rows.
- Poll interval sec:
Managed polling interval in seconds.
- Start Managed Polling / Stop Managed Polling:
Start/stop managed polling for the selected controller scope.
- Start All Controllers Polling / Stop All Controllers Polling:
Start/stop polling across configured controller set.
- Refresh Active Poll Sessions:
Reload list of active worker sessions and polling loops.
- Active Controller Sessions:
Active polling workers grouped by controller.
- Controller List:
Rows for currently configured/loaded controller entries.
- SEPAC Ring Timer Text View:
Controller-style textual output for ring/timer state.

## Signal Control Workspace

- Signal Command Console:
Primary command panel for signal control actions.
- Command Safety:
Controls that gate write actions.
- Operator key:
Operator-provided unlock key for write mode.
- Unlock sec:
Requested duration for temporary write authorization.
- Unlock Write Mode / Lock Write Mode:
Open/close write-command permission window.
- Write Confirmation:
Second-step confirmation for protected commands.
- Confirmation token:
Short-lived token required to execute pending protected action.
- Confirm Pending Command:
Applies pending action if token is valid and not expired.

## Maintenance Workspace

- System Maintenance:
Maintenance page shell for runtime health and housekeeping.
- Maintenance Operations:
Operational maintenance controls and outputs.
- System Health:
Runtime, storage, and alert-dispatch health snapshot.
- Refresh Health:
Recompute runtime/storage/dispatch health status.
- Warnings:
Non-critical issues that need operator attention.
- Critical:
Persistent/high-severity issues requiring immediate follow-up.
- Maintenance Actions:
Operator/admin actions for scheduled cleanup and reports.
- Run Retention Cleanup:
Execute data-retention cleanup immediately.
- Export Audit Report:
Generate operational audit/export artifact.

## Alarms & Events Workspace

- Events & Alarms:
Alarm/event triage workspace body title.
- Refresh Timeline:
Reload alarm and event timeline data.
- 15m / 1h / 24h / All:
Time-window shortcuts for timeline and alarm views.
- Active Alarms:
Current alarms with ack/silence controls.
- Selected alarm key:
Target alarm identifier for action commands.
- Alarm note (optional):
Free-text note attached to an alarm action.
- Silence minutes:
Duration for temporary alarm silence.
- Use Policy:
Apply configured silence policy to selected alarm.
- Ack / Clear Ack:
Set/remove alarm acknowledgement state.
- Silence / Clear Silence:
Set/remove alarm silence state.
- Alarm History:
Historical alarm action log with filters.
- Actor contains:
Filter history rows by operator/system actor text.
- Alarm key contains:
Filter history rows by alarm key substring.
- Row limit (5-200):
Maximum history rows returned.
- Timeline Feed:
Chronological event stream.

## Controllers Workspace

- Controllers:
Configuration workspace for controller records.
- Controller Profiles:
Editable JSON profile list for managed controller inventory.
- Selected controller ID (optional):
Optional controller target used by refresh and status views.
- Refresh Controllers:
Reloads configured controller rows into runtime state.
- Controller-profile JSON editor:
Advanced editor for profile JSON payloads.

## Access Workspace

- Operator Sign-In:
Session sign-in form for operator/admin credentials.
- Operator sign-in name:
Username field used for session authentication.
- Operator sign-in password:
Password field used for session authentication.
- Sign In / Sign Out:
Start/end authenticated operator session.
- Admin Recovery:
Lockout recovery controls.
- Admin recovery key phrase:
Admin recovery key input for lockout reset operations.
- Reset Login Lockout:
Clears temporary lockout state after repeated failed sign-in attempts.

## Proposed V2 Terminology (Optional, Not Yet Implemented)

This section captures suggested future-facing labels from workflow planning.
These are recommendations for UI redesign and do not override current implemented labels.

### Global / Dashboard Labels

| Proposed Label | Purpose | Current / Technical Equivalent | Recommendation |
|---|---|---|---|
| Dashboard | Main overview page with map and summary | N/A | Keep prominent |
| Controllers | List of all signal controllers | Signal Sites, Site Inventory | Main navigation |
| Total Intersections | Total number of controllers | Signal Sites total | Summary card |
| Online | Number of controllers currently responding | Online count | Summary card |
| In Alarm | Number of controllers with active alarms | Alarms count | Summary card |
| Last Updated | Timestamp of last successful poll | Updated | Keep visible |

### Intersection Detail Page (Primary Working Screen)

| Proposed Label | Purpose | Current / Technical Equivalent | Recommendation |
|---|---|---|---|
| Intersection Detail | Main page title for a single intersection | Selected Signal Site | Header |
| Current Pattern | Active timing pattern number | Pattern | Keep prominent |
| Status | Overall controller health | ONLINE / OFFLINE | Keep prominent |
| Live Phase Status | Real-time phase diagram and indications | Phase status fields | High visibility |
| Active Calls | Vehicle and pedestrian calls | Vehicle calls, Ped calls | Keep |
| Time Remaining | Seconds until phase change | Remaining time fields | Keep |
| Cabinet Equipment | Devices in cabinet | N/A | New section |
| Video Detection | Status of video detection systems | Vendor-specific statuses | New |
| Battery Backup | Battery backup status | N/A | New |
| Power Supply | Cabinet power status | N/A | New |
| Alarms | Active alarms for this intersection | Alarms & Events | Keep |

### Control Section

| Proposed Label | Purpose | Current / Technical Equivalent | Recommendation |
|---|---|---|---|
| Change Pattern | Select a different timing plan | Select Pattern | Keep |
| Mode | Free / Coordinated / Manual | Unit control status | Simplify |
| Manual Control | Hold, Advance, and related actions | Manual hold / Advance phase | Keep with safety dialog |
| Unlock Controls | Enable control actions with confirmation | Write mode / Operator key | Cleaner replacement |

### Management and Advanced Sections

| Proposed Label | Purpose | Current / Technical Equivalent | Recommendation |
|---|---|---|---|
| Controllers | Add, edit, remove controllers | Site Inventory | Keep |
| Metadata | Phase mapping and notes | N/A | New |
| Logs | Event and polling history | Events / Alarm history | Keep |
| Raw Data | Advanced troubleshooting values | Raw SNMP values, low-level diagnostics | Separate tab |
| Settings | Controller configuration | Site Inventory / future settings | Future use |

### Developer Notes

- Goal: prioritize technician-friendly language over software-centric jargon.
- Advanced technical fields should be hidden by default or moved to an Advanced or Raw Data area.
- Keep naming consistent across tabs, cards, filters, and actions (for example, Controllers vs Signal Sites).
