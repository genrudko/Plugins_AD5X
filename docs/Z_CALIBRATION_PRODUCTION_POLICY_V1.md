# Z Calibration Production Policy v1 — saved+check owner RC

**Policy ID:** `zcal-saved-check-v1-20260817`  
**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Status:** OWNER RC / first-layer acceptance required before unattended use  
**Scope:** the current owner's Flashforge AD5X hardware, the validated saved `auto` mesh and the current Z-Mod 1.7 print lifecycle

> **2026-08-23 runtime correction.** Real-AD5X testing proved that Z-Mod skips `MESH_TEST=3` when a fresh mesh is built by `PRINT_LEVELING=1`, leaving the old persistent/global Z value applied to the new mesh. The corrected invariant is: **final mesh selected → load persistent baseline → exactly one native Z-Mod `_MESH_TEST` / AutoZOffset reconciliation → print**. Fresh mesh is no longer treated as `Auto-Z=0`. The absolute historical mesh center `-1.925833` is evidence only and is no longer a production hard gate; load-cell recalibration and rebuilt meshes can legitimately move absolute contact coordinates. Z-Mod remains the sole physical contact/Auto-Z owner.

> **2026-08-23 pre-prime ordering correction.** Hardware logging proved `_USER_START_PRINT` is too late for fresh-mesh finalization: Z-Mod performs configured `CLEAR` line priming before the end hook. ZCAL therefore uses Z-Mod's documented custom `CLEAR` extension point as `_ADZ_PRIME_GATE`. Productization preserves prior `CLEAR`/`DISABLE_PRIMING`, routes `CLEAR` through the gate, keeps priming enabled so the gate runs, performs final native `_MESH_TEST` before delegated priming, and leaves the end hook as verification only for fresh mesh. Rollback/uninstall restore the prior priming settings.

> **2026-08-25 KAMP software-compatibility correction.** Interposing `_ADZ_PRIME_GATE` would otherwise hide the original `CLEAR` value from Z-Mod's purge router. The gate now preserves Z-Mod semantics after v6 anchor finalization: missing configured purge macros fall back to `LINE_PURGE`, and KAMP with `_CLEAR1..4` forces `LINE_PURGE`. The Auto-Z/machine-anchor step always completes before either route. This closes the software seam but does **not** by itself constitute owner hardware acceptance of unattended KAMP.

> **2026-08-25 purge selector contract.** Plugins AD5X exposes only Z-Mod purge algorithms whose callable macro exists in the audited AD5X configuration: `ORCA -> _CLEAR1`, `FF -> _CLEAR2`, `FF2 -> _CLEAR3`, `SCHREIDER -> _CLEAR4`, and `LINE -> LINE_PURGE`. `ADZ_SET_PURGE` changes only the persisted `adz_prime_delegate`; `clear` remains owned by `_ADZ_PRIME_GATE`, so machine-anchor finalization still precedes every purge. Update/repair preserve the current delegate and uninstall restores the pre-plugin `CLEAR`/delegate state. KAMP may temporarily execute `LINE_PURGE` for `_CLEAR1..4` without rewriting the user's selection. Z-Mod's UI/source also references `CLEAR_TRAP`, but the audited AD5X config defines `_CLEAR_TRAP` rather than callable `CLEAR_TRAP`; it is therefore not exposed until upstream semantics are unambiguous.

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
→ Z-Mod temporarily exposes the measured service delta through its native offset path
→ Plugins AD5X restores persistent user Z and transfers that delta into transient runtime mesh
→ verify anchor state and continue, or restore baseline and abort
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

Fresh KAMP/full-leveling software paths are routed through the same pre-prime native Auto-Z and v6 machine-anchor finalization. Unattended KAMP remains hardware-acceptance gated; no path may silently skip final reconciliation.

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

## 5. v6 machine-anchor transfer

The fast mesh remains **relative shape** and the slow final probe is the **absolute machine anchor**. Z-Mod measures `native_delta = slow_final_probe - fast_mesh_reference`. v6 does not treat any observed delta as an expected correction. It preserves the physical identity explicitly:

