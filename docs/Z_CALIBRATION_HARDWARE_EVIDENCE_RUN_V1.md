# Z Calibration Subsystem v2 — Hardware Evidence Run v1

**Status:** repository-only preparation for controlled hardware acceptance  
**Applies to:** issue #13 / `CALIBRATION-SUBSYSTEM-002`  
**Authority:** evidence record only; this document does not authorize motion

## 1. Purpose

Hardware Evidence Run v1 is the bridge between the repository-green fake/model layers and a future production motion adapter.

Its purpose is to collect exact, reviewable observations from the real AD5X without silently turning those observations into safety thresholds.

The evidence flow is:

```text
raw hardware observation
→ exact provenance
→ repeated evidence dataset
→ human/policy review
→ documented margin rationale
→ explicit owner acceptance
→ accepted calibration policy
→ accepted concrete motion policy
→ production motion adapter gate
```

An evidence run is therefore **not** a motion permission and is never equivalent to `owner_accepted=true`.

---

## 2. Hard boundary

Hardware Evidence Run v1 must not:

- enable the production Z-offset write gate;
- enable the production motion gate;
- create default safe-approach/contact/retract values;
- derive a release threshold automatically from one or more measurements;
- save a runtime mesh as default automatically;
- mutate persistent user Z trim;
- treat a successful ordinary printer operation as proof that an automatic safety envelope is acceptable;
- bypass ordinary Z-Mod/Klipper fallback.

The schema deliberately has no `owner_accepted` or `ready_for_motion` field.

---

## 3. Repository representation

Pure module:

`moonraker/components/plugins_ad5x_zevidence.py`

Schema version:

`1.0`

The module performs no printer I/O.

### Evidence phases

- `gate_a_read_only_baseline`
- `gate_b_controlled_measurement`
- `gate_c_repeatability`

These correspond to Gates A–C in `docs/Z_CALIBRATION_TEST_PLAN_V2.md`.

---

## 4. Required provenance per run

Every `HardwareEvidenceRunV1` records:

- unique `run_id`;
- evidence phase;
- exact 40-character Plugins AD5X repository SHA;
- exact/identifiable Z-Mod version;
- exact/identifiable Klipper version;
- exact/identifiable Moonraker version;
- `hardware_setup_id` identifying the physical setup;
- one or more source references;
- setup notes sufficient to distinguish the tested physical state.

The physical setup notes should identify at minimum, when relevant:

- installed hotend/nozzle state;
- build plate state/type;
- whether the head belts were mechanically adjusted;
- whether bed screws/fasteners were mechanically adjusted;
- whether the plate was removed/reseated;
- meaningful temperature condition;
- any other physical change since the previous accepted dataset.

A new mechanical adjustment is a new evidence context unless review proves it is equivalent.

---

## 5. Bed mesh observation

`BedMeshObservation` stores the raw rectangular mesh matrix and a source identifier.

It exposes only descriptive values:

- minimum Z;
- maximum Z;
- total span.

Those values are **not** automatically converted into:

- acceptable bed-flatness threshold;
- Z search margin;
- contact limit;
- Auto-Z correction limit;
- release acceptance.

### Current owner action

A fresh bed mesh taken after head-belt and bed-screw tightening is useful Gate-A/Gate-C context. Preserve the raw matrix if available, not only a screenshot or the displayed min/max.

If only a screenshot is available, it may be used as a source artifact, but the raw matrix is preferred for reproducible comparison.

---

## 6. Reference-series observation

`ReferenceSeriesObservation` stores every raw contact/reference sample.

It exposes descriptive statistics only:

- mean;
- median;
- spread;
- first-to-last drift.

It does not decide whether those values are safe or acceptable.

The existing calibration policy layer remains the owner of accepted thresholds once hardware evidence and margin rationale are reviewed.

---

## 7. Gate A — read-only baseline record

