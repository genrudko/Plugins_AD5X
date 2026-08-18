# Z Calibration backend coexistence repair — 2026-08-18

## Scope

This evidence records the controlled hardware productization pass after Owner RC acceptance, the shared-backend ownership collision discovered on the AD5X target, the repository coexistence repair, and the first successful standalone Z Calibration observer deployment on real hardware.

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

## Live backend discovery — architectural blocker

Moonraker/Klippy were healthy, but the active shared backend was IFS `0.1.6`:

```text
GET /server/plugins_ad5x/snapshot -> 200
backend_version = 0.1.6
modules = [ifs]

POST /server/plugins_ad5x/z_calibration/reconcile -> 404
GET  /server/plugins_ad5x/z_calibration/diagnostics -> 404
```

The live IFS feature line and the then-current ZCal feature line had independently evolved the same path:

```text
moonraker/components/plugins_ad5x.py
```

Replacing the live IFS file with the ZCal implementation would have restored Z endpoints by destroying the active IFS backend contract. This was rejected as an ownership collision, not treated as a Z-offset failure.

Raw target state at discovery remained healthy:

```text
print_state      = standby
homed_axes       = ""
effective_Z      = 0.0
persistent_Z     = -0.016
temp_z_offset    = 0.0
screen           = false
load_zoffset     = 1
MESH_TEST        = 3
PRINT_LEVELING   = 0
CC_ENABLED       = 0
START.zzoffset   = 99.0
force_kamp       = false
force_leveling   = false
policy_id        = zcal-saved-check-v1-20260817
active_mesh      = auto
```

## Repair decision

Z Calibration no longer owns the shared backend host.

Repository composition:

```text
plugins_ad5x.py
  shared/platform host only

plugins_ad5x_zcal.py
  standalone read-only Z Calibration Moonraker component
  GET  /server/plugins_ad5x/z_calibration/snapshot
  POST /server/plugins_ad5x/z_calibration/reconcile
  GET  /server/plugins_ad5x/z_calibration/diagnostics
```

Standalone Moonraker activation:

```text
[plugins_ad5x_zcal]
```

Canonical backend lifecycle:

```text
installer/z_calibration_backend_lifecycle.sh
install | update | repair | uninstall | status
```

Hard lifecycle invariants:

- target is the Z-Mod chroot;
- printer must be idle/terminal before mutation;
- curl only; no wget dependency;
- no Git operation inside the canonical lifecycle;
- no write/replacement of `plugins_ad5x.py`;
- no `FIRMWARE_RESTART`;
- no Z write, probe, G0 or G1 command;
- only `plugins_ad5x_zcal.py`, `plugins_ad5x_zcalibration.py` and the generated standalone Moonraker config are owned;
- Moonraker stop is followed by a bounded process-zero wait before Python component mutation or restore;
- destination ownership is fail-closed;
- install/update/repair/uninstall are transactional with rollback backup;
- shared backend signature is compared before/after every ZCal transaction but is not owned or version-pinned by ZCal;
- live verifier requires `observer`, `motion_owner=zmod`, `motion_actions_enabled=false`, and `offset_write_enabled=false`.

## Repository acceptance for coexistence repair

Final hardware source SHA:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

Exact-head CI:

```text
Z Calibration Core    run 32181810994  SUCCESS
Z Calibration Actions run 32181811662  SUCCESS
```

The final test head includes explicit regression proof of:

```text
Moonraker stop -> bounded process-zero wait -> mutate/restore
```

for install/update/repair, uninstall and rollback.

## Standalone observer deployment — real AD5X hardware PASS

Exact staged source:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

Pre-deployment state:

```text
print_state = standby
shared snapshot HTTP = 200
shared backend_version = 0.1.6
shared modules = [ifs]
shared runtime sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
standalone Z snapshot HTTP = 404
standalone runtime files = absent
standalone include count = 0
standalone manifest = absent
```

Canonical lifecycle result:

```text
backend_install_rc = 0
backend_status_rc  = 0
```

Moonraker/Klippy after the backend-only restart:

```text
klippy_connected  = true
klippy_state      = ready
failed_components = []
warnings          = []
```

Shared IFS backend after restart:

```text
GET /server/plugins_ad5x/snapshot -> 200
backend_version = 0.1.6
modules = [ifs]
shared runtime sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
```

The API signature remained exactly:

```text
http=200;backend_version=0.1.6;ifs=1
```

Standalone endpoints after install:

```text
GET  /server/plugins_ad5x/z_calibration/snapshot    -> 200
POST /server/plugins_ad5x/z_calibration/reconcile  -> 200
GET  /server/plugins_ad5x/z_calibration/diagnostics -> 200
```

Observer state:

```text
api_version            = 1.0
module_version         = 0.1.2
schema_version         = 1.1
available              = true
health                 = ok
calibration.state      = observer
motion_owner           = zmod
motion_actions_enabled = false
offset_write_enabled   = false
offset_hook_enabled    = true
offset_hook_status     = loaded
policy_status          = loaded
policy_id              = zcal-saved-check-v1-20260817
hook_commands          = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
```

Observed provenance:

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

Raw Klipper/Z-Mod sources in the same gate:

```text
print_state       = standby
homed_axes        = ""
effective_Z       = 0.0
persistent_Z      = -0.016
temp_z_offset     = 0.0
screen            = false
load_zoffset      = 1
MESH_TEST         = 3
PRINT_LEVELING    = 0
CC_ENABLED        = 0
START.zzoffset    = 99.0
force_kamp        = false
force_leveling    = false
policy_id         = zcal-saved-check-v1-20260817
active_mesh       = auto
```

Observer-vs-raw checks all passed:

```text
persistent_matches_raw = true
auto_matches_raw       = true
effective_matches_raw  = true
live_not_fabricated    = true
residual_matches       = true
motion_owner_zmod      = true
motion_disabled        = true
offset_write_disabled  = true
```

Expected and reported residual both equal `+0.016 mm`.

This is an accepted standby/unhomed observation: the persisted `-0.016` trim exists in `save_variables`, while current `gcode_move.homing_origin.z` is `0.0`. The observer intentionally leaves the residual as `external_unknown` instead of fabricating a live-adjustment/babystepping source.

Standalone ownership manifest after install:

```text
schema = 1
z_endpoint_original_http = 404
shared_signature_at_adoption = http=200;backend_version=0.1.6;ifs=1
observer_installed_sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
core_installed_sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
config_installed_sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
include_count = 1
```

Live IFS Git worktree after the complete gate remained exactly:

```text
branch = feature/ifs-manager-v1
HEAD   = d3887210f8f269ca27d6f2c8386f2edd3d3fa048
status = clean
tracked diff sha256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
untracked = none
```

No Klipper firmware restart, Z write, probe or motion command was issued.

## Gate status

Accepted:

- canonical RC ownership adoption;
- shared-backend collision diagnosis;
- standalone backend repository repair;
- standalone observer install on real AD5X;
- shared IFS coexistence byte-for-byte;
- live observer provenance against raw Klipper/Z-Mod objects.

Still pending as separate gates:

1. standalone `update` idempotence;
2. standalone `repair` idempotence;
3. uninstall + exact original-state restore (`404`, absent runtime/config/include state);
4. reinstall;
5. power-cycle regression;
6. frontend productization only after the physical lifecycle/provenance gates are complete.
