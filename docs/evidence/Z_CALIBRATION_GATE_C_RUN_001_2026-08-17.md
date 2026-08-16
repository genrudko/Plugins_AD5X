# Z Calibration Gate C — repeatability run 001

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** PRE-MOTION / NOT YET COMPLETE  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-c-001-ambient-back-to-back-2026-08-17`
- condition class: short-term/back-to-back ambient repeatability
- hardware context: same post-adjustment AD5X setup as Gate A and Gate B run 001 unless a later section records a physical change
- Z-Mod: `1.7.2-5`, branch `1.7`, checkout `2e32155d00e464094b8c7197e23783ec821a112c`
- Klipper runtime: `v0.13.0-753-g0df153f7-ZMOD-20260816`
- Klipper inspected checkout: `6bd8fca222811d465b4be3b0ed862915d6caf59e`
- Moonraker API: `1.5.0`, inspected checkout `a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e`
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

## Previous accepted evidence context

Gate B run 001 completed cleanly immediately before this run:

```text
reference average       = -1.985500 mm
reference median        = -1.986250 mm
reference range         =  0.017500 mm
first-to-last drift     = +0.010000 mm
saved auto center       = -1.925833 mm
current-minus-saved     = -0.059667 mm
persistent state change = false
saved mesh change       = false
cleanup confirmed       = true
```

This Gate C run must produce an independent series with its own fresh homing/tare path. The previous series is not reused as current measurement data.

## Planned semantics

```text
read-only preflight
→ runtime mesh clear only
→ fresh ordinary G28
→ move to X107.5/Y107.5/Z5
→ LOAD_CELL_TARE
→ PROBE_ACCURACY SAMPLES=10
→ explicit Z5 retract
→ restore saved auto mesh at runtime
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent user-trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter is permitted.

## Pending

- exact Plugins AD5X repository SHA at preflight: PENDING
- exact thermal/pre-motion state: PENDING
- pre-run `printer.cfg` hash: PENDING
- fresh homing result: PENDING
- tare observation: PENDING
- raw 10-sample reference series: PENDING
- descriptive mean/median/spread/drift: PENDING
- comparison with Gate B run 001: PENDING
- cleanup/retract confirmation: PENDING
- post-run effective offset: PENDING
- saved mesh unchanged proof: PENDING
- post-run `printer.cfg` hash: PENDING
- stop condition observed: PENDING

Until complete, this run is not policy-reviewable and authorizes nothing.
