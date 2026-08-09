# Calibration Center for Flashforge AD5X + Z-Mod

`CALIBRATION-CENTER-001` is a separate, lightweight calibration module. It does not belong to IFS, Camera Manager, Notify or Timelapse and does not require a background daemon.

## What it does

Current Draft provides:

- up to 8 persistent hotend/nozzle profiles;
- a Fluidd/Mainsail/Helix action-prompt entry point: `CALIBRATION_CENTER`;
- five independent load-cell/contact probes per automatic run;
- mean/median/range evidence and a strict repeatability gate;
- bed-mesh isolation during physical-reference measurement;
- rejection of unstable or unexpectedly large geometric changes;
- separate `AUTO MEASURED` and `USER VERIFIED` states;
- persistent `needs_calibration` readiness state;
- one-level previous-known-good rollback;
- documented `_USER_START_PRINT` integration after Z-Mod finishes its own start logic;
- a built-in guided first-layer test with beginner material presets;
- transient Calibration Center print/live correction isolated from the user's global Z-Mod offset via reversible `G92` coordinate-origin transforms;
- no edit of Klipper `[probe] z_offset`;
- no write to Flashforge `zProbeOffset`;
- no MCU firmware operation, USB reset or permanent background polling.

The physical/correction evidence is documented in [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md). The exact safety contract is in [`docs/ALGORITHM_AND_SAFETY.md`](docs/ALGORITHM_AND_SAFETY.md).

## Important technical boundary

A repeatable nozzle contact proves a stable physical reference. Public AD5X/Z-Mod source does **not** prove that this reference alone always equals the ideal extrusion gap for a never-verified hotend/nozzle combination.

Therefore a new profile follows this lifecycle:

```text
NEW / NEEDS CALIBRATION
        ↓ automatic 5-probe measurement
AUTO MEASURED
        ↓ one guided first-layer verification if this profile has never been verified
USER VERIFIED
        ↓ later switch back to this profile
automatic 5-probe measurement → accepted geometric state → ready to print
```

A switched profile is deliberately blocked from affecting print Z until a new five-probe run succeeds. A rejected run preserves previous known-good correction values, but it does **not** make the profile ready again.

## Default automatic sequence

`CC_CALIBRATE`:

1. rejects printing/paused state;
2. validates AD5X/profile/temperature/safety bounds;
3. saves G-code state and current bed-mesh profile;
4. immediately marks the profile as requiring a successful calibration;
5. schedules a heater/state failsafe;
6. reuses Z-Mod `_ORIG_CLEAR_NOZZLE` for the existing cleaning/contact path;
7. stabilises bed/nozzle at measurement temperature;
8. performs a final low-temperature mechanical wipe with Z-Mod `_GOTO_TRASH` + `_CLEAR_REZINA CLEAR_NOZ=1`;
9. clears loaded bed mesh so physical reference is not contaminated by mesh compensation;
10. homes with Z-Mod `_G28`;
11. derives the XY measurement point from configured AD5X client limits;
12. performs 5 × `LOAD_CELL_TARE → PROBE → capture → lift`;
13. calculates median, mean and total range;
14. rejects the whole series if `range > MAX_RANGE` (provisional default `0.030 mm`);
15. for an already verified profile, calculates `fresh_reference - verified_reference` and rejects an excessive jump;
16. only on success stores accepted evidence and clears `needs_calibration`;
17. turns heaters off and restores previous mesh/G-code state.

No outlier is silently removed in order to make a bad series pass.

## How profile correction is layered

At the end of Z-Mod `START_PRINT`, the documented `_USER_START_PRINT` hook calls `CC_APPLY_PROFILE`.

Calibration Center keeps three concepts separate:

1. **user/Z-Mod global Z baseline** — persistent and owned by Z-Mod/Helix/user;
2. **physical reference delta** — produced by accepted automatic probing;
3. **verified process bias** — learned by the guided first-layer verification.

A profile also stores `verified_global_z`: the global Z-Mod value that existed when the process layer was USER VERIFIED. If the user later changes the global baseline, Calibration Center normalises the profile in its own transient correction rather than rewriting the user's setting.

