# Plugins AD5X — IFS / Materials Manager architecture v2

Status: **canonical target architecture for IFS-MANAGER-001 / issue #15**

Architecture version: `2.0`
Runtime/API migration policy: additive over the existing `1.0` snapshot/store contract unless a separately documented migration requires otherwise.

## 1. Product boundary

Plugins AD5X IFS / Materials Manager is the user-facing materials subsystem for AD5X + Z-Mod. It must expose the complete useful IFS capability surface while keeping proven Z-Mod hardware/protocol/print-lifecycle internals provider-owned.

The subsystem is designed for **any Klipper/Moonraker UI or client**. Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen are first-party native adapter targets, not the architectural boundary of the backend.

Operational support boundary for v1: full IFS Manager requires Z-Mod `DISPLAY_OFF`. Native Flashforge screen mode is a maintenance compatibility state: Plugins AD5X suspends IFS controls/pre-print interception and leaves stock/Z-Mod ownership untouched. Full native-screen IFS parity is not a v1 target.

## 2. Canonical layers

```text
Flashforge IFS / sensors
          |
          v
      Z-Mod provider
 protocol / matcher / print lifecycle
          |
          v
 Plugins AD5X provider adapters
          |
          v
+------------------------------------+
|       Canonical IFS backend        |
| physical state                     |
| material/spool identity            |
| appearance                         |
| operation + permissions            |
| job requirements + mapping         |
| recovery/equivalent-spool policy   |
| source/provenance                  |
+------------------------------------+
          |
          +----------------------+----------------------+-------------------+
          |                      |                      |                   |
   normalized API/events    interoperability      first-party native   future Klipper
                             projections            adapters             consumers
          |                      |                      |
          |                 Orca lane_data          Fluidd
          |                 future AFC/MMU          Mainsail
          |                 contracts only          HelixScreen
          |                 when verified           GuppyScreen
          |                                         KlipperScreen
          v
      any capable client
```

Business rules, safety, hardware semantics, matching and source authority never belong to frontend code.

## 3. Truth domains

The backend keeps these domains explicitly separate:

1. physical IFS presence/state;
2. active/current source;
3. filament-at-toolhead state;
4. exact spool/material identity;
5. rich appearance;
6. external library identity (Spoolman, future sources);
7. current operation/recovery state;
8. job requirements from slicer/G-code;
9. job-specific `Tn → source` mapping;
10. provider compatibility projections;
11. UI session state / selected card;
12. diagnostics/raw provider evidence.

No frontend may infer one truth domain from another when the backend has not made that relationship explicit.

## 4. Source model

### 4.1 IFS sources

Four fixed physical IFS slots:

```text
ifs:1
ifs:2
ifs:3
ifs:4
```

They expose provider-backed presence/stall/active semantics.

### 4.2 External / bypass source

A manual external path is modeled separately:

```text
external:bypass
```

It is not `slot 5`. Unsupported/unknown provider telemetry stays unknown. Frontends may render the path as available only when the backend capability/provider state supports that claim.

## 5. Canonical spool/material model

A source may have rich metadata independent of physical presence:

```json
{
  "source": "manual",
  "brand": "Example",
  "series": "Engineering",
  "name": "ASA-GF Black",
  "material": "ASA-GF",
  "variant": "",
  "spoolman_spool_id": 42,
  "spoolman_filament_id": 7,
  "orca_filament_id": null,
  "orca_setting_id": null,
  "remaining_g": 612.5
}
```

Legacy `spoolman_id` may remain as an additive compatibility alias during migration but must not hide which Spoolman entity it refers to.

Physical presence is never inferred from metadata.

## 6. Appearance model

Rich appearance remains canonical:

- solid;
- dual;
- tricolor;
- gradient;
- rainbow;
- special;
- semantic finish.

Compatibility projections may use a single representative color but never destroy the full appearance model.

## 7. UI expertise policy

### Expert

Canonical complete capability surface. Every reliable supported capability/state is available somewhere in Expert without requiring stock Z-Mod UI fallback.

### Hybrid

Same backend with routine controls and contextual mapping visible, while diagnostics/service controls are collapsed.

### Auto

Same backend with healthy automatic decisions hidden behind simple ready/problem states. Auto may recommend/choose only actions already allowed by backend policy.

