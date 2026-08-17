# Z Calibration Gate C — clean power-cycle ambient run 003

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** COMPLETE / PASS AS CLEAN REBOOT-TIME-SEPARATED EVIDENCE  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion, Z-offset writes, thresholds or release of the temporary camera hardening proof

## Run identity

- run_id: `gate-c-003-clean-powercycle-ambient-2026-08-17`
- condition class: full power-cycle + time-separated ambient repeatability
- repository branch at preflight: `feature/z-calibration-subsystem-v2`
- repository SHA at preflight: `3cf8b5853a8eec295300fbe8a1ceb725cdf4eca4`
- Klipper runtime: `v0.13.0-753-g0df153f7-ZMOD-20260816`
- Moonraker API: `1.5.0`
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

This run follows the earlier diagnostic-only reboot run recorded in `Z_CALIBRATION_GATE_C_RUN_003_REBOOT_DIAGNOSTIC_2026-08-17.md`. That earlier boot contained camera-path kernel Oops events and therefore was intentionally not accepted as clean reboot evidence.

## Camera boot-path prerequisite

Before this accepted power-cycle, investigation established the startup chain:

```text
[delayed_gcode start_led]
initial_duration: 10
→ CAMERA_RESTART
→ RUN_SHELL_COMMAND CMD="s99camera" PARAMS="restart"
→ S99camera restart/up
```

The stock `S99camera up()` path performed global diagnostics across `/dev/video?`. On this AD5X topology:

```text
video0 = CCX2F3298: CCX2F3298
video1 = CCX2F3298: CCX2F3298
video2 = felix-vdec
```

Historical/current diagnostic evidence linked `v4l2-ctl` access to `felix-vdec` with kernel Oops/segfault behavior.

A surgical live proof patch was therefore applied to `/opt/config/mod/.shell/S99camera` before this run. It:

- removed fallback enumeration of all `video?` nodes when the configured camera is absent;
- removed the unconditional post-start `V4l2 --all` and all-node diagnostics;
- retained diagnostics only for configured `/dev/$VIDEO`;
- left normal `CAMERA_RESTART` semantics intact.

Patched script SHA-256:

```text
4ad46547e0d9e207cd44bfc3a94705a7faca761dfde331d61f2dcdab3259315b
```

A controlled pre-reboot `S99camera restart` validation passed:

```text
restart rc                 = 0
camera ready               = ~1 s
active capture device      = /dev/video0
new kernel Oops            = 0
new v4l2-ctl process marks = 0
```

This live proof is part of the test environment for this evidence run. It is **not yet a production/canonical release mechanism** and does not change the no-Z-Mod-fork boundary.

## Clean power-cycle preflight

Immediately before full power removal:

```text
print_stats.state          = standby
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name      = auto
heater_bed.temperature     = 23.38 C
heater_bed.target          = 0.0 C
extruder.temperature       = 23.89 C
extruder.target            = 0.0 C
printer.cfg SHA-256        = eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
S99camera SHA-256          = 4ad46547e0d9e207cd44bfc3a94705a7faca761dfde331d61f2dcdab3259315b
```

The active `auto` raw matrix matched the Gate A baseline. Camera configuration remained:

```text
START=on
WIDTH=1920
HEIGHT=1080
FPS=30
VIDEO=video0
FS=1
STREAMER=auto
FORMAT=MJPEG
```

Pre-power-cycle camera snapshot succeeded (`176058` bytes). The script contained no remaining global `/dev/video?` enumeration pattern.

The owner then fully removed printer power, waited approximately 30 seconds, and powered the printer on again.

## Clean post-boot acceptance

At approximately 395 s uptime after the power-cycle:

```text
kernel Internal error: Oops count = 0
kernel Process v4l2-ctl count     = 0
```

The only relevant `felix-vdec` boot messages were ordinary device-registration messages:

```text
felix-vdec ... failed to init reserved mem
felix-vdec ... h264decoder(felix) registered as /dev/video2
```

No Oops, call trace, `v4l2-ctl` crash marker or segmentation-fault marker was present.

Persistence checks:

```text
printer.cfg SHA-256 = eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891  MATCH
S99camera SHA-256   = 4ad46547e0d9e207cd44bfc3a94705a7faca761dfde331d61f2dcdab3259315b  MATCH
```

Camera automatically recovered without manual restart:

```text
zcam capture node = /dev/video0
resolution        = 1920x1080
FPS               = 30
post-boot snapshot= 171661 bytes
camera.log nodes  = /dev/video0 only
```

Moonraker/Klipper state:

```text
Moonraker klippy_connected = true
Moonraker klippy_state     = ready
failed_components          = []
Klipper state              = ready
print_stats.state          = standby
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name      = auto
heater_bed.temperature     ≈ 22.83 C
extruder.temperature       ≈ 23.74 C
both heater targets        = 0.0 C
```

The active/saved `auto` matrix remained the Gate A matrix.

## Stage 1 — fresh mesh clear, home and controlled center

Pre-motion ambient:

```text
bed    = 23.17 C, target 0.0 C
nozzle = 23.79 C, target 0.0 C
homed_axes = ""
bed_mesh.profile_name = auto
```

Controlled path:

```text
BED_MESH_CLEAR
G28
G90
G1 X107.5 Y107.5 F6000
G1 Z5 F600
M400
GET_POSITION
```

Result:

```text
print_stats.state        = standby
toolhead.homed_axes      = xyz
toolhead.position        = [107.5, 107.5, 5.0, 0.0]
gcode_move.position      = [107.5, 107.5, 5.0, 0.0]
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = ""
```

