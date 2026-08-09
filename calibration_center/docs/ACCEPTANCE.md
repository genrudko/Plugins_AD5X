# CALIBRATION-CENTER-001 — acceptance matrix

Target runtime: Flashforge AD5X `192.168.1.196`.

This document separates repository evidence from physical printer evidence. A repository/CI pass does not prove load-cell repeatability or first-layer quality, and the latter must not be fabricated when the execution environment cannot reach the printer LAN.

## Status vocabulary

- **PASS (source/CI)** — demonstrated by repository structure, static/model tests or GitHub Actions.
- **PASS (physical, partial)** — physically observed on the target, but the broader acceptance gate still has remaining scenarios.
- **PENDING (runtime)** — requires the physical AD5X.
- **PENDING (UX)** — required product UX is not yet complete in the action-prompt Draft.
- **FAIL / REJECTED** — demonstrated violation or invalid evidence; must not be promoted to accepted calibration data.

## Required acceptance

| # | Requirement | Evidence / procedure | Status |
|---|---|---|---|
| 1 | Plugin installs without dirty upstream repositories | Installer refuses unknown printer state and pre-existing dirty Z-Mod/Klipper/Moonraker, writes only `mod_data`, and rechecks clean state. Runtime `--status` must show all three CLEAN. | PASS (source/CI), PASS (physical, partial) |
| 2 | Z-Mod / Klipper / Moonraker remain clean | No tracked upstream path is modified by the implementation. Verified during Draft installs on target. | PASS (source/CI), PASS (physical, partial) |
| 3 | Plugin is independently updateable | Dedicated git checkout + Moonraker `[update_manager calibration_center]`. | PASS (source/CI), PASS (physical, partial) |
| 4 | Multiple nozzle profiles can be created | 8 persistent slots; common Stock/A1 one-button actions plus generic macro API. | PASS (source/CI), PENDING (runtime UI breadth) |
| 5 | Profile selection works | `CC_PROFILE_SELECT`, active slot persisted; changing profile marks it `needs_calibration=1`. | PASS (source/CI), PASS (physical, partial) |
| 6 | Automatic calibration performs a real measurement procedure | `CC_CALIBRATE` performs cleaning/preparation, clears mesh compensation, then five independent `LOAD_CELL_TARE → PROBE → capture → lift` cycles. | PASS (source/CI), PASS (physical, partial) |
| 7 | Multiple measurements are performed | CI asserts exactly five calls and separate post-probe capture. Three clean-path physical series completed. | PASS (source/CI), PASS (physical, partial) |
| 8 | Unstable result is rejected | Full-series range gate; no outlier is silently dropped. A physical `Range=0.0600 mm` series was rejected fail-closed. | PASS (source/CI), PASS (physical, partial) |
| 9 | Stable result can be saved | Accepted median/mean/range/reference persist through `save_variables`; only success clears `needs_calibration`. | PASS (source/CI), PASS (physical, partial) |
| 10 | Previous verified calibration can be restored | Previous reference/bias/global-baseline tuple is retained and `CC_ROLLBACK` swaps it back while idle without erasing failed-probe evidence. | PASS (source/CI), PENDING (runtime) |
| 11 | FIRMWARE_RESTART preserves state | Persistent profile/readiness state is `save_variables`; volatile run state is intentionally reset. | PASS (design), PASS (physical, partial) |
| 12 | Reboot preserves state | Same persistence contract; audit/profile state lives under `mod_data`. | PASS (design), PENDING (cold reboot) |
| 13 | Normal printing uses the selected effective Z | `_USER_START_PRINT` applies a **transient G92 coordinate-origin layer** containing verified process bias, global-Z normalization and, with `MESH_TEST=1/2`, accepted profile delta. It does not execute `SET_GCODE_OFFSET` family commands. | PASS (source/model), PENDING (USER VERIFIED print) |
| 14 | Plugin does not interfere with an active print | Calibration/profile changes/rollback/disable reject printing/paused state. Live Z exists only inside the generated verification job and is bounded. | PASS (source/CI), PASS (physical, partial) |
| 15 | Uninstall restores stock behaviour | Removes only marked custom include/hook/update-manager entry and checkout; keeps user state; never rewrites stock calibration files. | PASS (source/CI), PENDING (runtime) |
| 16 | Idle load is practically zero | No daemon or permanent polling loop. Audit helper is event-only; delayed cleanup checks exist only while a CC transient print/test correction is active. | PASS (source), PENDING (`ps`/load observation) |
| 17 | No MCU firmware modifications | No MCU flash/update command in operational payload. | PASS (source/CI) |
| 18 | No USB resets | No USB reset/unbind/bind path in operational payload. | PASS (source/CI) |
| 19 | Ordinary-user profile rename/custom text | Macro API exists, but current Z-Mod action-prompt UX has no free-text input and the Draft does not add DOM hacks. | PENDING (UX) |
| 20 | Last successful calibration date visible in main UI | Timestamped event audit exists, but the action prompt does not yet read/render it. | PENDING (UX) |
| 21 | Built-in first-layer test is self-contained and does not manufacture false Z evidence | Material presets + generated virtual-SD patch exist. Revised generator uses rounded-bead spacing, continuous connectors, review pause and bounded isolated live Z. | PASS (source/CI), PENDING (revised physical run) |
| 22 | Calibration Center never changes the user's global/persistent Z-Mod offset | Operational print/live path is regression-tested to contain no executable `SET_GCODE_OFFSET`, `_SET_GCODE_OFFSET` or `_SET_GCODE_OFFSET_FAST`; CC uses reversible `G92` origin transforms instead and records the global baseline only as profile metadata. | PASS (source/CI), PENDING (physical before/after proof) |

