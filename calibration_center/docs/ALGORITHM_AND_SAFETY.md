# Calibration Center — algorithm and safety contract

## Product truthfulness

Calibration Center distinguishes two operations:

- **automatic physical-reference calibration** — contact measurement, repeatability validation and geometric-delta calculation;
- **first-layer verification** — optional process validation which can establish/update a profile's `USER VERIFIED` process correction.

For a brand-new hotend/nozzle profile with no verified process correction, a stable probe series is reported as `AUTO MEASURED`, not falsely promoted to `USER VERIFIED`.

Once a profile has a verified reference and process correction, subsequent profile changes can be handled automatically as long as the physical acceptance proves that the profile-specific process bias is sufficiently invariant. A fresh accepted contact series is compared with the profile's verified physical reference using the same `fresh - saved` sign convention as current Z-Mod AutoZOffset.

## Preconditions — fail closed

`CC_CALIBRATE` rejects execution unless all applicable checks pass:

1. AD5X is detected through `_CLIENT_VARIABLE.ad5x`.
2. Klipper is operational enough for the macro itself to execute and expose `print_stats`, `probe`, `bed_mesh` and save variables.
3. `print_stats.state` is neither `printing` nor `paused`.
4. Installer compatibility checks have established the required Z-Mod primitives: `_G28`, `LOAD_CELL_TARE`, `_ORIG_CLEAR_NOZZLE`, `_SET_GCODE_OFFSET_FAST`, `_USER_START_PRINT` and the AD5X client contract.
5. The selected profile exists.
6. Requested temperature/repeatability/delta limits remain inside conservative hard bounds.
7. Another Calibration Center run is not already active.

The plugin does not invent an `eboard ready` object that current public Z-Mod does not expose as a documented macro contract. If the MCU/load-cell path is unavailable, existing Z-Mod/Klipper homing, tare or probe commands fail naturally and no accepted profile result is committed.

The standalone installer also fails closed if Moonraker cannot prove `print_stats.state`; it does not treat an empty/unreachable response as “idle”.

## Measurement sequence

The implementation mirrors current Z-Mod safe movement/preparation primitives rather than inventing hidden coordinates.

1. Save the current G-code state.
2. Remember the currently loaded bed-mesh profile.
3. Mark the selected profile `needs_calibration=1` immediately. From this point it may not affect print Z unless the complete run is accepted.
4. Reset Calibration Center's five volatile sample slots.
5. Arm a delayed heater/state failsafe.
6. Prepare and clean the nozzle through current Z-Mod `_ORIG_CLEAR_NOZZLE`.
7. Stabilise nozzle and bed at the configured measurement temperatures.
8. Clear the currently loaded bed mesh for the measurement. A hotend/nozzle physical reference must not accidentally include a previously loaded mesh compensation.
9. Home through `_G28`.
10. Move XY to the centre derived from the configured AD5X client limits: `(min_x+max_x)/2`, `(min_y+max_y)/2`.
11. For each of five independent measurements:
    - `LOAD_CELL_TARE`;
    - `PROBE`;
    - capture the completed probe result in a separate macro invocation;
    - lift to `Z=5`.
12. Evaluate all five samples.
13. Reject the complete run if the range exceeds the configured threshold. No outlier is silently removed to manufacture a pass.
14. Reject an already verified profile if the new median differs from its verified physical reference by more than the configured maximum delta.
15. Only on full success persist median/mean/range/reference evidence and set `needs_calibration=0`.
16. Turn heaters off, restore the previous mesh and restore the saved G-code state.

The default `MAX_RANGE=0.030 mm` is deliberately provisional until the target AD5X runtime dataset exists. It is a conservative software gate, not a claim that every AD5X load cell has a universal 30 µm specification.

## Probe coordinate compatibility

Calibration Center follows the same Klipper-version distinction already used by current Z-Mod:

- older path: `printer.probe.last_z_result`;
- Klipper 13 path: `printer.probe.last_probe_position.z`.

A change of Klipper measurement convention is therefore treated as a compatibility concern rather than silently mixing two reference coordinate formats.

## Statistics

For five samples `z1..z5`:

- `min = min(z1..z5)`;
- `max = max(z1..z5)`;
- `range = max - min`;
- `mean = sum / 5`;
- `median = third value after sorting`.

Acceptance requires `range <= MAX_RANGE`.

The total range is used for the hard gate because it exposes any one divergent contact. Mean and median are recorded; median is the primary profile reference.

## Correction layers

For an already verified profile:

```text
fresh_reference    = median of the accepted new five-probe series
verified_reference = physical reference stored when the profile was USER VERIFIED
reference_delta    = fresh_reference - verified_reference
verified_bias      = process correction established by first-layer verification
```

`reference_delta = fresh - saved` matches the sign convention used by current Z-Mod `_TEST_POINT` AutoZOffset.

A large `reference_delta` is rejected as changed/dirty/loose mechanics instead of being blindly compensated.

## Interaction with Z-Mod MESH_TEST

This is intentionally mode-aware.

### `MESH_TEST=1/2`

Z-Mod does not apply its AutoZOffset correction. Calibration Center can therefore apply:

```text
verified_bias + accepted profile reference_delta
```

### `MESH_TEST=3/4`

Z-Mod already performs its own print-time `fresh probe - saved mesh reference` AutoZOffset during `_START_PRINT`.

Calibration Center **does not** add its profile `reference_delta` a second time. Nor does it algebraically subtract/replace the upstream delta: the Z-Mod mesh reference and Calibration Center's verified profile reference are different physical anchors, so treating them as interchangeable would be an unsupported assumption.

