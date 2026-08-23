# Plugins AD5X — IFS / Materials Manager contract v2

Status: **canonical additive contract**
Work item: `IFS-MANAGER-001` / issue #15
Architecture: `2.0`
Wire/API compatibility baseline: `1.0`

This contract defines one frontend-neutral IFS / Materials Manager for AD5X + Z-Mod. It is intended for any Klipper/Moonraker UI or client. Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen are first-party native adapter targets, not separate backends.

See also:

- `docs/IFS_MANAGER_ARCHITECTURE_V2.md` — canonical target architecture;
- `docs/IFS_MANAGER_DISCOVERY_2026-08-22.md` — source/community evidence for the reset;
- `docs/ZMOD_IFS_MANAGER_PARITY_AUDIT_2026-08-17.md` — provider parity baseline.

## 1. Core rule: one backend, many presentations

All clients consume the same normalized state/actions/permissions.

```text
Z-Mod / Flashforge IFS
          |
          v
 Plugins AD5X backend
          |
          +--> normalized API/events --> any Klipper/Moonraker client
          +--> native adapters -------> Fluidd/Mainsail/Helix/Guppy/KS
          +--> interop projections ----> Orca lane_data / future verified contracts
```

Frontends MUST NOT implement their own:

- IFS serial/protocol behavior;
- safety policy;
- material/color matcher;
- print-start lifecycle;
- equivalent-spool mechanics;
- physical truth inference.

## 2. Provider ownership

Z-Mod remains authoritative for proven provider behavior:

- low-level IFS protocol and retry/timing logic;
- physical IFS runtime state;
- material/color scan and automatic matching;
- material filter + CIE LAB / ΔE76 color choice;
- current tool mapping / `file.json` semantics;
- in-print filament-change lifecycle;
- `PRINT_ZCOLOR` launch lifecycle;
- auto-insert behavior;
- equivalent-spool primitive such as `ANALOG_PRUTOK`, once its policy is fully source/hardware accepted.

Plugins AD5X translates provider mechanisms into stable semantic state/actions. It does not create a second hardware implementation.

## 3. Truth domains

These domains are independent unless the backend explicitly joins them:

1. **physical state** — whether filament is present in a physical IFS lane;
2. **active source** — runtime/provider-selected IFS lane or future external source;
3. **toolhead state** — whether filament is confirmed at the toolhead;
4. **spool/material identity** — rich user/library metadata;
5. **appearance** — solid/multicolor/finish representation;
6. **external identity** — Spoolman IDs, future RFID IDs, Orca exact IDs;
7. **operation/recovery state** — current semantic IFS action;
8. **job requirements** — tools/materials/colors requested by one file;
9. **job mapping** — `Tn -> physical source` for one print;
10. **compatibility projections** — lossy Z-Mod/Orca/etc. views;
11. **frontend selection** — local UI/session state only;
12. **diagnostics** — raw provider evidence, never an alternative truth model.

`raw_channel` is diagnostics only. `file.json` is job mapping, not occupancy and not spool metadata.

## 4. Source topology

### 4.1 Physical IFS

The canonical AD5X IFS topology has four fixed physical sources:

```text
ifs:1
ifs:2
ifs:3
ifs:4
```

They feed one selector and one extruder.

### 4.2 External / bypass

The architecture reserves a separate source:

```text
external:bypass
```

It MUST NOT be represented as fake `slot 5`. It has different telemetry and control semantics. Until provider/runtime behavior is directly verified, its `runtime_supported` and `control_supported` capabilities remain false.

## 5. Expert / Hybrid / Auto

`Expert` is the canonical capability surface.

`Hybrid` and `Auto` are progressive-disclosure presentation/automation policies over the same backend.

```text
interface_expertise:
  auto
  hybrid
  expert
```

Changing UI expertise MUST NOT:

- change physical truth;
- change installed capabilities;
- bypass backend permissions;
- create a different mapping/state engine.

