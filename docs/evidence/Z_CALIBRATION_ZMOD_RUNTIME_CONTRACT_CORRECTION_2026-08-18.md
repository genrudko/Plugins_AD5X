# CALIBRATION-SUBSYSTEM-002 — Z-Mod runtime contract correction

**Date:** 2026-08-18  
**Issue:** #13  
**Draft PR:** #14  
**Scope:** RC Productization target-runtime correction discovered before canonical live deployment.

## 1. Trigger

A read-only owner preflight executed from the outer AD5X SSH shell demonstrated that assumptions inherited from an ordinary Linux CI/runtime model were invalid for the printer.

The working Z-Mod environment is the chroot:

```text
/usr/data/.mod/.zmod
```

Inside that chroot the owner observed:

```text
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/prog/curl-7.55.1-https/bin:/opt/bin/:/opt/sbin/
git        /bin/git
python3    /bin/python3
wget       MISSING
sha256sum  /bin/sha256sum
tar        /bin/tar
```

The live Plugins AD5X worktree was simultaneously confirmed as:

```text
/opt/config/mod_data/plugins/ad5x_custom
branch feature/ifs-manager-v1
HEAD d3887210f8f269ca27d6f2c8386f2edd3d3fa048
```

The alias path `/root/printer_data/config/mod_data/plugins/ad5x_custom` resolves to the same live repository view inside the chroot.

## 2. Upstream Z-Mod source verification

Before correcting Plugins AD5X, the exact Z-Mod source baseline was inspected:

```text
ghzserg/z_ad5x
branch 1.7
commit 2e32155d00e464094b8c7197e23783ec821a112c
```

Relevant source facts:

- `.shell/0.sh` defines `MOD=/usr/data/.mod/.zmod` and `CURL=/usr/prog/curl-7.55.1-https/bin/curl` for AD5X host-side scripts;
- `.shell/zupdate.sh` and `.shell/zprint.sh` use `/usr/bin/curl` when already inside the Z-Mod chroot and the configured stock curl path outside it;
- `.shell/plugins.sh` explicitly performs AD5X plugin Git operations through `chroot ${MOD}` after clearing host library preload/path state;
- Z-Mod therefore does not support treating the outer SSH shell as a generic full Linux userspace for plugin lifecycle logic.

## 3. Defect found in Plugins AD5X

The problem was not limited to the operator command. The repository implementation itself contained unsupported `wget` dependencies in:

```text
install.sh
installer/z_calibration_runtime.sh
installer/z_calibration_rc_lifecycle.sh
```

Affected operations included Moonraker readiness/idle queries, backend snapshot, RC preflight/live verification, firmware restart and Camera/IFS status checks.

The earlier repository-green result did not detect this because the tests stubbed `wget`, thereby modelling the wrong target environment.

That earlier green state must therefore **not** be used as evidence of AD5X target-runtime compatibility.

## 4. Corrective implementation

The production shell contour now uses a Z-Mod-derived curl resolver:

```text
AD5X_CURL_BIN override
→ command -v curl
→ /usr/bin/curl
→ /usr/prog/curl-7.55.1-https/bin/curl
```

HTTP GET/POST helpers use bounded curl calls and no production shell code executes `wget`.

The installer/helper Python resolver also prefers the chroot-visible `python3` before the Moonraker venv fallback.

Corrective commit sequence:

```text
89ae25a3ea8361631c5195fad57e768900a20909  runtime helper uses Z-Mod curl contract
f8a4e0e0a93c9c09f7bb141825dd6ecd5be45274  canonical RC lifecycle made chroot-native
d7da071565ff82413724cd11fdcee06763d42e23  generic installer HTTP switched to curl
e682c07e41f094c261dbfa8911b0122a50c70929  tests changed to curl-only target model
3a9e7ae97237e6cdfbc0e8896b3eea95d6d89c57  executable-wget assertion corrected
```

## 5. CI gate

Exact corrected implementation head:

```text
3a9e7ae97237e6cdfbc0e8896b3eea95d6d89c57
```

Exact-head workflows:

```text
Z Calibration Core    32178578653  SUCCESS
Z Calibration Actions 32178578665  SUCCESS
```

Core job confirms:

```text
Python compile       PASS
shell syntax         PASS
repository tests     PASS
```

The new target-runtime test scans executable production shell lines and rejects an actual `wget` command while allowing documentation/comments to state that wget is unsupported.

## 6. Process correction

For future AD5X/Z-Mod patches, target-runtime assumptions are no longer inferred from desktop/Linux CI availability.

Required order is:

```text
read exact Z-Mod source/runtime contract
→ identify chroot/paths/tools/service primitives
→ encode those primitives in production code
→ encode the same constraints in repository tests
→ only then issue live-printer commands
```

A GitHub Actions Ubuntu runner remains useful for syntax/model tests, but presence of a tool on that runner is not evidence that the AD5X target provides it.

## 7. Remaining gate

This correction is repository-green only. The next live step is a **read-only chroot-native preflight** using `curl`, with no Git checkout/reset, no config mutation and no service restart. It must reconfirm the IFS branch/HEAD before any canonical RC adoption is attempted.