In these modes the accepted five-probe Calibration Center run is a required stability/profile-validity gate and the plugin layers only the separately verified process bias on top of the Z-Mod dynamic AutoZOffset.

This preserves Z-Mod's per-print dynamic bed/reference compensation without double counting a profile correction.

## Applying Z

Calibration Center never changes Klipper `[probe] z_offset` and never writes Flashforge `leftExtruderOffset.zProbeOffset`.

The platform's existing native/Z-Mod print-offset layer remains authoritative. Calibration Center applies only its own explicit runtime adjustment through the same `_SET_GCODE_OFFSET_FAST` mechanism already used by Z-Mod.

The documented Z-Mod `_USER_START_PRINT` hook runs after `_START_PRINT`. Calibration Center captures the actual runtime baseline there before applying profile correction; this prevents the first verification from assuming the native/Z-Mod base is zero.

No `SAVE_CONFIG`, MCU restart, MCU flash, firmware rollback, USB reset, USB unbind or USB bind is part of a calibration run.

## Profile readiness

Persistent profile readiness is independent from correction history.

- Creating a profile sets `needs_calibration=1`.
- Switching from one profile to another sets the newly selected profile `needs_calibration=1`.
- Starting any new calibration run sets `needs_calibration=1` before physical work begins.
- Only a completely accepted five-probe run sets it back to `0`.
- A failed/interrupted run preserves previous `USER VERIFIED` values for recovery but leaves the profile blocked from affecting print Z.

If an enabled selected profile has `needs_calibration=1`, `_USER_START_PRINT` emits a clear error and calls the normal Z-Mod `CANCEL_PRINT` path. The user can either complete Calibration Center calibration or explicitly `CC_DISABLE` and use stock Z-Mod behaviour. This is the intended fail-closed boundary.

## Profile state

Each profile keeps separate values for:

- name;
- hotend type;
- nozzle diameter;
- `needs_calibration` readiness flag;
- last accepted auto-reference median;
- last accepted mean/range;
- last rejected range/evidence marker;
- verified physical reference, if any;
- verified process bias, if any;
- accepted automatic profile delta;
- previous verified reference/bias pair for one-step rollback;
- calibration temperature metadata;
- logical state: `NEW`, `AUTO MEASURED`, `USER VERIFIED`, `REJECTED`;
- last result marker independent from the preserved known-good correction.

Operational profile values are persisted through Klipper/Z-Mod `save_variables`. The event-only `cc_audit.sh` appends a bounded timestamped audit log under `mod_data`; it is not a daemon and performs no polling.

## First-layer verification

The first-layer path is deliberately optional and is not presented as automatic calibration.

After a successful first `AUTO MEASURED` run, the user can print a real first-layer test and optionally use:

- `CC_LIVE_Z DELTA=-0.05`;
- `CC_LIVE_Z DELTA=-0.01`;
- `CC_LIVE_Z DELTA=+0.01`;
- `CC_LIVE_Z DELTA=+0.05`.

`CC_VERIFY_CURRENT` then stores:

- the latest accepted physical reference as `verified_reference`;
- the deliberate process correction as `verified_bias`;
- the previous verified pair for rollback;
- state `USER VERIFIED`.

For the first verification, the process bias is the deliberate live adjustment itself, not `current offset - 0`. For later verifications it is derived relative to the runtime baseline captured after Z-Mod `_START_PRINT`.

This preserves the epistemic distinction between a sensor measurement and an accepted extrusion result.

## Rollback

Before replacing a verified pair, Calibration Center copies it into previous-known-good fields. `CC_ROLLBACK` swaps that pair back while idle.

Rollback does **not** erase evidence that the latest physical probe run failed. If `last_result=REJECTED`, the profile remains `needs_calibration=1` until a new physical run succeeds.

Rollback never rewrites Flashforge native calibration files or Klipper probe configuration.

## Cleanup and error handling

Klipper/Jinja evaluates `action_raise_error()` while rendering a macro. Therefore `_CC_FINALIZE` deliberately contains **no** `action_raise_error` in its rejection branches.

Instead it queues:

1. rejection evidence/state preservation;
2. `_CC_CLEANUP`;
3. a separate `_CC_ERROR_*` macro.

This ensures heaters are turned off and state restoration commands are queued/executed before the user-facing error is raised.

The delayed failsafe also turns heaters off and attempts to restore mesh/G-code state if the run remains active too long. If Klipper itself enters a shutdown state during a hardware/probe failure, no macro can guarantee further motion/restoration; importantly, `needs_calibration` remains set and no newly accepted correction is committed.

## Native-base caveat

Calibration Center intentionally does not own or rewrite the Flashforge native `zProbeOffset`. If the user independently runs a native/stock Z calibration, that native base may change outside Calibration Center's profile history.

The current safe contract is therefore:

- stock calibration remains available as fallback;
- profile process bias remains a separate layer;
- after a meaningful native calibration/hotend change, rerun Calibration Center before relying on its profile.

Runtime acceptance must determine how stable the native base and profile bias are in the real A1-compatible-hotend workflow before any stronger automation claim is made.

## Compatibility guard

Calibration Center intentionally reuses current Z-Mod extension/safety primitives rather than forking them. The installer checks their presence and fails closed if the supported contract disappears.

The stock Z-Mod calibration path remains untouched and available after `CC_DISABLE` or uninstall.
