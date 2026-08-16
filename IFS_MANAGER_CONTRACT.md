# Plugins AD5X — IFS Manager v1 contract

Status: **experimental / additive v1 draft**  
Work item: `IFS-MANAGER-001` / issue #15

This document defines the frontend-neutral IFS Manager boundary. It is not a
KlipperScreen-specific DTO and must be suitable for Fluidd, Mainsail, HelixScreen
and GuppyScreen adapters as well.

## 1. Truth domains

The following domains are deliberately separate and MUST NOT be inferred from
one another:

1. **physical state** — whether filament is physically present in an IFS lane;
2. **active slot** — the operational slot used by Z-Mod/Flashforge;
3. **tool mapping** — slicer/tool to physical IFS slot mapping;
4. **spool metadata** — what material/spool is assigned to the slot;
5. **appearance** — visual properties of the filament;
6. **operation state** — current IFS action/recovery state;
7. **frontend selection** — which card the user selected in a UI session.

`raw_channel` is diagnostic evidence only and is never an alternative source of
truth for `active_slot`.

## 2. Compatibility

IFS Manager v1 is additive to the existing `modules.ifs` snapshot.

During migration the backend retains legacy flat fields such as:

```json
{
  "material": "PLA",
  "color": "#F330F9"
}
```

New frontends should prefer normalized `spool`, `appearance`, `capabilities` and
`permissions` fields when present. Old frontends may continue using the flat
fields.

Absence of a new field means **unsupported/unknown**, not `false` unless the
contract explicitly defines a boolean default.

## 3. Module envelope

Target shape:

```json
{
  "available": true,
  "state": "ready",
  "state_code": 5,
  "active_slot": 1,
  "runtime_active_slot": 1,
  "filament_at_toolhead": true,
  "print_state": "standby",
  "operation": {
    "state": "idle",
    "action": "",
    "slot": 0,
    "error": ""
  },
  "capabilities": {},
  "metadata_store": {
    "status": "ok",
    "schema_version": "1.0",
    "error": ""
  },
  "slots": [],
  "tool_mapping": [1, 1, 1, 4],
  "diagnostics": {}
}
```

High-rate telemetry is not introduced by this contract. Semantic changes use the
existing `notify_plugins_ad5x_snapshot_changed` invalidation model.

## 4. Slot contract

Each physical IFS slot is represented independently:

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
    "remaining_g": 612.5
  },

  "appearance": {
    "color_mode": "tricolor",
    "colors": ["#F330F9", "#27C4F4", "#FFD43B"],
    "finish": "silk"
  },

  "metadata_status": "assigned",

  "permissions": {
    "select_slot": true,
    "load_slot": true,
    "unload_slot": false,
    "blocked_reason": ""
  }
}
```

### `metadata_status`

- `assigned` — metadata exists and the lane is physically occupied;
- `stale` — metadata exists but the lane is physically empty;
- `none` — no useful metadata is known.

A frontend MUST visually prioritize physical emptiness over stale metadata. For
example, a physically empty slot that still contains old `TPU / #161616` metadata
must render as **empty**, not as an installed black TPU spool.

## 5. Spool metadata

The v1 schema reserves these normalized fields:

- `source`;
- `brand`;
- `series`;
- `name`;
- `material`;
- `variant`;
- `spoolman_id`;
- `remaining_g`.

Allowed source identifiers:

- `flashforge`;
- `manual`;
- `spoolman`;
- `slicer`;
- `rfid`;
- `unknown`.

A source identifier describes where metadata came from. It does **not** imply
that the corresponding integration is currently available.

### Persistent manual metadata

Plugins AD5X provides a manual metadata overlay without modifying the stock
Flashforge/Z-Mod metadata files.

Runtime path:

```text
/opt/config/mod_data/ad5x_custom/ifs_metadata.json
```

The store is versioned with `schema_version: "1.0"` and contains per-slot
`spool` + `appearance` records. Manual metadata overrides the effective metadata
presentation for that slot, while physical presence, active slot and tool mapping
remain independent truth domains.

The authenticated Moonraker write endpoint is:

```text
POST /server/plugins_ad5x/ifs/metadata
RPC  server.plugins_ad5x.ifs.metadata
```

Supported v1 operations:

- update one slot with normalized `spool` and `appearance` objects;
- `clear=true` to remove the manual overlay for one slot and return to the
  Flashforge/Z-Mod fallback.

The store is written atomically (temporary file + fsync + replace). A corrupt or
unsupported store is reported as `metadata_store.status = "invalid"`; normal
physical/mechanical IFS state remains available, but metadata writes fail closed
rather than overwriting the damaged file.

Metadata editing is non-mechanical: it does not emit G-code and therefore is not
coupled to the mechanical filament-operation write gate. Mechanical actions still
use their own fail-closed permissions.

