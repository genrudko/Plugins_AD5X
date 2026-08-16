# Z Calibration Reverse Engineering — 2026-08-16

**Purpose:** preserve the real-printer evidence that led to `Z Calibration Subsystem v2` so future implementation does not reconstruct the mechanism from chat memory.

**Target:** Flashforge AD5X + Z-Mod, current owner machine with Bambu Mod and Bambu Lab P1/X1-style hotend at the time of this session.

This document distinguishes **PROVEN** observations from **HYPOTHESES / NON-PROVEN** interpretations.

---

## 1. Current load-cell plugin behaviour — PROVEN from live source/runtime

Live `zmod_tenz.py` uses `/dev/ttyS7` at 9600 baud.

Important behaviour:

- polling command defaults to `H7`;
- host report interval is `0.2 s`;
- parser extracts the numeric value before `g` and returns `abs(value)`;
- therefore exposed `WeightValue` loses sign;
- raw manual `H7` returns the signed board response;
- Python layer does not create the observed 20-unit stepping/quantisation;
- `LOAD_CELL_TARE` sends `H1` and accepts an absolute result `<100`, not necessarily exact zero;
- tare has bounded retries.

Observed raw example:

```text
H7 > command H7 ok. 8439466 -80 g
```

while the signless UI value was `80`.

### Consequence

`WeightValue` graphs cannot be used later to infer whether load was positive or negative. Raw `H7` is required when sign matters.

---

## 2. Probe coordinate semantics — PROVEN

Current Klipper `[probe]` configuration uses:

```text
z_offset = -0.25 mm
samples = 3
sample_result = average
```

A representative probe produced:

```text
bed will contact at z = -1.520000 / -1.510000 / -1.520000
Result estimate contact  = -1.516667
```

Klipper object state after that probe:

```text
last_probe_position.z = -1.516666...
last_z_result         = -1.766666...
```

Difference is exactly `-0.25 mm`.

### Proven semantics

- `last_probe_position.z` == user-facing `estimate contact` coordinate;
- raw `probe at ... is z=...` / `last_z_result` includes the configured probe `z_offset=-0.25`;
- these two coordinate forms must never be mixed silently.

---

## 3. Stock Z homing and coordinate transform — PROVEN

Current Z homing uses stock-style upper Z endstop `PD2` with endstop position around `220` and not the inactive `g28_tenz` virtual probe path.

`GET_POSITION` controls showed expected separation between physical/kinematic/toolhead Z and transformed G-code Z when a bed mesh is active.

Example with saved `auto` active:

```text
kinematic Z = -2.065000
gcode Z     = -0.194167
```

Difference:

```text
-0.194167 - (-2.065000) = +1.870833 mm
```

which exactly matches the magnitude of the saved `auto` center value `-1.870833 mm`.

### Consequence

A surprising G-code Z while bed mesh is active is not itself evidence of a hidden offset bug. The mesh transform must be accounted for first.

---

## 4. Saved map baselines — historical context

Historical maps observed during the session:

### `MESH_DATA`

```text
[-0.385000,-0.500833,-0.565833,-0.485833,-0.343333]
[-0.370833,-0.480833,-0.510000,-0.478333,-0.359167]
[-0.354167,-0.444167,-0.508333,-0.467500,-0.350000]
[-0.355000,-0.418333,-0.484167,-0.430833,-0.325000]
[-0.348333,-0.430000,-0.459167,-0.414167,-0.292500]
```

Center: `-0.508333`.

### saved `auto`

```text
[-1.793333,-1.884167,-1.880833,-1.840833,-1.695000]
[-1.759167,-1.835000,-1.859167,-1.821667,-1.708333]
[-1.761667,-1.805833,-1.870833,-1.835000,-1.677500]
[-1.725833,-1.814167,-1.821667,-1.771667,-1.659167]
[-1.721667,-1.815000,-1.834167,-1.747500,-1.597500]
```

Center: `-1.870833`.

The two maps have similar shape after removing the common baseline shift (correlation observed around `0.93`, residual order around a few hundredths of a millimetre).

### Owner history — important constraint

During this session the owner recalled that `MESH_DATA` was likely built **before the current Bambu Mod / current hotend geometry**, when a different carriage/hotend setup was installed.

Therefore:

