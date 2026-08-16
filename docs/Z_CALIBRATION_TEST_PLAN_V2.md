# Z Calibration Subsystem v2 — Test & Release Plan

**Status:** mandatory verification baseline for issue #13  
**Date:** 2026-08-16  
**Applies to:** Z Calibration Core, backend/API, installer/lifecycle, Fluidd UI and later frontend adapters

## 1. Purpose

This subsystem can move Z toward the build plate and can change the effective print Z. A false positive or bad state transition can damage the plate, hotend or print.

Therefore testing is not an afterthought. Safety-critical behaviour must be proved before equivalent real-printer paths are enabled.

Core policy:

> **model/fake tests → controlled hardware tests → optional process verification → release candidate**

No threshold is accepted because it “looks reasonable”. Every threshold that can affect motion, acceptance or correction requires source/runtime evidence, repeated hardware measurements and a documented margin.

---

## 2. Acceptance layers

### Layer A — Pure model tests

No Klipper/Moonraker process and no printer required.

Prove:

- arithmetic;
- state-machine transitions;
- scoping and provenance;
- decision logic;
- persistence rules;
- failure atomicity.

These tests should be fast and run on every relevant commit.

### Layer B — Fake Klipper/Moonraker adapter

Use a deterministic simulator/fake adapter capable of replaying:

- homed/not-homed;
- bed mesh present/absent;
- probe trigger coordinates;
- unstable/drifting samples;
- early trigger;
- no trigger;
- delayed/missing H7;
- communication error;
- cancellation;
- restart/reconnect;
- external `SET_GCODE_OFFSET` changes.

This layer proves orchestration without physical risk.

### Layer C — Repository/integration tests

Prove:

- backend API schema/actions;
- installer/update/uninstall/rollback;
- config generation;
- no dirty tracked upstream files;
- structured diagnostic retention;
- frontend API adapter behaviour;
- UI state/error rendering.

### Layer D — Controlled real-printer metrology/safety

Idle printer only. Start with no persistent writes and conservative motion.

Each hardware gate is explicitly accepted before moving to a riskier gate.

### Layer E — Controlled print/process acceptance

Only after Layer D passes.

Verify runtime mesh, slicer/job offset, live babystepping and optional first-layer verifier on deliberately selected test prints.

### Layer F — Release regression

Repeated cold boots, temperature ranges, actual tool/plate changes, update/uninstall/fallback and frontend parity.

---

## 3. Pure offset-composition matrix

The canonical composition is:

```text
auto_alignment
+ persistent_user
+ slicer_job
+ live_adjustment
(+ observable external_unknown when attribution is impossible)
────────────────────────
= effective Klipper gcode_offset
```

Table-driven tests must cover at least:

1. all zero;
2. positive/negative auto with zero user trim;
3. persistent user trim only;
4. slicer job offset only;
5. live adjustment only;
6. all four same sign;
7. cancelling signs;
8. decimal precision/round-trip near expected Klipper resolution;
9. save live delta into persistent user trim;
10. do not save live delta;
11. new job clears old slicer offset;
12. cancel before print clears job-scoped state;
13. restart before print does not resurrect stale job/live state;
14. auto recalculation replaces, not accumulates, previous Auto-Z;
15. repeated API retries are idempotent where required;
16. external standard Klipper offset change remains observable and does not get silently overwritten without an explicit reconciliation decision.

Property-style invariants:

- composition is deterministic;
- job-scoped components do not become persistent without explicit save;
- recomputing the same inputs yields the same effective result;
- re-running calibration cannot double-apply Auto-Z;
- UI/API decomposition sums to the actual effective Klipper state within defined numeric tolerance.

---

## 4. State-machine tests

Required states include at minimum:

```text
IDLE
PRECHECK
PREPARE_PROBE
TARE
SAFE_APPROACH
SLOW_CONTACT_SEARCH
VERIFY_CONTACT
REPEATABILITY_CHECK
REFERENCE_DECISION
MESH_DECISION
OFFSET_COMPOSITION
READY
HARDWARE_CHANGE_SUSPECTED
ABORT
```

Test every allowed transition and explicit rejection of illegal transitions.

Negative examples:

- `IDLE → SLOW_CONTACT_SEARCH` without precheck;
- calibration while printing/paused when policy forbids it;
- search without homing/known motion state;
- offset application before accepted reference;
- saved-mesh alignment after failed reference validation;
- automatic permanent mesh save;
- applying a large delta while state is `HARDWARE_CHANGE_SUSPECTED`;
- resuming from `ABORT` without a fresh safe start.

Cancellation must be injected at every state that can own temporary motion/correction state.

Expected post-cancel invariant:

