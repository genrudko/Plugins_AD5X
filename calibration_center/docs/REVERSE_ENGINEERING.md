# CALIBRATION-CENTER-001 — reverse engineering Z calibration chain

Status: implementation baseline for Draft PR. Runtime observations still require validation on the target AD5X (`192.168.1.196`).

## Scope and evidence baseline

The model below is derived from the current public Z-Mod sources, with the AD5X runtime repository `ghzserg/z_ad5x` branch `1.7` at `2e32155d00e464094b8c7197e23783ec821a112c`, and the current upstream `ghzserg/zmod` main at `899a220b68d92a10b4dd7596fada0392aae34a85`.

Calibration Center must not rely on a guessed `-0.170 mm` correction from the motivating A1-hotend case. The measured/contact coordinate and the print correction are distinct concepts.

## 1. Z homing and nozzle-contact probing are different mechanisms

AD5X uses a dedicated Z endstop for homing and a separate probe input for nozzle/bed contact. In the current AD5X base configuration:

- Z homing uses the Z endstop (`stepper_z.endstop_pin`).
- Contact probing uses `[probe]` on a separate input.
- The probe has its own fixed Klipper geometry/config offset.
- Z-Mod AD5X macros call `LOAD_CELL_TARE` before contact measurements, proving that the load/strain sensing path is part of the measurement chain.

Therefore `G28`/Z homing must not be interpreted as a nozzle-to-bed Z measurement.

## 2. Probe geometry is not a per-hotend calibration store

The current Klipper `[probe] z_offset` is part of the configured probe geometry. Z-Mod documentation explicitly warns users not to use `Z_OFFSET_APPLY_PROBE`/`Z_OFFSET_APPLY_ENDSTOP` as the normal print-Z storage mechanism.

Calibration Center will therefore **never** edit `[probe] z_offset` and will not call `Z_OFFSET_APPLY_PROBE` or `Z_OFFSET_APPLY_ENDSTOP`.

## 3. Native Flashforge Z offset has a precise meaning in Z-Mod

Current `ghzserg/z_ad5x/.shell/zmod.py` implements `LOAD_ZOFFSET_NATIVE` as follows on AD5X:

1. Read Flashforge configuration (`/usr/prog/config/Adventurer5M.json`, falling back to `/opt/config/Adventurer5M.json`).
2. Read `leftExtruderOffset.zProbeOffset`.
3. Convert it directly to `SET_GCODE_OFFSET Z=<value>`.

The AD5M/AD5M Pro compatibility `+0.025 mm` adjustment is explicitly skipped for AD5X.

Thus, for AD5X, `leftExtruderOffset.zProbeOffset` is the native saved print Z-offset as consumed by Z-Mod. It is not just a raw contact-sensor sample.

Calibration Center does not write this Flashforge JSON directly because the public source does not establish the native application's complete persistence/synchronisation contract. Read-only snapshots are allowed; writes are fail-closed until that contract is proven.

## 4. Z-Mod already separates contact measurement from print offset

The current Z-Mod AutoZOffset path (`MESH_TEST=3/4`) is the strongest available evidence for the correction order and sign.

The relevant logic is:

```text
fresh_probe_reference = current contact probe result
saved_reference       = Z value from a previously established bed mesh point
reference_delta       = fresh_probe_reference - saved_reference

if native screen is active:
    LOAD_ZOFFSET_NATIVE

apply temporary runtime correction:
    Z_ADJUST = reference_delta
```

This is important: Z-Mod itself does **not** assume that a fresh nozzle contact directly equals an ideal first-layer offset. It uses fresh contact to measure a change relative to a prior geometric reference, then adds that delta to an existing print-offset layer.

Calibration Center adopts this physical separation instead of creating another coordinate convention.

## 5. Nozzle preparation is part of the measurement

Current Z-Mod cleaning/probing macros show that a contact value is only meaningful under controlled preparation:

- home first;
- heat bed/nozzle;
- `LOAD_CELL_TARE` before probing;
- temporarily remove runtime Z correction while measuring;
- probe to determine contact height;
- perform nozzle wipe using that measured contact height;
- reduce/stabilise nozzle temperature before subsequent operations;
- tare again.

Consequently the following are not optional details for a high-confidence calibration:

- nozzle contamination;
- nozzle temperature;
- bed temperature and thermal expansion;
- load-cell/strain-gauge tare and preload;
- hotend mechanical seating/compliance;
- nozzle/hotend geometry;
- probe repeatability.

## 6. Correction layers used by Calibration Center

The implementation uses these terms deliberately:

### A. Homed machine coordinate
Obtained by normal Z-Mod/Klipper homing. Not a contact calibration.

### B. Probe geometry
Klipper probe configuration. Treated as fixed platform configuration, not a user profile value.

### C. Measured physical reference
A reproducible nozzle/bed contact result measured after controlled preparation. Calibration Center uses repeated independent probes and records the median/range.

### D. Existing print offset
The base print correction already selected by the platform. With the native screen this is the Flashforge `zProbeOffset` loaded by `LOAD_ZOFFSET_NATIVE`; in screenless Z-Mod mode this is the corresponding Z-Mod print-offset path.

### E. Reference delta
A change in measured contact geometry relative to a previously verified reference:

```text
reference_delta = fresh_reference - verified_reference
```

This sign matches the current upstream Z-Mod `_TEST_POINT` implementation.

### F. User-verified process correction
A separately labelled correction established by a first-layer verification. It is not relabelled as an automatic probe result.

The initial product intentionally stores `AUTO MEASURED` and `USER VERIFIED` independently.

## 7. Why `+0.040 mm` and `-0.130 mm` can coexist

The public sources allow a stronger statement than “the automatic calibration was wrong by 0.170 mm”, but they do not prove one unique root cause.

If both numbers were values displayed/saved by the native AD5X UI, they belong to the same native `zProbeOffset` print-offset layer. In that case the practical first-layer correction changed by roughly 0.17 mm between the native automatic result and the user-verified result.

That does **not** imply that the raw physical contact probe was geometrically wrong by 0.17 mm. Z-Mod's own design demonstrates why: contact probing is used as a geometric/reference measurement, while print Z is a separate correction layer.

For an A1-compatible hotend, plausible contributors include changed mechanical compliance/preload, seating, tip geometry, contamination, thermal state, or a process bias between detected contact and optimal extrusion gap. The public source does not distinguish those causes sufficiently to claim one as proven.

Therefore Calibration Center will not encode a permanent `-0.170 mm` constant. It will:

1. establish repeatable physical contact;
2. preserve the current/base print offset as a separate value;
3. maintain a profile-specific verified reference/correction only when evidence exists;
4. remeasure geometry automatically and reject unstable results.

## 8. What remains a runtime acceptance question

The following cannot be honestly closed from source alone and must be measured on `192.168.1.196`:

- repeatability distribution of five independent probes after cleaning/tare;
- repeatability at multiple nozzle temperatures;
- sensitivity to bed temperature;
- stock vs A1-compatible hotend repeatability;
- whether the practical first-layer bias remains constant for one hotend/nozzle profile;
- whether that bias changes materially with plate type or temperature;
- exact runtime behaviour of native Flashforge calibration when it writes `zProbeOffset`.

Until those measurements exist, Calibration Center may automatically establish a **stable physical reference** and automatically propagate a previously verified correction, but it must not claim that contact alone proves an optimal extrusion gap for a never-verified hotend/nozzle profile.
