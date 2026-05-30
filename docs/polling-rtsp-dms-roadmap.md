## Plan: Polling Efficiency and Device Expansion

TL;DR: The codebase already has a solid device registry, a working Siemens M60 SNMP driver, and a clean state/service split. The next useful pass is to remove duplicated state orchestration, reduce SNMP request volume and retry noise, and then add capability-driven paths for RTSP video and schema-based NTCIP commands so dynamic message signs can be added without overloading the controller polling path.

Current state: Phase 0 is complete, Phase 1 is complete, Phase 2 is complete for the current polling scope, Phase 3 is complete for the current media-health scope, and Phase 4 is complete for the current command-schema foundation scope. Phase 5 is complete for the current validation scope.

Phase 4 exit criteria are now satisfied: commands advertise a schema and capability contract, and a first DMS-style command is validated before execution through the Skyline DMS emulator path.

Current Phase 5 status: the Skyline DMS post-command verification target, one representative traffic-signal acknowledgment or timeout validation target, and RTSP simulator or sample-stream verification are complete.

Post-Phase-5 bounded slice status: the RTSP protocol layer now has deterministic local DESCRIBE-response simulator coverage, including malformed-response and explicit non-2xx response handling, without adding playback, transcoding, or UI work.
Post-Phase-5 bounded slice follow-up status: `MediaService` now exposes one additive service-level DESCRIBE consumer path with sanitized success and explicit non-2xx outcome metadata while leaving the default reachability path unchanged.
RTSP current-scope end point: the selected-controller Video Feeds refresh path now consumes the bounded DESCRIBE service seam, so the current RTSP scope ends with one real caller using protocol-level outcomes through the existing monitor surface, without widening the default health path or adding playback work.
Selected detail live polling feedback status: intersection detail now surfaces selected-controller live polling failures with a prominent banner and a failure-aware Live Phase Diagram empty state, and live-refresh notices now distinguish successful updates from offline, timeout, and backoff snapshots.
Field SNMP compatibility finding: the current Siemens M60 field reference responds on SNMPv1 only, while the tested M50 target did not answer basic SNMPv1 or SNMPv2c probes, so M50 troubleshooting should precede any device-specific OID work.

## Current Execution Board

Use this as the active whole-roadmap board and update status markers when a phase milestone lands.

Status markers: `[ ]` not started, `[~]` in progress, `[x]` complete.

### Foundations Landed

- [x] Phase 0 baseline telemetry and polling analysis
- [x] Phase 1 state and service deduplication for selected-controller and profile flows
- [x] Phase 2 polling efficiency and reliability work for batching, coalescing, and offline backoff
- [x] Phase 3 RTSP/media health foundation and selected-controller media status exposure

### Active Command Track

- [x] Phase 4a bounded traffic-signal command catalog centralization
- [x] Phase 4b vendor-agnostic command capability exposure through the existing device seam
- [x] Phase 4c JSON-safe value-type and option-hint metadata for the current traffic-signal commands
- [x] Phase 4d let the existing control-panel path consume capability hints for labels or visibility without replacing the wrapper-based command handlers
- [x] Phase 4e add acknowledgment and multi-step command lifecycle support
- [x] Phase 4f land the first DMS-targeted schema and driver path behind a vendor-agnostic device-family boundary

### RTSP End Point

- [x] Wire one explicit caller, the selected-controller Video Feeds refresh path, to the bounded DESCRIBE service seam without changing the default conservative `MediaService.check_stream_health(...)` path
- [x] Keep RTSP scope bounded to validated stream config, credential-safe status shaping, conservative TCP reachability, DESCRIBE protocol outcomes, and selected-controller status exposure
- [x] Stop RTSP expansion here for the current roadmap scope and treat further RTSP work as a new roadmap decision instead of an automatic next slice

### Next Board Action

- [ ] Align controller-profile defaults and quick-create guidance with known field SNMP compatibility so Siemens M60 profiles default to SNMPv1 while other device types keep current behavior

### Validation Track

- [x] Focused request-count and regression coverage for the shipped polling optimization work
- [x] Fast Reflex compile gate for state and component refactors
- [x] Extend validation to cover RTSP simulator or sample-stream verification
- [x] Add DMS-style command-schema and acknowledgment validation
- [x] Add representative traffic-signal acknowledgment or timeout validation

### Current Operating Snapshot

- Baseline report: `docs/polling-rtsp-dms-phase0-baseline.md`
- Warm traffic-signal polls currently resolve to 44 OID objects and 5 SNMP round trips in the Siemens M60 driver path.
- Warm end-to-end snapshots currently resolve to 46 OID objects and 6 SNMP round trips through `PollingService.collect_snapshot`.
- Overlapping same-key snapshot requests are coalesced to one underlying connect/poll cycle.
- Repeated offline controllers back off and return stale/backoff metadata instead of immediately starting more SNMP work.

### Field SNMP Compatibility Note

