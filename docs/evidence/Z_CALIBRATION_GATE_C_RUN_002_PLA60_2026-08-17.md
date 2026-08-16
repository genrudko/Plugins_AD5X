# Z Calibration Gate C — repeatability run 002 (PLA bed 60 C)

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** MEASUREMENT COMPLETE / CLEANUP PENDING  
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

## Heated-condition load-cell tare

Command:

```text
LOAD_CELL_TARE
```

Z-Mod returned the command as `ok` and reported:

```text
H1 > command H1 ok. 8431997
N 1. Вес: 80.0
H1 > command H1 ok. 8430826
N 2. Вес: 20.0
Сброс тензодатчка: ОК. Вес: 80.0->20.0
```

This observation is retained exactly. It differs from the previous ambient runs (`60→0 g` in Gate B and `0→0 g` in Gate C run 001): this heated-condition tare required the second observation and ended at a reported residual `20 g`, while Z-Mod itself still classified the tare as `ОК`.

No new numeric tare acceptance threshold is inferred from this result. The `20 g` residual is retained as secondary H7/tare evidence and considered together with the independent contact series rather than silently normalized to zero or discarded.

## Heated-condition independent 10-sample reference series

Command:

```text
PROBE_ACCURACY SAMPLES=10
```

Klipper/Z-Mod reported:

```text
PROBE_ACCURACY at X:107.500 Y:107.500 Z:5.000
samples=10 retract=2.000 speed=2.0 lift_speed=5.0
```

User-facing contact estimates, in acquisition order:

```text
-1.995000
-1.980000
-1.980000
-1.997500
-1.985000
-1.985000
-2.002500
-1.995000
-1.977500
-2.000000
```

Descriptive statistics:

```text
maximum             = -1.977500 mm
minimum             = -2.002500 mm
range               =  0.025000 mm
average             = -1.989750 mm
median              = -1.990000 mm
standard deviation  =  0.008764 mm
first→last drift    = -0.005000 mm
```

The corresponding raw `probe ... is z=` values remained exactly `0.250000 mm` lower than the user-facing contact estimates, consistent with the configured `[probe] z_offset=-0.25` semantics. The two coordinate forms remain separate.

Post-probe live state before cleanup:

```text
heater_bed.temperature     = 59.99 C
heater_bed.target          = 60.0 C
heater_bed.power           = 0.0695713663
extruder.temperature       = 31.86 C
extruder.target            = 0.0 C
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, -0.2500, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name      = ""
```

No standard Klipper Z offset was introduced. The bed remained essentially at the selected 60 C target throughout the series. The nozzle heater remained off, while passive nozzle temperature reached `31.86 C`.

## Comparison with ambient runs

```text
                         Gate B ambient      Gate C001 ambient    Gate C002 bed 60 C
average                  -1.985500 mm        -1.973000 mm        -1.989750 mm
median                   -1.986250 mm        -1.975000 mm        -1.990000 mm
range                     0.017500 mm         0.022500 mm         0.025000 mm
stddev                    0.005220 mm         0.007730 mm         0.008764 mm
first→last drift         +0.010000 mm        +0.005000 mm        -0.005000 mm
```

Mean differences:

```text
60 C minus Gate B ambient      = -0.004250 mm
60 C minus Gate C001 ambient   = -0.016750 mm
60 C minus mean of ambient means (-1.979250) = -0.010500 mm
```

Saved `auto` center remains `-1.925833 mm`; this run's mean minus saved center is `-0.063917 mm`.

Descriptive interpretation only:

- the 60 C series remains tightly clustered on the scale of the historical anomalous/drifting runs;
- there is no large monotonic drift in the 10 samples;
- the hot-bed mean lies within `0.016750 mm` of each of the two ambient run means and `0.010500 mm` below the mean of those two ambient means;
- the 20 g tare residual did not coincide with an obvious collapse of contact-series repeatability in this run, but this is not proof that the residual is harmless or causally unrelated;
- no thermal correction, tare threshold, acceptance band, search envelope or motion-policy value is inferred from this single heated-bed run.

## Remaining controlled path

```text
explicit Z5 retract
→ restore saved auto mesh at runtime
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter is permitted.

## Pending

- cleanup/retract confirmation: PENDING
- post-run standard effective Z offset: PENDING
- saved mesh unchanged proof: PENDING
- post-run `printer.cfg` hash: PENDING
- stop condition observed: PENDING

Until cleanup/persistence verification is complete, this run is not yet structurally complete and authorizes nothing.