No motion error, shutdown, move-out-of-range or probe-trigger-prior error was observed before proceeding.

## Stage 2 — tare and independent 10-sample reference series

Pre-series state:

```text
state                   = standby
homed_axes              = xyz
toolhead.position       = [107.5, 107.5, 5.0, 0.0]
homing_origin           = [0.0, 0.0, 0.0, 0.0]
mesh                    = ""
bed                     = 22.90 C, target 0.0 C
nozzle                  = 23.85 C, target 0.0 C
```

Command path:

```text
LOAD_CELL_TARE
PROBE_ACCURACY SAMPLES=10
```

Z-Mod reported tare:

```text
Сброс тензодатчка: ОК. Вес: 40.0->0.0
```

No production tare threshold is inferred from that classification.

User-facing contact series:

```text
-1.995000
-1.980000
-1.992500
-1.982500
-1.985000
-1.975000
-1.977500
-1.990000
-1.980000
-1.982500
```

Corresponding raw Klipper probe positions remained exactly `0.250000 mm` lower, consistent with the established `[probe] z_offset=-0.25` semantics:

```text
-2.245000
-2.230000
-2.242500
-2.232500
-2.235000
-2.225000
-2.227500
-2.240000
-2.230000
-2.232500
```

Klipper/Z-Mod statistics:

```text
maximum             = -1.975000 mm
minimum             = -1.995000 mm
range               =  0.020000 mm
average             = -1.984000 mm
median              = -1.982500 mm
standard deviation  =  0.006245 mm
first→last drift    = +0.012500 mm
```

## Comparison with prior evidence

```text
Gate B ambient mean                    = -1.985500 mm
Gate C001 ambient mean                 = -1.973000 mm
Gate C002 bed-60C mean                 = -1.989750 mm
Gate C003 clean power-cycle mean       = -1.984000 mm
Gate C003 diagnostic series 1 mean     = -1.953750 mm
Gate C003 diagnostic series 2 mean     = -1.948250 mm
Gate C003 diagnostic two-series mean   = -1.951000 mm
```

Clean C003 mean differences:

```text
vs Gate B ambient                 = +0.001500 mm
vs Gate C001 ambient              = -0.011000 mm
vs Gate C002 bed-60C              = +0.005750 mm
vs diagnostic two-series mean     = -0.033000 mm
```

Descriptive interpretation only:

- the clean power-cycle series falls back inside the previously observed clean ambient/heated cluster;
- the approximately `+0.022...+0.039 mm` level seen in the earlier tainted diagnostic reboot was **not reproduced** by this clean power-cycle;
- therefore the earlier shift must not be treated as a deterministic reboot/power-cycle correction;
- the current evidence does not prove that the earlier kernel Oops caused the Z-reference shift either;
- the diagnostic run remains evidence of an abnormal machine state with a coherent shifted contact level, not evidence of a normal reboot effect;
- no correction magnitude, acceptance band, search envelope, thermal compensation, motion speed or tare threshold is inferred from this run alone.

## Cleanup and persistence closure

Cleanup path:

```text
G90
G1 Z5 F600
M400
BED_MESH_PROFILE LOAD=auto
M400
GET_POSITION
```

Final runtime state:

```text
print_stats.state          = standby
toolhead.homed_axes        = xyz
toolhead.position          = [107.5, 107.5, 5.0, 0.0]
gcode_move.gcode_position  = [107.5, 107.5, 6.925833, 0.0]
gcode_move.homing_origin   = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name      = auto
active matrix == Gate A    = true
saved auto == Gate A       = true
saved profiles             = [MESH_DATA, auto]
heater targets             = 0.0 C / 0.0 C
```

The `6.925833 mm` G-code Z with physical/toolhead Z `5.0 mm` is the expected active-mesh transform at center and is not a standard Z offset.

Final persistence/kernel/camera verification:

```text
printer.cfg SHA-256       = eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891  MATCH
S99camera SHA-256         = 4ad46547e0d9e207cd44bfc3a94705a7faca761dfde331d61f2dcdab3259315b  MATCH
kernel Oops markers       = 0
v4l2-ctl process markers  = 0
camera capture node       = /dev/video0
final snapshot            = 173946 bytes
```

## Run disposition

```text
clean full power-cycle            = true
camera auto-start usable          = true
kernel clean before calibration   = true
reference series present          = true
cleanup/retract confirmed         = true
standard Z offset unchanged       = true
active mesh restored              = true
saved mesh unchanged              = true
persistent printer.cfg changed    = false
calibration stop condition        = false
```

Therefore `gate-c-003-clean-powercycle-ambient-2026-08-17` is structurally complete and accepted as **clean reboot/time-separated Gate C evidence**.

This acceptance applies to the **evidence run**, not to production motion policy and not to the temporary live camera patch as a shipping implementation.

## Policy consequence

The evidence set now contains:

- clean Gate B ambient measurement;
- independent clean Gate C ambient repeatability;
- representative owner PLA bed-60C measurement;
- one tainted diagnostic reboot with a coherent shifted level;
- one clean full power-cycle that returned to the established clean measurement cluster.

The clean C003 materially weakens any hypothesis of a deterministic reboot offset and reinforces the requirement to validate the current contact reference instead of applying a blind reboot compensation.

Production Z-offset write and motion gates remain **OFF**. Accepted policy values still require repeated diverse evidence, documented margin rationale and explicit owner acceptance.