- The current Siemens M60 reference controller responds on SNMPv1 only for standard `sysDescr`, M60/SEPAC `currentPattern` and `unitControlStatus`, and representative NTCIP phase-status group objects; SNMPv2c is silent for the same target. Profiles for this surface should use `snmp_version="v1"`.
- The tested Siemens M50 target did not respond to bounded SNMPv1 or SNMPv2c probes for standard `sysDescr`, M60/SEPAC objects, or representative NTCIP objects. Treat that result as SNMP reachability, controller-agent enablement, community, modem/NAT, firewall, or UDP/161 troubleshooting before building an M50-specific OID profile.
- After the M50 answers a basic SNMP object, rerun the compatibility probe to determine whether it exposes standard NTCIP 1202 status, a SEPAC-compatible private surface, or a separate M50-specific object map.

## Steps

1. Phase 0 - Establish the baseline.
   - Trace the current request path through Device.start_polling, PollingService.collect_snapshot, FleetStateMixin.refresh_fleet_status, and SiemensM60.poll.
   - Record the current shape of a single poll cycle: number of GETs, identity OIDs versus live phase OIDs, average cycle time, and how often UI-driven refreshes can overlap background polling.
   - Identify which OIDs are stable enough to cache or move out of every poll cycle so the measurement feeds directly into the optimization target.
   - Use that baseline to decide whether a given optimization should reduce traffic, reduce latency, or improve failure recovery.

2. Phase 1 - Remove unnecessary duplication in state and service layers.
   - Consolidate repeated profile loading, selection, and refresh sync logic across configuration, fleet, monitor, polling, and command slices.
   - Keep FleetService as the normalization boundary for controller profiles so the state slices stop reparsing the same JSON in parallel ways.
   - Share the logic for applying a selected controller snapshot to UI state so map markers, fleet cards, and selected-controller detail all come from one path.
   - Audit compatibility wrappers and thin pass-through helpers so the cleanup removes code that no longer has a real caller, not just code that looks repetitive.
   - Name the consolidation point explicitly: a shared workflow helper or coordinator should own profile load, state refresh, and runtime sync so the plan has a concrete dedup target.
   - Keep runtime-registry synchronization centralized so profile edits, deletes, and reloads cannot drift apart.

3. Phase 2 - Cut SNMP request volume and improve polling reliability.
   - Add per-device request coalescing or in-flight locking in DeviceRuntimeService or PollingService so concurrent refreshes cannot trigger duplicate SNMP calls for the same controller.
   - Extend SNMPClient with a read-batching helper and refactor SiemensM60.poll to fetch grouped OIDs together instead of many single GETs per phase.
   - Separate slow-changing controller identity data from fast-changing live status data so stable fields can be cached longer than ring or phase state.
   - Add backoff after repeated failures and expose stale-state handling in the UI so offline controllers stop being hammered while still showing the last known good status.
   - Define whether backoff lives in Device.start_polling, PollingService, or SiemensM60 so the retry policy is unambiguous before implementation.
   - Align the background poll loop and the managed polling path around one cadence policy so there is one authoritative place for sleep, retry, and recovery behavior.
   - Consider adaptive polling intervals by controller health or change rate only after the basic dedupe and backoff behavior is proven.

4. Phase 3 - Add RTSP and video support as a separate capability.
   - Treat RTSP as a new device family, not as a branch inside the SNMP controller driver.
   - Add a media-oriented device or protocol layer that can validate stream reachability and expose stream health metadata.
   - Decide whether RTSP belongs in a separate protocol handler, a separate device type, or both, and keep its health checks off the controller poll loop by running them in an independent task or service boundary.
   - Use DeviceConfig.protocol and Device.get_capabilities() to advertise whether a profile supports video controls.
   - Deliver video to the browser through a relay or transcode path rather than trying to consume raw RTSP directly in the UI.
   - Keep frame processing and detection cadence independent from controller polling so media load cannot slow SNMP updates.
   - Replace the current Video Feeds placeholder in monitor.py only after the media path exists and the UI can actually show stream status or playback.

5. Phase 4 - Generalize NTCIP command support for controllers and dynamic message signs.
   - Move command validation into a schema and capability layer so commands know their parameters, confirmation rules, and writable state before execution.
   - Keep SiemensM60.command as one traffic-signal implementation of the broader command framework rather than the framework itself.
   - Model Phase 4 around vendor-agnostic NTCIP device families and capability contracts first, then map Skyline, Daktronics, and other DMS vendors onto that contract instead of treating any traffic-signal controller as the default.
   - Add multi-step command support for unlock, apply, confirm, and rollback flows because DMS devices will need transaction-like behavior.
   - Introduce a dedicated DMS driver boundary and keep its object definitions or vendor profile separate from the signal-controller OIDs.
   - Choose the first DMS vendor or emulator and whether the schema should live in Pydantic models, driver capability metadata, or both before implementation starts.
   - Add post-command acknowledgment polling so the UI can distinguish sent, accepted, and confirmed states.
   - Extend the command tests to cover schema validation and at least one confirm or timeout path for a representative controller target.

