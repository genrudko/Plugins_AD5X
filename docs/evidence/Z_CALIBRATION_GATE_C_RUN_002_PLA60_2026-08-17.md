# Z Calibration Gate C — repeatability run 002 (PLA bed 60 C)

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence phase:** `gate_c_repeatability`  
**Status:** PREHEAT / NOT YET COMPLETE  
**Authority:** evidence record only; does not authorize production Plugins AD5X motion or writes

## Run identity

- run_id: `gate-c-002-pla-bed-60c-2026-08-17`
- condition class: representative owner PLA bed condition
- owner-selected bed target: `60 C`
- Plugins AD5X repository SHA at condition selection: `b45ec605da9c7c0fb31889cc096795fd23383fc8`
- hardware context: same post-adjustment AD5X setup as Gate A, Gate B run 001 and Gate C run 001 unless a later section records a physical change
- command transport: SSH → Z-Mod chroot → local Moonraker → ordinary Klipper/Z-Mod G-code path

## Purpose

Measure whether the nozzle↔bed reference changes materially when the bed is brought from ambient to the owner's representative PLA target of `60 C`.

This run deliberately changes the bed thermal condition only at first. The nozzle remains unheated during this condition so bed-temperature influence is not conflated with hotend thermal expansion. A later condition may test a heated nozzle separately if required by the evidence.

## Previous repeatability context

```text
Gate B ambient mean   = -1.985500 mm
Gate C ambient mean   = -1.973000 mm
ambient mean delta    = +0.012500 mm
```

These values are descriptive evidence only and do not define an acceptance band.

## Planned path

```text
bed target 60 C
→ record actual bed/nozzle temperatures after heater wait
→ read-only preflight / persistence guard
→ runtime mesh clear only
→ fresh G28
→ X107.5/Y107.5/Z5
→ fresh LOAD_CELL_TARE
→ PROBE_ACCURACY SAMPLES=10
→ explicit Z5 retract
→ restore saved auto mesh at runtime
→ post-state/hash verification
```

No `SAVE_CONFIG`, persistent trim mutation, saved-mesh overwrite/delete, Plugins AD5X Z-offset write, or production Plugins AD5X motion adapter is permitted.

## Pending

- post-heat actual bed temperature: PENDING
- post-heat nozzle temperature: PENDING
- pre-run standard effective Z offset: PENDING
- pre-run `printer.cfg` hash: PENDING
- fresh homing result: PENDING
- tare observation: PENDING
- raw 10-sample series: PENDING
- descriptive statistics: PENDING
- comparison with ambient runs: PENDING
- cleanup/persistence verification: PENDING
- stop condition observed: PENDING

This run cannot authorize or freeze any motion/search/correction threshold by itself.