- With `MESH_TEST=3/4`, Z-Mod already performs its own differently anchored print-time AutoZOffset. Calibration Center does not add its profile reference delta a second time.
- With `MESH_TEST=1/2`, Calibration Center may include the accepted `auto_delta` in its transient correction.

The resulting Calibration Center correction is applied with a **G92 coordinate-origin transform**, not with `SET_GCODE_OFFSET` or Z-Mod `_SET_GCODE_OFFSET_FAST`. A short delayed cleanup check exists only while that transient profile origin is active and reverses it after the print ends.

If the selected enabled profile has `needs_calibration=1`, the print-start hook emits a clear error and invokes normal Z-Mod `CANCEL_PRINT`. The explicit fallback is `CC_DISABLE`, which leaves stock Z-Mod behaviour available.

## Profiles

The prompt provides one-button creation of common profiles such as:

- Stock / 0.4;
- A1 / 0.4;
- A1 / 0.6;
- A1 / 0.8.

Generic profile operations are also exposed as stable macro API:

```gcode
CC_PROFILE_CREATE SLOT=1 HOTEND=Stock NOZZLE=0.4 NAME=Stock_0.4
CC_PROFILE_CREATE SLOT=2 HOTEND=A1 NOZZLE=0.4 NAME=A1_0.4
CC_PROFILE_CREATE SLOT=3 HOTEND=A1 NOZZLE=0.6 NAME=A1_0.6
CC_PROFILE_CREATE SLOT=4 HOTEND=A1 NOZZLE=0.8 NAME=A1_0.8
CC_PROFILE_SELECT SLOT=4
CC_PROFILE_RENAME SLOT=4 NAME=A1_08_Hardened
```

A profile stores measured reference, accepted quality, verified reference/bias/global-Z baseline, previous verified tuple, readiness, hotend/nozzle metadata and calibration temperatures.

### Current Draft UX boundary

The action-prompt UI is deliberately built without DOM patching or a permanent web daemon. Current Z-Mod action prompts do not provide a free-text input control, so arbitrary profile renaming/custom profile text still uses the stable macro API above. Likewise, the event audit has a real timestamp, but the current prompt does not yet surface a human-readable “last calibration date”.

Critical Helix buttons deliberately use short labels (`Автокалибровка`, `Первый слой`, `Откат`, `Сохранить`, `Отмена`) because physical testing showed longer labels are clipped on the Helix screen.

## Guided built-in first-layer verification

From `CALIBRATION_CENTER → Первый слой`, the idle prompt offers starter presets:

- PLA — 210 / 60 °C;
- PETG — 240 / 75 °C;
- ABS — 250 / 100 °C;
- ASA — 250 / 100 °C;
- TPU — 225 / 50 °C.

These are conservative **starter verification presets**, not claimed as universally optimal material profiles. `Другой` keeps an expert fallback:

```gcode
CC_FIRST_LAYER_TEST MATERIAL=CUSTOM NOZZLE_TEMP=... BED_TEMP=...
```

Safety limits are 170..280 °C for the nozzle and 0..110 °C for the bed.

The plugin generates `Calibration_Center_First_Layer.gcode` on demand inside the configured `virtual_sdcard` directory. The generated file:

1. uses normal Z-Mod `START_PRINT EXTRUDER_TEMP=... BED_TEMP=...` with no special skip flags;
2. traverses the same Z-Mod start/mesh/global-offset logic and `_USER_START_PRINT` hook as an ordinary sliced print;
3. prints a centered serpentine patch whose layer height/line width scale from the selected nozzle diameter;
4. packs neighbouring roads with a rounded-rectangle bead model rather than the rejected `pitch = line_width` model;
5. extrudes short Y connectors as part of one continuous serpentine and normalises `M220/M221` to 100%;
6. exposes `-0.05 / -0.01 / +0.01 / +0.05` only while the generated test is actually printing;
7. applies each live step with isolated `G92` origin change + matching immediate relative Z move, leaving the global Z-Mod offset untouched;
8. caps total test adjustment at ±0.10 mm (with a tighter negative limit for thinner generated layers);
9. reopens the prompt after every live step and separately shows `Глобальный Z-Mod`, `CC профиль`, and `test ΔZ`;
10. after the patch, lifts the nozzle and enters controlled `PAUSE` review;
11. permits `Сохранить` only from that review pause;
12. reverses the test G92 origin on save, abort, natural fall-through or external cancel;
13. on first verification stores the deliberate test delta as process bias; on re-verification it absorbs the **profile correction actually active during the test plus final test delta** before moving the verified anchors.

