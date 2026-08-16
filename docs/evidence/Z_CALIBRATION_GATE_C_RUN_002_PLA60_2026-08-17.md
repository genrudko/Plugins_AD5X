# Z Calibration Gate C — repeatability run 002 (PLA bed 60 C)

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** HEATED CONDITION ESTABLISHED / PREFLIGHT PENDING  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-c-002-pla-bed-60c-2026-08-17`
- condition class: representative owner PLA bed condition
- owner-selected bed target: `60 C`
- Plugins AD5X repository SHA at condition selection: `b45ec605da9c7c0fb31889cc096795fd23383fc8`
- hardware context: same post-adjustment AD5X setup as Gate A, Gate B run 001 and Gate C run 001 unless a later section records a physical change
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

## Purpose

Measure whether the nozzle↔bed reference changes materially when the bed is brought from ambient to the owner's representative PLA target of `60 C`.

This run deliberately changes the bed thermal condition only at first. The nozzle remains unheated during this condition so bed-temperature influence is not conflated with hotend thermal expansion. A later condition may test a heated nozzle separately if required by the evidence.

## Previous repeatability context

```text
Gate B ambient mean   = -1.985500 mm
Gate C ambient mean   = -1.973000 mm
ambient mean delta    = +0.012500 mm
```

These values are descriptive evidence only and do not define an acceptance band.

## Heated condition establishment

Owner selected `60 C` as the representative PLA bed target.

Command:

```text
M190 S60
```

The command returned normally. Immediate live state after the heater wait:

```text
heater_bed.temperature   = 59.36 C
heater_bed.target        = 60.0 C
heater_bed.power         = 0.1141456259
extruder.temperature     = 26.54 C
extruder.target          = 0.0 C
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = auto
```

Interpretation:

- the ordinary Klipper heater wait accepted the 60 C target condition and returned normally;
- the bed was measured at `59.36 C` immediately after return, with target still `60.0 C`;
- the nozzle remained ambient/unheated at `26.54 C`;
- printer remained idle/standby;
- standard Klipper effective Z offset remained `0.0 mm`;
- saved `auto` was still the active runtime mesh before the measurement path began.

The `59.36 C` observation is retained exactly as measured. It is not rewritten as an assumed `60.00 C`, and no temperature tolerance policy is inferred from this one run.

## Planned path

```text
bed target 60 C
→ record actual bed/nozzle temperatures after heater wait
→ read-only preflight / persistence guard
→ runtime mesh clear only
→ fresh G28
→ X107.5/Y107.5/Z5
→ fresh LOAD_CELL_TARE
→ PROBE_ACCURACY SAMPLES=10
→ explicit Z5 retract
→ restore saved auto mesh at runtime
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter is permitted.

## Pending

- read-only preflight and pre-run `printer.cfg` hash: PENDING
- fresh homing result: PENDING
- tare observation: PENDING
- raw 10-sample series: PENDING
- descriptive statistics: PENDING
- comparison with ambient runs: PENDING
- cleanup/persistence verification: PENDING
- stop condition observed: PENDING

This run cannot authorize or freeze any motion/search/correction threshold by itself.