> The absolute `MESH_DATA ↔ auto` baseline difference (~1.36 mm at center) is **not valid evidence of present-day Z drift** and must not be used to tune Auto-Z.

This explanation is highly plausible and consistent with the same bed shape but different tool length, but the exact creation timestamp/hardware combination of `MESH_DATA` was not independently reconstructed from logs.

---

## 5. One early anomalous reference — PROVEN observation, UNKNOWN cause

A cold probe early in the investigation produced a very stable three-sample result around:

```text
-1.520000
-1.510000
-1.520000
Result = -1.516667
```

Later in the same investigation, after many controls, stable current probing repeatedly returned around:

```text
-1.80 ... -1.84 mm (user-facing contact estimate)
```

The early value was therefore roughly `0.3 mm` higher.

### Critical conclusion

The early `≈ -1.5167` state **was never reproduced after the system became stable**.

It must be treated as:

```text
UNCLASSIFIED ANOMALY / OUTLIER
```

not as proof of a normal thermal drift mechanism, not as proof of PD2 homing error and not as a basis for hard-coded correction behaviour.

Possible physical explanations such as debris/plastic on plate/nozzle are plausible because the sign is consistent with early contact, but they were not proven.

---

## 6. Earlier large transient series — PROVEN observation

A first `PROBE_ACCURACY SAMPLES=10` earlier in the investigation showed a dramatic sequence:

```text
-0.110000
-0.145000
-0.242500
-0.447500
-1.407500
-1.432500
-1.447500
-1.462500
-1.465000
-1.457500
```

Statistics:

```text
range   = 1.355 mm
average = -0.96175
median  = -1.42
stddev  = 0.598361
```

A second run without a new home/tare was stable:

```text
-1.4675
-1.4625
-1.4750
-1.4700
-1.4825
-1.4775
-1.4900
-1.4850
-1.4975
-1.4925
```

with range `0.035 mm`, average/median about `-1.480 mm` and stddev about `0.0109 mm`.

Subsequent ordinary probes after fresh home/tare could also be stable immediately, so `LOAD_CELL_TARE` alone and normal `G28` alone were **not proven** to generate this transient.

### Consequence

The system must reject unstable/drifting sample series rather than converting the first result into a large automatic Z correction.

---

## 7. 80°C map experiments

### 7.1 isolated hot probe

After heating the bed to 80°C and performing a controlled home/center/Z5/tare/probe sequence:

```text
-1.5250
-1.5300
-1.5325
Result = -1.529167
```

Triplet range: `0.0075 mm`.

Compared with the earlier cold `-1.516667`, immediate hot-vs-cold difference was only about `-0.0125 mm`.

This disproved a simplistic claim that ordinary bed heating by itself explains the old ~0.34 mm saved-auto mismatch.

### 7.2 `diag80`

A direct 5×5 `BED_MESH_CALIBRATE PROFILE=diag80` at 80°C, after tare, yielded approximately:

```text
[-1.465833,-1.612500,-1.666667,-1.629167,-1.463333]
[-1.650000,-1.741667,-1.748333,-1.716667,-1.549167]
[-1.664167,-1.723333,-1.775833,-1.730000,-1.613333]
[-1.645833,-1.740000,-1.775833,-1.717500,-1.566667]
[-1.640833,-1.749167,-1.808333,-1.705000,-1.580833]
```

Mainsail range/deviation was about `0.345 mm`.

The center encountered during the map was about `-1.775833`, roughly `-0.2467 mm` lower than the isolated center probe made shortly before the map.

The early rows differed more strongly from old saved `auto` than later rows.

### 7.3 `diag80b`

A second 5×5 map without a fresh tare after the first map yielded approximately:

```text
[-1.6458,-1.7825,-1.8092,-1.7358,-1.5767]
[-1.7008,-1.7983,-1.8192,-1.7983,-1.6533]
[-1.7050,-1.7742,-1.8142,-1.7975,-1.6483]
[-1.6842,-1.7775,-1.7925,-1.7542,-1.6217]
[-1.6758,-1.7700,-1.8217,-1.7233,-1.5842]
```

The difference `diag80b - diag80` was largest at early points (order `-0.18 mm`) and approached near-zero at late points.

### 7.4 `diag80c`

A later third map, after a `G28` but without a new tare immediately before the map, yielded approximately:

```text
[-1.6908,-1.8083,-1.8483,-1.7600,-1.5950]
[-1.7383,-1.8158,-1.8417,-1.8133,-1.6958]
[-1.7300,-1.8092,-1.8383,-1.8008,-1.6533]
[-1.7108,-1.7925,-1.8117,-1.7733,-1.6367]
[-1.7058,-1.8075,-1.8208,-1.7467,-1.6258]
```

Average shift vs `diag80b` was only around `-0.024 mm`.

### Interpretation discipline

These maps initially looked like a time/contact-history settling effect. However scan order and Y-position are correlated, and `diag80c` happened after a much longer thermal soak. Therefore the maps alone **cannot prove** whether the observed early-to-late differences were caused by time, thermal soak, bed geometry, mechanical conditioning or a mixture.

This is why v2 architecture must not encode a specific settling hypothesis as fact.

---

## 8. Stable repeated center probe later in session — PROVEN

After long operation, a fresh `LOAD_CELL_TARE` followed by `PROBE_ACCURACY SAMPLES=10` at center produced:

```text
-1.8200
-1.8400
-1.8275
-1.8250
-1.8475
-1.8350
-1.8325
-1.8400
-1.8500
-1.8350
```

Statistics:

```text
average = -1.835250
median  = -1.835000
range   = 0.030000
stddev  = 0.009045
```

This showed **no strong monotonic settling trend** in an already-stable state.

The `diag80c` center (~`-1.8383`) differed from this average by only a few microns.

### Consequence

Repeated-contact conditioning is not proven as a permanent normal mechanism. The implementation must validate stability per run instead of assuming that N contacts are always required to “seat” the mechanism.

---

## 9. Cooling control — PROVEN observation

After the bed had been held hot, it was actively cooled to roughly `34.5°C`, then fan was stopped, a new `G28` was done, followed by center/Z5/tare/probe.

Result:

```text
-1.8225
-1.8175
-1.8200
Result = -1.820000
```

This did **not** return to the early `-1.5167` state.

Therefore a simple reversible `cold ≈ -1.52 / hot ≈ -1.83` thermal-expansion model is disproven by this experiment.

Caveat: fast active cooling of the bed sensor does not prove every frame component had returned to its original thermal state, so all thermal influence is not excluded. What is excluded is the simplistic fully reversible ~0.3 mm bed-temperature-only explanation.

---

## 10. Bed mesh as hidden coordinate cause — DISPROVEN

With current stable geometry:

```text
probe with prior active state ≈ -1.820000
BED_MESH_CLEAR
probe                  ≈ -1.821667
```

Difference was only about `0.0017 mm`.

A direct A/B test later gave:

```text
mesh OFF: -1.825000
auto ON:  -1.814167
Δ ≈ +0.0108 mm
```

within ordinary probe scatter.

A further test with `auto` active **before** `G28` still produced about `-1.805 mm`, not the early `-1.52` state.

### Conclusion

Loading/clearing the saved `auto`, and the order `auto + G28`, do not explain the ~0.3 mm early anomaly.

---

## 11. Hidden gcode/homing offset as cause — DISPROVEN for tested state

After mesh clear and stable probe, `GET_POSITION` showed:

```text
stepper_z / kinematic / toolhead / gcode = same physical Z
base/homing offset only the known small user offset in that pre-reboot state
```

After a full printer power cycle, base/homing offsets returned to `0.000`, yet the contact reference remained around `-1.8375`.

### Conclusion

The ~0.3 mm early-vs-late difference was not preserved as a hidden Klipper gcode/homing offset.

---

## 12. Full power-cycle control — PROVEN

A complete printer OFF/ON was performed, not merely Klipper `RESTART`.

Post-boot controlled sequence:

```text
BED_MESH_CLEAR
G28
center
Z5
wait
LOAD_CELL_TARE
PROBE
H7
GET_POSITION
```

Result:

```text
contact estimate ≈ -1.837500
raw probe Z       ≈ -2.087500
H7 after contact   360 g
base/homing offset 0.000
```

Power cycle did not return the machine to the early `-1.52` state.

### Consequence

A volatile Klipper/Moonraker state or a simple transient load-cell-board state that resets on full power loss is not a sufficient explanation of the early anomaly.

---

## 13. H7 contact/load behaviour — PROVEN with timing caveat