Expert must eventually expose every meaningful reliable capability available from the supported AD5X/Z-Mod/IFS stack without forcing the user back to stock Z-Mod UI.

## 6. Module envelope

The existing additive `modules.ifs` envelope remains compatible with API schema `1.0`. Architecture-v2 fields are additive.

Representative shape:

```json
{
  "available": true,
  "state": "ready",
  "state_code": 5,
  "architecture_version": "2.0",
  "active_slot": 1,
  "runtime_active_slot": 1,
  "filament_at_toolhead": true,
  "print_state": "standby",
  "operation": {"state": "idle", "action": "", "slot": 0, "error": ""},
  "ui": {
    "expertise_levels": ["auto", "hybrid", "expert"],
    "canonical_expertise": "expert",
    "progressive_disclosure": true
  },
  "topology": {
    "kind": "selector_single_extruder",
    "ifs_slot_count": 4,
    "external_source": {"id": "external:bypass", "runtime_supported": false, "control_supported": false}
  },
  "job_preview": {},
  "preprint_plan": {},
  "capabilities": {},
  "metadata_store": {},
  "slots": [],
  "tool_mapping": [],
  "interoperability": {},
  "diagnostics": {}
}
```

No high-rate telemetry loop is introduced. Semantic changes use the existing snapshot invalidation/event model.

## 7. Slot contract

Each physical slot is independent. New identity fields are additive:

```json
{
  "slot": 3,
  "present": true,
  "stall": false,
  "active": false,
  "spool": {
    "source": "manual",
    "brand": "ERYONE",
    "series": "Silk",
    "name": "PLA Silk Triple",
    "material": "PLA",
    "variant": "",
    "spoolman_id": 42,
    "spoolman_spool_id": 42,
    "spoolman_filament_id": null,
    "orca_material": null,
    "orca_filament_id": null,
    "orca_setting_id": null,
    "remaining_g": 612.5,
    "nozzle_temp": null,
    "bed_temp": null
  },
  "appearance": {
    "color_mode": "tricolor",
    "colors": ["#F330F9", "#27C4F4", "#FFD43B"],
    "finish": "silk"
  },
  "metadata_status": "assigned",
  "permissions": {},
  "compatibility": {}
}
```

Legacy `spoolman_id` remains a migration alias and MUST NOT be confused with a Spoolman filament entity or Orca preset ID.

`metadata_status`:

- `assigned` — metadata exists and lane is physically occupied;
- `stale` — metadata exists but lane is physically empty;
- `none` — no useful metadata is known.

A frontend MUST visually prioritize physical emptiness over stale metadata.

## 8. Metadata store

The existing Plugins AD5X manual overlay remains independent of stock Flashforge/Z-Mod metadata files:

```text
/opt/config/mod_data/ad5x_custom/ifs_metadata.json
```

Store schema remains `1.0` until an explicit migration is implemented.

Authenticated endpoint remains:

```text
POST /server/plugins_ad5x/ifs/metadata
RPC  server.plugins_ad5x.ifs.metadata
```

Writes are non-mechanical. Store behavior remains atomic/fail-closed; corrupt/unsupported metadata is never silently replaced.

## 9. Appearance

Canonical modes:

- `solid`;
- `dual`;
- `tricolor`;
- `gradient`;
- `rainbow`;
- `special`.

Appearance and material identity remain separate. Compatibility projections may use only `colors[0]` as a representative color without destroying the full canonical appearance.

## 10. Z-Mod compatibility projection

Z-Mod currently exposes a narrower material + one RGB color model. Plugins AD5X therefore keeps a lossy compatibility projection.

Current provider values source-verified in `zmod_color` include:

```text
PLA, ABS, PETG, TPU, PLA-CF, PETG-CF, SILK
```

Normal projection:

```text
precise spool.material -> Z-Mod TYPE only when representable
appearance.colors[0]   -> Z-Mod primary HEX
rich identity/colors   -> Plugins AD5X only
```

