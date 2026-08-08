# CALIBRATION-CENTER-001 — acceptance matrix

Target runtime: Flashforge AD5X `192.168.1.196`.

This document separates repository evidence from physical printer evidence. A repository/CI pass does not prove load-cell repeatability or first-layer quality, and the latter must not be fabricated when the execution environment cannot reach the printer LAN.

## Status vocabulary

- **PASS (source/CI)** — demonstrated by repository structure, static/model tests or GitHub Actions.
- **PENDING (runtime)** — requires the physical AD5X.
- **FAIL** — demonstrated violation; must block acceptance.

## Required acceptance

| # | Requirement | Evidence / procedure | Status |
|---|---|---|---|
| 1 | Plugin installs without dirty upstream repositories | Installer refuses pre-existing dirty Z-Mod/Klipper/Moonraker, writes only `mod_data`, and rechecks clean state. Runtime `--status` must show all three CLEAN. | PASS (source/CI), PENDING (runtime) |
| 2 | Z-Mod / Klipper / Moonraker remain clean | No tracked upstream path is modified by the implementation. Verify after install on target. | PASS (source/CI), PENDING (runtime) |
| 3 | Plugin is independently updateable | Dedicated git checkout + Moonraker `[update_manager calibration_center]`. | PASS (source/CI), PENDING (runtime UI) |
| 4 | Multiple nozzle profiles can be created | 8 persistent slots; common Stock/A1 profile actions plus generic API. | PASS (source/CI), PENDING (runtime UI) |
| 5 | Profile selection works | `CC_PROFILE_SELECT`, active slot persisted via `SAVE_VARIABLE`. | PASS (source/CI), PENDING (runtime) |
| 6 | Automatic calibration performs a real measurement procedure | `CC_CALIBRATE` performs preparation then five independent `LOAD_CELL_TARE → PROBE → capture → lift` cycles. | PASS (source/CI), PENDING (physical) |
| 7 | Multiple measurements are performed | CI asserts exactly five calls. | PASS (source/CI), PENDING (physical) |
| 8 | Unstable result is rejected | Full-series range gate; no outlier is silently dropped. A rejected remeasure preserves an existing USER VERIFIED profile. | PASS (source/CI), PENDING (physical observation) |
| 9 | Stable result can be saved | Accepted median/mean/range and profile reference persist through `save_variables`. | PASS (source/CI), PENDING (physical) |
| 10 | Previous verified calibration can be restored | Previous reference/bias pair is retained and `CC_ROLLBACK` swaps it back while idle. | PASS (source/CI), PENDING (runtime) |
| 11 | FIRMWARE_RESTART preserves state | Persistent profile state is `save_variables`; volatile run state is intentionally reset. | PASS (design), PENDING (runtime) |
| 12 | Reboot preserves state | Same persistence contract; audit/profile state lives under `mod_data`. | PASS (design), PENDING (runtime) |
| 13 | Normal printing uses the selected effective Z | Documented `_USER_START_PRINT` hook applies verified bias and, when appropriate, Calibration Center geometric delta after Z-Mod start logic. `MESH_TEST=3/4` avoids double-applying Z-Mod AutoZOffset. | PASS (source/model), PENDING (first-layer print) |
| 14 | Plugin does not interfere with an active print | Calibration/profile selection/rollback/disable reject printing/paused state; live Z is explicitly limited to an active first-layer verification. | PASS (source/CI), PENDING (runtime) |
| 15 | Uninstall restores stock behaviour | Removes only marked custom include/hook/update-manager entry and checkout; keeps user state; never rewrites stock calibration files. | PASS (source/CI), PENDING (runtime) |
| 16 | Idle load is practically zero | No daemon, polling loop or periodic telemetry. Audit helper runs only on events. | PASS (source), PENDING (`ps`/load observation) |
| 17 | No MCU firmware modifications | No MCU flash/update command in operational payload. | PASS (source/CI) |
| 18 | No USB resets | No USB reset/unbind/bind path in operational payload. | PASS (source/CI) |

## Physical proof plan

### Gate A — installation and clean repositories

Only while the printer is idle:

