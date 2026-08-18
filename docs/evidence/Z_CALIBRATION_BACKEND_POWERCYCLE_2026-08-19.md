# Z Calibration standalone backend full power-cycle regression — 2026-08-19

## Scope

This evidence records the final physical lifecycle/provenance gate for the standalone Z Calibration backend on the real Flashforge AD5X: full printer power-cycle persistence/regression after the accepted reinstall/fresh-adoption gate.

The backend implementation remained pinned to the accepted exact implementation SHA:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

No runtime/lifecycle code drift occurred after that accepted implementation SHA; later branch-head commits are evidence-only.

## Cold-boot proof

The verification was executed after a physical printer power-off / power-on cycle. At gate execution:

```text
system_uptime_seconds = 254.76
```

This is consistent with a fresh cold boot rather than a Moonraker-only or Klipper-only restart.

## Boot health — PASS

```text
server_info_http = 200
klippy_connected = true
klippy_state = ready
failed_components = []
warnings = []
```

Canonical lifecycle status after cold boot:

```text
standalone backend status rc = 0
pure-Klipper RC Productization status rc = 0
```

## Ownership persistence — PASS

The fresh ownership state created by the accepted reinstall survived the full power-cycle unchanged.

Manifest identity:

```text
schema = 1
z_endpoint_original_http = 404
shared_signature_at_adoption = http=200;backend_version=0.1.6;ifs=1
observer_installed_sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
core_installed_sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
config_installed_sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
```

All manifest checks passed.

Original baseline remained:

```text
original observer = absent
original core = absent
original config = absent
original include count = 0
original tree sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
```

## Managed runtime persistence — PASS

Managed files still matched the accepted exact source byte-for-byte:

```text
plugins_ad5x_zcal.py sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
plugins_ad5x_zcalibration.py sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
zcal_backend.moonraker.conf sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
standalone Moonraker include count = 1
pure-Klipper RC include count = 1
```

## Standalone endpoints after cold boot — PASS

```text
GET  /server/plugins_ad5x/z_calibration/snapshot     -> 200
POST /server/plugins_ad5x/z_calibration/reconcile   -> 200
GET  /server/plugins_ad5x/z_calibration/diagnostics -> 200
```

Observer state after cold boot:

```text
available = true
health = ok
calibration.state = observer
motion_owner = zmod
motion_actions_enabled = false
offset_write_enabled = false
offset_hook_enabled = true
offset_hook_status = loaded
policy_status = loaded
policy_id = zcal-saved-check-v1-20260817
hook_commands = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
runtime.klippy = ready
runtime.print_state = standby
runtime.homed_axes = ""
```

## Offset provenance after cold boot — PASS

Observer values:

```text
persistent_user = -0.016
auto_alignment = 0.0
slicer_job = 0.0
live_adjustment = 0.0
external_unknown = +0.016
known_total = -0.016
effective = 0.0
provenance_status = external_unknown
```

Raw Klipper/Z-Mod sources in the same gate:

```text
print_state = standby
homed_axes = ""
effective_Z = 0.0
persistent_Z = -0.016
temp_z_offset = 0.0
screen = false
load_zoffset = 1
mesh_test = 3
print_leveling = 0
cc_enabled = 0
START.zzoffset = 99.0
START.force_kamp = false
START.force_leveling = false
policy_id = zcal-saved-check-v1-20260817
active_mesh = auto
_USER_START_PRINT = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
```

Observer-vs-raw verification all passed:

```text
persistent_matches_raw = true
auto_matches_raw = true
effective_matches_raw = true
live_not_fabricated = true
residual_matches = true
motion_owner_zmod = true
motion_disabled = true
offset_write_disabled = true
```

The `+0.016 mm` standby/unhomed residual remains intentionally classified as `external_unknown`; it is not fabricated as babystepping/live adjustment.

## IFS coexistence after cold boot — PASS

Shared backend remained byte-for-byte unchanged:

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

## Final physical lifecycle status

Accepted on real AD5X hardware:

1. RC Productization ownership adoption;
2. standalone backend install;
3. update idempotence;
4. repair idempotence;
5. uninstall with exact pre-install restore;
6. reinstall with fresh adoption of the current `404/absent` baseline;
7. full physical power-cycle persistence/regression.

Final result:

```text
FULL POWER-CYCLE persistence/regression hardware gate = PASS
physical backend lifecycle/provenance gate set = COMPLETE
```

Current hardware state:

```text
standalone Z Calibration backend = INSTALLED
pure-Klipper RC Productization = active
shared IFS backend = active
printer = healthy/standby
```

The physical lifecycle/provenance acceptance blocker for frontend/API productization is closed.
