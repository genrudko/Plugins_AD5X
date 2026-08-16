# Z Calibration Gate C — repeatability run 002 (PLA bed 60 C)

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** COMPLETE / PASS AS HEATED-BED REPEATABILITY EVIDENCE  
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

The bed heater is the deliberate thermal change in this run. The nozzle heater remains off throughout. Passive nozzle warming from the heated bed/chamber is recorded explicitly rather than treated as an unchanged-nozzle condition.

## Previous repeatability context

```text
Gate B ambient mean   = -1.985500 mm
Gate C001 ambient mean= -1.973000 mm
ambient mean delta    = +0.012500 mm
```

These values are descriptive evidence only and do not define an acceptance band.

## Heated condition establishment

Command:

```text
M190 S60
```

Immediate live state after heater wait:

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

The exact `59.36 C` observation is retained as measured; it is not rewritten as an assumed `60.00 C` and establishes no temperature tolerance policy.

## Heated read-only preflight

After additional dwell at target:

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

The raw active `auto` matrix and saved profile map matched the prior baseline. `6.925833` G-code Z at physical Z `5.0` is the expected active-mesh transform, not a standard Z offset.

## Heated-condition runtime mesh clear + fresh homing

Commands:

```text
BED_MESH_CLEAR
G28
M400
```

Post-G28:

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

Saved `MESH_DATA` and `auto` profiles remained present and unchanged.

## Heated-condition center / non-contact position

Commands:

```text
G90
G1 X107.5 Y107.5 F3000
G1 Z5 F300
M400
```

Post-move:

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

Z-Mod returned `ok` and reported:

```text
H1 > command H1 ok. 8431997
N 1. Вес: 80.0
H1 > command H1 ok. 8430826
N 2. Вес: 20.0
Сброс тензодатчка: ОК. Вес: 80.0->20.0
```

This differs from Gate B (`60→0 g`) and Gate C001 (`0→0 g`). The heated run ended with reported residual `20 g` while Z-Mod itself classified tare as `ОК`. No new tare threshold is inferred. The residual is retained as secondary H7/tare evidence.

## Heated-condition independent 10-sample reference series

Command:

```text
PROBE_ACCURACY SAMPLES=10
```

Klipper/Z-Mod conditions:

```text
X=107.500 Y=107.500 Z=5.000
samples=10 retract=2.000 speed=2.0 lift_speed=5.0
```

User-facing contact estimates:

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

The corresponding raw `probe ... is z=` values stayed exactly `0.250000 mm` lower than the user-facing contact estimates, consistent with configured `[probe] z_offset=-0.25`. The coordinate forms are kept separate.

Post-probe before cleanup:

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

Saved `auto` center remains `-1.925833 mm`; this run mean minus saved center is `-0.063917 mm`.

Descriptive interpretation only:

- the heated-bed contact series remains tightly clustered on the scale of historical anomalous/drifting runs;
- no large monotonic drift was observed;
- the 60 C mean is within `0.016750 mm` of both ambient means and `0.010500 mm` from the mean of the two ambient means;
- the `20 g` tare residual did not coincide with an obvious collapse of contact repeatability, but this does not prove the residual harmless or causally unrelated;
- no thermal correction, tare threshold, correction limit, search envelope or motion-policy value is inferred from this single heated-bed run.

## Cleanup / persistence verification

Cleanup command path:

```text
G90
G1 Z5 F300
M400
BED_MESH_PROFILE LOAD=auto
M400
```

The command returned `ok`. Post-cleanup live state:

```text
heater_bed.temperature     = 59.91 C
heater_bed.target          = 60.0 C
heater_bed.power           = 0.1605460859
extruder.temperature       = 33.89 C
extruder.target            = 0.0 C
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 6.925833, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
bed_mesh.profile_name      = auto
```

The raw active `auto` matrix exactly matched the saved baseline, and the saved `MESH_DATA` / `auto` profile map remained unchanged. `6.925833` G-code Z at physical/toolhead Z `5.0` is again the expected center mesh transform, not a standard Z offset.

Post-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

It exactly matched the pre-run, Gate B and Gate C001 hashes.

## Run disposition

```text
reference series present      = true
cleanup/retract confirmed     = true
standard Z offset unchanged   = true
persistent state changed      = false
saved mesh changed            = false
stop condition observed       = false
```

Therefore `gate-c-002-pla-bed-60c-2026-08-17` is structurally complete and suitable for later policy review as heated-bed repeatability evidence.

It does **not** authorize a motion policy, search envelope, correction limit, thermal compensation, tare threshold, production adapter or gate opening.

## Dataset note / next conditions

The dataset now contains:

1. one clean ambient controlled-measurement run (Gate B run 001);
2. one clean back-to-back ambient repeatability run (Gate C001);
3. one clean 60 C bed repeatability run (Gate C002).

The next useful evidence should not repeat the same condition immediately. Remaining useful condition diversity includes a representative higher-bed-temperature condition, reboot/power-cycle, reasonable time separation, and—if needed for actual print semantics—a deliberately heated-nozzle condition recorded separately from bed-only heating.