1. Install the Draft branch using `CALIBRATION_CENTER_REF=codex/5-calibration-center-001`.
2. Run the plugin `--status` command.
3. Record exact Calibration Center checkout SHA.
4. Record Z-Mod/Klipper/Moonraker status; all must be `CLEAN`.
5. Perform one normal `FIRMWARE_RESTART` to load the new cfg. No MCU update/flash command is allowed.
6. Confirm `CALIBRATION_CENTER` appears and stock Z-Mod calibration remains available.

Any dirty upstream repository is an acceptance failure.

### Gate B — safe probe repeatability

Start with the currently known-good mechanically seated hotend/nozzle and a clean bed.

1. Create/select the matching profile.
2. Run automatic calibration with the standard condition: bed 60 °C, cleaning 240 °C, measurement 150 °C.
3. Observe all five contacts. Stop immediately on any abnormal motion/nozzle-bed collision tendency.
4. Record all five samples, median, mean and range from the audit evidence.
5. Repeat the complete calibration run at least 10 times under the same mechanical/thermal condition.
6. Calculate between-run variation of medians as well as each run's internal range.

The provisional per-run gate is `range <= 0.030 mm`. This threshold is not declared physically final until the target AD5X dataset exists.

### Gate C — thermal sensitivity

Only after Gate B demonstrates safe repeatability:

1. Repeat a small set at alternative controlled measurement temperatures within the supported bounds.
2. Repeat with a representative hot-bed condition used in normal printing.
3. Determine whether contact reference shifts materially with nozzle/bed temperature.
4. If the shift is material, calibration temperature becomes part of the profile validity contract rather than being hidden as noise.

### Gate D — initial process verification

For a profile with no USER VERIFIED correction:

1. Obtain a successful AUTO MEASURED reference.
2. Print a normal first-layer verification object.
3. Use the optional live controls only if required.
4. Once the layer is physically accepted, save `USER VERIFIED`.
5. Record the resulting process bias separately from the physical reference.

This gate is specifically where the motivating A1-compatible hotend case is tested. The implementation must not prefill `-0.170 mm`.

### Gate E — automatic return to a verified profile

This is the product-critical test:

1. Verify profile A (for example A1 / 0.4) once.
2. Switch to another nozzle/profile and operate it.
3. Reinstall profile A's hotend/nozzle mechanically.
4. Select profile A.
5. Run only automatic calibration; do not manually type an offset.
6. Start the first-layer print.
7. Confirm the layer is correct using the automatically updated effective Z.

If this fails consistently while contact repeatability is good, that is evidence that process bias is not invariant enough for the desired one-button workflow. The product must then expose that physical boundary rather than disguise it.

### Gate F — reject/rollback/persistence

1. Confirm a verified profile exists.
2. If a naturally unstable probe series occurs, confirm it is rejected and the prior verified profile remains selected/usable. Do **not** deliberately contaminate the nozzle or induce unsafe mechanics to force a failure.
3. Create a second verified state and test `CC_ROLLBACK` while idle.
4. Perform `FIRMWARE_RESTART`; confirm profiles and verified values remain.
5. Cold reboot; confirm persistence again.

### Gate G — uninstall/fallback

1. Record stock/Z-Mod calibration availability before uninstall.
2. Run Calibration Center uninstall while idle.
3. Perform the normal config reload/restart needed by Z-Mod.
4. Confirm Calibration Center macros are gone.
5. Confirm stock Z-Mod calibration and normal print start still work.
6. Confirm Z-Mod/Klipper/Moonraker remain clean.
7. Confirm no MCU firmware operation and no USB reset occurred.

## Research acceptance: `+0.040 mm` vs `-0.130 mm`

Repository evidence establishes that, on current AD5X Z-Mod, Flashforge `leftExtruderOffset.zProbeOffset` is consumed as a native print Z-offset, while Z-Mod AutoZOffset uses fresh nozzle contact as a **geometric delta** relative to an established mesh reference and layers that delta on the print offset.

Therefore the observed ~0.17 mm difference is a real difference in the practically required print correction **if both displayed numbers were native print-Z values**, but it is not evidence that the raw contact sensor itself was wrong by exactly 0.17 mm.

The remaining causal split — hotend seating/compliance, load-cell preload, tip geometry, contamination, thermal state, or a stable process gap bias — requires the physical Gates B–E. The implementation deliberately stores measured reference and verified process correction separately so those experiments can distinguish them.
