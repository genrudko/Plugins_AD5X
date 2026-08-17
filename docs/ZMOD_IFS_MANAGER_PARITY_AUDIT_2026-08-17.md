# Z-Mod IFS Manager functional parity audit — 2026-08-17

Status: **active implementation checklist**  
Work item: `IFS-MANAGER-001` / issue #15  
Plugins AD5X branch: `feature/ifs-manager-v1`  
Reference provider: `ghzserg/z_ad5x`, branch `1.7`

## 1. Purpose

Plugins AD5X IFS / Materials Manager is intended to become the complete user-facing replacement for the stock Z-Mod IFS/material manager while continuing to use Z-Mod as a low-level/provider implementation where that is safer and more maintainable.

This document prevents a visually better replacement from becoming functionally poorer than Z-Mod.

Status vocabulary:

- **DONE** — implemented in the normalized Plugins AD5X backend/reference flow;
- **PARTIAL** — useful implementation exists but does not yet cover the Z-Mod user-facing workflow;
- **PROVIDER** — Z-Mod already owns the correct low-level behavior; Plugins AD5X should expose it through a normalized action/state instead of reimplementing it;
- **MISSING** — required product behavior is not implemented yet;
- **HARDWARE GATE** — implementation must remain disabled until real-printer acceptance;
- **TRACE** — source primitive was found, but its complete user-facing/configuration path still needs source/hardware tracing before product exposure.

This is a living matrix. It should be updated when a gap is closed rather than replaced by ad-hoc frontend-specific checklists.

## 2. Reference source facts

### `zmod_color.py`

Reference file SHA: `158338c4f8f6c937e3b1ae6f9ca34261983cc425`.

Registered public/internal commands include:

- `GET_ZCOLOR`;
- `SET_ZCOLOR`;
- `_SET_EXTRUDER_SLOT`;
- `PRINT_ZCOLOR`;
- `CHANGE_T_ZCOLOR`;
- `_CHANGE_FILAMENT`;
- `RUN_ZCOLOR`;
- `CHANGE_ZCOLOR`;
- `IN_ZCOLOR`;
- `UPDATE_FF_OFFSET`.

Observed user-facing semantics include:

- list current spool slots/material/color;
- select a spool for actions;
- change color;
- change material type;
- load/unload;
- remove filament from extruder;
- reset colors (prompt action; concrete reset macro remains a trace item);
- scan G-code for used tools, material and color metadata;
- auto-assign tools to slots;
- indicate material mismatch, color mismatch, weak color match and duplicate-slot mapping;
- manually remap each required tool to a slot;
- select leveling-before-print;
- start printing with IFS mapping;
- explicitly print without IFS when appropriate.

Z-Mod's auto-assignment is provider-owned and uses material filtering followed by perceptual color comparison (CIE LAB / ΔE76). Plugins AD5X must not duplicate this matcher.

`PRINT_ZCOLOR` is the authoritative Z-Mod multi-color launch lifecycle. In the non-stock-display path it validates the complete tool vector, writes `/usr/data/config/mod_data/file.json`, establishes the initial/current tool through the existing flow, and starts the virtual SD file. A generic frontend `print_start(filename)` is therefore not equivalent.

### `zmod_ifs.py`

Reference file SHA: `511d0140044a48529b9217d495f3737fe753790a`.

Provider primitives include:

- `INSERT_PRUTOK_IFS`;
- `REMOVE_PRUTOK_IFS`;
- `PURGE_PRUTOK_IFS`;
- `SET_CURRENT_PRUTOK`;
- `ANALOG_PRUTOK`;
- `IFS_MOTION`;
- `IFS_AUTOINSERT`;
- `IFS_STATUS`;
- `IFS_EXTRUDER_SENSOR`;
- `IFS_REMOVE_PRUTOK`;
- `IFS_REMOVE_CURRENT_PRUTOK`;
- driver-level `IFS_F10/F11/F13/F15/F18/F23/F24/F39/F112` operations.

The provider also publishes/derives physical lane state, active channel, insertion event, stall state and raw IFS state, and automatically reacts to an insertion event through the Z-Mod auto-insert flow.

`ANALOG_PRUTOK` provides an existing equivalent-spool fallback primitive: it looks for another present spool with matching material/color, rewrites the active mapping and resumes through the existing filament-change path. Its complete configuration/trigger UX still needs tracing before calling this full endless-spool parity.

## 3. Functional parity matrix

