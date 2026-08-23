# Z Calibration Production Policy v1 — saved+check owner RC

**Policy ID:** `zcal-saved-check-v1-20260817`  
**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Status:** OWNER RC / first-layer acceptance required before unattended use  
**Scope:** the current owner's Flashforge AD5X hardware, the validated saved `auto` mesh and the current Z-Mod 1.7 print lifecycle

> **2026-08-23 runtime correction.** Real-AD5X testing proved that Z-Mod skips `MESH_TEST=3` when a fresh mesh is built by `PRINT_LEVELING=1`, leaving the old persistent/global Z value applied to the new mesh. The corrected invariant is: **final mesh selected → load persistent baseline → exactly one native Z-Mod `_MESH_TEST` / AutoZOffset reconciliation → print**. Fresh mesh is no longer treated as `Auto-Z=0`. The absolute historical mesh center `-1.925833` is evidence only and is no longer a production hard gate; load-cell recalibration and rebuilt meshes can legitimately move absolute contact coordinates. Z-Mod remains the sole physical contact/Auto-Z owner.

Observed control case after load-cell calibration: `Probe=-1.7850`, `Mesh=-1.8125`, `Delta=+0.0275`, persistent `Z=-0.1010`, effective native result `Z=-0.0735`.

## 1. Purpose

This policy is the first owner-useful production release candidate for ordinary printing without manual Z-offset arithmetic.

It deliberately does **not** activate a second Plugins AD5X motion implementation. Z-Mod remains the production pre-print motion/contact engine. Plugins AD5X requires the final mesh selected for the job — saved or freshly built — to be followed by the native Z-Mod `MESH_TEST=3` AutoZOffset reconciliation before printing proceeds.

The intended invariant is:

```text
ordinary print request
→ Z-Mod selects or builds the final mesh for this job
→ persistent/global user Z baseline is loaded
→ exactly one final native Z-Mod MESH_TEST=3 AutoZOffset reconciliation
→ nozzle clean / tare / contact measurement owned by Z-Mod
→ Z-Mod temporary standard Klipper Z adjustment
→ Plugins AD5X validates the native result
→ accept and continue, or restore persistent global Z-offset and abort
```

This policy is evidence-bound to this printer and saved mesh. It is **not** a universal AD5X numeric default.

## 2. Required runtime mode

The guarded unattended path requires:

```text
screen                = false
LOAD_ZOFFSET          = 1
MESH_TEST             = 3
```

For a saved-mesh job the accepted profile remains `auto`. For a fresh-mesh job (`PRINT_LEVELING`, forced full leveling, or another accepted fresh-mesh path), Plugins AD5X requires the newly selected mesh to be followed by the same native `MESH_TEST=3` reconciliation instead of treating mesh creation as equivalent to Auto-Z.

`MESH_TEST=3` is intentional. Z-Mod mode 3 performs its existing AutoZOffset contact path but raises an error on its own large-delta condition instead of automatically falling back to KAMP. For this unattended policy, a large/mismatched condition must stop the job and require explicit review/full calibration rather than silently changing calibration strategy.

Fresh KAMP/full-leveling compatibility remains gated separately; no path may silently skip the final native Auto-Z reconciliation.

## 3. Accepted saved-mesh identity

The accepted saved profile is:

```text
profile = auto
```

Gate A raw matrix:

```text
-1.746667 -1.883333 -1.914167 -1.860000 -1.730833
-1.762500 -1.881667 -1.935833 -1.926667 -1.802500
-1.756667 -1.874167 -1.925833 -1.928333 -1.800833
-1.713333 -1.825833 -1.896667 -1.889167 -1.795833
-1.718333 -1.832500 -1.921667 -1.877500 -1.760000
```

Historical Gate A center/reference evidence:

```text
saved_reference = -1.925833 mm
```

This value is retained only as historical/observer evidence. **The absolute mesh center is not a production Z invariant.** Load-cell recalibration, mechanical service and a rebuilt mesh can legitimately move absolute contact coordinates while the persistent user Z baseline remains a separate quantity. The active RC guard therefore no longer rejects a job solely because the center differs from `-1.925833`.

