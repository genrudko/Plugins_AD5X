# Z Calibration Gate C — reboot/time-separated diagnostic run 003

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** COMPLETE AS DIAGNOSTIC EVIDENCE / NOT ACCEPTED AS CLEAN GATE C RUN  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-c-003-reboot-diagnostic-2026-08-17`
- condition class: reboot/time-separated ambient diagnostic
- ambient preflight: bed approximately `24.38 C`, nozzle approximately `26.35 C`
- printer state: `standby`
- standard Klipper `homing_origin.z`: `0.0 mm`
- `/opt/config/printer.cfg` SHA-256: `eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891`
- saved `auto` mesh present before the run
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

This run was performed after the reboot-recovery investigation recorded in `Z_CALIBRATION_GATE_C_REBOOT_RECOVERY_ANOMALY_2026-08-17.md`.

## Why this run is diagnostic only

The boot used for this measurement was not clean enough to qualify as accepted reboot/power-cycle Gate C evidence.

Before the calibration sequence, the current kernel had already recorded three additional camera-path Oops events:

```text
Oops #8  at uptime ~1724.319 s, Process v4l2-ctl, PID 15710
Oops #9  at uptime ~1740.761 s, Process v4l2-ctl, PID 15930
Oops #10 at uptime ~1741.081 s, Process v4l2-ctl, PID 15934
```

The observed call path included:

```text
dma_coherent_mem_available
→ av_buffer_alloc / av_mallocz
→ h264_decode_init
→ fops_vcodec_open
→ v4l2_open
```

The manual known-good `mjpg_streamer` process used later for remote visual supervision started only at uptime approximately `1823.180 s`, more than 80 seconds after Oops #10. Therefore those three Oops events were not caused by the later manual direct `mjpg_streamer` start.

This establishes a distinct camera/V4L2 boot-path defect, but does not prove that the kernel Oops changed the Z reference. Because the kernel was already tainted, the resulting contact data is retained as useful diagnostic evidence and is **not promoted to a clean reboot Gate C pass**.

## Preflight

Moonraker reported:

```text
klippy_connected = true
klippy_state     = ready
failed_components = []
api_version      = 1.5.0
```

Klipper reported:

```text
state            = ready
state_message    = Printer is ready
software_version = v0.13.0-753-g0df153f7-ZMOD-20260816
```

Live printer state before motion:

```text
heater_bed.temperature   = 24.38 C
heater_bed.target        = 0.0 C
extruder.temperature     = 26.35 C
extruder.target          = 0.0 C
print_stats.state        = standby
toolhead.homed_axes      = ""
gcode_move.homing_origin = [0.0, 0.0, 0.0, 0.0]
bed_mesh.profile_name    = auto
```

The active/saved `auto` matrix matched the post-adjustment baseline.

## Runtime mesh clear + fresh homing

Commands:

```text
BED_MESH_CLEAR
G28
```

The owner visually confirmed normal physical homing over the remote camera path.

The head was then positioned at the controlled center/non-contact point:

```text
G90
G1 X107.5 Y107.5 Z5
```

The owner again confirmed normal physical motion.

## Series 1 — first post-reboot contact series

Command path:

```text
LOAD_CELL_TARE
PROBE_ACCURACY SAMPLES=10
G90
G1 Z5
```

The command returned `ok` and the head returned to:

```text
X=107.5 Y=107.5 Z=5.0
homed_axes=xyz
homing_origin.z=0.0
```

Raw Klipper/Z-Mod probe lines:

```text
-2.190000
-2.195000
-2.212500
-2.202500
-2.207500
-2.197500
-2.202500
-2.212500
-2.205000
-2.212500
```

With configured `[probe] z_offset=-0.25`, the user-facing contact estimates are exactly `+0.250000 mm` from those raw values:

```text
-1.940000
-1.945000
-1.962500
-1.952500
-1.957500
-1.947500
-1.952500
-1.962500
-1.955000
-1.962500
```

Klipper/Z-Mod reported:

```text
maximum             = -1.940000 mm
minimum             = -1.962500 mm
range               =  0.022500 mm
average             = -1.953750 mm
median              = -1.953750 mm
standard deviation  =  0.007437 mm
first→last drift    = -0.022500 mm
```

Post-series live state remained idle with heaters off. Load-cell telemetry after tare stayed near zero, with `weightValue` observed around `0.0` and subsequent idle values within the small signed range visible in the ordinary stats stream. No tare acceptance threshold is inferred.

## Series 2 — immediate back-to-back repeat

To distinguish a persistent post-reboot level from a one-series settling effect, the same controlled point was probed again without a second reboot and without a new homing cycle.

Command path:

```text
LOAD_CELL_TARE
PROBE_ACCURACY SAMPLES=10
G90
G1 Z5
```

Raw probe lines:

```text
-2.197500
-2.190000
-2.197500
-2.202500
-2.190000
-2.195000
-2.210000
-2.200000
-2.205000
-2.195000
```

Corresponding user-facing contact estimates:

```text
-1.947500
-1.940000
-1.947500
-1.952500
-1.940000
-1.945000
-1.960000
-1.950000
-1.955000
-1.945000
```

Klipper/Z-Mod reported:

```text
maximum             = -1.940000 mm
minimum             = -1.960000 mm
range               =  0.020000 mm
average             = -1.948250 mm
median              = -1.947500 mm
standard deviation  =  0.006026 mm
first→last drift    = +0.002500 mm
```

Difference between the two post-reboot series means:

```text
series 2 - series 1 = +0.005500 mm
mean of both series = -1.951000 mm
```

The second series therefore remained on essentially the same new contact level rather than returning to the older `~ -1.98...-1.99 mm` level.

## Comparison with prior clean evidence

```text
Gate B ambient mean                = -1.985500 mm
Gate C001 ambient mean             = -1.973000 mm
Gate C002 bed 60 C mean            = -1.989750 mm
Gate C003 diagnostic series 1 mean = -1.953750 mm
Gate C003 diagnostic series 2 mean = -1.948250 mm
Gate C003 diagnostic two-series mean = -1.951000 mm
```

Mean differences using the two-series diagnostic mean:

```text
vs Gate B ambient      = +0.034500 mm
vs Gate C001 ambient   = +0.022000 mm
vs Gate C002 bed 60 C  = +0.038750 mm
```

Descriptive interpretation only:

- within each series, contact repeatability remained tight;
- two immediate post-reboot series agreed with each other to `0.0055 mm` in their means;
- the two-series level was shifted by roughly `+0.022...+0.039 mm` relative to the previous clean evidence runs;
- this supports the design requirement that a persistent saved contact reference must not be blindly trusted across machine states/reboots;
- one tainted-kernel reboot is not enough to claim a deterministic reboot correction or to freeze a production threshold;
- no correction magnitude, acceptance band, search envelope, thermal compensation or motion speed is inferred from this run.

## Cleanup / persistence verification

Cleanup command path:

```text
BED_MESH_PROFILE LOAD=auto
G90
G1 Z5
```

The command returned `ok`.

Post-cleanup state:

```text
bed_mesh.profile_name    = auto
gcode_move.gcode_position.z = 5.000000 mm
toolhead.position.z      = 3.074167 mm
gcode_move.homing_origin.z = 0.0 mm
heater_bed.target        = 0.0 C
extruder.target          = 0.0 C
print_stats.state        = standby
```

The `3.074167 mm` physical/toolhead Z with G-code Z `5.000000 mm` is the expected active-mesh transform at the saved center value `-1.925833 mm`:

```text
5.000000 + (-1.925833) = 3.074167 mm
```

It is not evidence of a standard Klipper Z offset.

Post-run `/opt/config/printer.cfg` SHA-256 remained:

```text
eeb58320516f538d2dcc3990a99c0da30e3b60dd11445d55e743781d3c8b1891
```

The saved `auto` profile remained unchanged and was restored active. A camera snapshot after cleanup succeeded (`190590` bytes), confirming continued remote visual supervision at that moment.

## Run disposition

```text
reference series present        = true
back-to-back confirmation       = true
cleanup/retract confirmed       = true
standard Z offset unchanged     = true
persistent printer.cfg changed  = false
saved mesh changed              = false
calibration stop condition      = false
kernel clean for reboot evidence= false
```

Therefore this run is **structurally useful diagnostic Gate C evidence**, but it is **not accepted as the clean reboot/power-cycle Gate C run** because the boot already contained camera-path kernel Oops events.

## Next acceptance objective

The next accepted reboot/time-separated Gate C run should begin only after the camera boot path is made deterministic enough that the new boot reaches:

1. Moonraker/Klipper ready;
2. no new `v4l2-ctl`/felix-vdec kernel Oops attributable to camera startup;
3. a usable remote camera path without unsafe all-`/dev/video?` diagnostics;
4. unchanged `printer.cfg` and saved `auto` mesh;
5. fresh ambient preflight, fresh `BED_MESH_CLEAR`, `G28`, center move, tare and independent 10-sample reference series.

A clean run should remain evidence-only until repeated diverse evidence, documented margins and explicit owner acceptance justify any production policy value.
