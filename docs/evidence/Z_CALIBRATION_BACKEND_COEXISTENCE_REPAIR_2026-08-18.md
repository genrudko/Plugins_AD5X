# Z Calibration backend coexistence repair — 2026-08-18

## Scope

This evidence records the controlled hardware productization pass after Owner RC acceptance, the shared-backend ownership collision discovered on the AD5X target, the repository coexistence repair, successful standalone Z Calibration observer deployment, update/repair idempotence, and exact uninstall restore on real hardware.

## Canonical RC adoption — hardware PASS

Exact source used for the controlled RC ownership adoption:

```text
67577e02e5f11f6847748c5e359b780eb14f0730
```

Live IFS worktree before and after adoption:

```text
branch = feature/ifs-manager-v1
HEAD   = d3887210f8f269ca27d6f2c8386f2edd3d3fa048
status = clean
tracked diff sha256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
untracked = none
```

Canonical RC ownership result:

```text
lifecycle_install_rc = 0
lifecycle_status_rc  = 0
owner_path           = /opt/config/mod_data/user.cfg
baseline_kind        = cc
baseline_source      = legacy_backup
original MESH_TEST   = 2
original CC_ENABLED  = 1
policy_original      = absent
```

Effective live state:

```text
print_state        = standby
effective commands = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
MESH_TEST          = 3
CC_ENABLED         = 0
policy_id          = zcal-saved-check-v1-20260817
max_auto_alignment = 0.12
```

## Shared-backend collision and repair

Live discovery proved that Moonraker was serving the IFS backend `0.1.6` from `plugins_ad5x.py`, while the then-current ZCal feature line had independently evolved the same file. ZCal endpoints were `404`; replacing the live file would have destroyed the active IFS contract.

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

Activation:

```text
[plugins_ad5x_zcal]
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

All hardware lifecycle gates below intentionally continue to use this exact implementation SHA. Later branch-head commits are evidence-only and do not alter runtime/lifecycle code.

## Standalone install — real AD5X hardware PASS

Pre-install standalone state:

```text
Z snapshot HTTP = 404
plugins_ad5x_zcal.py = absent
plugins_ad5x_zcalibration.py = absent
zcal_backend.moonraker.conf = absent
standalone include count = 0
manifest = absent
```

Install/status:

```text
backend_install_rc = 0
backend_status_rc  = 0
```

Moonraker/Klippy:

```text
klippy_connected  = true
klippy_state      = ready
failed_components = []
warnings          = []
```

Shared IFS invariant before/after:

```text
http=200;backend_version=0.1.6;ifs=1
plugins_ad5x.py sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
```

Standalone endpoints:

```text
snapshot    = 200
reconcile   = 200
diagnostics = 200
```

Observer contract:

```text
available              = true
health                 = ok
calibration.state      = observer
motion_owner           = zmod
motion_actions_enabled = false
offset_write_enabled   = false
offset_hook_enabled    = true
offset_hook_status     = loaded
policy_id              = zcal-saved-check-v1-20260817
```

Observed/raw-consistent provenance:

```text
persistent_user  = -0.016
auto_alignment   =  0.000
slicer_job       =  0.000
live_adjustment  =  0.000
external_unknown = +0.016
known_total      = -0.016
effective        =  0.000
status           = external_unknown
```

All observer-vs-raw checks passed. The `+0.016` standby/unhomed residual is deliberately left as `external_unknown`; it is not fabricated as babystepping.

Ownership state after install:

```text
schema = 1
z_endpoint_original_http = 404
shared_signature_at_adoption = http=200;backend_version=0.1.6;ifs=1
observer_installed_sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
core_installed_sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
config_installed_sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
include_count = 1
```

## Update + repair idempotence — real AD5X hardware PASS

Baseline ownership before the repeated lifecycle transitions:

```text
schema = 1
shared_signature_at_adoption = http=200;backend_version=0.1.6;ifs=1
z_endpoint_original_http = 404
original_tree_sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
include_count = 1
```

`update`:

```text
update_rc = 0
update_status_rc = 0
shared_before = http=200;backend_version=0.1.6;ifs=1
shared_after  = http=200;backend_version=0.1.6;ifs=1
shared runtime sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
original_tree_sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
include_count = 1
endpoints = 200 / 200 / 200
```

`repair`:

```text
repair_rc = 0
repair_status_rc = 0
shared_before = http=200;backend_version=0.1.6;ifs=1
shared_after  = http=200;backend_version=0.1.6;ifs=1
shared runtime sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
original_tree_sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
include_count = 1
endpoints = 200 / 200 / 200
```

Managed hashes remained equal to the accepted exact source after both transitions.

Final observer-vs-raw checks after `update` and `repair`:

```text
persistent_matches_raw = true
auto_matches_raw = true
effective_matches_raw = true
live_not_fabricated = true
residual_matches = true
motion_owner_zmod = true
motion_disabled = true
offset_write_disabled = true
persistent_user = -0.016
auto_alignment = 0.0
live_adjustment = 0.0
external_unknown = 0.016
effective = 0.0
provenance_status = external_unknown
```

## Uninstall + exact pre-install restore — real AD5X hardware PASS

The standalone backend was uninstalled from the same accepted exact source:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

Pre-uninstall ownership provenance:

```text
manifest_sha256 = 72de679bf69619a989792114ce6681fb8db8bf35389756c8f576b35da030534b
original_tree_sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
original_include_count = 0
original observer/core/config = absent
z_endpoint_original_http = 404
```

Canonical uninstall result:

```text
uninstall_rc = 0
backup = /opt/config/mod_data/ad5x_custom/backups/zcal-backend-uninstall-20260818-235827-24317
```

Moonraker/Klippy remained healthy after the Moonraker-only transition:

```text
server_info_http = 200
klippy_connected = true
klippy_state = ready
failed_components = []
warnings = []
```

Exact standalone restore:

```text
snapshot    = 404
reconcile   = 404
diagnostics = 404
plugins_ad5x_zcal.py = absent
plugins_ad5x_zcalibration.py = absent
zcal_backend.moonraker.conf = absent
standalone Moonraker include count = 0
ownership state dir = absent
standalone bytecode = absent
standalone status rc = 1 (expected inactive state)
```

The ownership state was archived with exact provenance:

```text
archived manifest sha256 = 72de679bf69619a989792114ce6681fb8db8bf35389756c8f576b35da030534b
archived original tree sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
archived original include count = 0
```

The first uninstall acceptance harness incorrectly checked the pure-Klipper RC policy include in Moonraker's `plugins.moonraker.conf`, yielding a false negative. The canonical RC lifecycle actually owns that include in:

```text
/opt/config/mod_data/plugins.cfg
```

Corrected read-only acceptance proved:

```text
standalone_include_in_moonraker = 0
rc_policy_include_in_klipper = 1
rc_policy_include_in_moonraker = 0
rc_productization_status_rc = 0
```

Raw pure-Klipper RC state after backend uninstall remained exactly:

```text
mesh_test = 3
cc_enabled = 0
load_zoffset = 1
print_leveling = 0
screen = false
force_kamp = false
force_leveling = false
policy_id = zcal-saved-check-v1-20260817
_USER_START_PRINT = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
```

Shared IFS remained byte-for-byte unchanged:

```text
http=200;backend_version=0.1.6;ifs=1
plugins_ad5x.py sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
```

Across install/update/repair/uninstall the live IFS worktree remained exactly:

```text
branch = feature/ifs-manager-v1
HEAD   = d3887210f8f269ca27d6f2c8386f2edd3d3fa048
status = clean
tracked diff sha256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
untracked = none
```

No Klipper firmware restart, Z write, probe or motion command was issued during the standalone lifecycle gates.

## Gate status

Accepted:

- canonical RC ownership adoption;
- shared-backend collision diagnosis;
- standalone backend repository repair;
- standalone observer `install` on real AD5X;
- standalone backend `update` idempotence on real AD5X;
- standalone backend `repair` idempotence on real AD5X;
- standalone backend `uninstall` with exact pre-install restore on real AD5X;
- corrected proof that the original uninstall red result was acceptance-harness false negative only;
- shared IFS coexistence byte-for-byte;
- observer provenance against raw Klipper/Z-Mod after repeated Moonraker-only transitions.

Current hardware state after accepted uninstall:

```text
standalone Z Calibration backend = intentionally UNINSTALLED
pure-Klipper RC Productization = active
shared IFS backend = active
printer = healthy/standby
```

Still pending as separate gates:

1. standalone reinstall from accepted exact implementation SHA;
2. power-cycle regression after reinstall;
3. frontend productization only after lifecycle/provenance gates are complete.