`interface_expertise` affects presentation and automation policy, not truth, capability existence or safety.

## 8. Physical dashboard vs job mapping

The main dashboard visualizes AD5X physical topology:

```text
[1] [2] [3] [4]
 \   |   |   /
     selector
        |
    toolhead

external/bypass ----> toolhead
```

Job mapping is contextual:

```text
T0 PETG Black -> IFS 1
T1 PLA White  -> IFS 3
T2 TPU        -> external/bypass (only when supported/selected)
```

The mapping editor belongs to pre-print / active-job detail, not as a permanent dominant panel.

## 9. Pre-print plan

Canonical workflow:

1. scan requirements through Z-Mod canonical scanner;
2. obtain Z-Mod canonical automatic assignment;
3. join with live physical state and rich metadata;
4. present ready/warning/blocker reasons;
5. permit manual draft correction when implemented;
6. immediately revalidate preview token, physical state, print state and permissions before mutation;
7. delegate accepted multi-material start to authoritative Z-Mod lifecycle.

Opening a pre-print plan is read-only.

## 10. Z-Mod compatibility

Z-Mod remains provider authority for:

- IFS protocol;
- scan/matching;
- ΔE behavior;
- auto insertion;
- in-print material change;
- `PRINT_ZCOLOR` lifecycle;
- equivalent-spool primitive where source-verified.

Plugins AD5X should expose semantic actions/states and never raw provider implementation details as the normal UX.

For equivalent/endless-spool behavior, the backend may expose a read-only candidate preview that mirrors the source-verified Z-Mod `ANALOG_PRUTOK` eligibility rule from provider-observed FFM metadata. This preview is advisory only: it must not use manual/Spoolman overlay metadata as provider truth, must keep `endless_spool=false`, and must not execute the provider transition until real-AD5X hardware acceptance enables that capability explicitly.

Recovery follows the same separation. The canonical module may publish a read-only recovery model containing provider evidence, source-verified primitives and provider-observed sequences. Current Z-Mod evidence includes `IFS_F15` driver reset, `IFS_F112` force-stop, `IFS_F18` unlock-all and `IFS_F39 PRUTOK=n` per-slot unlock; driver state 127 triggers provider reset/retry and timeout cleanup uses force-stop followed by unlock-all. This model is descriptive only until real-AD5X acceptance: capability `recovery.preview=true` does not imply `actions.recovery=true` or any executable endpoint. Diagnostic masks are evidence, not instructions.

## 11. OrcaSlicer projection

### 11.1 Transport prerequisite

OrcaSlicer integration requires the physical printer to use `Octo/Klipper` + `Moonraker` network agent. Other agents do not use the generic Moonraker `lane_data` path.

### 11.2 Projection shape

Plugins AD5X publishes four stable records in Moonraker namespace `lane_data`:

```json
{
  "lane1": {
    "lane": "0",
    "material": "PETG",
    "color": "#161616",
    "bed_temp": 75,
    "nozzle_temp": 240,
    "vendor": "Example",
    "vendor_name": "Example",
    "name": "PETG Black",
    "spool_name": "PETG Black",
    "spool_id": 42,
    "filament_id": null
  }
}
```

Rules:

- inner `lane` is zero-based string;
- outer keys remain `lane1..lane4`;
- empty physical lane publishes null material/color regardless of preserved stale metadata;
- representative primary color is used for rich multi-color filament;
- exact material identity remains canonical in Plugins AD5X;
- `material` is a conservative Orca wire value and may be omitted when unsafe to coerce;
- `filament_id` is omitted/null unless a real Orca-compatible exact ID is known;
- Spoolman filament ID is never mislabeled as Orca filament ID;
- shared namespace records/unknown fields are merged/preserved where practical;
- publication is event-driven, not high-rate polling.

### 11.3 Directionality

Current guaranteed direction:

```text
Plugins AD5X / IFS -> Moonraker lane_data -> OrcaSlicer
```

Orca generic Moonraker integration must not be assumed to write edited lane data back to Plugins AD5X.

The opposite product direction already has a different provider flow:

```text
Orca job/G-code -> zmod_preprocess / Z-Mod scan -> job requirements -> IFS pre-print plan
```

## 12. Spoolman adapter

Spoolman is optional and must degrade gracefully.

When enabled, the full-manager adapter provides:

