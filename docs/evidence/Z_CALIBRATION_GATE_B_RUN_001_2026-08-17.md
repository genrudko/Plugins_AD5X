# Z Calibration Gate B — controlled measurement run 001

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_b_controlled_measurement`  
**Status:** COMPLETE / STRUCTURALLY REVIEWABLE EVIDENCE  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-b-001-2026-08-17`
- Plugins AD5X repository SHA at preflight: `0122fe891b6537561503250c3824156d8b0e1a9d`
- hardware context: same post-adjustment AD5X context as Gate A; no additional physical change was reported before this run
- Z-Mod: `1.7.2-5`, branch `1.7`, checkout `2e32155d00e464094b8c7197e23783ec821a112c`
- Klipper runtime: `v0.13.0-753-g0df153f7-ZMOD-20260816`
- Klipper inspected checkout: `6bd8fca222811d465b4be3b0ed862915d6caf59e`
- Moonraker API: `1.5.0`, inspected checkout `a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e`
- command transport: SSH into AD5X host → `chroot /usr/data/.mod/.zmod` → local Moonraker `127.0.0.1:7125` → ordinary Klipper/Z-Mod G-code path

## Pre-motion snapshot

Source: owner-provided read-only Moonraker object query immediately before Gate-B motion.

### Job/runtime state

```text
print_stats.state          = standby
print_stats.filename       = ""
toolhead.homed_axes        = ""
toolhead.position          = [0.0, 0.0, 0.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [0.0, 0.0, 1.746667, 0.0]
gcode_move.gcode_position  = [0.0, 0.0, 1.746667, 0.0]
```

Interpretation:

- printer was idle/standby;
- axes were not homed yet, therefore ordinary homing was required before controlled measurement;
- current standard Klipper effective Z offset was `0.0 mm` (`homing_origin[2]`);
- there was no unexplained nonzero standard Klipper offset at preflight.

### Active mesh

```text
bed_mesh.profile_name = auto
mesh_min              = [0.0, 0.0]
mesh_max              = [215.0, 215.0]
```

The raw `auto` 5×5 matrix matched the Gate-A baseline.

### Probe state

```text
probe.last_query          = false
probe.last_probe_position = [0.0, 0.0, 0.0, 0.0]
probe.last_z_result       = 0.0
```

No prior probe result was reused as Gate-B evidence.

### Thermal state

```text
heater_bed.temperature = 26.43 C
heater_bed.target      = 0.0 C
extruder.temperature   = 26.5 C
extruder.target        = 0.0 C
```

This run is an ambient/cold-condition measurement.

### Machine bounds reported by live toolhead

```text
axis_minimum = [-20.0, -20.0, -10.0, 0]
axis_maximum = [225.0, 232.0, 230.0, 0]
```

These are runtime machine bounds only and do not become Plugins AD5X search-envelope thresholds.

## Persistence guard

Pre-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

## Exact controlled command path

No CALIBRATION-SUBSYSTEM-002 production motion adapter or Z-offset writer was deployed or used.

The owner executed the following semantics through Moonraker's standard `printer/gcode/script` endpoint, one controlled step at a time:

```text
BED_MESH_CLEAR
G28
M400

G90
G1 X107.5 Y107.5 F3000
G1 Z5 F300
M400

LOAD_CELL_TARE

PROBE_ACCURACY SAMPLES=10

G90
G1 Z5 F300
M400
BED_MESH_PROFILE LOAD=auto
M400
```

No `SAVE_CONFIG`, persistent user-trim write, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or Plugins AD5X production motion command occurred.

## Step observations

### Runtime mesh clear + homing

After `BED_MESH_CLEAR` + ordinary `G28`:

```text
toolhead.homed_axes      = xyz
toolhead.position        = [220.0375, 220.0, 220.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = ""
```

Saved profiles `auto` and `MESH_DATA` remained present while runtime mesh was cleared.

The owner reported that homing motion was visually normal.

### Center / known non-contact height

After moving at high Z to mesh center and then to Z5:

```text
toolhead.position       = [107.5, 107.5, 5.0, 0.0]
gcode_move.position     = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name   = ""
```

### Load-cell tare

`LOAD_CELL_TARE` transcript:

```text
H1 attempt 1 → 60.0 g
H1 attempt 2 → 0.0 g
result       → OK, 60.0 -> 0.0
```

For this run, the final observed tare residual is `0.0 g`.

The first nonzero result followed by a successful retry is retained as evidence rather than being hidden.

