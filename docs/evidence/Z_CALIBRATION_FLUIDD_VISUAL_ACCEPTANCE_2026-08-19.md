# Z Calibration Fluidd visual acceptance — 2026-08-19

## Scope

This evidence records acceptance of the first human-facing Fluidd Calibration Center slice after the standalone Z Calibration backend coexistence and lifecycle gates were completed.

This is **not** full Calibration Center feature completion. It accepts the read-only status/provenance UI layer only.

## Backend semantics repair

Exact Plugins AD5X backend repair source:

```text
cea95cd13347c868f478b26ddf6bf91a6cbd611b
```

Exact-head CI:

```text
Z Calibration Core    run 32191563348  SUCCESS
Z Calibration Actions run 32191563378  SUCCESS
```

The repair corrected two live-observed semantic defects without changing physical ownership:

1. Z-Mod `_START_PRINT.zzoffset = 99.0` is a sentinel meaning that slicer Z-offset is not set. The observer now normalizes it to `null` instead of exposing `+99.000 mm` as a user value.
2. Before Z homing, `gcode_move.homing_origin.z` is no longer claimed as a valid effective Z-offset and is no longer reconciled into a false `external_unknown` residual.

Real AD5X controlled update PASS:

```text
module_version = 0.1.3
homed_axes = ""
effective_valid = false
effective = null
persistent_user = -0.016
auto_alignment = 0.0
external_unknown = 0.0
provenance_status = not_homed
reported_homing_origin_z = 0.0
requested_slicer_z_offset = null
snapshot / reconcile / diagnostics = 200 / 200 / 200
motion_owner = zmod
motion_actions_enabled = false
offset_write_enabled = false
```

Ownership/adoption baseline, pure-Klipper RC, shared IFS backend and unrelated live IFS worktree remained unchanged.

## Fluidd UX repair

Exact Fluidd head accepted for this visual gate:

```text
e2c54f617c68cba1d5e5b01374fc9e3562f7e890
```

Merge-with-current-upstream CI:

```text
BUILD run 32192533707  SUCCESS
```

Passed:

- frozen dependency install;
- lint;
- type-check;
- unit tests;
- circular dependency check;
- production build;
- artifact upload.

CI artifact:

```text
fluidd-eb1c16e30ad2ac4306db7c5e757ab81cb70215ea.zip
sha256 = b0bbe927e496cf0563d66b9b5aea001661f8367336876d5e5085434179c03352
index sha256 = af675b33fae45f2555a2369b418903f78c1166ad2e1ff40ff9b94355edccadb2
AD5X chunk = Ad5xShell-D3yYdsjH.js
```

## Real AD5X controlled web deploy

Persistent backup created before replacement:

```text
/opt/config/mod_data/ad5x_custom/backups/fluidd-zcal-ux-e2c54f61-20260819-012931-28269
```

Deployment acceptance:

```text
artifact SHA verified
previous live tree backup = 276 / 276 files, exact tree match
zmod_httpd stopped and restarted
HTTP root after deploy = 200
disk index sha = expected
served index sha = expected
live Z-Mod config.json preserved
shared Plugins AD5X snapshot = 200
standalone ZCal snapshot = 200
Moonraker/Klippy = healthy / ready
failed_components = []
warnings = []
IFS branch/head/diff/untracked = unchanged
```

No Moonraker, Klipper or MCU restart was performed by the Fluidd deploy. Only the Fluidd web service was restarted.

## Owner visual acceptance

The owner supplied a full-page live Fluidd screenshot after hard refresh.

Observed and accepted behavior:

- `Центр калибровки Z` loads inside the normal Fluidd shell;
- safe-state banner reports the Z calibration system ready while explaining that effective Z appears only after Z homing;
- effective Z renders as `—` before homing instead of false `0.000 mm`;
- Auto-Z observer value renders `0.000 mm`;
- persistent user trim renders `-0.016 mm`;
- slicer Z-offset renders `не задан` instead of the Z-Mod sentinel `+99.000 mm`;
- no false orange `external_unknown` warning is shown while Z is unhomed;
- three primary Z summary cards use a compact three-column tablet/desktop composition;
- main safety/ownership rows use human-facing Russian labels;
- technical policy/model/raw provenance values are kept in `Расширенная диагностика`;
- shared Plugins AD5X / IFS system information remains available below the ZCal surface;
- the normal Fluidd navigation/layout remains intact.

Result:

```text
Fluidd Calibration Center read-only/status/provenance visual gate = PASS
```

## Remaining product scope

This PASS does not claim the whole Calibration Center is feature-complete.

Still required:

- mesh mode/status presentation;
- bounded structured diagnostic-event/history UI;
- backend-owned semantic action contract for user-facing operations such as `Проверить Z`, runtime `Построить карту`, `Полная калибровка`, cancel, and optional first-layer verification where those production paths are proven;
- frontends must call those semantic backend actions and must never implement direct probe/contact/Z-motion/Z-write logic;
- remaining release/hardware-change acceptance gates from the Z Calibration test plan;
- later frontend parity for Mainsail, HelixScreen, Guppy and KlipperScreen after the Fluidd contract is accepted.
