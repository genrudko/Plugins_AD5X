# Z-Mod IFS Manager parity audit

Initial audit: 2026-08-17
Expanded source/community review: **2026-08-22**
Work item: `IFS-MANAGER-001` / issue #15

## 1. Purpose

This audit defines the **minimum user-facing parity floor** Plugins AD5X must reach before its IFS / Materials Manager can replace the stock Z-Mod IFS manager for ordinary and Expert workflows.

It is not a request to fork Z-Mod. Proven hardware/protocol/matcher/print-lifecycle logic stays provider-owned and is normalized by Plugins AD5X.

The 2026-08-22 review corrected an earlier research mistake: `ghzserg/zmod` alone is not the whole AD5X runtime source. Relevant implementation is distributed across Z-Mod wiki, `zmod`, `base`, `z_ad5x`, Z-Mod Klipper/Moonraker forks and related plugins.

## 2. Provider source map

Before enabling any provider-overlapping write path, inspect the relevant current source in this order as applicable:

```text
Z-Mod wiki
   |
   +--> ghzserg/zmod
   +--> ghzserg/base
   +--> ghzserg/z_ad5x (.shell runtime modules)
   +--> ghzserg/zmod_klipper / zmod_moonraker
   +--> related official plugins/forks
```

For IFS specifically, high-value runtime sources include `zmod_color.py`, `zmod_ifs.py`, IFS sensor extras, print/change-filament macros and current `START_PRINT`/`PRINT_ZCOLOR` integration.

## 3. Parity matrix

| Capability | Z-Mod/provider behavior | Plugins AD5X current/target | Completion gate |
|---|---|---|---|
| Physical 4-slot state | Provider exposes IFS status/masks/current channel | normalized 4-slot model exists | retain hardware regression |
| Active/current slot | provider runtime source | normalized active/runtime slot exists | retain hardware regression |
| Toolhead filament | head switch/provider state | normalized boolean exists | retain hardware regression |
| Material/color display | stock `COLOR` and Flashforge metadata | normalized + rich overlay exists | Expert native UI |
| Material/color editing | provider supports normal mutation path | read projection exists; write gated | source + hardware write acceptance |
| Select/load/unload | provider primitives/macros | semantic actions exist | already hardware tested; preserve gates |
| G-code tool/color scan | Z-Mod scanner | delegated preview exists | parser-safe `ADIFS_JOB_PREVIEW` hardware regression |
| Automatic assignment | material + LAB/ΔE76 matcher | delegated provider assignment exists | no duplicate matcher |
| Weak/missing/duplicate reporting | provider returns flags/messages | normalized preview/preprint warnings | UI clarity acceptance |
| Job `Tn → slot` mapping | stock print flow uses mapping | read mapping + proposed mapping exists | editable/apply path still gated |
| Runtime remap during print | Z-Mod `PRINT`/change flow supports remap semantics | target Expert capability | source + hardware acceptance |
| Print with IFS | provider `PRINT_ZCOLOR` lifecycle | preview/launch gate exists, production start disabled | real print acceptance |
| Print without IFS | provider/silent policy supports bypassing IFS | target normalized mode | source + UI acceptance |
| Auto insertion | provider functionality | target normalized capability/state | source + hardware acceptance |
| Change filament during print | mature provider lifecycle | do not reimplement; wrap semantically | recovery/UX acceptance |
| Purge behavior | provider material-change/purge logic | target policy/status surface | source verification |
| Stop/reset/unlock | provider recovery primitives | target semantic recovery actions | bounded hardware acceptance |
| Equivalent/endless spool | provider has analogous-spool primitive (`ANALOG_PRUTOK`) and compatible-spool behavior | architecture now explicitly targets provider-backed policy | source semantics + hardware transition acceptance |
| IFS motion sensor | provider/sensor extras | target Expert diagnostics/recovery input | source/runtime verification |
| Spool library | not complete stock equivalent | full optional Spoolman required | integration acceptance |
| Orca material/color sync | not historical stock requirement; Z-Mod/community path discovered 2026-08-21 | `lane_data` compatibility projection required | Orca 2.4.2 acceptance |
| Multi-UI presentation | stock UI/macros are provider-specific | any Klipper/Moonraker client + 5 first-party native adapters | backend portability + native acceptance |

## 4. What must remain delegated to Z-Mod

Plugins AD5X MUST NOT independently reimplement:

- IFS serial protocol;
- low-level Fxx timings/retries;
- current scanner/parser when Z-Mod can provide the same job result;
- material filtering + LAB/ΔE matcher;
- established in-print material-change lifecycle;
- authoritative `PRINT_ZCOLOR` launch semantics;
- existing auto-insert behavior;
- equivalent-spool hardware transition where provider primitive already exists.

