# Z Calibration Gate C — repeatability run 001

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** COMPLETE / PASS AS REPEATABILITY EVIDENCE  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-c-001-ambient-back-to-back-2026-08-17`
- condition class: short-term/back-to-back ambient repeatability
- Plugins AD5X repository SHA at preflight: `9f32e19c883d605853b7c928925cab661a87f935`
- hardware context: same post-adjustment AD5X setup as Gate A and Gate B run 001; no physical change was reported before this preflight
- Z-Mod: `1.7.2-5`, branch `1.7`, checkout `2e32155d00e464094b8c7197e23783ec821a112c`
- Klipper runtime: `v0.13.0-753-g0df153f7-ZMOD-20260816`
- Klipper inspected checkout: `6bd8fca222811d465b4be3b0ed862915d6caf59e`
- Moonraker API: `1.5.0`, inspected checkout `a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e`
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

## Pre-motion / persistence baseline

```text
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name      = auto
heater_bed.temperature     = 25.79 C
heater_bed.target          = 0.0 C
extruder.temperature       = 26.55 C
extruder.target            = 0.0 C
printer.cfg SHA-256        = eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

The active `auto` raw matrix matched Gate A/Gate B and both saved profiles `auto` and `MESH_DATA` remained present.

## Controlled path

```text
BED_MESH_CLEAR
→ fresh G28
→ G90 / X107.5 Y107.5 / Z5
→ LOAD_CELL_TARE
→ PROBE_ACCURACY SAMPLES=10
→ explicit G1 Z5 retract
→ BED_MESH_PROFILE LOAD=auto
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent user-trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter was used.

### Fresh homing

Post-G28:

```text
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [220.0375, 220.0, 220.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = ""
```

Owner reported homing visually normal.

### Fresh tare

```text
H1 > command H1 ok. 8425884
N 1. Вес: 0.0
Сброс тензодатчка: ОК. Вес: 0.0->0.0
```

Tare succeeded on the first reported attempt with residual `0.0 g`.

### Independent 10-sample reference series

```text
-1.982500
-1.980000
-1.965000
-1.967500
-1.977500
-1.972500
-1.960000
-1.965000
-1.982500
-1.977500
```

```text
maximum             = -1.960000 mm
minimum             = -1.982500 mm
range               =  0.022500 mm
average             = -1.973000 mm
median              = -1.975000 mm
standard deviation  =  0.007730 mm
first→last drift    = +0.005000 mm
```

The corresponding raw probe-Z messages remained exactly `0.250000 mm` lower than the user-facing contact estimates, consistent with the already-established configured `[probe] z_offset=-0.25` semantics.

## Comparison with Gate B run 001

```text
                         Gate B run 001      Gate C run 001      C - B
average                  -1.985500 mm        -1.973000 mm        +0.012500 mm
median                   -1.986250 mm        -1.975000 mm        +0.011250 mm
range                     0.017500 mm         0.022500 mm        +0.005000 mm
stddev                    0.005220 mm         0.007730 mm        +0.002510 mm
first→last drift         +0.010000 mm        +0.005000 mm        -0.005000 mm
```

Descriptive interpretation only:

- the independently homed/tared second ambient series remained tightly clustered;
- no large monotonic drift or historical old-style transient was observed;
- mean-to-mean difference was `+0.012500 mm`;
- saved `auto` center remained `-1.925833 mm`; this run's mean minus saved center was `-0.047167 mm`;
- **no acceptance band, correction threshold or motion/search threshold is inferred from these two ambient runs**.

## Cleanup / persistence verification

Post-cleanup:

```text
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 6.925833, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
bed_mesh.profile_name      = auto
```

The `6.925833` G-code Z with physical/toolhead Z `5.0` is the expected saved-mesh transform at the center, not a standard Z offset.

The raw `auto` matrix and saved profile map remained unchanged.

Post-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

It exactly matched the pre-run and Gate-B hashes.

## Run disposition

```text
reference series present      = true
cleanup/retract confirmed     = true
standard Z offset unchanged   = true
persistent state changed      = false
saved mesh changed            = false
stop condition observed       = false
```

Therefore `gate-c-001-ambient-back-to-back-2026-08-17` is structurally complete and suitable for later policy review as repeatability evidence.

It does **not** by itself authorize a motion policy, search envelope, correction limit, production adapter or gate opening.

## Dataset note / next condition

The evidence set now contains one clean Gate-B controlled measurement and one clean Gate-C repeatability run under near-identical ambient conditions. That establishes useful short-term repeatability evidence, but condition diversity is still missing.

Do not spend more immediate runs on the identical ambient condition unless a later observation creates a reason. The next useful Gate-C run should use the owner's **actual representative PLA bed temperature**, followed later by representative higher-bed temperature, reboot/power-cycle and time-separated evidence.
