# Z Calibration Owner RC v1 — Acceptance Evidence

**Date:** 2026-08-18  
**Work item:** #13 `CALIBRATION-SUBSYSTEM-002`  
**Draft PR:** #14  
**Policy:** `zcal-saved-check-v1-20260817`

## Result

**OWNER UNATTENDED-PRINT ACCEPTANCE: PASS.**

The owner-useful `saved+check` RC path was deployed to the physical AD5X, produced a visually/tactually excellent PETG first layer without manual Z correction, and then completed a normal unattended overnight print successfully.

This acceptance is for the current owner printer, current mechanics/plate, accepted saved `auto` mesh and the current Z-Mod print lifecycle. It is not a universal AD5X policy default.

## Live RC deployment state

The deployed guard was sourced from RC commit:

```text
3b5dfc2a48f18b139a70c5f7aa164a1313c2564e
```

Canonical policy blob:

```text
316db096d5e23975e6fe36de8f21f8d1a02b7959
```

Post-deploy live verification returned:

```text
state       = standby
hook        = ['CC_APPLY_PROFILE', '_AD5X_Z_SAVED_CHECK_POLICY']
MESH_TEST   = 3
CC_ENABLED  = 0
mesh        = auto
center      = -1.925833
Z origin    = 0.0
policy      = zcal-saved-check-v1-20260817
Auto-Z max  = 0.12
```

Additional deployment checks:

- camera snapshot succeeded;
- kernel Oops markers: `0`;
- `v4l2-ctl` crash markers: `0`;
- active IFS worktree branch remained `feature/ifs-manager-v1`;
- active IFS worktree HEAD remained `d3887210f8f269ca27d6f2c8386f2edd3d3fa048`;
- no checkout/reset of the IFS worktree was performed.

Live deployment backup:

```text
/opt/config/mod_data/ad5x_custom/backups/zcal-rc-20260818-003457
```

## First-layer physical acceptance

Test object:

```text
80 x 80 x 0.20 mm
PETG
normal Fluidd Print path
saved `auto` map / no fresh bed-map request
no manual Z-offset correction
```

Captured printer log:

```text
/opt/config/mod_data/ad5x_custom/logs/zcal-first-layer-20260818-004359.log
```

Relevant Z-Mod measurement/composition evidence:

```text
probe: at 107.500,107.500 bed will contact at z=-1.932500
probe at 107.500,107.500 is z=-2.182500
Result: at 107.500,107.500 estimate contact at z=-1.938333
Probe: -1.9383  Mesh: -1.9258   Delta: -0.0125
Z-Offset: -0.0425 _TEST_POINT
```

The test completed through the normal print lifecycle. Owner visual/tactile inspection reported the layer as exceptionally smooth and uniform, with no manual Z correction required. Photos showed continuous line fusion across the test area without an obvious too-high gap pattern or severe over-squish ridging.

Two `BlockingIOError: [Errno 11] Resource temporarily unavailable` messages were observed on the g-code response output path during startup. They did not abort the print and are recorded as diagnostic noise / a separate follow-up, not as a Z-calibration acceptance failure.

## Composition confirmation on a subsequent real print

During a later normal print, live Klipper/Z-Mod query returned:

```text
effective homing_origin.z = -0.0158336664845542
Z-Mod temp_z_offset       = +0.014166333515445828
```

With the existing persistent user trim of `-0.030000 mm`, the standard composition closes numerically:

```text
-0.030000 + 0.0141663335 = -0.0158336665 mm
```

This confirms that the visible Klipper effective offset is the composed result, while the Z-Mod Auto-Z contribution remains separately observable; the Auto-Z contribution did not replace or double-apply the persistent trim.

## Unattended overnight acceptance

After the first-layer acceptance, the owner started a normal unattended print using the same deployed RC path. On 2026-08-18 the owner reported that the job **completed normally**.

No manual Z-offset intervention was required for the accepted first-layer test or the subsequent unattended print.

## Acceptance decision

For the current owner printer and accepted `auto` mesh:

- `saved+check` normal Print path: **PASS**;
- automatic per-print Z-Mod contact/alignment: **PASS**;
- persistent trim + Auto-Z composition in standard Klipper state: **PASS**;
- RC guard coexistence with the existing `_USER_START_PRINT` owner: **PASS**;
- first-layer physical result: **PASS**;
- unattended full-print result: **PASS**.

The owner RC objective is therefore complete.

## Next engineering step

Do **not** spend additional cycles re-proving the same owner RC path unless a regression appears. Continue by converting the proven live integration into maintainable canonical product lifecycle:

1. canonical installer/update/repair/uninstall ownership for the proven hook/guard integration, without dirtying or replacing unrelated IFS runtime work;
2. backend snapshot/provenance reporting of effective offset vs Auto-Z vs persistent/job/live contributions;
3. bounded structured diagnostics for the accepted path;
4. human Calibration Center UI in Fluidd first, then shared-contract parity for other frontends;
5. later release gates still required by the full test plan, including actual hardware/plate change acceptance and other deferred production paths.

PR #14 remains Draft. No Ready for Review or merge is implied by this owner acceptance.
