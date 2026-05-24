# OpenSignal ITS UI Label Glossary

This glossary defines user-facing labels in the web UI using traffic-signal operations language.

## Label Renames (Legacy -> Current)

- Events -> Alarms & Events
- Configuration -> Site Inventory
- Access -> Sign-In & Roles
- Analytics (page title) -> Alarms & Events
- Settings (page title) -> Site Inventory
- Fleet Profiles -> Signal Site Profiles
- Refresh Fleet -> Refresh Site Inventory
- Selected device_id (optional) -> Selected site ID (optional)
- Refresh Runtime Registry -> Refresh Active Poll Sessions
- Selected: -> Selected Site:
- Fleet N total -> Signal Sites N total

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
- Selected Site:
Current site/controller target selected in the UI.
- Updated:
Timestamp of the most recent status refresh.
- Pattern / Unit / SNMP / Signal Sites:
Compact summary of active pattern, unit state, protocol mode, and inventory totals.

## Workspace Tabs

- Sites & Status:
Choose target sites, configure connection/polling, and inspect live status.
- Signal Control:
Perform command operations with safety guardrails.
- Maintenance:
Inspect runtime health and run maintenance actions.
- Alarms & Events:
Review event timeline and alarm lifecycle actions.
- Site Inventory:
Manage configured site/controller profile records.
- Sign-In & Roles:
Sign in, sign out, and run admin lockout recovery actions.

## Sites & Status Workspace

- Site Connection & Polling:
Connection and polling controls for selected site/controller targets.
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
- Selected site ID (optional):
Optional site/controller identifier to scope actions.
- Selected Signal Site:
Current polling/action target summary card.
- Refresh Signal Sites:
Reload configured site inventory and current status rows.
- Poll interval sec:
Managed polling interval in seconds.
- Start Managed Polling / Stop Managed Polling:
Start/stop managed polling for the selected site scope.
- Start Site Polling / Stop Site Polling:
Start/stop polling across configured site set.
- Refresh Active Poll Sessions:
Reload list of active worker sessions and polling loops.
- Active Site Sessions:
Active polling workers grouped by site.
- Signal Site List:
Rows for currently configured/loaded site entries.
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

## Site Inventory Workspace

- Site Inventory:
Configuration workspace for site/controller records.
- Signal Site Profiles:
Editable JSON profile list for managed site inventory.
- Selected site ID (optional):
Optional site target used by refresh and status views.
- Refresh Site Inventory:
Reloads configured inventory rows into runtime state.
- Site-inventory JSON editor:
Advanced editor for profile JSON payloads.

## Sign-In & Roles Workspace

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