- four persistent physical source↔Spoolman bindings;
- search/select from library;
- vendor/material/color/name/weight ingestion;
- remaining amount when trustworthy;
- native Moonraker single-active-spool consumption tracking driven by the real active IFS source;
- no second consumption daemon;
- no deletion of an external spool entity when a lane empties;
- distinct IDs for spool vs filament entities.

Physical `present=false` is stronger than cached identity. An occupied→empty transition removes the slot's current local binding and persists an identity-invalidated tombstone. An empty slot exposes no old `current spool`. Re-insertion cannot revive the previous exact Spoolman ID; without a verified identity source the slot is `unassigned` until a new bind/edit.

The existing lightweight standalone IFS/Spoolman bridge is retained as a separate product path for users who only want IFS↔Spoolman. Its v2 direction is the same four-slot + automatic active-spool semantic core. Full and standalone modes are mutually exclusive runtime owners.

## 13. Interoperability ownership

Compatibility formats are projections, not sources of canonical truth.

```text
canonical IFS model -> Orca lane_data
canonical IFS model -> future verified AFC/MMU projection
canonical IFS model -> native UI adapters
```

Foreign UIs should not force foreign naming/semantics into the core domain model.

## 14. Capability publication

The backend should publish at least:

- `architecture_version: 2.0`;
- UI expertise levels and canonical Expert policy;
- source topology and external/bypass support status;
- integrations: Z-Mod, manual store, Spoolman, Orca/lane_data, slicer, RFID;
- mapping capabilities;
- recovery/equivalent-spool capabilities;
- compatibility projection status;
- runtime permissions separately from installed capabilities.

## 15. Native UI requirement

First-party adapters use each host UI's native navigation/cards/dialogs/notifications. They consume the backend and do not contain IFS business logic.

A stable compatibility projection consumed by a UI's own native components is also a valid native integration strategy when the contract is source-verified and does not require faking unsupported AD5X semantics.

For Mainsail, the official Happy Hare `mmu` object is not a safe read-only projection: its presence enables native `MMU_*` mapping, selection, recovery and maintenance paths. Plugins AD5X must not emulate `mmu`/`mmu_machine`. Mainsail theme navigation provides external `href` links only, so native semantic parity requires a small adapter/fork consuming the normalized Plugins AD5X backend directly.

## 16. Resource policy

- no heavy background daemon;
- no high-rate idle polling;
- publish/recompute on meaningful events;
- no parallel IFS serial ownership;
- no second color matcher;
- no frontend-local safety policy;
- backend failure must not break normal Z-Mod printing.

## 17. Hardware gates

Still disabled until specific real-printer acceptance:

- editable/applicable tool mapping;
- production `PRINT_ZCOLOR` launch;
- automatic equivalent/endless-spool switching;
- new recovery mechanics;
- Z-Mod compatibility writes;
- automated external/bypass switching.

Documentation or CI does not replace hardware proof for those paths.

## 18. Completion definition

IFS Manager v2 is complete only when:

- stock Z-Mod IFS manager is no longer required for normal or Expert user workflows;
- all reliable provider capabilities are represented without fake telemetry;
- Expert is complete and Auto/Hybrid are coherent simplifications;
- Spoolman is a real optional library integration;
- OrcaSlicer material/color sync works through standard Moonraker `lane_data` with documented configuration;
- first-party native UIs converge on the same semantics;
- other Klipper/Moonraker clients can integrate through the normalized API or verified projections;
- every enabled mechanical/print mutation has real AD5X acceptance evidence.

## 19. Deployment and updateability

IFS Manager is part of the `ad5x_custom` Z-Mod plugin lifecycle, not a patch set against core repositories. Canonical source remains under `mod_data/plugins/ad5x_custom`; Klipper/Moonraker Python entry points are plugin-owned symlinks. No tracked Z-Mod/Klipper/Moonraker file may be changed merely to install IFS Manager.

`install.sh` activates, `update.sh` re-links/reconciles after Update Manager changes without self-restarting Moonraker, and `uninstall.sh` detaches runtime while retaining the plugin registration. Local `.git/info/exclude` hides only owned link paths. Foreign destinations fail closed. A destructive core reclone may remove links and requires explicit plugin repair/re-enable unless future Z-Mod behavior is source-proven otherwise.