Projection state remains explicit (`in_sync`, `diverged`, `unknown`, `unsupported`). Production projection writes remain disabled until hardware accepted and must use Z-Mod's normal mutation path rather than editing Flashforge JSON directly.

## 11. Job scan and automatic mapping

Z-Mod remains the canonical matcher. Plugins AD5X delegates to the Z-Mod scanner/matcher and MUST NOT invent a second matcher or fake per-tool ΔE values that provider APIs do not expose.

### Parser-safe preview command

The hardware-accepted parser-safe bridge command is:

```text
ADIFS_JOB_PREVIEW FILENAME="relative/path.gcode"
```

**Do not use `AD5X_IFS_JOB_PREVIEW`**: real Klipper command parsing treats the digit as a boundary and produces `Unknown command: AD5`.

Moonraker endpoint:

```text
POST /server/plugins_ad5x/ifs/job/preview
RPC  server.plugins_ad5x.ifs.job.preview
```

Opening preview remains read-only.

## 12. Pre-print plan and mapping UX

Mapping is job-scoped. Main IFS dashboard is physical topology first.

Target pre-print representation:

```text
T0 PETG Black -> IFS 1 PETG Black
T1 PLA White  -> IFS 3 PLA White
T2 TPU        -> -- warning / external when explicitly supported
```

Auto hides healthy mappings. Hybrid exposes a compact summary and `Изменить`. Expert exposes full mapping/mismatch details.

Current write state remains conservative:

- preview: enabled;
- manual draft: enabled through the read-only `/server/plugins_ad5x/ifs/job/mapping/draft` contract and bound to the exact provider preview token;
- manual apply: disabled until hardware acceptance;
- production `PRINT_ZCOLOR` launch: disabled until hardware acceptance;
- preview tokens must include all mutable dependencies and be revalidated immediately before any future start.

## 13. OrcaSlicer interoperability

### 13.1 Required Orca connection mode

For printer → Orca filament synchronization, the physical printer in OrcaSlicer must use:

```text
Host type:     Octo/Klipper
Network agent: Moonraker
```

With another network agent the generic Moonraker `lane_data` integration is not used.

Initial compatibility target: **OrcaSlicer 2.4.2**.

### 13.2 Standard read surface

Orca reads:

```text
/server/database/item?namespace=lane_data
```

Plugins AD5X publishes four stable physical records with outer keys `lane1..lane4` and inner zero-based string lanes `"0".."3"`.

Rules:

- physically empty lanes publish null material/color even when stale metadata is retained internally;
- rich multicolor appearance projects to one representative/primary color;
- exact material identity is separate from conservative Orca `material`;
- specialty material is not guessed into a generic preset unless an explicit compatibility mapping exists;
- `filament_id` is omitted/null unless a real Orca-compatible exact identifier exists;
- Spoolman filament ID MUST NOT be mislabeled as Orca filament ID;
- unknown foreign fields in owned records are preserved where practical;
- duplicate foreign records for the same inner lane block publication rather than creating ambiguous Orca state;
- publication is event-driven and does not add an idle polling daemon.

Current guaranteed direction is **printer → Orca**. Generic Orca Moonraker integration is not assumed to write edits back.

Diagnostic URL:

```text
http://<printer>:7125/server/database/item?namespace=lane_data
```

## 14. Spoolman

Spoolman is an optional library/inventory provider, not physical truth.

Implemented full-manager capability includes search/select, four physical source↔spool bindings, distinct spool/filament IDs, metadata/remaining amount and native Moonraker active-spool consumption synchronization. Spoolman remains optional.

Physical presence is authoritative: `present=false` MUST NOT expose the previous concrete spool as currently installed. On a confirmed occupied→empty transition the local current binding is removed and a persistent identity-invalidated tombstone is recorded; the external Spoolman entity is not deleted. A later insertion MUST NOT resurrect that old Spoolman ID. Until explicit bind/edit (or a future verified identity provider) exact identity is `unassigned`; provider-observed material/color is not proof of concrete spool identity.

