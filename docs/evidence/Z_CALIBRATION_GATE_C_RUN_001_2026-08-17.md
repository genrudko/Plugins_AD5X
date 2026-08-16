# Z Calibration Gate C — repeatability run 001

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** MEASUREMENT IN PROGRESS  
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

This Gate C run must produce an independent series with its own fresh homing/tare path. The previous series is not reused as current measurement data.

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

- printer remains idle/standby;
- all axes remain homed from the previous run, but Gate C intentionally requires a fresh `G28` for independent path repeatability;
- standard Klipper effective Z offset remains `0.0 mm` (`homing_origin[2]`);
- the `6.925833` G-code Z with physical/toolhead Z `5.0` is the expected active-mesh transform at the center and is not a new standard Z offset.

### Active/saved mesh state

```text
bed_mesh.profile_name = auto
mesh_min              = [0.0, 0.0]
mesh_max              = [215.0, 215.0]
```

The raw `auto` profile supplied by the live object query matches the Gate-A/Gate-B matrix. `MESH_DATA` and `auto` remain present in the saved profile map.

### Thermal state

```text
heater_bed.temperature = 25.79 C
heater_bed.target      = 0.0 C
extruder.temperature   = 26.55 C
extruder.target        = 0.0 C
```

This is a second ambient/cold observation immediately following Gate B, suitable for short-term/back-to-back repeatability evidence.

### Persistence guard

Pre-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

This exactly matches the Gate-B pre/post hash. Post-run evidence must compare it again.

## Controlled path evidence so far

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

## Remaining controlled path

```text
PROBE_ACCURACY SAMPLES=10
→ explicit Z5 retract
→ restore saved auto mesh at runtime
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent user-trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter is permitted.

## Pending

- raw 10-sample reference series: PENDING
- descriptive mean/median/spread/drift: PENDING
- comparison with Gate B run 001: PENDING
- cleanup/retract confirmation: PENDING
- post-run effective offset: PENDING
- saved mesh unchanged proof: PENDING
- post-run `printer.cfg` hash: PENDING
- stop condition observed: PENDING

Until complete, this run is not policy-reviewable and authorizes nothing.