For saved-mesh jobs, profile identity (`auto`) remains guarded. For fresh-mesh jobs, the final native probe-to-active-mesh delta and its bounded Auto-Z result are the relevant runtime evidence.

## 4. Hardware evidence

Policy sources:

- `docs/evidence/Z_CALIBRATION_GATE_A_BASELINE_2026-08-16.md`
- `docs/evidence/Z_CALIBRATION_GATE_B_RUN_001_2026-08-17.md`
- `docs/evidence/Z_CALIBRATION_GATE_C_RUN_001_2026-08-17.md`
- `docs/evidence/Z_CALIBRATION_GATE_C_RUN_002_PLA60_2026-08-17.md`
- `docs/evidence/Z_CALIBRATION_GATE_C_RUN_003_CLEAN_POWER_CYCLE_2026-08-17.md`
- diagnostic contrast only: `docs/evidence/Z_CALIBRATION_GATE_C_RUN_003_REBOOT_DIAGNOSTIC_2026-08-17.md`

Clean reference medians and implied Z-Mod alignment delta against the accepted saved center:

| Run | Condition | Median contact | Median − saved reference |
|---|---|---:|---:|
| Gate B 001 | ambient | `-1.986250` | `-0.060417 mm` |
| Gate C 001 | independent ambient | `-1.975000` | `-0.049167 mm` |
| Gate C 002 | bed 60 °C | `-1.990000` | `-0.064167 mm` |
| Gate C 003 clean | full power-cycle, ambient | `-1.982500` | `-0.056667 mm` |

Observed clean-series spread was `0.017500…0.025000 mm`, with standard deviation `0.005220…0.008764 mm`.

The largest absolute clean median alignment observed in these accepted runs is:

```text
0.064167 mm
```

The earlier diagnostic reboot run produced a shifted two-series level around `-1.951000 mm`, but that boot already contained camera-path kernel Oops events and is not accepted as clean reboot evidence. The subsequent clean full power-cycle did not reproduce that level.

**No reboot compensation is defined or permitted by this policy.**

## 5. RC Auto-Z alignment envelope

Accepted maximum absolute temporary Auto-Z alignment:

```text
abs(auto_alignment) < 0.120000 mm
```

The guard rejects `abs(auto_alignment) >= 0.120000 mm`.

Margin rationale:

```text
largest accepted clean median alignment = 0.064167 mm
RC limit                                = 0.120000 mm
absolute headroom                       = 0.055833 mm
limit / observed clean maximum          ≈ 1.87
```

This is deliberately much tighter than Z-Mod's current broad internal `abs(zdelta) < 0.31` acceptance for AutoZOffset. Z-Mod's value remains upstream behavior; Plugins AD5X RC adds the evidence-bound owner guard after that path.

A delta at or beyond `0.120000 mm` is classified operationally as **hardware change suspected / full calibration required**, not as permission for a larger automatic correction.

The value is an owner-RC policy for this hardware/mesh. It must be revisited after a nozzle/hotend/plate geometry change, a rebuilt accepted mesh, or contradictory field evidence.

## 6. Offset ownership and rollback behavior

For this RC path:

- Z-Mod loads the owner's persistent global Z-offset;
- Z-Mod performs its existing temporary AutoZOffset adjustment through ordinary Klipper `gcode_offset`;
- Plugins AD5X does not perform an additional production motion or Z-offset write;
- on policy rejection, the hook calls `LOAD_GCODE_OFFSET` before raising the abort so the persistent global baseline is restored and Z-Mod's temporary Auto-Z value is cleared;
- on acceptance, Plugins AD5X adopts the already-effective Z-Mod state into its lifecycle/diagnostics without applying the Auto-Z a second time;
- terminal print lifecycle still clears Plugins transient provenance state.

Therefore the existing Plugins-owned production motion and write gates remain closed for RC v1. This is intentional: the owner RC delegates those physical operations to the already-proven Z-Mod path rather than pretending a new Plugins adapter has been accepted.