A Gate-A record should capture the exact current state before any Plugins AD5X-controlled calibration motion exists.

Record:

- software versions/SHAs;
- active probe/Z configuration sources;
- relevant machine bounds;
- saved mesh identity/reference where available;
- current standard Klipper effective Z offset;
- current physical hotend/nozzle/plate setup;
- current fresh bed mesh;
- any mechanical work immediately preceding the record.

A Gate-A record is intentionally **not complete for motion-policy review** because no controlled reference-series evidence exists yet.

---

## 8. Gate B — controlled no-persistence measurement

Gate B comes only after the repository/fake safety contour is green and the exact hardware action is reviewed.

The measurement record must include:

- raw repeated reference/contact series;
- exact source/command path used to obtain it;
- tare residual when applicable;
- H7 status/value provenance when available;
- proof that persistent user trim was unchanged;
- proof that saved mesh state was unchanged;
- cleanup/retract confirmation where motion occurred;
- diagnostic correlation/source reference.

A failed or suspicious Gate-B attempt is still retained as evidence. It simply remains blocked from policy review.

---

## 9. Gate C — repeatability dataset

Repeat Gate-B-style observations under deliberately distinct, recorded conditions as required by the main test plan, including later:

- ambient/cold state;
- representative PLA bed condition;
- representative higher-bed-temperature condition used by the owner hardware;
- reboot/power-cycle condition;
- reasonable idle/time separation;
- relevant physical re-seat/change cases.

The repository only exposes the IDs of complete repeatability records. It does not infer how many runs are sufficient for release.

---

## 10. Evidence completeness blockers

A measurement/repeatability record is not suitable for policy review if any of these are true:

- reference series missing;
- cleanup not explicitly confirmed;
- persistent state changed unexpectedly;
- saved mesh changed unexpectedly;
- a stop condition was observed.

A read-only baseline is also intentionally blocked by `measurement_phase_required`.

`complete_for_policy_review=true` means only:

> the record is structurally complete enough to be reviewed.

It does **not** mean:

> the motion policy is safe or accepted.

---

## 11. Cleanup failure disposition

Pure module:

`moonraker/components/plugins_ad5x_zcleanup_safety.py`

The orchestrator already returns independent confirmations for:

- `offset_reconciled`;
- `mesh_reconciled`;
- `retracted`.

Hardware-facing continuation policy is now explicitly fail-closed:

```text
all required cleanup confirmations == true
→ CLEAN

any false / missing / unknown confirmation
→ UNSAFE
```

An `UNSAFE` cleanup disposition forbids automatic continuation. The operator must use the ordinary known-safe recovery/fallback path and inspect actual printer state before another automatic calibration attempt.

---

## 12. Stop conditions

Hardware evidence collection stops immediately if any accepted stop condition from the main test plan occurs, including:

- uncontrolled downward movement;
- contact outside the expected safe window;
- failed stop/retract;
- unexpected persistent Z change;
- unexpected saved-mesh mutation;
- unexplained disagreement between backend composition and actual Klipper effective offset;
- new unexplained reference drift/scatter;
- diagnostic evidence insufficient to reconstruct the decision;
- any condition that may threaten the plate or hotend.

A stopped run is recorded with `stop_condition_observed=true` and is not policy-reviewable.

---

## 13. Promotion into an accepted policy

Hardware evidence does not promote itself.

After enough representative runs exist, a separate review must explicitly decide:

- which run IDs are authoritative;
- which source/config semantics are trusted;
- what concrete search/motion parameters are proposed;
- how much safety margin is added and why;
- whether H7 remains secondary or has sufficient measured latency/stopping evidence for any stronger role;
- whether the candidate is accepted by the owner.

Only then may the existing `HardwarePolicyEvidence` / `AcceptedCalibrationPolicy` and `ProductionMotionPolicy` gates be populated with accepted values.

No production adapter should contain fallback numeric motion defaults for missing policy values.