## 6. Appearance

Appearance is independent from material type.

### Color mode

Supported schema values:

- `solid`;
- `dual`;
- `tricolor`;
- `gradient`;
- `rainbow`;
- `special`.

`colors` is an ordered array of canonical `#RRGGBB` values. A frontend should
render these visually (solid fill, sectors, split swatch or gradient) instead of
using hexadecimal text as the primary UI.

### Finish

Supported schema values:

- `standard`;
- `matte`;
- `silk`;
- `satin`;
- `metallic`;
- `transparent`;
- `translucent`;
- `glitter`;
- `glow`;
- `wood`;
- `carbon_fiber`;
- `other`.

Finish is a semantic label. Frontends may add a subtle visual treatment, but
must not rely on shader/visual effects as the only indication of finish.

### Legacy Flashforge normalization

Current Flashforge metadata provides one `ffmColorN` value. It normalizes to:

```json
{
  "color_mode": "solid",
  "colors": ["#161616"],
  "finish": "standard"
}
```

No upstream Flashforge/Z-Mod file format is changed by this normalization.

## 7. Capabilities vs permissions

These concepts are different.

### Capabilities

Capabilities answer: **can this backend/hardware/software combination implement
this feature at all?**

Current v1 shape:

```json
{
  "schema_version": "1.0",
  "slot_count": 4,
  "actions": {
    "select_slot": true,
    "load_slot": true,
    "unload_slot": true,
    "eject_slot": false,
    "recovery": false,
    "manage": true
  },
  "metadata_schema": {
    "spool_fields": true,
    "multi_color": true,
    "finish": true
  },
  "integrations": {
    "flashforge": true,
    "manual_store": true,
    "spoolman": false,
    "slicer": false,
    "rfid": false
  },
  "mapping": {
    "tool_to_slot": true,
    "endless_spool": false
  }
}
```

Capabilities MUST NOT claim an integration merely because the schema has a field
for that integration. In particular, `spoolman_id` being representable does not
mean per-slot Spoolman enrichment is implemented yet.

### Runtime permissions

Permissions answer: **is this action allowed right now for this specific slot?**

They are computed by the backend and consumed by frontends. Frontends must not
re-implement the hardware safety rules independently.

Current fail-closed baseline:

- `printing` → filament writes blocked;
- `paused` → filament writes blocked;
- unknown/non-terminal print state → filament writes blocked;
- non-ready IFS → writes blocked;
- another IFS operation running → writes blocked;
- physically empty slot → select/load blocked;
- unload → only active slot with confirmed filament at toolhead.

## 8. Mechanical action scope

Hardware-proven/implemented action namespace currently includes:

- `select_slot`;
- `load_slot`;
- `unload_slot` for the active toolhead filament.

The following remain separate future flows until their Z-Mod/hardware semantics
are proven:

- cold eject of an inactive lane;
- cutter/eject actions;
- jam recovery;
- automatic retry;
- endless spool / automatic refill;
- pre-print material remapping.

A frontend must not present unsupported operations as ordinary buttons.

## 9. Reference frontend UX

KlipperScreen is the first reference consumer of the Manager contract; it is not
the owner of IFS business or safety logic.

The current reference implementation provides:

- four 2×2 lane/spool cards;
- physical empty/present state at a glance;
- distinct active and frontend-selected states;
- visual segmented swatches for mono/multi-color metadata;
- finish/color-mode labels such as Silk/Matte / 2 colors / 3 colors;
- one contextual action bar for the selected slot;
- action sensitivity taken only from backend `slot.permissions`;
- diagnostics and tool mapping in a Details/Advanced view;
- a local spool metadata editor using the manual store endpoint;
- no HEX-first main UI.

Frontend selection is local/session UI state and MUST NOT be stored as hardware
`active_slot`.

The reference UI may continue to evolve visually, but it must not regain backend
safety logic, Z-Mod parsing or macro selection.

## 10. Frontend portability

All frontends consume the same normalized state/actions:

- KlipperScreen — reference local UI;
- Fluidd — primary web UI;
- Mainsail;
- HelixScreen;
- GuppyScreen.

Z-Mod internals, raw IFS protocol state, Flashforge JSON parsing, safety rules and
macro selection stay in Plugins_AD5X/backend layers, not in frontend adapters.

## 11. Resource and failure policy

- no parallel access to the IFS serial device;
- no steady-state high-frequency polling for cosmetic UI;
- no separate heavy daemon for this contract;
- backend failure must not prevent normal Z-Mod printing;
- corrupt/unsupported manual metadata must not erase itself automatically;
- CI proof does not replace real-printer acceptance for mechanical operations or
  final local-screen UX.
