# Pre-Production Hardening + UI Dual-Track Plan

This plan keeps hardening visible and measurable while actively shipping UI/product improvements.

Reference architecture: `docs/ui-architecture-blueprint.md`

## Execution Model

Use a fixed capacity split each week:

- Hardening and pre-deployment: 35%
- UI improvements and operator workflow UX: 50%
- New features (non-UI): 15%

Rebalance only if a hardening blocker fails an exit criterion.

## Current 2-Week Execution Board

Use this as the active checklist and update status markers daily.

Status markers: `[ ]` not started, `[~]` in progress, `[x]` complete.

### Week 1 (Stabilize + High-Impact UI)

Hardening (secondary):

- [ ] Publish laptop deployment env baseline (`.env.example` + required vars list)
- [ ] Run preflight on a clean laptop profile and capture output evidence
- [ ] Verify denied ops API behavior when token is missing
- [ ] Verify authorized ops API behavior with bearer token

UI (primary):

- [x] Merge maintenance/runtime health cards into a clearer information hierarchy
- [x] Improve alarm triage readability (severity emphasis + row grouping)
- [x] Improve write confirmation/lockout messaging clarity
- [x] Run compact-screen layout pass for common laptop resolutions
- [x] Implement shell mode selector scaffold (Monitor/Control/Operations/Analytics/Configuration)

### Week 2 (Pilot Workflow Confidence + UX Polish)

Hardening (secondary):

- [ ] VPN degradation behavior rehearsal (poll fail/reconnect expectations)
- [ ] Recovery flow rehearsal (lockout reset, audit export, retention cleanup)
- [ ] Alert queue/deadletter operator visibility verification
- [ ] Capture acceptance evidence bundle for pilot signoff

UI (primary):

- [x] Improve selected-device context visibility in fleet controls
- [x] Improve runtime registry readability and scanability
- [x] Reduce events/alarms panel control clutter (grouping + defaults)
- [x] Draft release notes for user-visible UI changes
- [x] Extract module sections into component files aligned to architecture blueprint

## Daily Tracking Template

Copy this block into standup notes each day:

- Date:
- Hardening focus item:
- UI focus item:
- Completed today:
- Blockers:
- Evidence produced (tests/screenshots/logs):

## Weekly Cadence

1. Monday: pick sprint goals for both tracks and lock scope.
2. Wednesday: checkpoint against exit criteria; adjust only if blockers appear.
3. Friday: validation run, evidence capture, and gate decision.

## Hardening Track (Secondary but Gated)

### H0 Blockers (Must Stay Green)

1. Ops API access policy
- Required token by default unless explicit unauthenticated override.
- Authorization bearer token path validated in tests.

2. Audit export path containment
- Export writes constrained to configured export directory.
- Path traversal/out-of-scope writes rejected.

3. Startup preflight in production-like environments
- Missing secrets and unsafe ops API exposure blocked.

### H1 Pilot-Safe Completion Checklist

1. Config baseline profile for laptop deployment
- Single reference `.env` profile template and required values list.
- Preflight check output captured for baseline.

2. VPN degradation behavior verified
- Document expected behavior for poll failures/reconnect.
- Confirm no unsafe command retries.

3. Recovery runbook rehearsal
- Credential reset flow tested.
- Retention/export ops tested.
- Alert queue/deadletter visibility verified.

4. Acceptance evidence
- Last full test run green.
- Ops endpoints behavior captured with auth and denied cases.

## UI Track (Primary Delivery)

### U1 Immediate UX Upgrades (Current Priority)

1. Information architecture cleanup
- Consolidate maintenance and runtime health sections.
- Reduce cognitive load in events/alarms controls.

2. Operator workflow clarity
- Stronger status hierarchy for alarm triage and command safety state.
- Improve labels/messaging for write confirmation and lockout states.

3. Fleet usability
- Better selected-device context and runtime registry visibility.
- Improve readability of fleet rows and runtime status rows.

4. Mobile/compact layout pass
- Ensure controls remain usable on smaller laptop screens.

### U2 Evidence of Done per UI Item

1. User-facing change listed in release notes section.
2. Relevant state/service mapping logic covered by tests when feasible.
3. Manual validation screenshot/video captured (optional but preferred).