If the product needs a better user workflow, wrap the provider mechanism through normalized semantic state/actions.

## 5. Mapping conclusion

The 2026-08-22 UX/source review clarifies that **mapping is a job-level concern**, not the main physical dashboard.

AD5X topology is fixed:

```text
IFS1 --\
IFS2 ---+--> selector --> one extruder
IFS3 ---+
IFS4 --/
```

Therefore:

- main screen = physical spools/sources/path/state;
- `Tn → slot` appears in pre-print and active-job context;
- Auto may hide healthy mapping;
- Hybrid shows compact mapping + correction affordance;
- Expert exposes full mapping/mismatch details.

This still preserves all provider mapping capability; it only removes unnecessary permanent UI dominance.

## 6. External / bypass

A direct/manual feed path is modeled as a distinct source, not a fifth IFS lane.

No IFS presence/stall/selector telemetry may be fabricated for it. Provider/runtime support must be proven before automated control is enabled.

## 7. Equivalent / endless spool

Earlier parity documents treated endless-spool support mostly as future custom functionality. The expanded Z-Mod review changes that conclusion.

Z-Mod already has an analogous/equivalent-spool concept and `ANALOG_PRUTOK` provider primitive. Plugins AD5X therefore must:

- discover exact current semantics/configuration;
- expose understandable equivalent/fallback relationships;
- retain Z-Mod as transition authority;
- not implement a second automatic switch engine;
- keep automatic fallback disabled until hardware accepted.

## 8. OrcaSlicer interoperability discovered 2026-08-21/22

Community/source review established a simple generic path:

```text
Plugins AD5X canonical slots
        |
        v
Moonraker database namespace lane_data
        |
        v
OrcaSlicer (Moonraker network agent)
```

Current Orca generic Moonraker reader consumes `lane`, `material`, `color`, `nozzle_temp`, `bed_temp`. Inner lane number is a zero-based string.

The product should publish stable `lane1..lane4` records, while preserving exact/rich metadata internally.

Current exact custom Orca filament preset matching is not reliable. `filament_id` must not be populated with a Spoolman filament ID by accident.

Orca configuration prerequisite must be documented:

```text
Host type:     Octo/Klipper
Network agent: Moonraker
```

Initial acceptance target: OrcaSlicer 2.4.2.

## 9. Spoolman parity/extension

Spoolman is not provider physical truth. It is an optional library/inventory layer.

Full target integration includes real spool browsing/binding and supported consumption/remaining data, with separate IDs for Spoolman spool and filament entities. Emptying an IFS lane must not delete the library spool.

## 10. Expert completeness rule

Expert is the canonical capability surface.

A reliable provider capability counts as a parity gap until it is:

1. represented in normalized backend state/actions;
2. permission/safety modeled;
3. exposed in Expert through a usable semantic workflow;
4. accepted on hardware if it mutates mechanics/printing.

Auto/Hybrid may hide detail but may not be used as an excuse to omit Expert capability.

## 11. Diagnostics rule

Useful real provider signals should be exposed in Expert/Diagnostics, including physical lane state, active source, head switch/toolhead state, IFS motion/stall/retry information where available, operation errors and matcher/compatibility results.

Do not copy Happy Hare diagnostics that have no AD5X source (encoder path, hubs, compression, clog sensors, etc.).

## 12. Remaining high-priority gaps after v2 reset

1. provider-backed material/color writes;
2. editable/applicable pre-print mapping;
3. production `PRINT_ZCOLOR` launch;
4. normalized print-without-IFS / external path policy;
5. runtime remap UI/workflow;
6. equivalent/endless-spool policy + transition acceptance;
7. semantic recovery actions;
8. full Spoolman adapter;
9. Orca `lane_data` runtime publisher + real 2.4.2 acceptance;
10. final Expert/Hybrid/Auto UX across first-party native UIs;
11. generic third-party Klipper/Moonraker consumer documentation.

## 13. Current safety boundary

The audit does not enable write paths by documentation alone.

Keep disabled until individually accepted:

```text
apply_preprint_mapping = false
start_job = false
zmod_projection_write = false
automatic endless/equivalent spool = false
unproven recovery motion = false
automated external/bypass switching = false
```

Existing select/load/unload hardware path remains subject to current backend permission gates.

## 14. Exit criterion

Parity is closed only when a user can perform every reliable, meaningful stock Z-Mod IFS workflow — and the additional committed Plugins AD5X workflows such as full Spoolman and Orca sync — without falling back to the stock IFS manager, while preserving provider authority and hardware safety.