| Capability | Z-Mod 1.7 behavior | Plugins AD5X current state | Status | Required next state |
|---|---|---|---|---|
| IFS availability | detects IFS online/offline and changes provider state | normalized `available/state` from bridge | DONE | keep provider-owned |
| Four lane presence | physical port/silk state | normalized lane `present` | DONE | native visualization in every UI |
| Active/current lane | provider/current FF channel | runtime + configured active slot normalization | DONE | make distinction understandable in diagnostics only |
| Toolhead filament presence | extruder sensor used in flows | Moonraker head sensor integrated into permissions | DONE | native state indication where useful |
| Stall / insertion diagnostics | provider exposes stall, insert, NeedInsert | normalized diagnostics available | DONE | product-grade warning/recovery presentation |
| Material/color display | stock single material + RGB per slot | Flashforge/Z-Mod fallback + rich overlay | DONE | rich native spool cards |
| Change material/color in Z-Mod representation | `CHANGE_ZCOLOR` writes stock/provider representation | read-only compatibility projection only | PARTIAL + HARDWARE GATE | normalized compatibility write action with stale/readback verification |
| Rich multi-color appearance | not represented by stock single RGB model | solid/dual/tricolor/gradient/rainbow/special + finish | DONE (model) | product-grade visual component in all UIs |
| Manufacturer/series/name/variant | limited/not native in stock manager | persistent Plugins AD5X rich metadata overlay | DONE | merge with optional Spoolman authority cleanly |
| Select active lane | `_SET_EXTRUDER_SLOT` / provider state | normalized `select_slot` action | DONE | retain backend permission ownership |
| Load lane | `IN_ZCOLOR` -> existing Z-Mod load path | normalized `load_slot` -> `INSERT_PRUTOK_IFS` | DONE (technical) | keep hardware evidence and improve UX feedback |
| Unload active filament | stock/Z-Mod unload path | normalized active-slot unload wrapper | DONE (bounded) | expose recovery alternatives for non-normal states |
| Arbitrary/recovery unload | provider has lower-level removal primitives | deliberately restricted | MISSING + HARDWARE GATE | separate recovery action contract; never silently broaden normal unload |
| Automatic insertion | insertion event triggers `_IFS_AUTOINSERT` | state is visible; Plugins AD5X does not own the automation | PROVIDER/PARTIAL | surface progress/errors without duplicating provider motion logic |
| Purge/recovery primitive | `PURGE_PRUTOK_IFS` | not exposed | MISSING + HARDWARE GATE | expert/recovery semantic action if hardware use-case is accepted |
| Driver reset | `IFS_F15` | not exposed | MISSING + HARDWARE GATE | diagnostics/recovery action with explicit confirmation |
| Emergency filament stop | `IFS_F112` | not exposed as user action | MISSING + HARDWARE GATE | backend emergency/recovery semantic action, not raw macro button |
| Unlock lane/all lanes | `IFS_F39` / `IFS_F18` | not exposed | MISSING + HARDWARE GATE | recovery-only normalized actions if needed by parity/use cases |
| G-code tool discovery | `get_used_colors` scans T-codes/header/prepared Z-Mod data | delegated live `zmod_color.get_used_colors` | DONE | retain one canonical matcher/scanner |
| File material/color requirements | parsed from slicer metadata | normalized `job_preview.requirements` | DONE | richer pre-print presentation |
| Automatic material/color assignment | material filter + ΔE76 + provider flags | delegated live `get_auto_tool_assignments` | DONE | never create a competing Plugins AD5X matcher |
| Weak/missing/duplicate match flags | provider aggregate flags | normalized aggregate warnings | DONE | present actionable, human-readable warnings |
| Complete resolved Tn->slot vector | full vector required by Z-Mod print lifecycle | `allowed_tool_count` + `resolved_tool_map` now preserved/tokenized | DONE (repo) | real-printer read-only preview acceptance |
| Manual Tn->slot correction | Z-Mod prompt can remap each tool | backend currently publishes preview; no normalized apply/edit action | MISSING | frontend-neutral draft/edit/apply mapping contract |
| Pre-print plan | Z-Mod prompt shows mapping and state | normalized `preprint_plan` joins requirements, assignments, physical/rich spool data | DONE (repo) | hardware acceptance + product UI |
| Leveling-before-print choice | explicit toggle in Z-Mod pre-print prompt | not yet modeled as user choice in IFS launch contract | MISSING | normalized launch option; later integrate with broader Plugins AD5X mesh/calibration policy |
| IFS-off print path | Z-Mod can explicitly print without material station | not part of IFS Manager launch API yet | MISSING | safe explicit fallback; do not hijack normal generic printing |
| Safe IFS multi-color launch | `PRINT_ZCOLOR` authoritative lifecycle | launch gate/token exists, write remains deliberately disabled | PARTIAL + HARDWARE GATE | controlled provider-delegated launch action + stale/live revalidation + real-printer proof |
| In-print filament change | `_CHANGE_FILAMENT` consumes `file.json` mapping and handles errors/pause | intentionally left provider-owned | PROVIDER | surface current transition/progress/errors if observable |
| Equivalent-spool fallback | `ANALOG_PRUTOK` can swap mapping to matching present spool and resume | not exposed; `endless_spool=false` | TRACE/MISSING + HARDWARE GATE | trace trigger/config semantics; expose as normalized endless-spool policy/action |
| Low-level IFS status | `IFS_STATUS` and raw F13 state | normalized diagnostics | DONE | keep raw detail under Diagnostics, not main screen |
| Per-material motion/purge tuning | provider reads `filament.json` profiles with temperatures/speeds/lengths | not managed by IFS Manager | TRACE | determine whether stock user-facing manager exposes these settings; if yes include advanced parity, otherwise keep provider config out of normal UI |
| Reset-colors action | stock prompt offers `RESET_ZCOLOR` | not exposed | TRACE | locate exact macro semantics before deciding parity implementation |
| Spool library | no equivalent full catalog contract in this Z-Mod flow | schema fields only; integration disabled | MISSING (product differentiator) | optional full Spoolman adapter/search/bind/unbind/sync/degrade flow |

