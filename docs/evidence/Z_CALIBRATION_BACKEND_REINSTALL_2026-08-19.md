# Z Calibration standalone backend reinstall — 2026-08-19

## Scope

This evidence records the controlled standalone Z Calibration backend reinstall on the real Flashforge AD5X after the accepted uninstall/exact-restore gate.

The backend implementation used for hardware remains pinned to the already accepted exact source:

```text
45c57eebec24c26094d448fd4c679f5d3545f7d0
```

Later branch-head commits are evidence-only and do not change the accepted runtime/lifecycle implementation.

## Pre-install baseline

The accepted uninstall left the standalone backend completely absent while pure-Klipper RC Productization and the shared IFS backend remained active.

Immediately before reinstall:

```text
print_state = standby
plugins_ad5x_zcal.py = absent
plugins_ad5x_zcalibration.py = absent
zcal_backend.moonraker.conf = absent
standalone ownership state = absent
standalone Moonraker include count = 0
standalone bytecode = absent
snapshot / reconcile / diagnostics = 404 / 404 / 404
```

The pure-Klipper RC policy include remained exactly once in:

```text
/opt/config/mod_data/plugins.cfg
```

and canonical RC status returned `0`.

The shared IFS baseline remained:

```text
http=200;backend_version=0.1.6;ifs=1
plugins_ad5x.py sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
```

The unrelated live IFS worktree remained:

```text
branch = feature/ifs-manager-v1
HEAD   = d3887210f8f269ca27d6f2c8386f2edd3d3fa048
status = clean
tracked diff sha256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
untracked = none
```

## Reinstall result — hardware PASS

Canonical lifecycle invocation:

```text
installer/z_calibration_backend_lifecycle.sh install
```

Result:

```text
reinstall_rc = 0
reinstall_status_rc = 0
```

Moonraker/Klippy after the backend-only restart:

```text
server_info_http = 200
klippy_connected = true
klippy_state = ready
failed_components = []
warnings = []
```

## Fresh ownership adoption

The reinstall created a new ownership state from the current absent baseline.

Fresh manifest:

```text
schema = 1
z_endpoint_original_http = 404
shared_signature_at_adoption = http=200;backend_version=0.1.6;ifs=1
observer_installed_sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
core_installed_sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
config_installed_sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
```

Fresh original snapshot:

```text
original observer = absent
original core = absent
original config = absent
original include count = 0
original tree sha256 = c274b6b12b762c27181de3fc7dc943dea0d84e43e7c5a2bb119b8d577def7140
```

All manifest identity/hash checks passed.

## Runtime after reinstall

Managed runtime hashes match the accepted exact source:

```text
plugins_ad5x_zcal.py sha256 = 5ea297835814570ff74b18e5a12fc51a1735617ce4272744b93eb72ad49b20da
plugins_ad5x_zcalibration.py sha256 = 50095b5099565f5a1b398dff02fc57f308f810f0fd6c6719af49a4f758e1f527
zcal_backend.moonraker.conf sha256 = d9a27445b881a66ca6b30fa84b187c8d69f85f4ca3e8b83e913263f68e616669
standalone include count = 1
```

Standalone endpoints:

```text
snapshot    = 200
reconcile   = 200
diagnostics = 200
```

Observer state:

```text
available = true
health = ok
calibration.state = observer
motion_owner = zmod
motion_actions_enabled = false
offset_write_enabled = false
offset_hook_status = loaded
```

## Provenance after reinstall

Observed values:

```text
persistent_user = -0.016
auto_alignment = 0.0
slicer_job = 0.0
live_adjustment = 0.0
external_unknown = 0.016
effective = 0.0
provenance_status = external_unknown
```

Observer-vs-raw verification:

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

The standby/unhomed `+0.016` residual remains intentionally classified as `external_unknown`; it is not fabricated as live adjustment or babystepping.

## Coexistence invariants after reinstall

Pure-Klipper RC Productization remained active and verified:

```text
rc_productization_status_after = 0
rc_policy_include_count = 1
```

Shared IFS remained byte-for-byte unchanged:

```text
http=200;backend_version=0.1.6;ifs=1
plugins_ad5x.py sha256 = 0c68c99739e77d2c751b447cbf52921201b4e4aba6e053382aa60310b8cb3623
```

Live IFS Git worktree remained exactly unchanged:

```text
branch = feature/ifs-manager-v1
HEAD   = d3887210f8f269ca27d6f2c8386f2edd3d3fa048
status = clean
tracked diff sha256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
untracked = none
```

No Klipper firmware restart, Z write, probe or motion command was issued.

## Gate status

Reinstall / fresh-adoption hardware gate: **PASS**.

Current hardware state:

```text
standalone Z Calibration backend = INSTALLED
pure-Klipper RC Productization = active
shared IFS backend = active
printer = healthy/standby
```

The backend intentionally remains installed for the next independent gate: full printer power-cycle persistence/regression.