```text
v5: fast_mesh + (persistent_user_offset + native_delta)
v6: (fast_mesh + native_delta) + persistent_user_offset
```

Plugins AD5X therefore restores the persistent user offset and moves the same measured `native_delta` into a **transient runtime mesh**. The pristine/saved mesh is never overwritten. After transfer, `homing_origin.z` again represents the real user correction rather than `user + service anchor`.

Observed deltas `+0.1150`, `+0.1300`, and `+0.1475 mm` are evidence that common-mode is run-dependent, not a target. No `expected_reconciliation_delta` exists in v6. The only numeric acceptance boundary is `abs(native_delta) < 0.310000 mm`, mirroring Z-Mod `_TEST_POINT`. `0.310000 mm` is a fail-closed plausibility limit, **not an expected correction**, calibration constant, or compensation term.

## 6. Offset ownership and rollback behavior

For v6:

- Z-Mod loads the persistent global user Z-offset and temporarily applies its measured `zdelta`;
- Plugins AD5X requires `final_probe_completed=1`;
- `LOAD_GCODE_OFFSET` restores the real user Z-offset;
- `ADZ_MESH_ANCHOR` applies `zdelta` to an in-memory bed-mesh copy;
- `machine_anchor_finalized=1` must agree with `ad5x_z_mesh_anchor.active=true`;
- runtime anchor state is never persisted with `SAVE_CONFIG` or `BED_MESH_PROFILE SAVE`;
- the `virtual_sdcard:reset_file` job boundary, explicit reset/disable actions, rollback and uninstall clear transient anchor state;
- manual `ADZ_CHECK` restores user Z after its diagnostic `_MESH_TEST`.

The semantic model is therefore **mesh shape + transient machine anchor + user Z-offset**. A user Z such as `-0.0910 mm` may coexist with a service anchor such as `+0.1375 mm` without contaminating the displayed user offset.

## 7. Fail-closed conditions

Unattended saved+check must abort when any guarded condition is true:

- `MESH_TEST != 3`;
- active mesh profile is not the accepted `auto` profile;
- the scoped precision final probe did not complete;
- `abs(native_delta) >= 0.310000 mm`;
- transient mesh-anchor runtime state and `machine_anchor_finalized` disagree;
- the existing Plugins lifecycle hook/backend cannot complete its late adoption;
- Z-Mod itself aborts its preceding nozzle-clean/contact/mesh check.

The policy does not silently switch to a different saved profile, apply a second common-mode correction, select automatic KAMP fallback, or introduce reboot compensation.

## 8. H7/load-cell role

Load-cell probing/tare remains part of the upstream Z-Mod motion path. Plugins AD5X continues to treat H7/load-cell telemetry as secondary safety evidence until separate latency/stopping evidence is sufficient for a stronger role.

No new H7 hard-stop threshold is introduced by this RC policy.

## 9. Owner acceptance boundary

On 2026-08-17 the owner explicitly requested acceleration from evidence gathering to a usable release-candidate path so an ordinary print can be started without manual Z-offset adjustment.

Repository/unit/CI acceptance is necessary but not sufficient for unattended use. Final owner acceptance of this RC requires **one short first-layer print test** through the real normal print path after deployment:

1. Z-Mod AutoZOffset executes automatically;
2. Plugins AD5X guard reports `Z v6 PASS` with separate machine-anchor and user-Z values;
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

## AD5X measurement policy validated 2026-08-25

The release-candidate measurement policy is `adz-metrology-mesh5-median3-final05-median3-anchor-v5-20260825`: bed-mesh acquisition is a fast relative-shape scan at **5 mm/s**, **3** samples and **median**, while the final in-mesh reconciliation probe remains the precision absolute-Z measurement at **0.5 mm/s**, **3** samples and **median**. This split limits exposure of the relative mesh shape to the long slow-scan failure mode seen in first-layer acceptance. Time-domain drift and speed-dependent local mechanics remain hypotheses for that spatial error, not established root causes. The native edge-cleaning probe keeps Z-Mod's own probe defaults; its tare is reused for the immediately following final reconciliation probe during an active print. Plugins AD5X still delegates physical tare/probe/motion to Z-Mod.