The lightweight standalone IFS/Spoolman bridge remains a valid separate product path, but it and the full IFS backend MUST NOT be simultaneous runtime owners. The target standalone v2 shares the four-slot/active-spool semantics rather than maintaining a competing consumption tracker.

## 15. Equivalent / endless spool

Z-Mod already exposes provider primitives for analogous/equivalent filament. Plugins AD5X normalizes them into understandable policy/Expert UI rather than inventing a second engine.

Automatic fallback remains disabled until exact provider policy and real hardware transition/recovery are accepted.

## 16. Capabilities vs permissions

Capabilities mean the installed system implements a feature. Permissions mean an action is allowed **right now**.

The backend remains the only authority for runtime permissions. Existing mechanical baseline stays fail-closed:

- printing/paused/unknown print state → ordinary IFS mechanical writes blocked;
- non-ready IFS → writes blocked;
- another IFS operation → writes blocked;
- empty lane → select/load blocked;
- unload → only active source with confirmed toolhead filament.

Metadata/library edits are non-mechanical and may have a different permission policy.

## 17. Recovery / diagnostics

Expert mode may expose provider-backed state such as active slot/source, head switch, IFS motion sensor, stall/insert/retry state, operation/error, matcher messages, compatibility status and bounded raw evidence.

Raw `IFS_Fxx` commands are not normal user actions. They may support source-verified semantic recovery workflows.

No fake Happy-Hare encoder/hub/clog/compression telemetry is permitted when AD5X does not provide it.

## 18. Frontend portability

First-party native adapter targets remain Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen.

The contract is intentionally broader: any Klipper/Moonraker UI may consume the normalized API/events or a source-verified interoperability projection. A compatibility object rendered by a host UI's own native component is acceptable native presentation when semantics are accurate.

## 19. Resource / failure policy

- no parallel IFS serial access;
- no high-rate idle polling for cosmetic UI;
- no heavy daemon for the manager;
- backend/projection failure must not prevent normal Z-Mod printing;
- corrupt metadata must not erase itself automatically;
- no direct independent write to stock Flashforge metadata for compatibility sync;
- no second color matcher;
- UI consumes backend permissions;
- CI does not replace real-printer acceptance for mechanical/print mutations.

## 20. Hardware-gated features

Remain disabled until separately source-verified and accepted on a real AD5X:

- applying editable pre-print mapping;
- production `PRINT_ZCOLOR` start;
- automatic endless/equivalent-spool transition;
- new jam/recovery mechanics;
- Z-Mod material/color projection writes;
- automated external/bypass switching.

## 21. Completion definition

IFS / Materials Manager is complete only when stock Z-Mod IFS UI is not required for normal or Expert workflows; every reliable provider capability is represented without fake telemetry; Expert is complete and Auto/Hybrid are coherent simplifications; full optional Spoolman works; Orca material/color sync works through standard Moonraker `lane_data`; first-party native UIs share one semantic model; other Klipper clients can integrate; and every enabled mechanical/print mutation has real AD5X evidence.

## 22. Plugin lifecycle / updateability contract

The manager MUST be installable without tracked modifications to Z-Mod, Klipper or Moonraker repositories. Runtime Python integration uses plugin-owned links from the installed `ad5x_custom` checkout and the Z-Mod `install.sh` / `update.sh` / `uninstall.sh` lifecycle. Unknown destination files are never overwritten. `DISABLE_PLUGIN` detaches runtime without deleting the plugin's Update Manager registration; full unregister is a separate explicit operation.

The Update Manager hook MUST NOT self-restart Moonraker. Python changes requiring a new host process are reported as restart-required. Destructive core recovery may require explicit plugin re-enable/repair; no automatic recovery claim is made without source/hardware evidence.