## Repeated reference/contact series

Klipper/Z-Mod reported the actual `PROBE_ACCURACY` parameters:

```text
X=107.500
Y=107.500
start Z=5.000
samples=10
retract=2.000
speed=2.0 mm/s
lift_speed=5.0 mm/s
```

User-facing `bed will contact at z=` samples, preserving the previously proven `last_probe_position` coordinate semantics:

```text
-1.995000
-1.982500
-1.987500
-1.980000
-1.990000
-1.990000
-1.980000
-1.987500
-1.977500
-1.985000
```

Corresponding raw Klipper probe values including configured `[probe] z_offset=-0.25` were:

```text
-2.245000
-2.232500
-2.237500
-2.230000
-2.240000
-2.240000
-2.230000
-2.237500
-2.227500
-2.235000
```

Klipper summary:

```text
maximum            = -1.977500 mm
minimum            = -1.995000 mm
range              =  0.017500 mm
average            = -1.985500 mm
median             = -1.986250 mm
standard deviation =  0.005220 mm
```

Additional descriptive statistic used by Hardware Evidence Run v1:

```text
first-to-last drift = +0.010000 mm
```

No large monotonic drift or isolated large excursion is present in this series. This is a descriptive observation only; it does not freeze an acceptance threshold.

### Comparison with current saved `auto` center

Gate-A/current saved `auto` center sample at X107.5/Y107.5:

```text
-1.925833 mm
```

This Gate-B series mean:

```text
-1.985500 mm
```

Descriptive current-minus-saved-center difference:

```text
-0.059667 mm
```

This difference is **not** applied as Auto-Z by this run and is not an accepted correction threshold. It is retained for later repeated-evidence/policy review.

## Post-probe state before explicit cleanup

Immediately after `PROBE_ACCURACY`:

```text
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [107.5, 107.5, -0.235..., 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = ""
```

The physical/toolhead Z is consistent with the final raw probe coordinate plus the command's reported 2.0 mm retract. Gate B nevertheless required an explicit higher cleanup retract before completion.

## Explicit cleanup and persistence verification

The run explicitly commanded:

```text
G90
G1 Z5 F300
M400
BED_MESH_PROFILE LOAD=auto
M400
```

Final observed state:

```text
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
gcode_move.position        = [107.5, 107.5, 6.925833, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
bed_mesh.profile_name      = auto
```

The `toolhead Z=5.0` versus transformed G-code Z `6.925833` difference after reloading `auto` is exactly the expected center mesh transform magnitude `1.925833 mm`. It is not a new `gcode_offset`; `homing_origin[2]` remained `0.0`.

The active `auto` raw 5×5 matrix and saved profile data matched the pre-run/Gate-A data.

Post-run `/opt/config/printer.cfg` SHA-256:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

It is byte-identical to the pre-run hash.

## Hardware Evidence Run v1 disposition

Objective fields for this run:

```text
phase                       = gate_b_controlled_measurement
reference_series_present    = true
cleanup_confirmed            = true
persistent_state_changed     = false
saved_mesh_changed           = false
stop_condition_observed      = false
tare_residual                = 0.0 g
```

Therefore the run is structurally complete/reviewable under Hardware Evidence Run v1.

This means only that the evidence record is complete enough for later human/policy review. It does **not** mean that a calibration threshold, motion envelope, correction limit, approach speed, contact speed, or production motion policy is accepted.

## Gate-B run 001 result

**PASS as a controlled no-persistence hardware evidence run.**

Proven by this run:

- ordinary homing completed normally;
- runtime mesh could be cleared and restored without persistent mutation;
- center reference measurement completed with ten retained raw samples;
- tare converged from 60 g to 0 g;
- repeated reference series was internally tight on this run (`0.0175 mm` range);
- standard effective Klipper Z offset stayed at `0.0 mm`;
- explicit retract returned physical/toolhead Z to `5.0 mm`;
- saved `auto` profile remained unchanged;
- `printer.cfg` remained byte-identical;
- no stop condition was observed.

Not proven/accepted by this run:

- release-quality repeatability across temperature/time/reboot conditions;
- a safe search envelope;
- a production approach/contact/retract policy;
- an Auto-Z correction limit;
- H7 latency/stopping capability;
- permission to enable the CALIBRATION-SUBSYSTEM-002 production motion/write gates.

The next hardware phase is Gate C repeatability using distinct run IDs and recorded conditions before any numeric production policy is frozen.
