# CALIBRATION-CENTER-001 — reverse engineering Z calibration chain

Status: implementation baseline for Draft PR. Runtime observations still require validation on the target AD5X (`192.168.1.196`).

## Scope and evidence baseline

The core Z-Mod model below is derived from the inspected AD5X runtime source at `ghzserg/z_ad5x` commit `2e32155d00e464094b8c7197e23783ec821a112c`. HelixScreen persistence behaviour was additionally inspected because the target uses Helix rather than the native screen.

Calibration Center must not rely on a guessed `-0.170 mm` correction from the motivating A1-hotend case. The measured/contact coordinate, user/global print offset and profile process correction are distinct concepts.

## 1. Z homing and nozzle-contact probing are different mechanisms

AD5X uses a dedicated Z endstop for homing and a separate probe input for nozzle/bed contact.

- Z homing uses the Z endstop.
- Contact probing uses `[probe]` on a separate input.
- The probe has its own fixed Klipper geometry/config offset.
- Z-Mod AD5X macros call `LOAD_CELL_TARE` before contact measurements.

Therefore `G28`/Z homing must not be interpreted as a nozzle-to-bed Z measurement.

## 2. Probe geometry is not a per-hotend calibration store

The Klipper `[probe] z_offset` is platform probe geometry. Z-Mod documentation/source does not use `Z_OFFSET_APPLY_PROBE`/`Z_OFFSET_APPLY_ENDSTOP` as the normal print-Z profile store.

Calibration Center therefore never edits `[probe] z_offset` and never calls `Z_OFFSET_APPLY_PROBE` or `Z_OFFSET_APPLY_ENDSTOP`.

## 3. Native Flashforge Z offset has a precise meaning in Z-Mod

Current AD5X `LOAD_ZOFFSET_NATIVE` logic:

1. reads Flashforge configuration (`Adventurer5M.json`);
2. reads `leftExtruderOffset.zProbeOffset`;
3. maps it into the runtime print Z-offset layer.

Thus, for AD5X, `leftExtruderOffset.zProbeOffset` is a native saved **print correction** as consumed by Z-Mod, not merely a raw contact-sensor sample.

Calibration Center does not write the Flashforge JSON directly because the public source does not establish the native application's complete persistence/synchronisation contract.

## 4. Z-Mod already separates contact measurement from print offset

The current Z-Mod AutoZOffset path (`MESH_TEST=3/4`) is the strongest evidence for correction order and sign:

```text
fresh_probe_reference = current contact probe result
saved_reference        = Z value from an established mesh/reference point
reference_delta        = fresh_probe_reference - saved_reference

apply geometric runtime correction:
    Z_ADJUST = reference_delta
```

Z-Mod itself does not assume that a fresh nozzle contact directly equals an ideal first-layer offset. It uses contact to measure a geometric change relative to an established reference, then layers that change with the print-offset path.

Calibration Center adopts this separation.

## 5. Nozzle preparation is part of the measurement

Current Z-Mod cleaning/probing macros show that a contact value is meaningful only under controlled preparation:

- home first;
- heat bed/nozzle;
- tare before probing;
- temporarily isolate runtime Z correction during contact work;
- probe to determine contact height;
- wipe the nozzle using known-safe motion;
- stabilise measurement temperature;
- tare again.

Consequently the following are not optional details for high-confidence calibration:

- nozzle contamination;
- nozzle temperature;
- bed temperature / thermal expansion;
- load-cell tare and preload;
- hotend seating/compliance;
- nozzle/hotend geometry;
- probe repeatability.

## 6. Correction layers used by Calibration Center

### A. Homed machine coordinate
Normal Z-Mod/Klipper homing. Not a contact calibration.

### B. Probe geometry
Klipper probe configuration. Fixed platform configuration, not a profile value.

### C. Measured physical reference
Repeatable nozzle/bed contact after controlled preparation. Calibration Center records repeated evidence (median/range).

### D. User/Z-Mod global print offset
The user/platform print-Z baseline. On the screenless Z-Mod/Helix target this is represented by the saved Z-Mod global `gcode_offsets.z` path and loaded for prints. It is independently user-editable and **not owned by Calibration Center**.

### E. Reference delta

```text
reference_delta = fresh_reference - verified_reference
```

This matches current Z-Mod `_TEST_POINT` sign convention.

### F. User-verified process correction
A separately labelled profile correction established by first-layer verification. It is not relabelled as an automatic contact result.

