# Z Calibration Subsystem v2

**Status:** accepted design baseline for issue #13  
**Date:** 2026-08-16  
**Base:** `genrudko/Plugins_AD5X:dev`  
**Supersedes:** product architecture of issue #5 / closed Draft PR #6

## 1. Product goal

Build an explainable, safe, frontend-neutral Z calibration subsystem for Flashforge AD5X + Z-Mod/Klipper/Moonraker.

The subsystem must make the normal user experience simple:

```text
I changed a nozzle / hotend / plate
→ run calibration or just start a print
→ printer establishes the current nozzle↔bed reference
→ printer validates the result
→ printer aligns the selected bed mesh policy
→ standard Klipper Z-offset is composed and applied
→ print starts
```

The user must not need to understand `MESH_TEST`, `temp_z_offset`, `homing_origin`, probe coordinate formats, raw load-cell values or hidden macro state.

At the same time an experienced Klipper user must keep standard semantics, console visibility, standard Z adjustment controls and access to low-level diagnostics.

## 2. Architectural position

The subsystem lives in the common Plugins AD5X backend/API and uses Z-Mod/Klipper as the low-level execution layer.

```text
Klipper / Z-Mod / load cell / bed_mesh
                │
                ▼
       Z Calibration Core
  state / safety / decisions / logs
                │
                ▼
      Plugins AD5X backend API
                │
      ┌─────────┼─────────┬──────────┬──────────┐
      ▼         ▼         ▼          ▼          ▼
   Fluidd    Mainsail  HelixScreen  Guppy  KlipperScreen
```

Frontend implementations display and invoke the same state/actions. They do not contain independent Auto-Z mathematics.

No Z-Mod fork is introduced.

## 3. User-visible Z model

The user-visible concept remains the normal Klipper **Z-offset**.

Internally the subsystem tracks provenance of the components that compose it:

```text
Auto-Z alignment
+ persistent user Z trim
+ slicer/job Z offset
+ live babystepping
────────────────────────
= effective Klipper gcode_offset
```

### 3.1 Auto-Z alignment

Runtime correction derived from the difference between the trustworthy reference associated with the selected saved mesh and the current validated nozzle↔bed reference.

Scope: current calibration/print context. It is recalculated when required and is not silently persisted as the user's manual trim.

### 3.2 Persistent user Z trim

The user's intentional long-lived first-layer preference.

This is the value changed only by an explicit save operation after manual/live adjustment or an explicit calibration UI action.

Automation must not silently overwrite it.

### 3.3 Slicer/job Z offset

Correction belonging to the current G-code job.

Preferred integration is an explicit `START_PRINT`/Plugins AD5X job parameter or an explicit Plugins AD5X job-offset command so provenance is known.

If external/legacy G-code changes standard Klipper offset without provenance, the subsystem must not globally hijack `SET_GCODE_OFFSET`. It should preserve standard Klipper behaviour and classify the difference as external/unknown when possible, logging and surfacing it in Advanced diagnostics.

Job offset is cleared at the job boundary.

### 3.4 Live babystepping

Normal runtime Z adjustment remains familiar to Klipper users.

The current effective Klipper offset changes immediately. If the adjustment was initiated through Plugins AD5X UI, provenance is `live_adjustment`. External standard Klipper adjustments remain valid and are logged as external/unknown if attribution cannot be proven.

An explicit `Save Z correction` operation may fold the accepted live delta into persistent user trim. Without explicit save it must not become persistent.

### 3.5 Effective offset is standard Klipper state

After composition, the actual runtime state must be represented through normal Klipper offset semantics so `GET_POSITION`, Fluidd, Mainsail and console tooling observe the effective value.

Plugins AD5X must not create a second hidden product-level coordinate system that disagrees with Klipper.

## 4. No normal Z profiles per hotend/nozzle

Persistent Z profiles tied to a particular hotend/nozzle are not part of the normal v2 product model.

A hotend/nozzle swap changes physical tool length. The correct response is to re-establish the current nozzle↔bed reference, not to require the user to select a stored Z profile.