## Gate Definitions

### Gate A: Continue Dual-Track (default)

- H0 blockers all green.
- UI sprint commitments on track.

### Gate B: Hardening Spike (temporary)

Trigger only if one of these occurs:

1. New high-risk vulnerability found.
2. Preflight safety control regresses.
3. Ops auth/path protections fail tests.

When triggered, run a short hardening spike (1-2 days), then return to dual-track.

### Gate C: Shift More to UI/Features

Can increase UI+features to 75-85% when:

1. H1 checklist complete.
2. Two consecutive full regression runs are green after weekly changes.
3. No open high-risk hardening blockers.

### Pivot Trigger (explicit)

If all conditions below are true, increase UI + feature capacity to 75-85%:

1. Week 1 hardening checklist is complete.
2. At least one VPN/recovery rehearsal from Week 2 is complete.
3. Latest two full regression runs are green.
4. No Red items in H0 blockers.

## Lightweight Scoreboard

Update this once per week.

- Hardening H0: Green | Yellow | Red
- Hardening H1 Completion: 0-100%
- UI Sprint Completion: 0-100%
- Full Regression: Pass | Fail
- Production Risk Level: Low | Medium | High

## Evidence Log (append-only)

Add one entry per meaningful checkpoint.

- YYYY-MM-DD: what was validated, by whom, and proof location.
- 2026-05-23: Extracted workspace-specific dashboard sections into component modules (`configuration`, `control`, `operations`, `analytics`) and rewired shell composition in `opensignal_its.py`; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Restructured Operations workspace into grouped Runtime Health/Maintenance cards with warning vs critical visual emphasis; applied responsive auto-fit grid templates for main dashboard and analytics cards to improve compact laptop layouts; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Pivoted dashboard from stacked single-page flow to workspace page rendering (Monitor/Control/Operations/Analytics/Settings/Admin), moved authentication/recovery controls into Admin page, and removed login prompts from monitor/control workflows; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Extracted page-level workspace shell components (`monitor`, `settings`, `admin`, `layout`) and converted top workspace selector to tab-style shell composition, reducing `opensignal_its.py` to orchestration and improving maintainability; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Improved tab affordance with clearer active indicator and sticky nav shell treatment; extracted Control wrapper into dedicated `control_page` module for full page-level parity across workspaces; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Completed page-module parity by extracting Operations and Analytics wrappers into `operations_page` and `analytics_page` modules; `layout.py` now primarily routes between page builders; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Added shared `workspace_page_frame` component and adopted it across Monitor/Control/Operations/Analytics/Settings/Admin page modules to standardize page structure and reduce duplicated shell markup; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Added reusable `workspace_section_card` helper and applied it to Operations and Analytics sub-panels for consistent section composition, subtitles, and reduced duplicated card-heading markup; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Completed final UX copy consistency pass (page subtitles, panel helper text, and primary action labels) across workspace pages and section cards to improve scanability and verb clarity; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Performed manual runtime walkthrough on local app (`localhost:3002`/`8002`) verifying tab navigation (Monitor/Control/Operations/Analytics/Settings/Admin), copy updates, and auth isolation to Admin page; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Drafted user-visible UI release notes in `docs/ui-release-notes-draft.md` covering workspace navigation, auth separation, responsive layout, and UX copy updates.
- 2026-05-23: Improved monitor usability with dedicated Device Target Context, Runtime Registry, and Fleet Snapshot section cards to increase selected-device visibility and registry scanability; validated with `py_compile` and full unittest run (91 tests, pass).
- 2026-05-23: Enforced login-first UI access (unauthenticated users now see only sign-in/recovery controls) and relabeled key pages/panels to traffic-signal domain language (`Sites & Status`, `Signal Control`, `System Maintenance`, `Active Site Sessions`) to reduce onboarding ambiguity; validated with `py_compile`, full unittest run (91 tests, pass), and manual browser walkthrough.

## Current Starting Status

- H0 blockers: Green (token-required policy, auth header support, export path containment)
- H1 completion: 40%
- UI sprint completion: 100% (phase complete; next phase is map/site-centric IA refinement)
- Full regression: Pass
- Production risk level: Medium
