# CALIBRATION-SUBSYSTEM-002 — RC Productization repository acceptance

**Date:** 2026-08-18  
**Scope:** repository/fake acceptance only; this document does **not** claim a new physical-printer acceptance.  
**Issue:** #13  
**Draft PR:** #14  
**Branch:** `feature/z-calibration-subsystem-v2`  
**Base:** `dev`

## 1. Purpose

This evidence records the canonical repository implementation that productizes the owner-accepted manual RC v1 deployment without taking ownership of Z-Mod's physical Auto-Z/contact path.

The accepted production shape is:

```text
Z-Mod physical Auto-Z/contact
        ↓
existing winning _USER_START_PRINT owner
        ↓
optional CC_APPLY_PROFILE compatibility call
        ↓
_AD5X_Z_SAVED_CHECK_POLICY
        ↓
standard Klipper effective gcode_offset
```

Plugins AD5X does not introduce a second probe/motion/contact implementation.

## 2. Productization commits

Repository-green implementation sequence:

```text
ed3b974fd2a4246dde1a145b8bbd0610e18f175e
  feat(zcal): productize owner RC hook lifecycle

259c1d24d7a8c48fedb143125504f86b8bfbd802
  fix(zcal): reload Klipper across product lifecycle

814455b13646fe9fa4fbcdd5b1de4c42aef58d84
  feat(zcal): add worktree-neutral RC lifecycle

5a604daf64340747dafc0630ad56becf232ff14e
  test(zcal): narrow worktree-neutral assertion

5d28972c0dc13e385e64332a5ac8cbf7c417d76f
  feat(zcal): expose read-only offset provenance
```

At `5d28972c0dc13e385e64332a5ac8cbf7c417d76f`:

```text
Z Calibration Core    run 32176301856  SUCCESS
Z Calibration Actions run 32176301990  SUCCESS
```

`dev` remained the branch base and the feature branch was `behind_by=0` before this evidence-only update.

## 3. Canonical RC lifecycle

`installer/z_calibration_productization.py` now owns deterministic classification, snapshot, patch, repair and restore of the user extension hook and RC-owned state.

Supported proven hook bodies are deliberately narrow:

```text
empty
CC_APPLY_PROFILE
_AD5X_Z_SAVED_CHECK_POLICY
CC_APPLY_PROFILE + _AD5X_Z_SAVED_CHECK_POLICY
```

Rules:

- the winning owner is resolved from the effective Moonraker/Klipper body plus the include graph, not from a naive physical-section count;
- a foreign/unexpected hook fails closed;
- duplicate guard calls fail or are repaired only when ownership is already proven;
- install/update/repair are idempotent;
- the original hook bytes are retained for byte-for-byte uninstall restore;
- previous `MESH_TEST` and `CC_ENABLED` presence/value are retained and restored;
- generated policy ownership is tracked and foreign replacement is never overwritten or removed;
- an already-manually-patched RC is adopted only when compatible legacy backup evidence proves the pre-RC baseline;
- transaction rollback covers hook owner, `variables.cfg`, generated policy and ownership state.

The old `z_calibration.cfg` no longer declares `_USER_START_PRINT` and no longer calls a backend remote method. It is a compatibility include seam only.

## 4. Effective-runtime transaction boundary

Disk mutation alone is insufficient because Klipper must reload its config.

The canonical lifecycle therefore crosses a bounded Moonraker/Klipper transition and uses Moonraker's firmware-restart API before accepting the new effective state.

Uninstall retains ownership provenance until the reloaded runtime proves all of the following:

- effective hook body equals the recorded original baseline;
- RC policy macro is absent;
- previous `MESH_TEST` is restored;
- previous `CC_ENABLED` is restored.

Only after this proof is the ownership manifest finalized/removed.

Rollback restores both filesystem bytes and the effective Klipper config.

## 5. Worktree-neutral Z Calibration entrypoint

`installer/z_calibration_rc_lifecycle.sh` is the canonical Z Calibration lifecycle entrypoint for:

```text
install
update
repair
uninstall
status
```

It deliberately contains no Git operation.

