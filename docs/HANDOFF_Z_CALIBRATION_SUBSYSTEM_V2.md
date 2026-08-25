# Handoff — CALIBRATION-SUBSYSTEM-002 implementation

**Work item:** issue #13 — `CALIBRATION-SUBSYSTEM-002: explainable safe Auto-Z, mesh policy and multi-frontend Calibration Center`  
**Repository:** `genrudko/Plugins_AD5X`  
**Branch:** `feature/z-calibration-subsystem-v2`  
**Base:** current `dev` at branch creation: `ab25f96c017d56fe3a754ce4d05664c710dd2a80`  
**Old work:** issue #5 CLOSED / PR #6 CLOSED UNMERGED; research/history only

## 1. Role

You are the implementation engineer for Z Calibration Subsystem v2.

GitHub and the actual source/runtime are authoritative. Do not reconstruct the design from chat memory when the repository already states it.

Do not broaden scope into unrelated Hardware Manager/IFS/Camera work.

## 2. Mandatory reading before code

Read current versions on the working branch:

- `ROADMAP.md`
- `ARCHITECTURE.md`
- `PROJECT_STATE.md`
- `DECISIONS.md`
- issue #13
- `docs/Z_CALIBRATION_SUBSYSTEM_V2.md`
- `docs/Z_CALIBRATION_REVERSE_ENGINEERING_2026-08-16.md`
- `docs/Z_CALIBRATION_TEST_PLAN_V2.md`

Also inspect the current Plugins AD5X backend and installer:

- `moonraker/components/plugins_ad5x.py`
- `plugins_ad5x.moonraker.conf`
- `install.sh`
- current tests

For frontend integration, read the accepted Fluidd integration decisions D-018–D-021 and inspect current `genrudko/fluidd:ad5x-dev` before making frontend changes.

Old PR #6 may be inspected only for reusable evidence/lessons. Do **not** cherry-pick or revive its profile/G92 product architecture wholesale.

## 3. Hard architectural contract

### 3.1 One backend, many frontends

Business logic/state/safety live in the common Plugins AD5X backend/core.

Fluidd/Mainsail/HelixScreen/Guppy/KlipperScreen are adapters/views and must not implement their own Auto-Z arithmetic.

### 3.2 Standard Klipper effective Z-offset

Internal provenance:

```text
Auto-Z alignment
+ persistent user Z trim
+ slicer/job Z offset
+ live babystepping
────────────────────────
= effective Klipper gcode_offset
```

The effective runtime state must remain standard Klipper semantics and be observable through ordinary Klipper/Fluidd/Mainsail tooling.

Do not create a hidden parallel product-level coordinate system.

### 3.3 No normal per-hotend Z profiles

A hotend/nozzle swap is handled by measuring the current nozzle↔bed reference.

A large confirmed delta does not become a huge automatic offset. It becomes a `hardware_change_suspected` / full-calibration path.

### 3.4 Bed mesh modes

Implement semantic modes:

- `saved`
- `saved+check` — recommended normal mode
- `runtime`

Runtime mesh must not overwrite saved/default mesh without an explicit separate user action.

### 3.5 First-layer test

Optional/user-invoked/recommended, not mandatory on every print.

It verifies process quality and persistent user trim. It is not a geometric safety interlock.

### 3.6 Fail-closed plate protection

No unbounded downward search.

No huge unexpected correction from one sample.

No persistent user trim or saved-mesh mutation on failure/cancel.

H7 is secondary until dedicated latency/stop-distance evidence proves it can act as an independent hard watchdog.

No safety threshold is accepted without source/hardware evidence and margin.

## 4. Implementation sequence

Use the existing issue/branch/Draft PR only. Do not create a parallel implementation contour unless the coordinator explicitly asks.

### Milestone A — formal core model + fake adapter

Implement first, without real-printer mutation:

1. Z calibration state model;
2. offset provenance/composition model;
3. state machine;
4. search-envelope policy;
5. reference-series validation;
6. large-delta decision model;
7. mesh-mode decision model;
8. structured diagnostic event schema/storage abstraction;
9. fake Klipper/Moonraker adapter;
10. table-driven and negative tests from `Z_CALIBRATION_TEST_PLAN_V2.md`.

Prefer pure Python/model code that can be tested without Moonraker/Klipper.

Stop and report architecture/file/API proposal before binding safety decisions deeply into runtime if the existing backend boundary forces a major design change.

### Milestone B — Plugins AD5X backend/API integration

Extend the accepted optional Moonraker backend rather than introducing a second daemon.

Define versioned module state/actions for `z_calibration`.

Requirements:

- nonblocking/event-driven;
- frontend-neutral;
- authenticated action endpoints;
- snapshot/state invalidation consistent with existing backend contract;
- safe behaviour when Klippy is unavailable/not ready;
- no steady-state high-rate polling;
- bounded diagnostic history;
- action cancellation;
- actual Klipper effective offset reconciliation.

