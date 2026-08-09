# Calibration Center — algorithm and safety contract

## Product truthfulness

Calibration Center distinguishes two operations:

- **automatic physical-reference calibration** — contact measurement, repeatability validation and geometric-delta calculation;
- **first-layer verification** — process validation which can establish/update a profile's `USER VERIFIED` process correction.

For a brand-new hotend/nozzle profile with no verified process correction, a stable probe series is reported as `AUTO MEASURED`, not falsely promoted to `USER VERIFIED`.

Once a profile has a verified reference and process correction, subsequent profile changes can be handled automatically as long as physical acceptance proves that the profile-specific process bias is sufficiently invariant.

## Preconditions — fail closed

`CC_CALIBRATE` rejects execution unless all applicable checks pass:

1. AD5X is detected through `_CLIENT_VARIABLE.ad5x`.
2. Klipper exposes the required `print_stats`, `probe`, `bed_mesh` and save-variable objects.
3. `print_stats.state` is neither `printing` nor `paused`.
4. Installer compatibility checks have established the required current Z-Mod primitives (`_G28`, `LOAD_CELL_TARE`, `_ORIG_CLEAR_NOZZLE`, cleaning primitives, `_USER_START_PRINT`, etc.). `_SET_GCODE_OFFSET_FAST` remains part of the upstream compatibility contract because current Z-Mod cleaning/start logic uses it; **Calibration Center's own print/live correction path does not execute it**.
5. The selected profile exists.
6. Requested temperature/repeatability/delta limits remain inside hard bounds.
7. Another Calibration Center measurement run is not already active.

If the MCU/load-cell path is unavailable, existing Z-Mod/Klipper homing, tare or probe commands fail naturally and no accepted profile result is committed.

The standalone installer also fails closed if Moonraker cannot prove `print_stats.state`; it does not treat an empty/unreachable response as “idle”.

## Measurement sequence

The implementation mirrors current Z-Mod safe movement/preparation primitives rather than inventing hidden coordinates.

1. Save the current G-code state.
2. Remember the currently loaded bed-mesh profile.
3. Mark the selected profile `needs_calibration=1` immediately.
4. Reset five volatile sample slots.
5. Arm a delayed heater/state failsafe.
6. Prepare and clean the nozzle through current Z-Mod `_ORIG_CLEAR_NOZZLE`.
7. Stabilise nozzle and bed at configured measurement temperatures.
8. Perform the final low-temperature mechanical rubber wipe.
9. Clear the loaded bed mesh for physical-reference measurement.
10. Home through `_G28` and move to the AD5X client-area centre.
11. Perform five independent `LOAD_CELL_TARE → PROBE → capture → lift` cycles.
12. Evaluate all five samples.
13. Reject the complete run if total range exceeds the configured threshold; no outlier is silently removed.
14. Reject an already verified profile if the new median differs from its verified physical reference by more than the configured maximum delta.
15. Only on full success persist evidence and set `needs_calibration=0`.
16. Turn heaters off and restore mesh/G-code state.

The default `MAX_RANGE=0.030 mm` is provisional until a broader target-AD5X runtime dataset exists.

## Probe coordinate compatibility

Calibration Center follows the Klipper-version distinction already used by current Z-Mod:

- older path: `printer.probe.last_z_result`;
- Klipper 13 path: `printer.probe.last_probe_position.z`.

A change of probe-result convention is treated as a coordinate-format change. A stable new reference can be accepted, but the old verified physical/process/global tuple becomes historical previous state and the profile returns to `AUTO MEASURED` until one new first-layer verification is performed. Cross-format deltas and rollback are prohibited.

## Statistics

For five samples `z1..z5`:

- `min = min(z1..z5)`;
- `max = max(z1..z5)`;
- `range = max - min`;
- `mean = sum / 5`;
- `median = third value after sorting`.

Acceptance requires `range <= MAX_RANGE`. Mean and median are recorded; median is the primary profile reference.

## Correction layers

For an already verified profile:

