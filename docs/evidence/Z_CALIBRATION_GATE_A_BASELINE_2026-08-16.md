# Z Calibration Gate A — post-adjustment bed-mesh baseline

**Date:** 2026-08-16  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_a_read_only_baseline`  
**Authority:** descriptive hardware evidence only; does not authorize Plugins AD5X motion or writes

## Provenance

- Plugins AD5X repository source context before this evidence artifact: `439c795a75531a75d273a1e14f3bb01829a7aaf5`.
- Source 1: owner-provided screenshot of the live bed-mesh UI after current mechanical adjustment.
- Source 2: owner-provided live `/usr/data/config/printer.cfg` excerpt containing Klipper `SAVE_CONFIG` bed-mesh profiles.
- Physical context reported by owner immediately before this baseline: head-belt tightening and bed screws/fasteners tightening.
- Mesh geometry: 5 × 5 measured points, X 0..215 mm, Y 0..215 mm, bicubic interpolation, `mesh_x_pps=5`, `mesh_y_pps=5`, tension 0.2.
- The Plugins AD5X CALIBRATION-SUBSYSTEM-002 motion/write path was not deployed or used for this measurement.
- Exact live Z-Mod/Klipper/Moonraker versions, active probe definition and Z travel bounds are not present in the supplied excerpt and remain pending Gate-A provenance fields.

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

## Gate-A status

This artifact records the fresh bed-mesh baseline after the reported mechanical adjustment. It remains a **partial Gate-A record** until exact live software versions and the active probe/Z-limit ownership are captured from the included configuration sources.

No `owner_accepted`, `ready_for_motion`, search margin, approach speed, contact speed, retract distance, Auto-Z correction limit or release threshold is established by this record.