A large confirmed reference delta is treated as evidence of a hardware/plate/tool geometry change:

```text
large confirmed delta
→ do not apply a huge silent correction
→ state = hardware_change_suspected
→ repeat/validate
→ request full calibration / runtime mesh as appropriate
```

Slicer profiles for nozzle diameter, flow, material and temperature remain separate and are unaffected by this decision.

Hardware Manager may still know which hotend/nozzle hardware is installed for capability/configuration purposes, but that identity does not own a hidden Z-offset profile.

## 5. Bed mesh policy

The user gets three understandable pre-print modes.

### `saved`

Use the selected saved bed mesh without an automatic current-reference alignment check.

This is the fastest/expert mode and must be clearly labelled as such.

### `saved+check`

Recommended normal mode.

```text
prepare probe
→ validate current Z reference
→ compare to saved mesh reference
→ accept only plausible alignment
→ apply runtime Auto-Z alignment
→ print
```

A normal check uses repeated samples at a known reference location. A large/suspicious delta must be independently reconfirmed; the system must not trust one anomalous sample.

If a large delta persists, escalate to full calibration/runtime mesh rather than applying a large automatic correction.

### `runtime`

Build a fresh bed mesh for the current print, similar to the stock AD5X user expectation.

The runtime mesh belongs to the current job/session by default. It must **not overwrite the saved/default mesh automatically**.

Saving a runtime mesh as the new default is a separate explicit user action.

## 6. Reference measurement model

The core distinguishes:

- Z homing reference;
- physical nozzle↔bed contact reference;
- bed-mesh geometric data;
- print/process Z correction.

They are not interchangeable numbers.

A normal current-reference measurement is a sequence, not a single sample:

```text
precheck
→ nozzle/probe preparation
→ unloaded tare
→ safe approach
→ slow contact search
→ repeated samples
→ spread/drift/plausibility validation
→ accepted reference or fail-closed abort
```

Exact sample counts and numeric thresholds are test-derived configuration, not architecture constants.

A suspicious large delta requires an independent confirmation path, which may include a second reference location or escalation to runtime mesh/full calibration.

## 7. Safety state machine

Safety is part of the core contract, not a UI option.

```text
IDLE
 ↓
PRECHECK
 ↓
PREPARE_PROBE
 ↓
TARE
 ↓
SAFE_APPROACH
 ↓
SLOW_CONTACT_SEARCH
 ↓
VERIFY_CONTACT
 ↓
REPEATABILITY_CHECK
 ↓
REFERENCE_DECISION
 ↓
MESH_DECISION
 ↓
OFFSET_COMPOSITION
 ↓
READY
```

Any unsafe or ambiguous state goes to `ABORT`, not to a best-effort continuation.

### 7.1 Bounded search envelope

The system must never perform an unbounded downward search for the bed.

If a trustworthy previous reference exists, the allowed search window is bounded around it with a tested margin.

If no trustworthy reference exists, use a separate conservative initial-acquisition workflow. Initial acquisition may require explicit user supervision until an independent safety mechanism has been proven on hardware.

No implementation may simply fall back to Klipper `position_min` as a normal probing lower bound.

### 7.2 Approach policy

Fast movement is allowed only to a position proven to be safely above the possible contact zone.

The final approach is slow and bounded.

### 7.3 Probe/result validation

Reject at minimum:

- probe already triggered unexpectedly before approach;
- no trigger before the lower safe bound;
- excessive sample spread;
- monotonic/drifting sequence inconsistent with a stable reference;
- result incompatible with known machine/reference bounds;
- unexpectedly large delta not reconfirmed;
- contradictory sensor state;
- cancellation or communication failure.

### 7.4 Large delta is not a large Auto-Z command

A large confirmed delta is diagnostic information, not permission to blindly add the same magnitude to runtime offset.

It must trigger a controlled `hardware_change_suspected` / recalibration path.

### 7.5 Persistent state protection

On any failed or cancelled calibration:

- persistent user trim remains unchanged;
- saved/default mesh remains unchanged;
- previous known-good calibration metadata remains available;
- partial runtime correction is cleared/reconciled;
- structured failure evidence is recorded.