## Physical evidence already recorded

### Clean-path automatic reference

A1-compatible hotend / 0.4 mm nozzle, final rubber-wipe path at ~150 °C:

- run #1: `Median=-0.48333`, `Mean=-0.48217`, `Range=0.01000 mm`;
- run #2: `Median=-0.49667`, `Mean=-0.49567`, `Range=0.01833 mm`;
- run #3: `Median=-0.48833`, `Mean=-0.48700`, `Range=0.00917 mm`.

Between-run median span is `0.01334 mm`. This is sufficient to continue first-layer product validation, but it does not replace the broader thermal/reinstall dataset.

### First built-in first-layer generator — REJECTED as calibration evidence

The first generated PLA test was physically run through normal Z-Mod `START_PRINT` at 210/60 °C. The ordinary working Z-Mod/Helix baseline shown before/around testing was approximately `-0.125...-0.130 mm`. The generated sheet had obvious separations along adjacent roads. Two live `-0.05 mm` steps moved the displayed value to about `-0.225 mm`; merging improved, but the patch still separated along print roads.

No `USER VERIFIED` value was saved. This result must **not** be interpreted as evidence that the correct process bias is `-0.100 mm` or that the correct global/runtime Z is `-0.225 mm`.

Two independent failures were exposed:

1. **Generator geometry:** the old patch used `line_spacing = line_width`, which leaves a theoretical gap for rounded deposited beads and can mimic a nozzle-too-high condition.
2. **Z-state isolation:** after the live-adjust experiments the operator later found the printer's Z-offset at `-0.225 mm` and had to restore it manually. Whether that exact value had already reached every persistent backing store was not separately instrumented during the run; operationally, the result is still a safety failure because the CC experiment altered the user's working Z state beyond the test boundary.

The operator then manually set approximately `-0.13 mm` and started an ordinary real sliced print. Camera evidence shows the large green first-layer region as substantially continuous/uniform, without the obvious longitudinal road gaps seen in the rejected CC patch. The camera view has screen/moire artifacts and partial toolhead occlusion, so this is **qualitative control evidence**, not a declaration of perfect first-layer metrology.

This strengthens the conclusion that `-0.225 mm` was an invalid CC experiment state rather than a newly discovered correct process offset.

### Revised isolation design

The next revision makes the boundary explicit:

- the user/Z-Mod global offset remains an independent persistent baseline;
- CC reads the saved `gcode_offsets.z` baseline but does not write it;
- profile print correction is a reversible `G92` coordinate-origin transform;
- first-layer live adjustment uses `G92` plus an immediate relative physical Z move so the change is visible now without changing `homing_origin`/global Z-offset;
- total test adjustment is capped at ±0.10 mm (and the negative limit is smaller for thinner generated layers);
- first-layer result may be saved only from the controlled review `PAUSE`;
- accept, abort, natural fall-through and external-cancel watchdog paths reverse only the CC `G92` test origin;
- profile metadata records `verified_global_z`; if the user later changes the global baseline, CC normalizes the verified profile in its own transient layer rather than rewriting the user's setting;
- re-verification absorbs the profile correction actually active at the test plus the final live delta before moving the verified physical/global anchors.

## Physical proof plan

### Gate A — installation and clean repositories

Only while the printer is idle:

1. Install the Draft branch using `CALIBRATION_CENTER_REF=codex/5-calibration-center-001`.
2. Run the plugin `--status` command.
3. Record exact Calibration Center checkout SHA.
4. Record Z-Mod/Klipper/Moonraker status; all must be `CLEAN`.
5. Perform one normal `FIRMWARE_RESTART` to load the new cfg. No MCU update/flash command is allowed.
6. Confirm `CALIBRATION_CENTER` appears and stock Z-Mod calibration remains available.

Any unknown printer state or dirty upstream repository is an acceptance failure.

### Gate B — safe probe repeatability

Start with the currently known-good mechanically seated hotend/nozzle and a clean bed.

1. Create/select the matching profile.
2. Run automatic calibration with the controlled condition: bed 60 °C, cleaning 240 °C, measurement 150 °C.
3. Observe all five contacts. Stop immediately on any abnormal motion/nozzle-bed collision tendency.
4. Record all five samples, median, mean and range from the audit evidence.
5. Later extend the current three clean-path runs toward a broader dataset under the same mechanical/thermal condition.
6. Calculate between-run variation of medians as well as each run's internal range.

The provisional per-run gate is `range <= 0.030 mm`. This threshold is not declared physically final until the broader target AD5X dataset exists.

### Gate C — thermal sensitivity

Only after Gate B demonstrates safe repeatability:

1. Repeat a small set at alternative controlled measurement temperatures within supported bounds.
2. Repeat with representative hot-bed conditions used in normal printing.
3. Determine whether contact reference shifts materially with nozzle/bed temperature.
4. If the shift is material, calibration temperature becomes part of profile validity rather than being hidden as noise.

### Gate D — revised initial process verification and global-Z isolation

For the current AUTO MEASURED A1/0.4 profile:

1. Before launching CC, record the actual user/Z-Mod global offset. Current manually restored working control is approximately `-0.13 mm`.
2. Launch the built-in PLA test through the material preset UI.
3. Confirm the prompt explicitly shows the global Z-Mod baseline separately from `CC профиль` and `test ΔZ`.
4. **Without pressing any live button yet**, confirm Helix's ordinary print-tune Z display still represents the same global baseline; the CC test must not rewrite it.
5. Inspect the revised bead-packed patch. If it already forms a good sheet at `test ΔZ=0`, do not adjust Z merely because the old generator needed `-0.10`.
6. If a real adjustment is required, use the smallest useful step. Total test ΔZ must refuse movement outside its bounded range.
7. After each step, confirm the CC prompt reopens and the displayed **global Z-Mod value remains unchanged** while only `test ΔZ` changes.
8. At patch completion, confirm the job enters review `PAUSE`.
9. First exercise **Без сохранения**. After cancellation/cleanup, confirm global Z-Mod is exactly the same value recorded in step 1.
10. Repeat once and exercise the **system Helix Cancel** path after a small test adjustment. Again confirm the global Z-Mod value is unchanged after cleanup.
11. Only after both isolation paths pass, perform the final visual run and use **Сохранить** if the sheet is physically good.
12. Confirm `USER VERIFIED` is stored while the global Z-Mod baseline remains unchanged.
13. Start an ordinary sliced print and confirm the verified profile produces the expected layer using transient CC correction, with no mutation of the global Z-Mod value.

