# Sprint 1 Device Registry Plan

## Why this sprint
The current architecture has solid device and protocol layers, but the state layer is still large and Siemens-specific. This sprint converts orchestration to registry-driven device management so feature work can scale to multiple controller types.

## Scope
1. Move Siemens-specific parsing from state into driver/parser helpers.
2. Use device registry factory for polling and command dispatch.
3. Add normalized status contract usage across services and state.
4. Add multi-device state support and aggregated health UI.
5. Shift polling ownership to device instances.

## Deliverables

### D1. Parser extraction from state
- Extract ring/phase decode and console formatting from states into:
  - `opensignal_its/devices/siemens_m60.py` helper methods, or
  - `opensignal_its/devices/parsers/siemens_m60_parser.py`.
- `TrafficState` should consume normalized data from `DeviceStatus.extra`.

### D2. Registry-driven service dispatch
- Replace Siemens-only service entrypoints with generic methods:
  - `PollingService.collect_snapshot(device_type, config)`
  - `CommandService.execute_command(device_type, config, cmd_type, value, safe_probe)`
- Device creation must use `Device.create(device_type, config)`.

### D3. Multi-device state model
- Introduce state collections:
  - `devices: list[DeviceConfig]`
  - `selected_device_id`
  - `device_status_by_id`
- Keep existing single-device panel temporarily as compatibility UI.

### D4. Device-managed polling
- Start/stop background polling through `Device.start_polling()` and `Device.stop_polling()`.
- State subscribes/aggregates status snapshots rather than running controller-specific polling loops.

### D5. Test gate
- Add tests for:
  - registry create success/failure,
  - generic polling/command dispatch,
  - multi-device status aggregation,
  - parser output contract.

## Out of scope (Sprint 1)
- New vendor driver implementation.
- Major UI redesign.
- Remote API exposure.

## Acceptance criteria
1. No Siemens-specific parsing remains in `TrafficState`.
2. Services no longer instantiate `SiemensM60` directly.
3. At least two logical devices can be represented in state without code changes to service dispatch.
4. Existing command safety/auth/audit tests remain green.
5. New registry/multi-device tests pass.