```text
fresh_reference    = median of accepted new five-probe series
verified_reference = physical reference stored when profile was USER VERIFIED
reference_delta    = fresh_reference - verified_reference
verified_bias      = accepted process correction
verified_global_z  = user/Z-Mod global baseline present at verification
current_global_z   = current saved user/Z-Mod global baseline
```

The persistent global baseline is explicitly **not owned by Calibration Center**.

For a print, Calibration Center calculates:

```text
global_comp = verified_global_z - current_global_z
```

Then:

- `MESH_TEST=1/2`: `cc_total = verified_bias + reference_delta + global_comp`;
- `MESH_TEST=3/4`: `cc_total = verified_bias + global_comp`, because Z-Mod already owns its differently anchored dynamic AutoZOffset.

A large physical `reference_delta` is rejected rather than blindly compensated.

## Applying Z — hard isolation boundary

Calibration Center never changes Klipper `[probe] z_offset`, never writes Flashforge `leftExtruderOffset.zProbeOffset`, and **does not execute the Z-Mod/Klipper `SET_GCODE_OFFSET` family in its print/live correction path**.

Physical testing of the first first-layer implementation showed why this boundary is necessary: after two experimental `-0.05 mm` live steps the operator later found the printer Z-offset at about `-0.225 mm` and had to restore the normal working value manually. Even without claiming which persistence layer had captured that exact value, a test-only adjustment escaping the test boundary is unacceptable.

The revised implementation uses Klipper's standard **G92 origin transformation** as a separate transient coordinate layer:

```text
current logical Z = g
requested transient correction = d
G92 Z=(g - d)
```

This changes the G-code origin/base-position used by future absolute moves without altering `gcode_move.homing_origin`, which is the coordinate status altered by `SET_GCODE_OFFSET`.

### Profile correction

At `_USER_START_PRINT`, after normal Z-Mod start logic, `_CC_PROFILE_TRANSIENT_APPLY` applies `cc_total` via `G92`. No immediate physical move is required because subsequent object G-code contains absolute Z moves.

A delayed profile-origin watchdog is armed only while a non-zero CC profile origin exists. While printing/paused it reschedules at a low rate; once print state leaves those states it reverses the exact G92 origin and stops. There is no idle `initial_duration` and no permanent polling daemon.

### Built-in first-layer live adjustment

For an immediate test step `d`, Calibration Center performs:

```gcode
G92 Z={current_gcode_z - d}
G91
G1 Z{d} F300
G90
```

The G92 part changes future absolute-Z mapping; the relative move applies the step physically immediately while keeping the generated layer's logical Z coherent.

One live step is limited to ±0.05 mm. Total test correction is limited to ±0.10 mm, with a tighter downward bound for generated layers thinner than 0.20 mm. If acceptable first-layer quality cannot be reached inside that bounded region, the test is rejected instead of inviting progressively larger nozzle-down movement.

## Profile readiness

- Creating a profile sets `needs_calibration=1`.
- Switching profiles sets the newly selected profile `needs_calibration=1`.
- Starting any new calibration run sets `needs_calibration=1` before physical work begins.
- Only a completely accepted five-probe run sets it back to `0`.
- A failed/interrupted run preserves previous `USER VERIFIED` values for recovery but leaves the profile blocked from affecting print Z.

If an enabled selected profile has `needs_calibration=1`, `_USER_START_PRINT` emits an error and uses normal Z-Mod `CANCEL_PRINT`. The user can complete Calibration Center calibration or explicitly `CC_DISABLE` and use stock Z-Mod behaviour.

## Profile state

Each profile keeps separate values for:

- name / hotend type / nozzle diameter;
- `needs_calibration`;
- last accepted auto-reference median, mean and range;
- last rejected evidence marker;
- auto probe-coordinate format;
- verified physical reference;
- verified process bias;
- **verified user/Z-Mod global-Z baseline**;
- accepted automatic profile delta;
- previous verified reference/bias/probe-format/global-Z tuple for one-step rollback;
- calibration temperature metadata;
- logical state: `NEW`, `AUTO MEASURED`, `USER VERIFIED`, `REJECTED`;
- last result marker independent from preserved known-good correction.