The measurement policy is deliberately **scoped, not global**. Idle/manual Z-Mod paths (`BED_MESH_CALIBRATE`, `AUTO_FULL_BED_LEVEL`, and manual `KAMP`) pass through with upstream parameters and semantics. Plugins AD5X applies `5 mm/s / median3` only to a fresh mesh acquired during an active print and to explicit Plugins AD5X production actions such as `ADZ_REBUILD_AUTO` / `ADZ_BUILD_RUNTIME_MESH`. There is no global `[probe]` override. `ADZ_REBUILD_AUTO` mirrors Z-Mod's current clean -> full mesh -> park -> stop sequence but invokes the Plugins-owned scoped mesh command, then records the accepted `auto` fingerprint.

A rebuilt `auto` profile follows normal Klipper profile persistence semantics: the new profile is live and fingerprinted immediately, but `SAVE_CONFIG` is still required if the owner wants that profile to survive a Klipper restart. Plugins AD5X does **not** call `SAVE_CONFIG` automatically because that command would also commit unrelated pending configuration changes. Therefore profile persistence and fingerprint persistence must be kept intentionally in sync before a restart. Temporary `ad5x_runtime` profiles are explicitly removed after restoring `auto`, preventing an unrelated later `SAVE_CONFIG` from persisting them.

Split-speed hardware runs on 2026-08-25 produced native Z-Mod reconciliation deltas of `+0.1150`, `+0.1300`, and `+0.1475 mm`. These are run-specific common-mode translations, not an expected center. v6 intentionally removes the old `+0.1300 ± 0.0500 mm` diagnostic envelope and retains only Z-Mod's own `abs(delta) < 0.310000 mm` plausibility boundary.

The production-path identity is unchanged. For `mesh=-2.0025`, `probe=-1.8650`, persistent user `Z=-0.0910`, the measured delta is `+0.1375`: v5 represented the physical sum as `-2.0025 + (+0.0465) = -1.9560`, while v6 represents it as `(-2.0025 + 0.1375) + (-0.0910) = -1.9560`. v6 is preferred because the displayed/user-owned Z-offset remains the actual `-0.0910 mm`.

The experimental v4 policy incorrectly subtracted a fixed `0.1300 mm` after native anchoring. v5 proved that the measured native anchor can work physically; v6 keeps that metrology but moves the service delta out of `gcode_offset` and into a transient runtime mesh.

First-layer acceptance on 2026-08-25 rejected the all-slow mesh policy: the 80x80 layer was spatially non-uniform, with adjacent lines locally under-squished by roughly 0.02-0.03 mm. The slow 5x5 scan and the prior saved map had almost zero mean shift but local point differences spanning about 0.073 mm. This proves the all-slow policy is unsuitable for mesh shape even though center reconciliation remained repeatable.

Hardware evidence: stock-like full native Auto-Z produced a 40 µm delta range. With 0.5 mm/s / median3 / no second center tare, five independent full native cleaning cycles produced center medians `-1.9025, -1.9050, -1.9000, -1.9000, -1.8975` (7.5 µm range). A fresh 5x5 mesh under the same policy had center `-1.9000`; final no-retare reconciliation was `-1.9075` (delta -7.5 µm). A subsequent saved-mesh cycle returned `-1.8925` against the same center (delta +7.5 µm).

Saved-mesh compatibility is fail-closed: the plugin fingerprints the accepted `auto` mesh with policy id, profile name, and exact probed matrix. Old 5 mm/s / average3 meshes are not mixed with 0.5 mm/s reconciliation. A measurement-policy upgrade invalidates this fingerprint once; a fresh `auto` must be built before saved-mesh Auto-Z is accepted. Rollback/uninstall restores pre-plugin saved-variable state.
