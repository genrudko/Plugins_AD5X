# Z Calibration Gate A — post-adjustment bed-mesh baseline

**Date:** 2026-08-16  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_a_read_only_baseline`  
**Authority:** descriptive hardware evidence only; does not authorize Plugins AD5X motion or writes

## Provenance

- Plugins AD5X repository source context before the first evidence artifact: `439c795a75531a75d273a1e14f3bb01829a7aaf5`.
- Source 1: owner-provided screenshot of the live bed-mesh UI after current mechanical adjustment.
- Source 2: owner-provided live `printer.cfg` `SAVE_CONFIG` excerpt containing Klipper bed-mesh profiles.
- Source 3: owner-provided read-only Z-Mod chroot configuration inspection under `/opt/config`.
- Source 4: owner-provided read-only live Moonraker/Klipper API responses plus exact Git checkout inspection inside the Z-Mod chroot.
- Physical context reported by owner immediately before this baseline: head-belt tightening and bed screws/fasteners tightening.
- Mesh geometry: 5 × 5 measured points, X 0..215 mm, Y 0..215 mm, bicubic interpolation, `mesh_x_pps=5`, `mesh_y_pps=5`, tension 0.2.
- The Plugins AD5X CALIBRATION-SUBSYSTEM-002 motion/write path was not deployed or used for this measurement.
- Z-Mod chroot used for configuration/runtime inspection: `/usr/data/.mod/.zmod`; active configuration namespace inside the chroot: `/opt/config`.

## Live software/runtime provenance

### Z-Mod

- reported AD5X version from `/opt/config/mod/version_5x.txt`: `1.7.2-5`;
- checkout branch: `1.7`;
- exact checkout HEAD: `2e32155d00e464094b8c7197e23783ec821a112c`.

### Klipper

Live `/printer/info` reported:

```text
state            = ready
hostname         = flashforge
klipper_path     = /usr/data/config/base/klipper
python_path      = /usr/prog/Python-3.8.2/bin/python3
process_id       = 1706
log_file         = /usr/data/logs/printer.log
config_file      = /usr/data/config/printer.cfg
software_version = v0.13.0-753-g0df153f7-ZMOD-20260816
```

The inspected checkout at `/opt/config/base/klipper` reports exact HEAD:

```text
6bd8fca222811d465b4be3b0ed862915d6caf59e
```

The runtime software string embeds `g0df153f7`, while the inspected checkout HEAD is `6bd8fca...`. These are retained as **distinct provenance facts**. This Gate-A record does not infer that they are equivalent and does not invent a cause for the difference.

### Moonraker

Live `/server/info` reported:

```text
klippy_connected       = true
klippy_state           = ready
failed_components      = []
warnings               = []
moonraker_version      = ?
api_version            = [1, 5, 0]
api_version_string     = 1.5.0
```

The inspected checkout at `/opt/config/base/moonraker` reports exact HEAD:

```text
a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e
```

Moonraker's semantic/version field is literally `?` in the live API response. The evidence therefore records `?` rather than substituting an invented semantic version; exact checkout SHA plus API version are retained for reproducibility.

## Active include context

The live `/opt/config/mod_data/plugins.cfg` supplied by the owner includes:

```ini
[include plugins/recommend/recommend.cfg]
[include plugins/dryer/ru/dryer.cfg]
[include plugins/ad5x_custom/ad5x_custom.cfg]
[include ad5x_custom/generated/notify.cfg]
[include ad5x_custom/generated/timelapse.cfg]
[include plugins/calibration_center/calibration_center/calibration_center.cfg]
```

Ownership/interpretation for this evidence record:

- `recommend` is the active Z-Mod recommendation override and contributes the runtime probe/bed-mesh overrides described below;
- `ad5x_custom` is the existing Plugins AD5X customization contour;
- `calibration_center` is the project's existing unfinished/legacy Calibration Center contour, not an unknown third-party plugin and not evidence of a second independent probe owner;
- the active-file scan found no `[stepper_z]` override in the active include set; the effective Z-stepper values therefore come from `/opt/config/printer.base.cfg` on the supplied configuration evidence;
- the active `recommend` file contains `[probe]` overrides for `speed` and `lift_speed`, which merge with the base `[probe]` definition rather than replacing the complete probe contract.

## Effective current Z/probe configuration from supplied active sources

### `stepper_z`

Base owner: `/opt/config/printer.base.cfg`.

```ini
[stepper_z]
position_endstop: 220
step_pin: PC7
dir_pin: PC8
enable_pin: !PB14
microsteps: 16
rotation_distance: 8
endstop_pin: PD2
position_max: 230
position_min: -10
homing_speed: 20
homing_retract_dist: 5
homing_retract_speed: 10
```

No active `[stepper_z]` override was observed in the supplied active include set, so these are the current merged values on the available evidence.

### `probe`

Base owner: `/opt/config/printer.base.cfg`:

```ini
[probe]
pin: !PB3
z_offset: -0.25
samples_result: average
speed: 5
samples: 3
samples_tolerance: 0.1
samples_tolerance_retries: 4
```

Active Z-Mod `recommend` override: `/opt/config/mod_data/plugins/recommend/recommend.cfg`:

```ini
[probe]
speed: 2
lift_speed: 5
```

Effective merged probe facts on the supplied configuration evidence:

```text
pin                         = !PB3
z_offset                    = -0.25 mm
samples_result              = average
samples                     = 3
samples_tolerance           = 0.1 mm
samples_tolerance_retries   = 4
speed                       = 2 mm/s   (recommend override)
lift_speed                  = 5 mm/s   (recommend override/addition)
```

### Active `recommend` bed-mesh overrides

```ini
[bed_mesh]
move_check_distance: 5
horizontal_move_z: 2
```

These values are recorded as current runtime configuration facts only. In particular, `position_min=-10`, `horizontal_move_z=2`, probe speed `2`, and lift speed `5` are **not** automatically accepted as Plugins AD5X Auto-Z safety/search/motion thresholds. The v2 production motion policy still requires separate repeated hardware evidence, margin rationale and explicit owner acceptance.

## Fresh active profile — `auto`

Raw measured matrix from `SAVE_CONFIG`:

```text
-1.746667  -1.883333  -1.914167  -1.860000  -1.730833
-1.762500  -1.881667  -1.935833  -1.926667  -1.802500
-1.756667  -1.874167  -1.925833  -1.928333  -1.800833
-1.713333  -1.825833  -1.896667  -1.889167  -1.795833
-1.718333  -1.832500  -1.921667  -1.877500  -1.760000
```

Descriptive statistics only:

- minimum measured value: `-1.935833 mm`;
- maximum measured value: `-1.713333 mm`;
- raw measured span (`max-min`): `0.222500 mm`;
- arithmetic mean: `-1.83843332 mm`;
- median: `-1.860000 mm`;
- center sample: `-1.925833 mm`.

The UI reports profile deviation `0.2225`, which exactly matches the raw measured span. The interpolated 3D view reports about `0.2243`; that small increase is consistent with interpolation overshoot and must not replace the raw-point span in evidence.

## Earlier stored comparison profile — `MESH_DATA`

Raw matrix from the same supplied `SAVE_CONFIG` block:

```text
-0.385000  -0.500833  -0.565833  -0.485833  -0.343333
-0.370833  -0.480833  -0.510000  -0.478333  -0.359167
-0.354167  -0.444167  -0.508333  -0.467500  -0.350000
-0.355000  -0.418333  -0.484167  -0.430833  -0.325000
-0.348333  -0.430000  -0.459167  -0.414167  -0.292500
```

Descriptive statistics:

- minimum: `-0.565833 mm`;
- maximum: `-0.292500 mm`;
- span: `0.273333 mm`;
- arithmetic mean: `-0.42246660 mm`;
- median: `-0.430000 mm`;
- center sample: `-0.508333 mm`.

## Shape-only comparison

The absolute vertical baselines of `auto` and `MESH_DATA` differ by about `-1.41596672 mm` in their means. This Gate-A record does **not** classify that common-mode shift as bed deformation or an Auto-Z correction. Without identical reference/probe provenance, the absolute profile levels must not be compared as if they were pure bed shape.

After removing each profile's own arithmetic mean to compare shape only:

- Pearson shape correlation is approximately `0.862`;
- RMS point-by-point residual is approximately `0.0375 mm`;
- maximum absolute centered residual is approximately `0.0676 mm`;
- mean absolute centered residual is approximately `0.0326 mm`.

The fresh `auto` measured span is `0.050833 mm` smaller than `MESH_DATA`, a reduction of approximately `18.6%` in raw point-to-point range. This is descriptive evidence only. It is not by itself proof of a release-quality mechanical improvement or a basis for any motion/search threshold.

## Geometric observation

The measured surface remains a broad, smooth bowl-like shape: the central/interior region is lower than much of the perimeter, with no single isolated point dominating the range. The raw 5 × 5 matrix does not show a one-point spike comparable to a gross probe outlier.

This observation is qualitative and must not be converted into a calibration acceptance threshold.

## Gate-A status — COMPLETE

This artifact now records:

- the fresh bed-mesh baseline after the reported mechanical adjustment;
- active configuration include context;
- current base `stepper_z` contract;
- merged base + active-Z-Mod-`recommend` probe contract;
- active `recommend` bed-mesh overrides;
- exact Z-Mod version/branch/checkout SHA;
- live Klipper readiness/runtime software string plus exact inspected checkout SHA;
- live Moonraker readiness/API version plus exact inspected checkout SHA.

The optional live standard-Klipper effective-offset snapshot was not required to close this read-only Gate-A baseline because this gate establishes machine/configuration/mesh provenance rather than an Auto-Z correction. Effective-offset reconciliation remains a mandatory runtime preflight for any later controlled action.

**Gate A is complete as descriptive evidence.** It authorizes no motion or writes and establishes no production safety threshold.

No `owner_accepted`, `ready_for_motion`, search margin, approach speed, contact speed, retract distance, Auto-Z correction limit or release threshold is established by this record.