Operational profile values persist through `save_variables`. The event-only audit helper appends a bounded timestamped log; it is not a daemon.

## First-layer verification

The supported verification path is the generated virtual-SD first-layer test. Calibration Center does **not** expose its transient Z controls over an arbitrary ordinary print; this narrows the safety boundary and gives the plugin a deterministic review/cleanup lifecycle.

The generated test:

1. uses normal Z-Mod `START_PRINT`;
2. uses rounded-bead line spacing and continuous serpentine connectors;
3. starts with `test ΔZ=0` relative to whatever global/profile layers are active;
4. permits bounded isolated ±Z while lines are printing;
5. shows global Z-Mod, profile transient and test transient separately;
6. lifts and enters `PAUSE` after the patch;
7. allows `Сохранить` only from that review pause.

For a never-verified profile:

```text
new_verified_bias = final_test_live_delta
```

For an existing verified profile, the active profile transient may already contain old bias, accepted `auto_delta`, and global-baseline normalisation. Saving new physical/global anchors makes the latter components zero on the next print, so re-verification stores:

```text
new_verified_bias = profile_correction_actually_active_during_test
                    + final_test_live_delta
```

This preserves the same accepted effective print plane after the anchors move.

`CC_VERIFY_CURRENT` also stores the current `verified_global_z`, resets `auto_delta` to zero and moves the old verified tuple to previous history.

## Test cleanup and external cancel

Accept, no-save abort and natural file fall-through reverse the test G92 origin explicitly. A delayed first-layer watchdog is armed by the generated test only; if the operator uses the generic Helix/system cancel path, it detects that the job has ended, reverses the test G92 origin and stops rescheduling.

The separate profile-origin watchdog then removes any verified-profile G92 layer after print cancellation/end.

**Physical acceptance requires proving that the user/Z-Mod global offset is identical before and after every one of these paths.** A later compensating write is not acceptable; the requirement is that Calibration Center never writes that global value in the first place.

## Rollback

Before replacing a verified tuple, Calibration Center copies reference, bias, probe format and verified global-Z baseline into previous-known-good fields. `CC_ROLLBACK` swaps that tuple back while idle.

Rollback does not erase evidence that the latest physical probe run failed. If `last_result=REJECTED`, the profile remains `needs_calibration=1` until a new physical run succeeds.

Rollback never rewrites the user's global Z-Mod offset, Flashforge native calibration files or Klipper probe configuration.

## Measurement cleanup and error handling

Klipper/Jinja evaluates `action_raise_error()` while rendering a macro. Therefore `_CC_FINALIZE` contains no `action_raise_error` in rejection branches. It queues rejection evidence, `_CC_CLEANUP`, then a separate `_CC_ERROR_*` macro so heaters/state restoration happen before the user-facing error.

The measurement failsafe also turns heaters off and attempts to restore mesh/G-code state if the run remains active too long. If Klipper itself enters shutdown during a hardware/probe failure, no macro can guarantee further motion/restoration; importantly, `needs_calibration` remains set and no newly accepted correction is committed.

## Global/native-base caveat

Calibration Center does not own the Flashforge native `zProbeOffset` or the user/Z-Mod global `gcode_offsets.z` setting.

The current contract is:

- stock calibration remains available as fallback;
- user/Z-Mod global Z remains independently editable by the user/Helix/Z-Mod;
- Calibration Center records the global value at profile verification and normalises later changes inside its own transient layer;
- meaningful hotend/nozzle changes still require a fresh accepted physical Calibration Center run;
- if the user intentionally wants a changed global Z to redefine all existing profile process planes, those profiles should be re-verified rather than relying on implicit side effects.

## Compatibility guard

Calibration Center reuses current Z-Mod extension/safety primitives rather than forking them. The installer checks their presence and fails closed if the supported contract disappears.

The stock Z-Mod calibration path remains untouched and available after `CC_DISABLE` or uninstall.