### 7.6 Retract on abort

When motion state permits it safely, abort retracts away from the plate before returning control.

### 7.7 Load-cell/H7 is secondary until proven

Current reverse engineering shows `H7`/WeightValue latency, filtering/relaxation and sign-handling details that prevent us from treating it as a proven independent hard real-time force watchdog today.

Therefore:

- PB3/Klipper probe contact remains the primary low-level stop in the current baseline;
- H7 may be used for plausibility and secondary safety checks;
- H7 may become an independent force watchdog only after measured latency/threshold/motion tests prove that it can stop motion with sufficient margin;
- the primary plate-protection design must remain safe if H7 is unavailable or delayed.

No force threshold is accepted without hardware evidence and safety margin.

## 8. First-layer verifier policy

The first-layer test is **optional and user-invoked/recommended**, not a mandatory operation before every print.

Automatic contact/mesh measurements establish geometric reference. A printed first layer verifies the complete process:

- extrusion;
- plate condition/adhesion;
- material behaviour;
- temperatures;
- flow;
- user preference for squish.

Recommended uses:

- first activation of Z Calibration Subsystem;
- major hotend/nozzle/plate change;
- persistent large reference change after full revalidation;
- tuning persistent user Z trim;
- explicit user request.

If skipped, UI may report:

```text
Geometry calibration: PASS
First-layer verification: NOT RUN
```

That is not automatically a print blocker when geometric/safety checks are valid.

The first-layer verifier is never a plate-protection interlock.

### 8.1 Test behaviour

The verifier must:

- start from the same normal print path and offset composition as a real job;
- begin at zero additional test delta;
- allow small bounded live adjustments;
- show the current effective offset and its components;
- never persist a correction without explicit user save;
- prove Cancel/Abort leaves persistent state unchanged;
- use a physically validated continuous first-layer pattern;
- keep correction bounds conservative.

The old PR #6 rejected first-layer generator and its G92-specific product model are historical evidence, not the implementation baseline.

## 9. Structured diagnostic history

The subsystem must explain every Auto-Z decision without requiring manual archaeology in `klippy.log`.

Use a lightweight, bounded event log (for example JSONL with rotation/record cap; exact storage is implementation-defined).

No high-rate idle polling or heavy database is required.

Minimum event families:

- `calibration_started` / `calibration_completed` / `calibration_failed`;
- `tare`;
- `probe_series`;
- `reference_decision`;
- `mesh_selected` / `runtime_mesh_built` / `mesh_saved`;
- `offset_composed`;
- `job_offset_received`;
- `live_adjustment` / `live_adjustment_saved`;
- `hardware_change_suspected`;
- `safety_abort`;
- `first_layer_verification_started/completed/cancelled`;
- version/config identity.

Each relevant event should include enough provenance to answer:

```text
what value was measured?
what values were active?
what correction was applied?
where did each correction come from?
why was the result accepted or rejected?
what safety rule fired?
```

Logs must avoid secrets and should keep bounded retention (target order: tens to low hundreds of calibration/print events, not endless telemetry).

## 10. Backend state/API model

Exact schema versioning belongs to implementation, but the semantic state should cover at least:

```text
z_calibration:
  health
  state
  reference:
    value
    samples
    spread
    timestamp
    validity
  mesh:
    mode
    profile
    reference
    status
  offset:
    auto_alignment
    persistent_user
    slicer_job
    live_adjustment
    external_unknown
    effective
  first_layer:
    status
    timestamp
  safety:
    state
    last_abort
  diagnostics:
    last_event
```

Actions exposed through backend should be semantic operations, not UI-specific macros, for example:

- check Z;
- run full calibration;
- build runtime mesh;
- save current mesh as default;
- set/save persistent user trim;
- set/clear job offset;
- start optional first-layer verification;
- fetch diagnostic history.

Exact RPC names are implementation details to be fixed with API tests.

## 11. Frontend UX

### 11.1 Normal view

Normal users should see a concise state:

```text
Z calibration        Ready
Bed mesh             Saved + checked
Current Z-offset     +0.006 mm
Auto correction      +0.036 mm
User trim            -0.030 mm
Job offset            0.000 mm

[Check Z]
[Build bed mesh]
[Full calibration]
[Test first layer]
```

Job/live contributions appear only when non-zero/relevant.

Warnings explain the problem and next action rather than exposing macro numbers.

### 11.2 Advanced view

Advanced exposes:

- probe samples/statistics;
- mesh reference/profile;
- current reference and delta;
- every offset component and provenance;
- raw/secondary load-cell state when available;
- last safety decision;
- recent structured events;
- relevant Klipper/Z-Mod state.

## 12. Frontend rollout

Implementation order:

1. common backend/state/action contract;
2. Fluidd as the first full frontend using existing `src/ad5x/**` integration policy;
3. Mainsail parity after API stabilizes;
4. HelixScreen and Guppy adapters using the same contract;
5. KlipperScreen adapter after its AD5X runtime/platform work is independently accepted.

Pixel-identical UI is not required. Semantic state/actions and safety behaviour must be equivalent.

## 13. Reverse-engineering facts that constrain v2

The detailed evidence is recorded in `Z_CALIBRATION_REVERSE_ENGINEERING_2026-08-16.md`.

Key constraints:

- current `[probe] z_offset` is `-0.25 mm`;
- user-facing contact estimate and raw `probe at` differ by exactly that amount;
- `last_probe_position.z` matches the user-facing contact estimate;
- `WeightValue` from current `zmod_tenz.py` folds sign using `abs()`, while raw `H7` preserves sign;
- `LOAD_CELL_TARE` can accept near-zero, not only exact zero;
- mesh clear/load, G28 ordering and a full power-cycle did not reproduce/explain the one early ~0.3 mm anomaly;
- stable repeated probing later in the session is internally consistent around the current Bambu Mod geometry;
- the early `≈ -1.5167 mm` result is an unclassified non-reproduced anomaly and must not drive architecture;
- historical `MESH_DATA` absolute baseline is not comparable to the current hotend/carriage setup according to owner history;
- `GET_POSITION` did not reveal a hidden software coordinate shift of ~0.3 mm;
- H7 has transient/relaxation behaviour after motion/contact, so raw immediate readings require timing-aware interpretation.

## 14. Test strategy

The detailed test matrix is in `Z_CALIBRATION_TEST_PLAN_V2.md`.

Core rule:

> Safety-critical behaviour is proven in pure/model/fake-adapter tests before any equivalent real-printer path is exercised.

Repository tests must be broad and fast enough to run routinely. Heavy hardware acceptance is reserved for explicit gates, not every edit.

## 15. Migration from old Calibration Center

Closed issue #5 / Draft PR #6 are historical research artifacts.

Do **not** cherry-pick the old profile/correction architecture wholesale.

Useful lessons that may be carried forward only after re-evaluation:

- repeated measurement/statistics;
- explicit fail-closed calibration state;
- installer/uninstall isolation;
- first-layer test cancellation evidence;
- physically rejected test-pattern lessons;
- need to keep persistent user state untouched on failed tests.

Explicitly superseded:

- Z profiles per hotend/nozzle as the main product model;
- parallel hidden G92 correction model as the product contract;
- reliance on old absolute map baselines across different carriage/hotend geometry;
- any assumption that a single large delta should be directly applied.

## 16. Release acceptance principles

The subsystem is not release-ready until all of the following are true:

- no unbounded Z search path exists;
- failure injection proves persistent offset/mesh are not corrupted;
- large-delta handling is fail-closed;
- standard Klipper effective offset remains observable and compatible;
- slicer/job/live offset scopes cannot leak into the next print;
- runtime mesh cannot overwrite saved mesh without explicit user action;
- structured diagnostics explain decisions;
- controlled real-printer safety tests pass;
- representative temperature and actual hardware-change tests pass;
- optional first-layer verifier is physically accepted separately;
- install/update/uninstall/fallback preserve ordinary Z-Mod operation;
- frontend absence cannot make the backend unsafe;
- owner explicitly accepts the exact candidate before Ready/Merge.