## 7. Fail-closed conditions

Unattended saved+check must abort when any guarded condition is true:

- `MESH_TEST != 3`;
- active mesh profile is not the accepted `auto` profile;
- `abs(_TEST_POINT.temp_z_offset) >= 0.120000 mm`;
- the existing Plugins lifecycle hook/backend cannot complete its late adoption;
- Z-Mod itself aborts its preceding nozzle-clean/contact/mesh check.

The policy does not silently switch to a different saved profile, a large correction, automatic KAMP fallback or reboot compensation.

## 8. H7/load-cell role

Load-cell probing/tare remains part of the upstream Z-Mod motion path. Plugins AD5X continues to treat H7/load-cell telemetry as secondary safety evidence until separate latency/stopping evidence is sufficient for a stronger role.

No new H7 hard-stop threshold is introduced by this RC policy.

## 9. Owner acceptance boundary

On 2026-08-17 the owner explicitly requested acceleration from evidence gathering to a usable release-candidate path so an ordinary print can be started without manual Z-offset adjustment.

Repository/unit/CI acceptance is necessary but not sufficient for unattended use. Final owner acceptance of this RC requires **one short first-layer print test** through the real normal print path after deployment:

1. Z-Mod AutoZOffset executes automatically;
2. Plugins AD5X guard reports `saved+check PASS`;
3. first layer is visually normal without manual Z-offset correction;
4. no unexpected calibration/kernel/runtime fault appears.

After that owner-observed first-layer acceptance, the same unchanged hardware/mesh/policy may be used for the intended unattended print. Any geometry change or guard failure returns the system to explicit calibration/review instead of silently extending the policy.

## 10. Update and version rollback lifecycle

The canonical lifecycle exposes `install`, `update`, `repair`, `rollback`, `uninstall`, and `status`. Every mutation is preceded by a bounded transaction snapshot and followed by a Klipper reload plus live verification.

For `update`, the pre-update effective state is recorded only after the new version has passed live verification. If apply/reload/verification fails, the transaction is restored automatically. If the update technically succeeds but later proves undesirable on hardware, explicit `rollback` restores the previous successful snapshot, reloads Klipper, verifies the restored state, and preserves the version being left as the next undo point.

Rollback snapshots are accepted only from the managed Z Calibration backup root and must contain the productizer plan, transaction snapshot, and `plugins.cfg` snapshot. A missing or foreign rollback target fails closed without guessing. Each recorded snapshot also stores whether the pre-update runtime was an active ZCAL state or an intentionally inactive/parked state. Rollback to an active snapshot reruns the ZCAL live verifier; rollback to a parked snapshot requires the restored configuration to reload to Klipper-ready state instead of incorrectly demanding that the ZCAL policy be active. `uninstall` remains a separate operation that restores the original pre-ZCAL ownership/settings baseline rather than merely moving to the previous plugin version.

A parked update may also refresh a stale generated `zcal_owner_rc.cfg` whose hash no longer matches the old manifest, but only after proving all of the following: the policy include is absent, the live policy macro (including the legacy namespace) is absent, the effective `_USER_START_PRINT` body is the pristine owned baseline, the manifest still owns the exact generated policy path, and the destination is a regular non-symlink file. The stale file is captured in the transaction snapshot before replacement, so both automatic failure rollback and later explicit rollback restore the parked bytes exactly. Any unproven or active state still fails closed.

This lifecycle is deliberately independent of Git worktree state so future Z-Mod/Klipper updates can be compatibility-checked and the plugin can be updated or rolled back without modifying upstream Z-Mod files.

## 11. Deferred work

Not required for this RC first-layer/unattended-print objective:

- Plugins-owned real motion adapter for `full_calibration`;
- runtime mesh generation path;
- broader multi-frontend action UI;
- universal policy defaults for other AD5X machines;
- canonical packaging of the separate camera startup hardening proof.

Those remain follow-on work and must not block validation of the narrow owner-useful saved+check path.