6. Phase 5 - Validate each increment with measurable checks.
   - Add request-count assertions for Siemens M60 polling so the SNMP reduction is visible in tests.
   - Add focused unit coverage for request coalescing, backoff, stale-state handling, and runtime-registry pruning.
   - Keep python -m reflex compile --dry --no-rich as the fast compile gate after any state or component refactor.
   - Add a mock RTSP server or DESCRIBE and SETUP simulator before wiring any playback UI.
   - Add one command-schema test for a DMS-style target and one acknowledgment test for a controller target.

## Relevant files

- opensignal_its/devices/base.py - shared device abstraction, polling loop, and registry entry point.
- opensignal_its/devices/siemens_m60.py - current SNMP polling and NTCIP command implementation that needs request reduction and clearer command boundaries.
- opensignal_its/protocols/snmp.py - low-level SNMP transport wrapper where batching, retries, and backoff belong.
- opensignal_its/services/polling_service.py - polling orchestration, runtime registry sync, and the right place to centralize polling policy.
- opensignal_its/services/device_runtime_service.py - long-lived device registry, where duplicate in-flight requests and stale entries should be managed.
- opensignal_its/services/command_service.py - command execution path that should evolve toward schema-driven validation.
- opensignal_its/states/configuration_state.py - profile persistence and controller selection state, which still contains repeated refresh orchestration.
- opensignal_its/states/fleet_state.py - fleet refresh loop and snapshot application.
- opensignal_its/states/monitor_state.py - selected-controller detail flow and placeholder detail tabs.
- opensignal_its/states/command_state.py - command UI flow and command safety hooks.
- opensignal_its/models/device.py - device protocol field and status model that can be extended for video and future device families.
- opensignal_its/components/workspaces/monitor.py - current Video Feeds placeholder and controller detail presentation.
- opensignal_its/tests/test_registry_services.py - polling and registry tests that can be extended for coalescing and stale-entry pruning.
- opensignal_its/tests/test_traffic_state_adapters.py - state adapter coverage for page-load sync and command or poll orchestration.
- docs/NTCIP_1202_KEY_OBJECTS.json - existing NTCIP controller reference to reuse for command and object modeling.

## Verification

1. Run the focused unit suites for touched state and service slices after each phase.
2. Run python -m reflex compile --dry --no-rich after any state or component refactor.
3. Add request-count or call-count assertions for Siemens M60 polling so the SNMP reduction is measurable.
4. Use a sample RTSP stream or a mocked RTSP server to verify the video driver boundary before adding UI playback.
5. Validate DMS command behavior with a simulator or mocked device so schema validation and acknowledgment handling are covered.

## Decisions

- Keep the Siemens M60 path as the current traffic-signal reference implementation only; do not treat it as the default controller model for other signal-controller vendors, DMS, video detection, or other ITS hardware domains.
- Model new ITS hardware by vendor-agnostic NTCIP device family and capability contract first, then map vendor-specific implementations behind that boundary, including multiple traffic-signal vendors such as Yunex/Siemens and Econolite.
- Separate video streaming and detection from SNMP polling cadence; do not run frame decode inside the controller poll loop.
- Treat DMS as a distinct NTCIP device family with schema-driven commands and explicit confirmation rules.
- Optimize request volume and retry behavior before expanding the amount of data each poll collects.
- Scope excluded for now: full video analytics training, a broad UI redesign, and vendor-specific DMS support beyond the first target driver.

## Recommended Execution Order

1. Phase 0 and Phase 2 together first: establish a poll baseline, then cut request volume, coalesce duplicate polls, and add backoff or stale handling. This gives the fastest operator impact and the clearest measurement.
2. Phase 1 next: remove duplicated state and service orchestration so the polling and selection paths have one shared flow.
3. Phase 3 after polling is stable: add RTSP as a separate capability with only stream-health plumbing first.
4. Phase 4 last: add schema-driven NTCIP command support and then DMS, since that work depends on the command framework being less ad hoc.

## Phase Exit Criteria

- Phase 1 is done when profile load, selection, map refresh, and runtime-registry sync use one shared path and the duplicated wrapper logic is gone.
- Phase 2 is done when a measured poll cycle uses fewer SNMP requests, concurrent refreshes do not duplicate work, and repeated failures back off instead of hammering the controller.
- Phase 3 is done when an RTSP device can report stream reachability and health without affecting controller polling cadence.
- Phase 4 is done when commands advertise a schema or capability contract and at least one DMS-style command can be validated before execution.

## Further Considerations

1. If you want the most value first, start with SNMP efficiency and polling reliability before any RTSP or DMS work.
2. For video, the first milestone should be stream health and connectivity, not object detection, because it validates the transport boundary before adding compute-heavy analytics.
3. For DMS, pick one vendor or emulator first so the object table and command schema are grounded in a real target.