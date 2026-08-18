# Z Calibration backend coexistence repair — 2026-08-18

## Scope

This evidence records the first controlled hardware productization pass after Owner RC acceptance and the repository repair required by the live Moonraker backend collision discovered on the AD5X target.

The repair is repository-only at the time of this document. The standalone Z Calibration Moonraker observer has **not yet been deployed to hardware** after the repair.

## Canonical RC adoption — hardware PASS

Exact source used for the controlled adoption:

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

Effective live state after the bounded Klipper reload:

```text
print_state        = standby
effective commands = CC_APPLY_PROFILE, _AD5X_Z_SAVED_CHECK_POLICY
MESH_TEST          = 3
CC_ENABLED         = 0
policy_id          = zcal-saved-check-v1-20260817
max_auto_alignment = 0.12
```

The generated policy include was present exactly once and the unrelated live IFS worktree remained byte-for-byte unchanged.

## Live backend discovery — architectural blocker found

Moonraker/Klippy were healthy:

```text
klippy_connected  = true
klippy_state      = ready
failed_components = []
warnings          = []
```

However the live shared endpoint reported:

```text
GET /server/plugins_ad5x/snapshot -> 200
backend_version = 0.1.6
```

The returned shared snapshot was the IFS backend contract and contained no `z_calibration` module.

The Z Calibration observer endpoints expected by the then-current PR #14 implementation were absent:

```text
POST /server/plugins_ad5x/z_calibration/reconcile -> 404
GET  /server/plugins_ad5x/z_calibration/diagnostics -> 404
```

Raw Klipper/Z-Mod state remained healthy and readable:

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

No Z write or motion command was issued during discovery and the IFS worktree invariant remained unchanged.

## Root cause

The feature branches had independently evolved the same Moonraker component path:

```text
moonraker/components/plugins_ad5x.py
```

The live IFS branch used an IFS-capable shared backend (`0.1.6`), while the Z Calibration branch had turned the same file into the Z observer backend (`0.1.2`). Replacing the live file with the Z Calibration version would restore Z endpoints by destroying the active IFS backend contract.

This is an ownership collision, not a Z-offset failure.

The two feature lines are materially diverged after their common base and must not be resolved by copying one monolithic `plugins_ad5x.py` over the other.

## Repair decision

Z Calibration no longer owns the shared backend host.

The repository now uses this composition:

```text
plugins_ad5x.py
  shared/platform host only

plugins_ad5x_zcal.py
  standalone read-only Z Calibration Moonraker component
  GET  /server/plugins_ad5x/z_calibration/snapshot
  POST /server/plugins_ad5x/z_calibration/reconcile
  GET  /server/plugins_ad5x/z_calibration/diagnostics
```

Moonraker activation is isolated through:

```text
[plugins_ad5x_zcal]
```

in a managed generated include.

This permits an IFS-capable `plugins_ad5x.py` and the Z observer to coexist in the same Moonraker runtime without endpoint collision or file replacement.

## Standalone lifecycle safety contract

New canonical entrypoint:

```text
installer/z_calibration_backend_lifecycle.sh
```

Supported modes:

```text
install | update | repair | uninstall | status
```

Hard invariants:

- target is the Z-Mod chroot;
- curl is used; wget is not a dependency;
- no Git checkout/reset/clean/fetch;
- no write to `plugins_ad5x.py`;
- no `FIRMWARE_RESTART`;
- no Z write, probe, G0 or G1 command;
- printer must be in an accepted idle/terminal state before mutation;
- only `plugins_ad5x_zcal.py`, `plugins_ad5x_zcalibration.py` and the standalone generated Moonraker config are managed;
- destination ownership is fail-closed;
- install/update/repair/uninstall are filesystem-transactional with rollback backup;
- shared backend signature is compared before and after each individual ZCal transaction but is **not owned or permanently pinned by ZCal**;
- live verification requires all three standalone endpoints and verifies `motion_owner=zmod`, `motion_actions_enabled=false`, and `offset_write_enabled=false`.

## Repository acceptance

Exact implementation head:

```text
8cfb2681174cd021a7307a7148e0c64f3f71ab36
```

Exact-head workflows:

```text
Z Calibration Core
run 32181201323
SUCCESS

Z Calibration Actions
run 32181201215
SUCCESS
```

Coverage includes:

- shared host no longer registers Z feature endpoints;
- standalone Z component does not claim `/server/plugins_ad5x/snapshot`;
- accepted owner composition remains reconciled without writes;
- unexplained residual remains `external_unknown`, never fabricated as babystepping;
- the observed post-restart standby case (`persistent=-0.016`, `auto=0`, `effective=0`) remains explicitly unattributed rather than mislabelled;
- standalone lifecycle never deploys shared `plugins_ad5x.py`;
- lifecycle is curl-only, Git-free and Klipper-motion-free;
- shared backend is a per-transaction invariant rather than ZCal-owned state;
- rollback/uninstall provenance assets are present.

Both Z Calibration workflows now include this evidence path in their trigger set so the final evidence-only branch head is revalidated by the same complete repository suite before the next hardware gate.

## Next hardware gate

Do not use generic `install.sh` for this gate.

The next controlled target operation must stage an exact repository commit outside the live IFS worktree and invoke only:

```text
installer/z_calibration_backend_lifecycle.sh install
```

Acceptance requires:

1. live printer idle;
2. IFS Git branch/HEAD/status/diff/untracked unchanged;
3. shared `/server/plugins_ad5x/snapshot` remains the same IFS backend signature across the Moonraker restart;
4. standalone Z snapshot becomes available;
5. reconcile and diagnostics return 200;
6. observer reports no motion/write capability;
7. raw provenance agrees with standard Klipper/Z-Mod objects;
8. no physical Z motion occurs.

Only after that gate may backend provenance be accepted on hardware.