```text
persistent user trim unchanged
saved mesh unchanged
no stale job/auto/live correction left armed
safe retract attempted when motion state permits
failure event recorded
```

---

## 5. Probe-series validation tests

Replay/provide sample sequences for:

### Stable series

Low spread, no directional drift, plausible reference. Must pass.

### Single outlier

Example shape:

```text
-1.52
-1.83
-1.84
```

Must not directly convert the first value into a large Auto-Z. Policy may reject the series or rerun an independent confirmation sequence, but must remain fail-closed.

### Monotonic drift

Example shape similar to the historical first anomalous PROBE_ACCURACY run. Must fail/retry rather than accept median blindly.

### High scatter

Spread above configured gate. Must fail.

### Early trigger

Probe reports contact before entering the allowed contact window. Must abort as suspicious.

### No trigger

Probe does not trigger by lower safe bound. Must stop downward search and abort/retract.

### Repeated large delta

A large shift is confirmed consistently. Must become `HARDWARE_CHANGE_SUSPECTED` / full-calibration path, not a huge automatic `gcode_offset`.

### Communication failure

Klipper/Moonraker response missing, timeout or malformed. Must not continue with stale values.

---

## 6. Search-envelope safety tests

The implementation must expose a testable pure function/policy for the allowed Z search interval.

Tests:

- valid previous reference + configured margin;
- previous reference near machine boundary;
- invalid/missing previous reference;
- impossible range;
- negative/zero margin config;
- corrupted reference state;
- configured limit outside machine limits;
- initial-acquisition mode;
- runtime attempt to exceed lower safe bound.

Hard invariant:

> There is no normal code path in which the automatic contact search simply continues to Klipper `position_min` because contact was not found.

Mutation test: deliberately remove/disable the lower-bound guard and prove the test suite fails.

---

## 7. Large-delta policy tests

The boundary between normal alignment and suspected hardware change is a safety decision.

Tests must prove:

- below-threshold stable delta may align;
- exactly-at-boundary behaviour is deterministic;
- above-threshold single measurement does not align;
- above-threshold confirmed repeated measurement still does not silently align;
- user cancel after hardware-change warning leaves all persistent state unchanged;
- full recalibration may establish a new baseline only after its own acceptance gates;
- saved mesh is not implicitly redefined merely because a large reference delta was observed.

Threshold value remains configurable/test-derived until hardware acceptance freezes it.

---

## 8. H7 / load-cell safety tests

Current product baseline assumes H7 is secondary.

Repository/fake tests must cover:

- H7 available and plausible;
- H7 delayed;
- stale H7 value after retract;
- H7 missing/timeout;
- signless `WeightValue` vs signed raw H7 distinction;
- H7 contradiction with PB3/probe state;
- H7 impossible/out-of-range value;
- tare leaves near-zero but not exact zero;
- H7 safety feature disabled/unavailable.

Hard invariant:

> Loss or delay of H7 cannot remove the primary bounded-motion protection.

A future independent force watchdog requires a separate hardware acceptance section proving latency and stopping distance under worst tested approach speed.

---

## 9. Bed-mesh policy tests

### `saved`

- loads/keeps selected saved mesh;
- does not invent Auto-Z check;
- UI marks mode clearly;
- missing requested saved mesh fails predictably.

### `saved+check`

- obtains validated reference;
- uses correct saved mesh reference metadata;
- computes one Auto-Z alignment;
- does not double-apply on retry;
- large/suspicious delta escalates;
- failed check leaves saved mesh untouched.

### `runtime`

- builds a fresh runtime mesh;
- uses it for current print/session;
- does not overwrite permanent/default profile automatically;
- cancel/failure does not corrupt old saved mesh;
- explicit `Save as default` is separate and auditable;
- runtime mesh state is cleared/reconciled at correct lifecycle boundaries.

Also test profile switch/reconnect/restart semantics so frontend display matches actual Klipper mesh state.

---

## 10. Slicer/job offset tests

Preferred explicit job-offset contract must be tested with:

- absent parameter → zero;
- positive and negative values;
- malformed value;
- absurd/out-of-policy value;
- duplicate parameter/action;
- same job retry;
- next job without offset;
- cancel before print;
- cancel during print;
- reconnect during print;
- user trim + job offset composition;
- Auto-Z + job offset composition;
- live babystepping on top of job offset.

Unknown external `SET_GCODE_OFFSET` behaviour:

- do not prevent standard Klipper operation globally;
- detect mismatch between backend composition and actual Klipper effective state when observable;
- classify as external/unknown rather than silently pretending provenance;
- do not silently “correct it back” while a print is active unless an explicit safety policy requires abort/reconciliation.

