# Z Calibration backend coexistence repair — 2026-08-18

## Scope

This evidence records the controlled hardware productization pass after Owner RC acceptance, the shared-backend ownership collision discovered on the AD5X target, the repository coexistence repair, successful standalone Z Calibration observer deployment, update/repair idempotence, and exact uninstall restore on real hardware.

The subsequent reinstall/fresh-adoption hardware PASS is recorded separately in:

```text
docs/evidence/Z_CALIBRATION_BACKEND_REINSTALL_2026-08-19.md
```

## Canonical RC adoption — hardware PASS

Exact source used for the controlled RC ownership adoption:

```text
67577e02e5f11f6847748c5e359b780eb14f0730
```

Accepted winning state:

```text
_USER_START_PRINT = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
MESH_TEST = 3
CC_ENABLED = 0
policy_id = zcal-saved-check-v1-20260817
```

## Shared-backend collision and repair

Live discovery proved that Moonraker was serving the IFS backend `0.1.6` from `plugins_ad5x.py`, while the then-current ZCal feature line had independently evolved the same file. Replacing the live file would have destroyed the active IFS contract.

The accepted repair is additive coexistence:

```text
plugins_ad5x.py
  shared/platform/IFS host

plugins_ad5x_zcal.py
  standalone read-only Z Calibration component
  GET  /server/plugins_ad5x/z_calibration/snapshot
  POST /server/plugins_ad5x/z_calibration/reconcile
  GET  /server/plugins_ad5x/z_calibration/diagnostics
```

Canonical lifecycle:

```text
installer/z_calibration_backend_lifecycle.sh
install | update | repair | uninstall | status
```

Hard invariants:

- Z-Mod chroot target;
- idle/terminal state required before mutation;
- curl only, no wget;
- no Git operation inside lifecycle;
- no write/replacement of `plugins_ad5x.py`;
- no `FIRMWARE_RESTART`;
- no Z write, probe, G0 or G1;
- only standalone observer/core/config are owned;
- Moonraker stop -> bounded process-zero wait -> mutation/restore;
- transaction backup + rollback;
- shared backend compared before/after every transaction but never owned/pinned by ZCal;
- observer verifier requires `motion_owner=zmod`, `motion_actions_enabled=false`, `offset_write_enabled=false`.

## Repository acceptance

Accepted implementation/hardware source:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

Exact-head CI:

```text
Z Calibration Core    run 32181810994  SUCCESS
Z Calibration Actions run 32181811662  SUCCESS
```

All hardware lifecycle gates intentionally use this exact implementation SHA. Later branch-head commits are evidence-only and do not alter runtime/lifecycle code.

## Standalone lifecycle — real AD5X hardware PASS

### Install

```text
backend_install_rc = 0
backend_status_rc = 0
snapshot / reconcile / diagnostics = 200 / 200 / 200
```

Observer remained read-only and Z-Mod-owned:

```text
calibration.state = observer
motion_owner = zmod
motion_actions_enabled = false
offset_write_enabled = false
```

### Update idempotence

```text
update_rc = 0
update_status_rc = 0
endpoints = 200 / 200 / 200
```

Original ownership snapshot, managed hashes, shared IFS backend and live IFS worktree remained unchanged.

### Repair idempotence

```text
repair_rc = 0
repair_status_rc = 0
endpoints = 200 / 200 / 200
```

Original ownership snapshot, managed hashes, shared IFS backend and live IFS worktree again remained unchanged.

### Uninstall + exact pre-install restore

Canonical uninstall:

```text
uninstall_rc = 0
backup = /opt/config/mod_data/ad5x_custom/backups/zcal-backend-uninstall-20260818-235827-24317
```

Exact restored standalone state:

```text
snapshot / reconcile / diagnostics = 404 / 404 / 404
plugins_ad5x_zcal.py = absent
plugins_ad5x_zcalibration.py = absent
zcal_backend.moonraker.conf = absent
standalone Moonraker include = absent
ownership state = absent
standalone bytecode = absent
```

Archived ownership provenance remained exact:

```text
manifest sha256 = 72de679bf69619a989792114ce6681fb8db8bf35389756c8f576b35da030534b
original tree sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
original include count = 0
```

The first uninstall acceptance harness produced a false negative because it checked the pure-Klipper RC include in Moonraker's include file. Corrected read-only acceptance proved the canonical RC include remained exactly once in:

```text
/opt/config/mod_data/plugins.cfg
```

and RC Productization remained active and verified.

## Shared IFS invariant

Across install/update/repair/uninstall:

```text
http=200;backend_version=0.1.6;ifs=1
plugins_ad5x.py sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
```

The unrelated live IFS worktree remained exactly:

```text
branch = feature/ifs-manager-v1
HEAD   = d3887210f8f269ca27d6f2c8386f2edd3d3fa048
status = clean
tracked diff sha256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
untracked = none
```

No Klipper firmware restart, Z write, probe or motion command was issued during lifecycle acceptance.

## Current state

The exact uninstall gate is accepted. A subsequent clean reinstall/fresh-adoption hardware gate also passed and is documented in `Z_CALIBRATION_BACKEND_REINSTALL_2026-08-19.md`.

Current hardware state after that reinstall:

```text
standalone Z Calibration backend = INSTALLED
pure-Klipper RC Productization = active
shared IFS backend = active
printer = healthy/standby
```

Next independent gate: full printer power-cycle persistence/regression. Frontend productization remains blocked until that gate passes.
