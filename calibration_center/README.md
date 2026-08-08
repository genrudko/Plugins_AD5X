# Calibration Center for Flashforge AD5X + Z-Mod

`CALIBRATION-CENTER-001` is a separate, lightweight calibration module. It does not belong to IFS, Camera Manager, Notify or Timelapse and does not require a background daemon.

## What it does

Calibration Center provides:

- up to 8 persistent hotend/nozzle profiles;
- a simple Fluidd/Mainsail action-prompt entry point: `CALIBRATION_CENTER`;
- five independent load-cell/contact probes per automatic run;
- mean/median/range evidence and a strict repeatability gate;
- rejection of unstable or unexpectedly large geometric changes;
- separate `AUTO MEASURED` and `USER VERIFIED` states;
- one-level previous-known-good rollback;
- a documented `_USER_START_PRINT` integration which applies only the selected profile correction after Z-Mod finishes its own start logic;
- no edit of Klipper `[probe] z_offset`;
- no write to Flashforge `zProbeOffset`;
- no MCU firmware operation, USB reset or background polling.

The physical/correction model and its evidence are documented in [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md).

## Important technical boundary

A repeatable nozzle contact proves a stable physical reference. Public AD5X/Z-Mod source does **not** prove that this reference alone always equals the ideal extrusion gap for a never-verified hotend/nozzle combination.

Therefore a new profile follows this lifecycle:

```text
NEW
  ↓ automatic 5-probe measurement
AUTO MEASURED
  ↓ optional first-layer verification once
USER VERIFIED
  ↓ future nozzle/hotend swaps
automatic measurement → geometric delta → ready to print
```

This is intentionally stricter than pretending that five probe contacts automatically determine perfect first-layer extrusion.

## Default automatic sequence

`CC_CALIBRATE`:

1. rejects printing/paused state;
2. validates AD5X/profile/temperature/safety bounds;
3. schedules a heater failsafe;
4. reuses Z-Mod `_ORIG_CLEAR_NOZZLE` for the existing proven cleaning path;
5. stabilises bed/nozzle temperature;
6. homes with Z-Mod `_G28`;
7. derives the XY measurement point from the configured AD5X client limits;
8. performs 5 × `LOAD_CELL_TARE → PROBE → capture → lift`;
9. calculates median, mean and total range;
10. rejects the whole series if `range > MAX_RANGE` (default provisional `0.030 mm`);
11. for an already verified profile, calculates `fresh_reference - verified_reference` and rejects an excessive jump;
12. persists accepted evidence in `save_variables` and an on-demand audit log.

No outlier is silently removed in order to pass a bad series.

## How profile correction is layered

At the end of Z-Mod `START_PRINT`, the documented `_USER_START_PRINT` hook calls `CC_APPLY_PROFILE`.

Calibration Center stores a **process bias** separately from the automatic geometric delta.

- If Z-Mod `MESH_TEST=3/4` is active, Z-Mod already performs its own fresh-reference AutoZOffset. Calibration Center does not add its geometric delta a second time; it only adds the verified profile process bias.
- If `MESH_TEST=1/2` is active, Calibration Center may add the last accepted profile geometric delta plus the verified process bias.

This avoids double-applying the same physical change.

## Profiles

Common profile creation is available from the `CALIBRATION_CENTER` prompt. Generic operations are also exposed for the UI layer and expert recovery:

```gcode
CC_PROFILE_CREATE SLOT=1 HOTEND=Stock NOZZLE=0.4 NAME=Stock_0.4
CC_PROFILE_CREATE SLOT=2 HOTEND=A1 NOZZLE=0.4 NAME=A1_0.4
CC_PROFILE_CREATE SLOT=3 HOTEND=A1 NOZZLE=0.6 NAME=A1_0.6
CC_PROFILE_CREATE SLOT=4 HOTEND=A1 NOZZLE=0.8 NAME=A1_0.8
CC_PROFILE_SELECT SLOT=4
CC_PROFILE_RENAME SLOT=4 NAME=A1_08_Hardened
```

A profile stores measured reference, measurement quality, verified reference/bias, previous verified pair, nozzle/hotend metadata and calibration temperatures.

## First-layer verification

The first-layer path is deliberately optional and is **not** the automatic calibration mechanism.

During a real test print, `CC_FIRST_LAYER_CONTROLS` exposes:

- `-0.05`
- `-0.01`
- `+0.01`
- `+0.05`
- `Сохранить как USER VERIFIED`

`CC_VERIFY_CURRENT` records the resulting **process bias** relative to the Z-Mod runtime base that existed before Calibration Center added its profile correction. It also anchors the latest accepted physical reference.

## Install — current Draft branch

For acceptance of this work item before merge:

```sh
rm -f /tmp/calibration-center-install.sh
wget -qO /tmp/calibration-center-install.sh \
  "https://raw.githubusercontent.com/genrudko/Plugins_AD5X/codex/5-calibration-center-001/calibration_center/install.sh?cb=$(date +%s)"
chmod +x /tmp/calibration-center-install.sh
CALIBRATION_CENTER_REF="codex/5-calibration-center-001" /tmp/calibration-center-install.sh --install
```

The installer:

- refuses an active print/pause;
- refuses pre-existing dirty Z-Mod/Klipper/Moonraker repositories;
- checks the required Z-Mod safety/extension primitives;
- creates a separate git checkout at `/opt/config/mod_data/plugins/calibration_center`;
- adds only an include in `mod_data/plugins.cfg`;
- uses the officially documented `mod_data/user.cfg` `_USER_START_PRINT` extension point;
- refuses to overwrite an already customised `_USER_START_PRINT`;
- adds a dedicated Moonraker Update Manager entry;
- snapshots all touched custom config files before modification;
- leaves Z-Mod/Klipper/Moonraker repositories untouched.

A normal Klipper `FIRMWARE_RESTART` is required once to load a new cfg include. The installer does not execute it automatically and never flashes an MCU.

## Status

```sh
/opt/config/mod_data/plugins/calibration_center/calibration_center/install.sh --status
```

Expected upstream result after install:

```text
Z-Mod          CLEAN
Klipper        CLEAN
Moonraker      CLEAN
CalibCenter    CLEAN
```

## Disable without uninstall

```gcode
CC_DISABLE
```

This disables profile corrections only. Stock Z-Mod calibration remains available.

Re-enable:

```gcode
CC_ENABLE
```

## Uninstall

```sh
/opt/config/mod_data/plugins/calibration_center/calibration_center/install.sh --uninstall
```

Uninstall removes the include, the marked `_USER_START_PRINT` hook, Update Manager entry and plugin checkout. It intentionally preserves `/opt/config/mod_data/calibration_center` profile/audit data for recovery. It never restores/writes Flashforge Z calibration files because it never modified them.

## Runtime acceptance

Source/static acceptance is automated in `tests/test_calibration_center.py`. Physical acceptance must be performed on the target AD5X because probe repeatability, hotend mechanics and temperature dependence cannot be proved by repository tests.

See [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) for the exact evidence matrix.
