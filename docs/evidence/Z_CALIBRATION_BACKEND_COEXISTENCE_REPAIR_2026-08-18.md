# Z Calibration backend coexistence repair — 2026-08-18

## Scope

This evidence records the controlled Z Calibration backend productization sequence on the real Flashforge AD5X: shared-backend collision discovery, additive standalone repair, lifecycle acceptance, exact uninstall restore, reinstall/fresh adoption, and final full power-cycle persistence/regression.

Detailed later-stage evidence:

```text
docs/evidence/Z_CALIBRATION_BACKEND_REINSTALL_2026-08-19.md
docs/evidence/Z_CALIBRATION_BACKEND_POWERCYCLE_2026-08-19.md
```

## Canonical RC adoption — hardware PASS

Accepted winning state:

```text
_USER_START_PRINT = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
MESH_TEST = 3
CC_ENABLED = 0
policy_id = zcal-saved-check-v1-20260817
```

Z-Mod remains the sole physical Auto-Z/contact owner. Plugins AD5X owns only the fail-closed policy/guard and read-only observer.

## Shared-backend collision and accepted repair

Hardware discovery proved that Moonraker was serving the active IFS backend `0.1.6` from `plugins_ad5x.py`, while the then-current ZCal feature line had independently evolved the same shared path. Replacing the live shared host would have destroyed the active IFS contract.

The accepted coexistence repair is additive:

```text
plugins_ad5x.py
  shared/platform/IFS host

plugins_ad5x_zcal.py
  standalone read-only Z Calibration component
  GET  /server/plugins_ad5x/z_calibration/snapshot
  POST /server/plugins_ad5x/z_calibration/reconcile
  GET  /server/plugins_ad5x/z_calibration/diagnostics
```

Canonical backend lifecycle:

```text
installer/z_calibration_backend_lifecycle.sh
install | update | repair | uninstall | status
```

Hard invariants:

- Z-Mod chroot target;
- idle/terminal state required before mutation;
- curl only, no wget;
- no Git operation inside lifecycle;
- no write/replacement of shared `plugins_ad5x.py`;
- no `FIRMWARE_RESTART`;
- no Z write, probe, G0 or G1;
- standalone observer/core/config ownership only;
- Moonraker stop -> bounded process-zero wait -> mutation/restore;
- transaction backup + rollback;
- shared backend compared before/after every transaction but never owned/pinned by ZCal;
- observer must remain `motion_owner=zmod`, `motion_actions_enabled=false`, `offset_write_enabled=false`.

## Accepted implementation source

All physical backend lifecycle gates were executed from the exact accepted implementation SHA:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

Exact-head CI for that implementation:

```text
Z Calibration Core    run 32181810994  SUCCESS
Z Calibration Actions run 32181811662  SUCCESS
```

Later branch-head commits are evidence-only and do not alter accepted runtime/lifecycle code.

## Real AD5X lifecycle acceptance

### Install — PASS

```text
install_rc = 0
status_rc = 0
snapshot / reconcile / diagnostics = 200 / 200 / 200
```

Observer remained read-only and Z-Mod-owned.

### Update idempotence — PASS

```text
update_rc = 0
update_status_rc = 0
endpoints = 200 / 200 / 200
```

Original ownership snapshot, managed hashes, shared IFS backend and live IFS worktree remained unchanged.

### Repair idempotence — PASS

```text
repair_rc = 0
repair_status_rc = 0
endpoints = 200 / 200 / 200
```

Original ownership snapshot, managed hashes, shared IFS backend and live IFS worktree again remained unchanged.

### Uninstall + exact pre-install restore — PASS

```text
uninstall_rc = 0
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

The first uninstall acceptance harness red result was a false negative caused by checking the pure-Klipper RC include in Moonraker's include file. Corrected read-only acceptance proved the RC include remained exactly once in `/opt/config/mod_data/plugins.cfg`, and RC status remained healthy.

### Reinstall / fresh adoption — PASS

The accepted uninstall left a clean `404/absent` baseline, which the reinstall adopted again correctly:

```text
reinstall_rc = 0
reinstall_status_rc = 0
snapshot / reconcile / diagnostics = 200 / 200 / 200
z_endpoint_original_http = 404
fresh original include count = 0
fresh original tree sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
```

Managed runtime hashes matched the accepted exact source.

### Full physical power-cycle persistence/regression — PASS

Verification after a physical printer power-off / power-on cycle observed:

```text
system_uptime_seconds = 254.76
server_info_http = 200
klippy_connected = true
klippy_state = ready
failed_components = []
warnings = []
backend status rc = 0
RC Productization status rc = 0
```

Fresh ownership provenance survived cold boot unchanged:

```text
schema = 1
z_endpoint_original_http = 404
shared_signature_at_adoption = http=200;backend_version=0.1.6;ifs=1
original tree sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
original include count = 0
```

Managed files and includes survived unchanged:

```text
plugins_ad5x_zcal.py sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
plugins_ad5x_zcalibration.py sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
zcal_backend.moonraker.conf sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
standalone Moonraker include count = 1
pure-Klipper RC include count = 1
```

Standalone endpoints after cold boot:

```text
snapshot / reconcile / diagnostics = 200 / 200 / 200
```

Observer remained healthy/read-only:

```text
available = true
health = ok
calibration.state = observer
motion_owner = zmod
motion_actions_enabled = false
offset_write_enabled = false
offset_hook_status = loaded
```

Observer-vs-raw provenance after cold boot passed completely:

```text
persistent_user = -0.016
auto_alignment = 0.0
live_adjustment = 0.0
external_unknown = +0.016
effective = 0.0
persistent_matches_raw = true
auto_matches_raw = true
effective_matches_raw = true
live_not_fabricated = true
residual_matches = true
motion_owner_zmod = true
motion_disabled = true
offset_write_disabled = true
```

The standby/unhomed `+0.016 mm` residual remains intentionally classified as `external_unknown`, not fabricated as babystepping/live adjustment.

## Shared IFS invariant

Across install/update/repair/uninstall/reinstall and the full cold boot:

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

## Final gate status

Accepted on real AD5X hardware:

1. RC Productization ownership adoption;
2. standalone backend install;
3. update idempotence;
4. repair idempotence;
5. uninstall + exact pre-install restore;
6. reinstall + fresh `404/absent` adoption;
7. full physical power-cycle persistence/regression.

Final result:

```text
physical backend lifecycle/provenance gate set = COMPLETE
```

Current hardware state:

```text
standalone Z Calibration backend = INSTALLED
pure-Klipper RC Productization = active
shared IFS backend = active
printer = healthy/standby
```

The physical lifecycle/provenance blocker for frontend/API productization is closed. Frontend work must consume the accepted standalone read-only Z Calibration API and must not reimplement safety, Z-offset arithmetic, contact motion, or ownership logic.