## 4. What must remain provider-owned

Full user-facing replacement does **not** justify reimplementing these proven internals in Plugins AD5X:

1. IFS serial protocol ownership;
2. raw F10/F11/F13/Fxx command timing/retry behavior;
3. Z-Mod G-code color/material scanning where available;
4. Z-Mod material/color matching and ΔE behavior;
5. established in-print filament-change motion lifecycle;
6. `PRINT_ZCOLOR` launch semantics until/unless a future upstream contract supersedes them.

Plugins AD5X should wrap these through semantic backend actions and normalized state, with capability detection and fail-closed handling.

## 5. Product improvements beyond parity

Parity is the floor, not the design target.

Plugins AD5X adds or should add:

- rich spool identity and appearance independent of the one-RGB stock representation;
- dual/tricolor/gradient/rainbow/special appearances;
- finish metadata;
- optional full Spoolman integration;
- clear source/provenance and compatibility state;
- a consolidated pre-print plan rather than raw macro prompts;
- progressive disclosure for normal/advanced/diagnostic workflows;
- consistent semantic behavior across Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen;
- genuinely native presentation in every host UI;
- consumer-grade visual clarity while preserving advanced Klipper flexibility.

## 6. Immediate implementation sequence derived from the audit

### A. Finish safe print/mapping core

1. hardware-accept the newly preserved complete `resolved_tool_map` in read-only preview;
2. add a frontend-neutral editable mapping draft without writing `file.json` directly from a frontend;
3. add controlled provider-delegated mapping/launch action using the authoritative `PRINT_ZCOLOR` lifecycle;
4. revalidate preview token, IFS state, physical lane presence and print state immediately before mutation;
5. prove one-color and controlled multi-color launch on the real printer before setting any production write capability true;
6. model the leveling-before-print choice explicitly rather than burying it in a raw macro string.

### B. Close daily-operation parity

1. compatibility write/readback for material + primary color;
2. normal load/unload/select feedback and operation progress;
3. recovery action contract for abnormal filament states;
4. trace and then expose provider endless/equivalent-spool semantics;
5. locate/decide `RESET_ZCOLOR` parity and any genuinely user-facing filament-profile settings.

### C. Add differentiators before final UX freezes

1. full optional Spoolman integration in backend;
2. richer spool visualization and remaining-filament state;
3. final information architecture for primary / pre-print / advanced / diagnostics levels.

### D. Native frontend convergence

Reference UI may be implemented first, but completion requires native adapters for:

- Fluidd;
- Mainsail;
- HelixScreen;
- GuppyScreen;
- KlipperScreen.

No frontend may become the owner of mapping, safety, Spoolman synchronization or hardware semantics.

## 7. Current conclusion

The existing Plugins AD5X work is a valid foundation and already exceeds Z-Mod's stock metadata model in several areas, but it is **not yet a complete Z-Mod Manager replacement**.

The largest remaining parity gaps are currently:

1. write/readback synchronization of stock material/color representation;
2. editable/applicable pre-print mapping;
3. safe `PRINT_ZCOLOR` launch;
4. leveling/fallback choices in the normalized launch workflow;
5. recovery/endless-spool provider functions;
6. full optional Spoolman integration;
7. product-grade native UX across all supported frontends.

These gaps are now explicit acceptance items rather than implicit future work.