Its source may be materialized from an exact Git object/commit into a staging directory and executed from there. It must not switch, reset or clean the live `ad5x_custom` worktree.

This is required because the live worktree may be on an unrelated ongoing feature branch such as IFS. Z Calibration productization is not allowed to change that branch, HEAD or unrelated files.

## 6. Read-only backend provenance

The accepted RC backend is now an observer/explainer, not a production Z writer.

`moonraker/components/plugins_ad5x.py`:

- registers no `plugins_ad5x_z_job_start` remote method;
- performs no `run_gcode` call;
- reports Z-Mod as the motion owner;
- reports `offset_write_enabled=false`;
- reads standard Klipper/Z-Mod objects and reconciles them into the frontend-neutral snapshot.

Exact live Z-Mod source baseline used to define provenance semantics:

```text
ghzserg/z_ad5x branch 1.7
commit 2e32155d00e464094b8c7197e23783ec821a112c
reported live version 1.7.2-5
```

For the accepted `screen=False + load_zoffset=1` global path, exact Z-Mod source proves:

- `save_variables.variables.gcode_offsets.z` is persisted/global Z with `_TEST_POINT.temp_z_offset` removed when it is saved;
- `_TEST_POINT.temp_z_offset` is the temporary saved-mesh Auto-Z alignment applied with `Z_ADJUST`;
- `START_PRINT Z_OFFSET` is ignored when global Z-offset control is active.

Therefore the current accepted RC decomposition is:

```text
persistent_user = save_variables.variables.gcode_offsets.z
Auto-Z          = gcode_macro _TEST_POINT.temp_z_offset
slicer_job      = 0 on the accepted global path
effective       = gcode_move.homing_origin.z
```

and:

```text
external_unknown = effective - (persistent_user + Auto-Z)
```

within reconciliation tolerance.

An arbitrary residual is **not** labelled `live_adjustment`. Static Klipper state does not prove that provenance. Until a future explicit Plugins AD5X live-adjustment action can attribute it, the residual remains `external_unknown`.

The owner-accepted example is covered directly by repository tests:

```text
persistent_user  -0.030000 mm
Auto-Z           +0.014166 mm
slicer_job        0.000000 mm
live_adjustment   0.000000 mm
external_unknown  0.000000 mm
──────────────────────────
effective        -0.015834 mm
```

## 7. What is repository-proven

Repository tests now cover the requested productization risks, including:

- stock empty extension;
- `CC_APPLY_PROFILE` only;
- already-patched expected chain;
- foreign hook;
- duplicate guard;
- missing owner;
- resolvable and ambiguous duplicate physical definitions;
- install/update idempotence;
- partial-state repair;
- transaction rollback at mutation boundaries;
- byte-for-byte hook restore;
- prior `MESH_TEST` restore;
- prior `CC_ENABLED` restore;
- no Plugins-owned `PROBE`, `G0/G1` or production `SET_GCODE_OFFSET` path;
- no checkout/reset/clean in the canonical Z Calibration lifecycle;
- unrelated runtime/IFS state untouched by productization tests;
- effective Klipper reload across apply/uninstall/rollback;
- accepted real offset composition provenance;
- requested slicer Z-offset reported as ignored on the accepted global path;
- unknown residual retained as `external_unknown` rather than guessed as babystepping;
- malformed/missing provenance sources degrade without fabricating values;
- runtime hook/policy identity detection for the productized chain.

## 8. What is **not** yet proven

This repository acceptance does not replace a controlled physical-printer gate.

Still pending after repository-green state:

1. deploy/update/repair through the canonical worktree-neutral lifecycle on the real AD5X;
2. prove that the active IFS branch/HEAD/files remain unchanged;
3. prove effective hook/policy identity after Klipper reload;
4. prove backend snapshot on the actual accepted print path exposes the expected persistent + Auto-Z composition with zero unexplained residual;
5. uninstall/rollback/power-cycle regression on hardware;
6. only after those gates, continue to frontend productization/Calibration Center UI.

No frontend is allowed to implement safety or offset-composition math independently.
