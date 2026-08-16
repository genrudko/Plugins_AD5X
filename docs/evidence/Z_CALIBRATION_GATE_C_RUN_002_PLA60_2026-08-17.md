# Z Calibration Gate C — repeatability run 002 (PLA bed 60 C)

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** HOT CENTER POSITION ESTABLISHED / TARE PENDING  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-c-002-pla-bed-60c-2026-08-17`
- condition class: representative owner PLA bed condition
- owner-selected bed target: `60 C`
- Plugins AD5X repository SHA at condition selection: `b45ec605da9c7c0fb31889cc096795fd23383fc8`
- Plugins AD5X repository SHA at heated preflight: `00881e8b9cab6c5c5322f481e2bc078d9b286ba0`
- hardware context: same post-adjustment AD5X setup as Gate A, Gate B run 001 and Gate C run 001; no physical change was reported before this run
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

## Purpose

Measure whether the nozzle↔bed reference changes materially when the bed is brought from ambient to the owner's representative PLA target of `60 C`.

This run deliberately changes the bed thermal condition only at first. The nozzle heater remains off during this condition so bed-temperature influence is not deliberately conflated with hotend heating. Passive nozzle warming from the heated bed/chamber is recorded rather than ignored.

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
- the nozzle heater remained off and nozzle temperature was `26.54 C` at that point;
- printer remained idle/standby;
- standard Klipper effective Z offset remained `0.0 mm`;
- saved `auto` was still the active runtime mesh before the measurement path began.

The `59.36 C` observation is retained exactly as measured. It is not rewritten as an assumed `60.00 C`, and no temperature tolerance policy is inferred from this one run.

## Heated read-only preflight

A second live read-only snapshot was taken after the bed had remained at its `60 C` target condition for additional time.

```text
heater_bed.temperature     = 60.13 C
heater_bed.target          = 60.0 C
heater_bed.power           = 0.0430253862
extruder.temperature       = 29.23 C
extruder.target            = 0.0 C
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 6.925833, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
bed_mesh.profile_name      = auto
printer.cfg SHA-256        = eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

The raw active `auto` matrix and saved profile map matched the prior baseline. The `6.925833` G-code Z with physical/toolhead Z `5.0` is the expected active-mesh transform at the center and is not a new standard Z offset.

Interpretation:

- the bed condition is observed essentially at the selected target (`60.13 C` actual, `60.0 C` target) with low maintenance power;
- the nozzle heater remains off, but the nozzle has passively warmed from `26.54 C` to `29.23 C`; this passive warming is part of the recorded physical condition and must not be mislabeled as a strictly unchanged nozzle temperature;
- standard Klipper effective Z offset remains `0.0 mm`;
- printer remains standby;
- the saved `auto` profile remains active and unchanged before runtime clear;
- the persistent-config guard exactly matches Gate B and Gate C run 001.

## Heated-condition runtime mesh clear + fresh homing

Commands:

```text
BED_MESH_CLEAR
G28
M400
```

Both commands returned `ok`. Post-G28 live state:

```text
heater_bed.temperature     = 60.02 C
heater_bed.target          = 60.0 C
heater_bed.power           = 0.1654182796
extruder.temperature       = 30.54 C
extruder.target            = 0.0 C
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [220.0375, 220.0, 220.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name      = ""
```

Saved profiles `MESH_DATA` and `auto` remained present with the same raw point matrices. Runtime mesh was cleared only; no saved profile was changed or deleted.

Interpretation:

- fresh ordinary homing completed under the heated-bed condition with all axes homed;
- standard Klipper effective Z offset remained `0.0 mm`;
- bed remained at the selected 60 C condition during homing (`60.02 C` actual, `60.0 C` target);
- nozzle heater remained off while passive nozzle temperature rose further to `30.54 C`;
- printer remained standby and no stop condition was observed.

## Heated-condition controlled center/non-contact positioning

Command path:

```text
G90
G1 X107.5 Y107.5 F3000
G1 Z5 F300
M400
```

The command returned `ok`. Post-move live state:

```text
heater_bed.temperature     = 59.96 C
heater_bed.target          = 60.0 C
heater_bed.power           = 0.0612670134
extruder.temperature       = 30.07 C
extruder.target            = 0.0 C
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 5.0, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 5.0, 0.0]
bed_mesh.profile_name      = ""
```

Saved `MESH_DATA` and `auto` profiles remained present and unchanged in the live profile map.

Interpretation:

- the physical/toolhead and G-code coordinates agree at the controlled no-mesh center position;
- standard Klipper effective Z offset remains `0.0 mm`;
- runtime mesh remains cleared;
- the bed remains effectively at the 60 C target condition (`59.96 C` actual);
- the nozzle heater remains off, with passive nozzle temperature `30.07 C`;
- printer remains standby and no stop condition is observed.

## Remaining planned path

```text
fresh LOAD_CELL_TARE
→ PROBE_ACCURACY SAMPLES=10
→ explicit Z5 retract
→ restore saved auto mesh at runtime
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter is permitted.

## Pending

- tare observation: PENDING
- raw 10-sample series: PENDING
- descriptive statistics: PENDING
- comparison with ambient runs: PENDING
- cleanup/persistence verification: PENDING
- stop condition observed: PENDING

This run cannot authorize or freeze any motion/search/correction threshold by itself.