### G. Verified global-Z anchor
The value of the user/Z-Mod global baseline present when a profile is USER VERIFIED. Calibration Center stores this as metadata so later user changes to the global baseline can be normalised in a transient profile layer without rewriting the user's setting.

## 7. Screenless Z-Mod / Helix persistence boundary

This boundary became product-critical during physical first-layer testing.

### Z-Mod public vs fast offset paths

On the inspected screenless Z-Mod configuration:

- public `SET_GCODE_OFFSET` wraps the renamed Klipper command and saves user Z changes into `gcode_offsets` when appropriate;
- `_SET_GCODE_OFFSET_FAST` calls the renamed base command directly and bypasses that wrapper's `SAVE_VARIABLE` step;
- print-start logic can reload saved `gcode_offsets` as the global baseline.

So `_SET_GCODE_OFFSET_FAST` itself is not equivalent to the public persistent wrapper. However, using the same `homing_origin`/offset coordinate layer for Calibration Center still couples the experiment to the Z state that Helix and Z-Mod display/manage globally.

### HelixScreen behaviour

HelixScreen explicitly supports ZMOD z-offset persistence. Its Z tune controls use the public ZMOD offset path, and recent Helix releases enable persistent ZMOD offset loading on connect. This makes the user-visible global offset a deliberate persistent product feature, not a scratch register for plugin-local experiments.

### Physical incident

During the rejected first built-in first-layer test:

- working global baseline was approximately `-0.125...-0.130 mm`;
- two CC live `-0.05 mm` adjustments made the displayed Z state approximately `-0.225 mm`;
- after the test, the operator later found the printer offset still at `-0.225 mm` and manually restored it;
- an ordinary sliced print at manually restored `-0.13 mm` again produced a visually coherent first layer.

The run did not instrument every persistence backing store at the instant of the write, so reverse engineering should not claim that one specific file/write primitive alone caused the retained value. The product conclusion is still unambiguous: **a CC test adjustment escaped its intended lifetime and contaminated the user's working Z state.**

Therefore the revised safety contract is stronger than “restore after test”: Calibration Center print/live corrections must not use the global `SET_GCODE_OFFSET` coordinate layer at all.

## 8. Why G92 is used for the revised transient layer

Klipper distinguishes normal G-code origin (`G92`) from `SET_GCODE_OFFSET` / `homing_origin`.

Calibration Center can therefore shift future absolute Z commands with a reversible G92 origin transform while leaving the user/Z-Mod global offset untouched.

For desired transient correction `d` at current logical Z `g`:

```text
G92 Z=(g - d)
```

For a live first-layer step, a matching relative physical `G1 Z=d` is issued immediately after the G92 change so the nozzle moves now while logical generated-layer Z remains coherent.

This is the revised isolation mechanism for both profile application and built-in first-layer adjustment.

## 9. Why `+0.040 mm` and `-0.130 mm` can coexist

If both numbers were values displayed/saved by the native AD5X UI, they belong to the print-offset layer. The practical first-layer correction therefore differed by roughly 0.17 mm between those states.

That does **not** imply that the raw physical contact probe was geometrically wrong by 0.17 mm. Z-Mod's own design demonstrates why: contact probing is a geometric/reference measurement, while print Z is a separate correction layer.

For an A1-compatible hotend, plausible contributors include changed mechanical compliance/preload, seating, tip geometry, contamination, thermal state, or a stable process bias between detected contact and optimal extrusion gap. Source evidence does not distinguish those causes enough to claim one as proven.

Calibration Center therefore never encodes a permanent `-0.170 mm` constant. It:

1. establishes repeatable physical contact;
2. treats user/global print Z as a separate external baseline;
3. stores profile-specific verified reference, process bias and global anchor only when evidence exists;
4. remeasures geometry automatically and rejects unstable results;
5. applies its own correction in an isolated transient coordinate layer.

## 10. What remains a runtime acceptance question

The following cannot be closed from source alone and require the target AD5X:

- broader repeatability distribution of independent probe series;
- sensitivity to nozzle and bed temperature;
- stock vs A1-compatible hotend repeatability;
- invariance of practical first-layer bias for one hotend/nozzle profile;
- return-to-profile behaviour after real nozzle swaps;
- MESH_TEST 1/2 versus 3/4 interaction;
- **proof that the revised G92-based CC test/profile paths leave the user/Z-Mod global offset bit-for-bit unchanged across save, no-save, system cancel and normal print end.**

Until those measurements exist, Calibration Center may automatically establish a stable physical reference and propagate a previously verified correction, but it must not claim that contact alone proves an optimal extrusion gap for a never-verified hotend/nozzle profile.