Add API contract tests and failure injection.

### Milestone C — installer/config lifecycle

Extend the existing managed-copy / observed-stop installation model.

Prove:

- install/update/apply/repair/uninstall;
- ownership checks;
- rollback;
- config validation;
- no tracked Z-Mod/Klipper/Moonraker dirty modifications;
- ordinary Z-Mod fallback remains available.

### Milestone D — Fluidd full UI

Only after backend state/actions are stable enough.

Use `genrudko/fluidd:ad5x-dev` and existing `src/ad5x/**` ownership/integration seams.

Normal UI:

- Z calibration readiness;
- effective Z-offset;
- Auto-Z contribution;
- persistent user trim;
- job/live contributions when relevant;
- mesh mode/status;
- last warning/error;
- `Check Z`;
- `Build mesh`;
- `Full calibration`;
- optional `Test first layer`;
- diagnostics/Advanced.

No Auto-Z math in Vue components/store.

Run exact-head Fluidd lint/type/unit/circular/build gates.

### Milestone E — controlled real-printer acceptance

Do not mutate the printer before repository/model/API safety tests are green and the coordinator explicitly approves the next physical gate.

Follow `docs/Z_CALIBRATION_TEST_PLAN_V2.md` gates A–J.

For live debugging, use logical command batches when safe, but stop at result-dependent gates. Never send uncontrolled downward moves based on an unverified reference.

Record exact raw output and structured diagnostic events.

### Milestone F — optional first-layer verifier

Implement/accept only after geometric/safety core is proven.

Start physical acceptance at zero additional test delta.

Prove both no-save and cancel paths preserve persistent user Z exactly.

Do not reuse the physically rejected old PR #6 first-layer generator without independently revalidating its geometry and lifecycle.

### Milestone G — frontend parity

After API and Fluidd UI are accepted, create bounded follow-up implementation work for:

- Mainsail;
- HelixScreen;
- Guppy;
- KlipperScreen after its AD5X platform/runtime acceptance.

All use the same backend semantics. Do not hold core release hostage to pixel-identical parity if the coordinator chooses staged frontend rollout, but do not duplicate business logic.

## 5. Testing requirements

`docs/Z_CALIBRATION_TEST_PLAN_V2.md` is mandatory, not advisory.

At minimum the final candidate must prove:

- offset composition/provenance;
- job/live reset boundaries;
- no double-apply Auto-Z;
- state-machine negative transitions;
- bounded search and mutation test of lower-bound guard;
- early/no-trigger handling;
- unstable/drifting/outlier series;
- confirmed large-delta escalation;
- H7 unavailable/delayed behaviour;
- saved/saved+check/runtime mesh semantics;
- failed/cancelled operations do not mutate persistent user trim/saved mesh;
- structured log is bounded and sufficient for diagnosis;
- API failure/reconnect/cancel;
- installer/rollback/uninstall;
- no tracked upstream modifications;
- Fluidd normal/error/reconnect states;
- real-printer repeatability/safety gates;
- optional first-layer test physical acceptance;
- actual nozzle/hotend or plate-change acceptance before public release.

Prefer table-driven tests, fake adapters and failure injection over large collections of brittle one-off tests.

## 6. Safety stop conditions

Immediately stop and report instead of improvising if:

- implementation requires an unbounded search to work;
- PB3/probe semantics differ from the recorded runtime without explanation;
- effective Klipper offset cannot be reconciled with backend composition;
- a cancel/failure path changes persistent user trim or saved mesh;
- runtime mesh overwrites saved mesh implicitly;
- slicer/job offset leaks into another job;
- Auto-Z applies twice;
- a real-printer test would require intentionally risking a plate strike to prove a negative path;
- H7 is being promoted to a hard watchdog without timing evidence;
- a new source/runtime observation contradicts the accepted reverse-engineering facts.

When evidence changes, update the architecture/decision docs rather than hiding the contradiction in code.

## 7. Git/PR discipline

- source of truth: GitHub;
- work only in issue #13 / `feature/z-calibration-subsystem-v2` / its Draft PR;
- keep PR Draft;
- no Ready for Review or merge without explicit owner command;
- no direct feature work in `dev`;
- do not revive old PR #6;
- before final acceptance: rebase/sync as appropriate so `behind_by=0` against current `dev` and run all applicable exact-head gates;
- record exact head, changed files, CI run IDs and physical acceptance evidence.

## 8. First response expected from the implementation chat

Before changing code, report only after verifying current GitHub state:

1. current `dev` head;
2. issue #13 state;
3. feature branch head;
4. Draft PR state/head/base/behind_by;
5. relevant current backend/installer files;
6. old PR #6 remains closed/unmerged;
7. concise Milestone A file/API/test plan based on the actual repository.

Then proceed with Milestone A unless repository evidence shows a blocker that requires coordinator decision.

Do not ask the owner to manually inspect GitHub state that the connector/source can establish.