---

## 11. Live babystepping tests

- normal Fluidd/Mainsail/Plugins UI step changes effective Z immediately;
- multiple small steps accumulate correctly;
- positive/negative cancellation;
- bounds for Plugins-controlled first-layer verifier;
- normal print babystepping is not incorrectly constrained by verifier-only limits;
- explicit save folds intended delta into persistent user trim exactly once;
- `do not save` leaves persistent user trim unchanged;
- print cancel clears transient live provenance as designed;
- reboot does not persist unsaved live adjustment;
- frontend refresh/reconnect shows actual current effective state.

---

## 12. First-layer verifier tests

The verifier is optional and separate from geometric calibration.

### Repository tests

- geometry-calibrated state does not require verifier PASS for every print;
- UI can show `Geometry PASS / First layer NOT RUN`;
- recommended-after-hardware-change flag does not become an unconditional print blocker;
- verifier always starts at zero additional test delta;
- allowed test adjustment step/total bounds are enforced;
- no persistent save without explicit user confirmation;
- `Cancel`, Helix/Guppy/KlipperScreen-equivalent system cancel and backend abort leave persistent Z unchanged;
- generated path is continuous and uses physically accepted line-spacing model;
- verifier runs through the same effective offset composition as a real print.

### Physical acceptance

1. run zero-delta patch first;
2. confirm no artificial inter-road gaps;
3. small positive/negative adjustment behaves predictably;
4. cancel without save leaves persistent value identical;
5. explicit save changes only persistent user trim by intended amount;
6. following ordinary sliced print uses same effective Z model;
7. repeat representative PLA plus at least one materially different first-layer material/profile if scope permits.

The verifier is **not** accepted as a safety mechanism.

---

## 13. Structured diagnostic log tests

Required properties:

- deterministic schema/version;
- event timestamps/order;
- correlation ID per calibration/print attempt;
- bounded retention/rotation;
- no high-rate idle writes;
- no secrets/tokens/passwords;
- every offset decision includes provenance;
- every safety abort includes reason and relevant safe values;
- failed parse/corrupt old record cannot break calibration core;
- log write failure degrades diagnostics but does not create unsafe motion;
- export/snapshot can be used by future `Collect diagnostics` workflow.

Regression scenario:

Recreate an early anomalous reference in fake adapter and verify the log alone contains enough evidence to reconstruct:

- expected reference;
- measured samples;
- mesh mode/reference;
- all offset components;
- decision/retry/abort;
- sensor/tare summary.

---

## 14. API contract tests

For snapshot/action API:

- schema/version compatibility;
- module present/absent/degraded;
- backend not ready;
- Klippy disconnected/reconnected;
- state revision/invalidation;
- concurrent duplicate requests;
- action rejected while printing;
- stale frontend revision cannot accidentally apply stale state;
- cancellation acknowledgement;
- safe errors are human-readable but do not expose secrets;
- frontend-neutral semantics: no Fluidd-specific state names in backend contract.

Every write/action endpoint must have explicit authentication/transport policy consistent with the accepted Plugins AD5X Moonraker backend contract.

---

## 15. Installer/lifecycle tests

Preserve existing managed-copy/observed-stop architecture.

Test:

- fresh install;
- repeat install/idempotence;
- update;
- `--apply-only` repair;
- unknown runtime destination ownership fail-closed;
- config validation before mutation;
- rollback after failure before stop;
- rollback after stop;
- rollback after start but before ready;
- uninstall;
- hard-recovery/git-clean runtime loss then repair;
- Moonraker/Klippy readiness;
- no use of unsafe fixed-sleep restart primitive;
- no tracked Z-Mod/Klipper/Moonraker source modifications;
- removal of Z Calibration module restores ordinary Z-Mod path.

---

## 16. Fluidd tests

Fluidd remains the first full UI.

Required:

- route/nav capability gating;
- backend absent → safe unavailable view;
- snapshot renders normal state;
- offset composition matches backend exactly;
- slicer/live contributions appear only when relevant;
- warning/error states provide next action;
- no UI-side Auto-Z math;
- `Check Z`, `Build mesh`, `Full calibration`, optional `Test first layer` dispatch semantic backend actions;
- cancel state disables/reenables controls correctly;
- reconnect full-resync;
- mobile/desktop layout as supported by Fluidd;
- normal upstream Fluidd tests/build/lint/type-check remain green;
- AD5X code remains localized under existing integration seams.

Later frontends reuse the same behavioural contract tests where practical.

---

## 17. Real-printer acceptance gates

### Gate A — Read-only baseline

Record exact:

- Z-Mod/Klipper/Moonraker versions;
- active macros/config owners;
- probe config;
- stepper Z bounds/endstop;
- saved mesh identities;
- Plugins AD5X backend version;
- hotend/nozzle/plate physical setup.

No writes/motion beyond normal read-only status.

### Gate B — Controlled no-persistence measurement

Idle printer.

- home;
- safe reference position;
- tare;
- repeated probe series;
- no save/config mutation;
- verify backend values against raw console/Klipper objects;
- verify abort/cancel leaves state unchanged.

### Gate C — Repeatability dataset

Collect repeated accepted series:

- cold/ambient;
- representative PLA bed temperature;
- representative high bed temperature (e.g. ABS/ASA target used by owner hardware, subject to safe printer limits);
- after reboot/power cycle;
- after reasonable idle/time intervals.

Freeze thresholds only after this dataset and source semantics are reviewed.

### Gate D — Bounded-search safety

Start conservatively above the known contact zone.

Prove:

- lower bound is enforced;
- no-trigger simulation/fault path stops before unsafe travel;
- early-trigger path aborts;
- retract behaviour;
- communication-loss path;
- H7 unavailable path remains bounded.

No deliberately destructive probe-input bypass is allowed on the real plate merely to prove the last line of defence. Where hardware fault injection would itself create unacceptable risk, prove it in fake/model tests and use a non-contact conservative hardware proxy test.

### Gate E — Saved mesh + check

- use known saved mesh;
- measure current reference;
- verify applied Auto-Z exactly once;
- compare backend decomposition to `GET_POSITION`/Klipper state;
- repeat enough times to show no accumulation;
- force a safe synthetic large-delta decision in fake/backend test before any real large-delta experiment.

### Gate F — Runtime mesh

- build fresh runtime mesh;
- verify current job uses it;
- verify saved/default mesh remains unchanged;
- cancel halfway and confirm old mesh remains safe;
- explicitly save one known-good runtime mesh only when owner chooses to test save semantics.

### Gate G — Job/slicer/live composition

Controlled sliced print:

- no slicer offset;
- small known slicer offset;
- live adjustment;
- no-save path;
- explicit-save path;
- next job proves no stale job offset leak.

### Gate H — Optional first-layer verifier

Physical acceptance per Section 12. It is not required on every normal print after acceptance.

### Gate I — Real hardware/plate change

After core safety is accepted:

- actual nozzle or hotend change, or controlled plate change;
- verify large reference change is detected/confirmed safely;
- full calibration establishes new valid baseline;
- no manual hotend Z profile selection is required;
- normal print succeeds with standard offset semantics.

### Gate J — Lifecycle/fallback

- reboot;
- full power cycle;
- Plugins AD5X update/repair;
- Z-Mod update compatibility check where safe;
- uninstall/disable;
- ordinary Z-Mod printing remains available after fallback.

---

## 18. Release regression matrix

Before public release, repeat at minimum:

| Axis | Required examples |
|---|---|
| Boot state | warm restart, full cold power cycle |
| Mesh mode | saved, saved+check, runtime |
| Plate state | normal plate; at least one controlled re-seat/change |
| Tool state | current hotend; one actual nozzle/hotend change |
| Bed temperature | ambient/low, PLA-class, high-bed representative |
| Offset source | user, slicer/job, live, combinations |
| Failure | early trigger, no trigger simulation, unstable samples, API loss/cancel |
| Frontend | Fluidd mandatory; each later adapter before its own release |
| Lifecycle | install, update, repair, uninstall/fallback |

Public release requires no known plate-contact safety blocker.

---

## 19. Evidence required per acceptance candidate

Record:

- exact Git commit SHA(s);
- exact relevant frontend SHA(s);
- exact Z-Mod/Klipper/Moonraker versions;
- test counts/results;
- CI workflow run IDs;
- real-printer hardware setup;
- calibration diagnostic log artifact;
- accepted threshold configuration and evidence source;
- owner acceptance status.

Do not mark Ready for Review or merge until explicit owner acceptance of the exact candidate.

---

## 20. Stop conditions

Immediately stop hardware acceptance and investigate if any of the following occurs:

- uncontrolled downward motion;
- unexpected contact outside safe window;
- abort fails to stop/retract as designed;
- persistent user trim changes without explicit save;
- saved mesh changes without explicit save;
- job offset survives into the next job;
- Auto-Z is applied twice;
- backend and actual Klipper effective offset disagree without explicit external/unknown classification;
- diagnostic state cannot explain a safety decision;
- repeated probe series shows new unexplained drift/large scatter;
- any test threatens plate/hotend damage.

The correct failure mode is **refuse to calibrate/print through the automatic path and retain ordinary Z-Mod fallback**, not guess a correction.