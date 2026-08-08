# Calibration Center — algorithm and safety contract

## Product truthfulness

Calibration Center distinguishes two operations:

- **automatic physical-reference calibration** — contact measurement, repeatability validation and geometric delta calculation;
- **first-layer verification** — optional process validation which can establish/update a profile's `USER VERIFIED` correction.

For a brand-new hotend/nozzle profile with no verified process correction, a stable probe series is reported as `AUTO MEASURED`, not falsely promoted to `USER VERIFIED`.

Once a profile has a verified reference and verified print correction, subsequent calibrations can be automatic: fresh stable contact is compared with the verified reference and the resulting geometric delta is propagated using the same sign convention as current Z-Mod AutoZOffset.

## Preconditions — fail closed

`CC_CALIBRATE` must reject execution unless all applicable checks pass:

1. AD5X platform detected through `_CLIENT_VARIABLE.ad5x`.
2. Klipper is ready enough to expose `toolhead`, `print_stats`, `probe` and save variables.
3. `print_stats.state` is neither `printing` nor `paused`.
4. Z-Mod primitives `_G28`, `LOAD_CELL_TARE`, `_ORIG_CLEAR_NOZZLE` and `_SET_GCODE_OFFSET_FAST` are available in the supported compatibility baseline.
5. Profile slot exists and is selected.
6. Requested temperatures and repeatability threshold are within conservative configured bounds.

Any failed precondition aborts before contact probing.

## Measurement sequence

The initial implementation deliberately mirrors Z-Mod's own safe movement pattern rather than inventing coordinates.

1. Save the relevant current state.
2. Clear any stale Calibration Center temporary sample variables.
3. Prepare and clean the nozzle through the existing Z-Mod `_ORIG_CLEAR_NOZZLE` path.
4. Stabilise the nozzle at the configured measurement temperature and the bed at the calibration temperature.
5. Home through `_G28`.
6. Move XY to the centre derived from the current AD5X client limits (`(min_x+max_x)/2`, `(min_y+max_y)/2`).
7. For each independent measurement:
   - `LOAD_CELL_TARE`;
   - `PROBE`;
   - capture the result in a *separate macro invocation* so Klipper template evaluation observes the completed probe;
   - lift to `Z=5` using the same post-probe pattern present upstream.
8. Evaluate all five samples.
9. Reject the entire run if the range exceeds the configured threshold. No outlier is silently discarded to make an unstable series pass.
10. On success, store the median/mean/range as measurement evidence and update the profile's `AUTO MEASURED` reference.

The default repeatability gate is intentionally conservative and provisional until runtime acceptance. The implementation exposes it as a bounded parameter; it is not represented as a universal property of AD5X physics.

## Statistics

For five samples `z1..z5`:

- `min = min(z1..z5)`
- `max = max(z1..z5)`
- `range = max - min`
- `mean = sum / 5`
- `median = third value after sorting`

Acceptance requires `range <= max_range`.

The range is used for the hard gate because it makes a single divergent contact visible. Mean and median are both recorded; the median is the primary contact reference.

## Automatic correction model

For an already verified profile:

```text
fresh_reference    = median of accepted new probe series
verified_reference = physical reference stored when the profile was verified
reference_delta    = fresh_reference - verified_reference
candidate_effective = verified_effective + reference_delta
```

`reference_delta = fresh - saved` is the same sign convention used by current Z-Mod `_TEST_POINT` AutoZOffset.

The candidate is rejected if any safety bound is exceeded. The first implementation uses a configurable maximum absolute reference delta. Large jumps are treated as a changed/dirty/loose mechanical state, not automatically compensated.

## Applying Z

Calibration Center does not alter Klipper `[probe] z_offset` and does not write Flashforge `zProbeOffset`.

Runtime application is deliberately temporary and reversible:

- for native-screen mode, the platform's normal/native Z offset remains authoritative; Calibration Center's verified profile correction is applied as an explicit runtime adjustment;
- for screenless mode, the existing Z-Mod print-offset path remains authoritative and the same profile delta is layered on top.

The initial implementation exposes a dedicated apply/restore adapter and records the previous known-good Calibration Center value before replacing it.

No `SAVE_CONFIG`, MCU restart, MCU flash or USB reset is required by a calibration run.

## Profile state

Each profile stores separately:

- name;
- hotend type;
- nozzle diameter;
- last accepted auto-reference median;
- last measurement mean/range;
- verified reference, if any;
- verified effective correction, if any;
- current runtime/profile correction;
- previous known-good values for one-step rollback;
- calibration temperature metadata;
- state: `NEW`, `AUTO_MEASURED`, `USER_VERIFIED`, `REJECTED`.

The macros persist operational numeric/string values through Z-Mod/Klipper `save_variables`. An on-demand state helper writes an atomic JSON audit/history record with timestamps; it is not a daemon.

## First-layer verification

`CC_VERIFY` is the only operation that can mark a profile `USER_VERIFIED`.

The user may optionally run a test first layer and adjust the effective runtime Z. Once satisfied, `CC_VERIFY EFFECTIVE=<value>` records:

- the most recent accepted auto-reference as `verified_reference`;
- the supplied verified effective Z as `verified_effective`;
- previous verified values for rollback;
- status `USER_VERIFIED`.

This preserves the epistemic distinction between sensor measurement and a process result.

## Rollback

Before replacing a verified pair, Calibration Center copies it into the profile's previous-known-good fields. `CC_ROLLBACK` restores only Calibration Center profile state/runtime correction. It does not rewrite Flashforge native files or Klipper probe configuration.

## Abort and error handling

A failed probe, unavailable MCU/Klipper state or template error naturally aborts the G-code sequence. Calibration Center additionally ensures that `_CC_FINALIZE` refuses to save unless all five sample-valid flags were set.

An unstable series:

- is recorded as rejected evidence;
- never updates `verified_reference` or `verified_effective`;
- never applies a new candidate correction;
- instructs the user to check nozzle cleanliness/hotend seating.

## Compatibility guard

Because Calibration Center intentionally reuses current Z-Mod private safety primitives, the installer checks for the expected command/config baseline. If a later Z-Mod version removes or changes those primitives, installation/update must fail closed instead of guessing equivalent movement.

The stock Z-Mod calibration path remains untouched and available after install, disable or uninstall.