**Any change of the global Z-Mod offset caused by CC is an immediate Gate D failure**, even if a later restore appears to repair it. The design requirement is isolation, not compensating persistence after the fact.

### Gate E — automatic return to a verified profile

This is the product-critical test:

1. Verify profile A (for example A1 / 0.4) once.
2. Switch to another nozzle/profile and operate it.
3. Reinstall profile A's hotend/nozzle mechanically.
4. Select profile A; it must become `needs_calibration=1`.
5. Run only automatic calibration; do not manually type an offset.
6. Confirm the profile becomes ready only after the complete five-probe run is accepted.
7. Start the first-layer print.
8. Confirm the layer is correct using the resulting effective Z.
9. Confirm the user's global Z-Mod baseline has not been rewritten by profile application.

If this fails consistently while contact repeatability is good, that is evidence that process bias is not invariant enough for the desired one-button workflow. The product must expose that physical boundary rather than disguise it.

### Gate F — reject/rollback/persistence

1. Confirm a verified, ready profile exists.
2. If a naturally unstable probe series occurs, confirm it is rejected, previous known-good values remain stored, and the profile becomes/stays blocked from affecting print Z. Do **not** deliberately contaminate the nozzle or induce unsafe mechanics to force a failure.
3. Confirm a print attempt with the enabled blocked profile is cancelled with a clear message.
4. Confirm `CC_DISABLE` returns to stock Z-Mod behaviour without deleting profile history or changing the global Z-Mod offset.
5. After a later successful physical run, confirm the profile becomes ready again.
6. Create a second verified process state and test `CC_ROLLBACK` while idle.
7. Perform `FIRMWARE_RESTART`; confirm profiles, readiness and verified values remain.
8. Cold reboot; confirm persistence again.

### Gate G — MESH_TEST interaction

Test the supported correction-layer modes explicitly:

1. With `MESH_TEST=1/2`, verify that accepted Calibration Center `reference_delta + verified_bias + global-baseline normalization` produces the expected effective Z through the transient G92 layer.
2. With `MESH_TEST=3/4`, verify Z-Mod performs its normal dynamic AutoZOffset and Calibration Center does not duplicate that geometric delta.
3. Confirm there is no doubled geometric correction.
4. Confirm neither mode rewrites the user's global Z-Mod offset.
5. Compare first-layer outcome and audit evidence between the two mode families.

Do not assume the two reference deltas are numerically interchangeable: their stored reference anchors differ.

### Gate H — uninstall/fallback

1. Record stock/Z-Mod calibration availability and global Z-offset before uninstall.
2. Run Calibration Center uninstall while idle.
3. Perform the normal config reload/restart needed by Z-Mod.
4. Confirm Calibration Center macros are gone.
5. Confirm stock Z-Mod calibration and normal print start still work.
6. Confirm the pre-existing global Z-offset is unchanged.
7. Confirm Z-Mod/Klipper/Moonraker remain clean.
8. Confirm no MCU firmware operation and no USB reset occurred.

## Research acceptance: `+0.040 mm` vs `-0.130 mm`

Repository evidence establishes that, on current AD5X Z-Mod, Flashforge `leftExtruderOffset.zProbeOffset` is consumed as a native print Z-offset, while Z-Mod AutoZOffset uses fresh nozzle contact as a **geometric delta** relative to an established mesh reference and layers that delta on the print offset.

Therefore the observed ~0.17 mm difference is a real difference in the practically required print correction **if both displayed numbers were native print-Z values**, but it is not evidence that the raw contact sensor itself was wrong by exactly 0.17 mm.

The remaining causal split — hotend seating/compliance, load-cell preload, tip geometry, contamination, thermal state, or a stable process-gap bias — requires physical Gates B–G. The implementation deliberately stores measured reference, verified process correction and verified global-Z baseline separately so those experiments can distinguish them.
