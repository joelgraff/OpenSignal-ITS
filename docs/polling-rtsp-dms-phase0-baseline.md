## Phase 0 Baseline: Siemens M60 Poll Shape

### Scope

This report captures the current Siemens M60 polling baseline and the orchestration telemetry added in Phase 0. It does not include any polling optimization, request coalescing, batching, caching, or backoff behavior.

### Measured Baseline

| Surface | Metric | Value |
| --- | --- | --- |
| SiemensM60.poll | SNMP GETs per successful poll | 93 |
| PollingService.collect_snapshot | Total SNMP GETs including connect probe | 95 |
| SiemensM60.poll | Average duration (3 controlled runs) | 0.000218975 s |
| SiemensM60.poll | Max duration (3 controlled runs) | 0.000285832 s |
| FleetStateMixin.refresh_fleet_status | Average duration (3 controlled runs) | 0.001233212 s |
| FleetStateMixin.refresh_fleet_status | Max duration (3 controlled runs) | 0.001298796 s |
| PollingService.collect_snapshot overlap probe | Average duration (2 controlled overlap runs) | 0.000107050 s |
| PollingService.collect_snapshot overlap probe | Max duration (2 controlled overlap runs) | 0.000127371 s |
| Device.start_polling overlap probe | Average duration (2 controlled overlap runs) | 0.000105071 s |
| Device.start_polling overlap probe | Max duration (2 controlled overlap runs) | 0.000119303 s |

### Current Poll Shape

The current successful Siemens M60 poll uses four request groups:

1. Identity/static reads: `sysDescr`, `currentPattern`, `unitStatus`.
2. Ring/status reads: two ring status GETs.
3. Group mask reads: greens, reds, vehicle calls, and pedestrian calls for groups 1 and 2.
4. Per-phase live reads: 16 phases × 5 live reads each = 80 GETs.

That totals 93 GETs for `SiemensM60.poll` on the happy path. The separate `PollingService.collect_snapshot` orchestration path adds the two SNMP GETs performed by `connect()`, so the end-to-end snapshot path is 95 GETs.

### Identity Versus Live Data

Static or slow-changing candidates:

- `OID_SYS_DESCR` is identity-only and is a strong cache candidate.
- `OID_PHASE_MAX_GREEN_1_TEMPLATE` is configuration-like and is fetched once per phase on every poll today.
- `OID_PHASE_GREENS_GROUP_TEMPLATE`, `OID_PHASE_REDS_GROUP_TEMPLATE`, `OID_PHASE_VEH_CALL_GROUP_TEMPLATE`, and `OID_PHASE_PED_CALL_GROUP_TEMPLATE` are group masks that are likely slower-changing than the per-phase live grid.

Live or frequently changing data:

- `OID_CURRENT_PATTERN`
- `OID_UNIT_STATUS`
- `OID_RING_STATUS_TEMPLATE`
- `OID_PHASE_STATUS_TEMPLATE`
- `OID_VEH_CALL_TEMPLATE`
- `OID_PED_CALL_TEMPLATE`
- `OID_TIME_REMAINING_TEMPLATE`

### Overlap Observation

A controlled local overlap probe recorded `last_overlap_detected = true` for `PollingService.collect_snapshot` when `Device.start_polling` was already active for the same runtime key. This confirms the telemetry is measuring overlap, not preventing it. No coalescing or skip logic was added.

### Phase 2 Candidate Targets

These are the highest-value candidates for later optimization work, based on current shape and request volume:

- Cache `OID_SYS_DESCR` outside the hot poll path.
- Reevaluate whether the phase group masks need to be fetched on every cycle.
- Review the per-phase vehicle/ped call reads because the code already also reads the group-level call masks.
- Keep `OID_RING_STATUS_TEMPLATE` and the phase live grid in the fast path until later measurements prove they can move.

### Notes

- The request-count telemetry is exposed in `status.extra["poll_telemetry"]` for Siemens M60 polls.
- The orchestration timing and overlap telemetry is exposed through `PollingService.poll_telemetry(runtime_key)`.
- These measurements were taken with controlled local fakes and are meant as a baseline, not a hardware performance guarantee.

### Phase 2a Note

After skipping redundant per-phase vehicle-call and pedestrian-call reads when both group-mask paths are available, the successful Siemens M60 poll path drops from 93 GETs to 61 GETs. The end-to-end `PollingService.collect_snapshot` path drops from 95 GETs to 63 GETs because the connect probe still performs its existing 2 GETs.

When the relevant group masks are missing, the existing per-phase fallback reads remain in place. The current missing-mask probe still attempts the existing group-1 scalar fallback before it falls back to per-phase reads, so that edge case measured 95 GETs.

### Phase 2b Note

Caching `OID_SYS_DESCR` per Siemens M60 instance keeps the first successful poll at 61 GETs but drops subsequent polls on the same instance to 60 GETs.

- Cache scope: per `SiemensM60` instance only.
- Warm same-instance `PollingService.collect_snapshot`: 62 GETs, because the connect probe still contributes its existing 2 GETs and the warm poll reuses cached `sysDescr`.
- Missing or failed `sysDescr` reads do not poison the cache; the next successful read can still populate it.

### Phase 2c Note

Caching `OID_PHASE_MAX_GREEN_1_TEMPLATE` per Siemens M60 instance keeps the first successful poll at 61 GETs but drops subsequent polls on the same instance to 44 GETs after all 16 phase max-green values are cached.

- Cache scope: per `SiemensM60` instance only, and only successful per-phase max-green reads are cached.
- Warm same-instance `PollingService.collect_snapshot`: 46 GETs, because the connect probe still contributes its existing 2 GETs and the warm poll reuses cached `sysDescr` plus all 16 max-green values.
- Missing or failed phase max-green reads do not poison the cache; successful phases stay cached and failed phases are retried on later polls.

### Phase 2d Note

Batched GETs keep the warm Siemens M60 object-read count at 44 OID objects but cut the warm SNMP round-trip count from 44 to 5.

- Metric names: `request_count` and `object_count` track OID objects read; `round_trip_count` tracks SNMP GET PDUs.
- Warm same-instance `PollingService.collect_snapshot`: 46 OID objects and 46 round trips before batching, versus 46 OID objects and 7 round trips after batching, with the existing 2-GET connect probe preserved.
- Batch failure falls back to individual reads for the affected group and preserves prior output semantics; the missing-group-mask path still resolves to the same object-read baseline while paying extra round trips for the failed batch attempts.

### Phase 2e Note

Batched connect probes keep the warm Siemens M60 object-read count at 44 OID objects but cut the warm end-to-end `PollingService.collect_snapshot` round-trip count from 7 to 6 by turning the 2-GET connect probe into one batched probe.

- Connect semantics stay the same: success still requires at least one of `sysDescr` or `currentPattern`, and the probe falls back to individual reads if the batch fails or returns partial data.
- Warm same-instance `PollingService.collect_snapshot`: 46 OID objects and 6 round trips end-to-end, with the warm poll still contributing 44 OID objects and 5 round trips.
- Batch failure or partial connect data falls back to individual connect reads and preserves the existing status text and error behavior.

### Phase 2f Note

Overlapping `PollingService.collect_snapshot` calls for the same runtime key now share one in-flight connect/poll cycle, so duplicate SNMP work does not double under overlap.

- Coalescing scope: per runtime key, limited to `PollingService.collect_snapshot`.
- Same-key overlap telemetry still records both refresh calls, but only one underlying device connect/poll cycle runs and both callers receive the same payload/mp_model result.
- Sequential same-key calls and different runtime keys still run independently, so warm-path counts remain unchanged outside overlap.