At stable current geometry, after tare:

```text
Z=-1.79 → H7 0 g
```

A descending sequence read immediately after moves produced:

```text
-1.79 →   0 g
-1.83 →   0 g
-1.87 →   0 g
-1.91 →   0 g
-1.95 →   0 g
-1.99 → 160 g
-2.03 → 240 g
```

After moving back to Z5, an immediate H7 still showed `320 g`, but after 3 seconds it returned to `0 g`.

This proved that instantaneous H7 has timing/filter/relaxation effects.

The test was repeated with 3-second dwell at each point:

```text
Z=-1.90 →  40 g
Z=-1.95 → 160 g
Z=-1.99 → 220 g
Z=-2.03 → 340 g
Z=+5.00 →   0 g
```

### Conclusion

There is a real repeatable load increase with deeper Z in the stable current state, but H7 cannot be treated as an instantaneous hard real-time force signal without validating latency under motion.

This is why v2 safety architecture treats H7 as secondary until a dedicated timing/stop-distance test proves otherwise.

---

## 14. Current saved `auto` is consistent with current hardware — PROVEN within probe scatter

Saved `auto` center:

```text
-1.870833
```

Stable current center probes during the later part of the session:

```text
~ -1.80 ... -1.84
```

Difference is on the order of a few hundredths of a millimetre, not 1+ mm and not the earlier ~0.34 mm anomaly.

Therefore the current saved `auto` is plausibly a map built with the present Bambu Mod geometry or a sufficiently similar current tool length.

The historical `MESH_DATA` is the out-of-family absolute baseline and must not be used as current reference evidence.

---

## 15. Current Z-Mod mesh-test architecture — PROVEN from source inspection

Normal headless startup loads saved profile `auto` through delayed startup logic.

`START_PRINT` keeps an already active profile unless force/build conditions change it.

Current `MESH_TEST=3/4` path ultimately:

- clears/loads/uses mesh state;
- cleans/probes;
- takes a reference probe;
- compares `last_probe_position.z` to the mesh reference point;
- computes `zdelta`;
- if `abs(zdelta) < 0.31`, applies a runtime `Z_ADJUST=zdelta` through Z-Mod offset machinery;
- otherwise mode 3 errors and mode 4 may rebuild via KAMP.

### Product problem

Even if the arithmetic is internally valid for a pure rigid reference shift, the user experience is opaque:

- multiple offset layers exist;
- `MESH_TEST` modes are not human concepts;
- large/unexpected deltas are difficult to explain;
- one transient anomaly can create a dangerous correction attempt unless rejected;
- saved mesh, current reference, user trim, slicer offset and live adjustment are not presented as an auditable composition.

The v2 objective is therefore not merely to rename `MESH_TEST`; it is to replace the product-level policy with a validated state/decision model while reusing safe low-level Z-Mod/Klipper primitives where appropriate.

---

## 16. What is NOT proven

Do not encode any of these as facts without new evidence:

- that G28/PD2 is intrinsically inaccurate;
- that `g28_tenz` is required for correct first layer;
- that repeated probing always mechanically seats the head;
- that 80°C heating causes a 0.3 mm reversible Z shift;
- that the early `-1.5167` value was caused by debris;
- that H7 can stop dangerous motion fast enough to be an independent hard watchdog;
- that a specific 0.31/0.03/etc threshold is universally safe for release;
- that `MESH_DATA` and current `auto` were made with the same carriage/hotend;
- that a single center point is sufficient to confirm a large global reference shift.

---

## 17. Architecture consequences accepted for v2

1. Treat the early ~0.3 mm anomaly as a reason for **outlier rejection/reconfirmation**, not as a permanent correction model.
2. Do not require persistent hotend/nozzle Z profiles for normal operation.
3. Preserve standard Klipper effective offset semantics.
4. Track auto/user/slicer/live offset provenance separately.
5. Large unexpected delta triggers diagnosis/full calibration, not blind application.
6. Runtime mesh is a first-class optional pre-print mode and does not overwrite saved mesh without explicit action.
7. First-layer test verifies process/quality, not geometric safety, and remains optional.
8. Build structured diagnostics so a future anomaly captures the state immediately.
9. Plate-protection logic must remain safe without assuming instantaneous H7.
10. Every safety threshold must be derived from source/hardware tests with margin before release.