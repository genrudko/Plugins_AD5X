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

## Previous accepted evidence context

Gate B run 001 completed cleanly immediately before this run:

```text
reference average       = -1.985500 mm
reference median        = -1.986250 mm
reference range         =  0.017500 mm
first-to-last drift     = +0.010000 mm
saved auto center       = -1.925833 mm
current-minus-saved     = -0.059667 mm
persistent state change = false
saved mesh change       = false
cleanup confirmed       = true
```

This Gate C run produced an independent series with its own fresh homing/tare path. The previous series was not reused as current measurement data.

## Pre-motion snapshot

Source: owner-provided read-only Moonraker object query immediately before the repeatability run.

### Runtime state

```text
print_stats.state          = standby
print_stats.filename       = ""
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 6.925833, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
```

Interpretation:

- printer remained idle/standby;
- all axes were homed from the previous run, but Gate C intentionally performed a fresh `G28` for independent path repeatability;
- standard Klipper effective Z offset remained `0.0 mm` (`homing_origin[2]`);
- the `6.925833` G-code Z with physical/toolhead Z `5.0` was the expected active-mesh transform at the center and was not a new standard Z offset.

### Active/saved mesh state

```text
bed_mesh.profile_name = auto
mesh_min              = [0.0, 0.0]
mesh_max              = [215.0, 215.0]
```

The raw `auto` profile supplied by the live object query matched the Gate-A/Gate-B matrix. `MESH_DATA` and `auto` remained present in the saved profile map.

### Thermal state

```text
heater_bed.temperature = 25.79 C
heater_bed.target      = 0.0 C
extruder.temperature   = 26.55 C
extruder.target        = 0.0 C
```

This was a second ambient/cold observation immediately following Gate B, suitable for short-term/back-to-back repeatability evidence.

### Persistence guard

Pre-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

This exactly matched the Gate-B pre/post hash.

## Controlled path evidence

### Runtime mesh clear + fresh ordinary homing

Commands:

```text
BED_MESH_CLEAR
G28
M400
```

Post-G28 live state:

```text
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [220.0375, 220.0, 220.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = ""
```

Saved `MESH_DATA` and `auto` profiles remained present. Owner reported homing visually normal.

### Controlled center/non-contact positioning

Command path:

```text
G90
G1 X107.5 Y107.5 F3000
G1 Z5 F300
M400
```

Post-move live state:

```text
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
gcode_move.position      = [107.5, 107.5, 5.0, 0.0]
bed_mesh.profile_name    = ""
```

No runtime mesh was active and no standard Klipper Z offset was introduced.

### Fresh load-cell tare

Command:

```text
LOAD_CELL_TARE
```

Observed Z-Mod responses:

```text
H1 > command H1 ok. 8425884
N 1. Вес: 0.0
Сброс тензодатчка: ОК. Вес: 0.0->0.0
```

Interpretation: this independent run's tare succeeded on the first reported attempt with residual `0.0 g`. This is retained as descriptive H7/tare evidence only.

### Independent repeated reference series

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

Descriptive statistics reported/derived:

```text
maximum             = -1.960000 mm
minimum             = -1.982500 mm
range               =  0.022500 mm
average             = -1.973000 mm
median              = -1.975000 mm
standard deviation  =  0.007730 mm
first→last drift    = +0.005000 mm
```

The corresponding raw probe-Z messages remained exactly `0.250000 mm` lower than each user-facing contact estimate, consistent with the configured `[probe] z_offset=-0.25` semantics already established in reverse engineering. These coordinate forms are not mixed in the reference dataset.

Post-probe state before explicit cleanup:

```text
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [107.5, 107.5, -0.2275, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = ""
```

No standard Klipper Z offset was introduced by the measurement.

## Short-term comparison with Gate B run 001

```text
                         Gate B run 001      Gate C run 001      C - B
average                  -1.985500 mm        -1.973000 mm        +0.012500 mm
median                   -1.986250 mm        -1.975000 mm        +0.011250 mm
range                     0.017500 mm         0.022500 mm        +0.005000 mm
stddev                    0.005220 mm         0.007730 mm        +0.002510 mm
first→last drift         +0.010000 mm        +0.005000 mm        -0.005000 mm
```

Descriptive interpretation only:

- the independently homed/tared second ambient series remained tightly clustered and showed no large monotonic drift or old-style transient;
- its mean was `+0.012500 mm` higher (less negative) than Gate B run 001;
- both series remained close on the scale of the historical anomalies, but **no acceptance band or motion/search threshold is inferred from two runs**;
- the saved `auto` center remained `-1.925833 mm`; Gate-C mean minus that saved center is `-0.047167 mm`, retained as observation only and not applied.

## Cleanup / persistence verification

Cleanup command path:

```text
G90
G1 Z5 F300
M400
BED_MESH_PROFILE LOAD=auto
M400
```

Post-cleanup live state:

```text
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 6.925833, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
bed_mesh.profile_name      = auto
```

Interpretation:

- explicit retract returned physical/toolhead Z to `5.0 mm`;
- saved `auto` was restored as the active runtime profile;
- `homing_origin.z` remained exactly `0.0 mm`;
- the post-load G-code Z `6.925833` again differs from physical Z by the saved center mesh transform and is not a persistent/user offset;
- raw `auto` matrix and saved profile map remained unchanged in the live query.

Post-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

It exactly matches the pre-run, Gate-B pre-run and Gate-B post-run hashes.

## Run disposition

```text
reference series present      = true
cleanup/retract confirmed     = true
standard Z offset unchanged   = true
persistent state changed      = false
saved mesh changed            = false
stop condition observed       = false
```

Therefore `gate-c-001-ambient-back-to-back-2026-08-17` is **structurally complete and suitable for later policy review as repeatability evidence**.

It does **not** by itself authorize a motion policy, search envelope, correction limit, production adapter or gate opening.

## Next evidence condition

Do not spend additional runs on identical immediate ambient repetition unless a later observation creates a reason to do so. The next useful Gate-C condition should be a distinct recorded condition such as the owner's representative PLA bed temperature, followed later by representative higher-bed temperature, reboot/power-cycle and time-separated evidence.
