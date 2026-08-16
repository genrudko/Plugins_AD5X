# Z Calibration Gate B — controlled measurement run 001

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_b_controlled_measurement`  
**Status:** PRE-MOTION / NOT YET COMPLETE  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-b-001-2026-08-17`
- Plugins AD5X repository SHA at preflight: `0122fe891b6537561503250c3824156d8b0e1a9d`
- hardware context: same post-adjustment AD5X context as Gate A unless a later section records a physical change before measurement
- Z-Mod: `1.7.2-5`, branch `1.7`, checkout `2e32155d00e464094b8c7197e23783ec821a112c`
- Klipper runtime: `v0.13.0-753-g0df153f7-ZMOD-20260816`
- Klipper inspected checkout: `6bd8fca222811d465b4be3b0ed862915d6caf59e`
- Moonraker API: `1.5.0`, inspected checkout `a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e`

## Pre-motion snapshot

Source: owner-provided read-only Moonraker object query immediately before Gate-B motion.

### Job/runtime state

```text
print_stats.state      = standby
print_stats.filename   = ""
toolhead.homed_axes    = ""
toolhead.position      = [0.0, 0.0, 0.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
gcode_move.position    = [0.0, 0.0, 1.746667, 0.0]
gcode_move.gcode_position = [0.0, 0.0, 1.746667, 0.0]
```

Interpretation:

- printer is idle/standby;
- axes are not homed yet, therefore homing is a required first controlled action;
- current standard Klipper effective Z offset is `0.0 mm` (`homing_origin[2]`);
- there is no unexplained nonzero standard Klipper offset at this preflight.

### Active mesh

```text
bed_mesh.profile_name = auto
mesh_min              = [0.0, 0.0]
mesh_max              = [215.0, 215.0]
```

The raw `auto` 5×5 matrix matches the Gate-A baseline. Gate-B may clear/reload the mesh at runtime for measurement, but must not save/overwrite/delete the persistent profile.

### Probe state

```text
probe.last_query          = false
probe.last_probe_position = [0.0, 0.0, 0.0, 0.0]
probe.last_z_result       = 0.0
```

No prior probe result is being reused as Gate-B evidence.

### Thermal state

```text
heater_bed.temperature = 26.43 C
heater_bed.target      = 0.0 C
extruder.temperature   = 26.5 C
extruder.target        = 0.0 C
```

This run begins in an ambient/cold printer condition.

### Machine bounds reported by live toolhead

```text
axis_minimum = [-20.0, -20.0, -10.0, 0]
axis_maximum = [225.0, 232.0, 230.0, 0]
```

These are runtime machine bounds only and do not become Plugins AD5X search-envelope thresholds.

## Persistence guard

Pre-run `/opt/config/printer.cfg` hash:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

Post-run evidence must compare this hash and re-query saved mesh/profile state. A changed hash is a blocker until the exact cause is explained.

## Planned controlled measurement path

The run must use the already proven ordinary Klipper/Z-Mod path only; the CALIBRATION-SUBSYSTEM-002 production motion/write gates remain closed.

Planned semantics:

```text
runtime mesh clear only
→ ordinary homing
→ move to known center reference position
→ move to known non-contact Z5 reference height
→ LOAD_CELL_TARE
→ repeated PROBE_ACCURACY series
→ explicit safe retract
→ restore saved `auto` mesh at runtime
→ post-run object/hash/persistence checks
```

No `SAVE_CONFIG`, persistent Z trim mutation, saved mesh overwrite, Plugins AD5X Z-offset write, or Plugins AD5X production motion adapter is permitted in this run.

## Pending measurement evidence

- exact command script used: PENDING
- raw probe/contact samples: PENDING
- descriptive mean/median/spread/drift: PENDING
- tare residual/H7 observation: PENDING
- cleanup/retract confirmation: PENDING
- post-run effective offset: PENDING
- post-run active/saved mesh state: PENDING
- post-run `printer.cfg` hash: PENDING
- stop condition observed: PENDING

Until these fields are complete, this run is not policy-reviewable and authorizes nothing.