### Physical first-layer evidence so far

The first built-in generator revision was physically exercised on the target AD5X with PLA at 210/60 °C and A1/0.4. The normal working Z-Mod/Helix baseline was approximately `-0.125...-0.130 mm`. The generated patch showed visible separation between roads. Applying two live `-0.05 mm` steps moved the displayed Z state to about `-0.225 mm` and improved merging, but the sheet still separated visibly along print roads.

That run is **not accepted as Z-offset evidence** and no `USER VERIFIED` value was saved.

Physical follow-up exposed a second safety issue: after the experiment the operator found the printer's Z-offset at `-0.225 mm` and had to restore it manually. The operator then set approximately `-0.13 mm` and an ordinary sliced print again produced a visually coherent first layer in camera evidence. This makes `-0.13 mm` the current practical control baseline, not a value discovered by Calibration Center.

The revised design therefore fixes **both** failure classes: bead spacing and Z-state isolation. Source/CI acceptance now explicitly rejects any executable `SET_GCODE_OFFSET`, `_SET_GCODE_OFFSET`, or `_SET_GCODE_OFFSET_FAST` in the Calibration Center print/live operational layer. Physical acceptance must still prove before/after that the global Z-Mod value is unchanged.

See [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) for that exact procedure.

## Install — current Draft branch

For runtime acceptance before merge:

```sh
rm -f /tmp/calibration-center-install.sh
wget -qO /tmp/calibration-center-install.sh \
  "https://raw.githubusercontent.com/genrudko/Plugins_AD5X/codex/5-calibration-center-001/calibration_center/install.sh?cb=$(date +%s)"
chmod +x /tmp/calibration-center-install.sh
CALIBRATION_CENTER_REF="codex/5-calibration-center-001" /tmp/calibration-center-install.sh --install
```

The installer:

- refuses printing/paused state;
- fails closed if Moonraker cannot prove printer state;
- refuses pre-existing dirty Z-Mod/Klipper/Moonraker repositories;
- checks required Z-Mod safety/extension primitives, including `START_PRINT`, `END_PRINT`, virtual-SD printing and `PAUSE`;
- creates a separate git checkout at `/opt/config/mod_data/plugins/calibration_center`;
- adds only an include in `mod_data/plugins.cfg`;
- uses the documented `mod_data/user.cfg` `_USER_START_PRINT` extension point;
- refuses to overwrite an already customised `_USER_START_PRINT`;
- adds a dedicated Moonraker Update Manager entry;
- snapshots all touched custom config files before modification;
- scans every split Calibration Center cfg for forbidden operational primitives;
- leaves Z-Mod/Klipper/Moonraker tracked repositories untouched.

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

This disables Calibration Center profile enforcement/corrections. Stock Z-Mod calibration remains available.

Re-enable:

```gcode
CC_ENABLE
```

## Uninstall

```sh
/opt/config/mod_data/plugins/calibration_center/calibration_center/install.sh --uninstall
```

Uninstall removes the include, the marked `_USER_START_PRINT` hook, Update Manager entry and plugin checkout. It intentionally preserves `/opt/config/mod_data/calibration_center` profile/audit data for recovery. It never restores or writes Flashforge Z calibration files because it never modified them.

## Runtime acceptance

Repository/static acceptance is automated in `tests/test_calibration_center*.py`. Physical acceptance must be performed on the target AD5X because load-cell repeatability, hotend mechanics, temperature dependence, first-layer behaviour and global-offset isolation cannot be proven by repository tests.

See [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) for the evidence matrix and physical test gates.
