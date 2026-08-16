# Plugins AD5X — IFS Manager v1 contract

Status: **experimental / additive v1 draft**  
Work item: `IFS-MANAGER-001` / issue #15

This document defines the frontend-neutral IFS Manager boundary. It is not a
KlipperScreen-specific DTO and must be suitable for Fluidd, Mainsail, HelixScreen
and GuppyScreen adapters as well.

Current repository backend version: `0.1.6`. API schema stays additive `1.0`.

## 1. Truth domains

The following domains are deliberately separate and MUST NOT be inferred from
one another:

1. **physical state** — whether filament is physically present in an IFS lane;
2. **active slot** — the operational slot used by Z-Mod/Flashforge;
3. **tool mapping** — current slicer/tool to physical IFS slot mapping;
4. **job requirements** — tools/materials/colors required by one G-code file;
5. **spool metadata** — what material/spool is assigned to the slot;
6. **appearance** — visual properties of the filament;
7. **operation state** — current IFS action/recovery state;
8. **frontend selection** — which card the user selected in a UI session;
9. **Z-Mod compatibility projection** — the lossy material/primary-color view
   representable by Z-Mod.

`raw_channel` is diagnostic evidence only and is never an alternative source of
truth for `active_slot`.

`file.json` is current **tool mapping**, not occupancy and not spool metadata.

## 2. Authority and source precedence

The current authority model is:

```text
physical IFS state ----------- Z-Mod / IFS runtime
active slot ------------------ Z-Mod / FFMInfo.channel
current print tool mapping --- Z-Mod / file.json
job scan and auto-matching --- live Z-Mod zmod_color implementation
legacy material+primary color- Z-Mod / Flashforge compatibility state
rich spool metadata ---------- Plugins AD5X manual/Spoolman/etc. overlay
frontend selected card ------- frontend session only
```

Plugins AD5X MUST NOT maintain a competing slicer-color matcher when the live
Z-Mod implementation can provide the canonical result.

## 3. Compatibility

IFS Manager v1 is additive to the existing `modules.ifs` snapshot.

During migration the backend retains legacy flat fields such as:

```json
{
  "material": "PLA",
  "color": "#F330F9"
}
```

New frontends should prefer normalized `spool`, `appearance`, `capabilities`,
`permissions`, `compatibility` and `job_preview` fields when present. Old
frontends may continue using legacy flat fields.

Absence of a new field means **unsupported/unknown**, not `false` unless the
contract explicitly defines a boolean default.

## 4. Module envelope

Representative shape:

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
  "job_preview": {
    "available": false,
    "source": "zmod",
    "filename": "",
    "requirements": [],
    "assignments": [],
    "auto_assign": {},
    "messages": [],
    "error": "not_scanned"
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

## 5. Slot contract

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
  },

  "compatibility": {
    "zmod": {
      "write_ready": true,
      "sync_state": "diverged",
      "desired": {"material": "PLA", "color": "#F330F9"},
      "current": {"material": "PLA", "color": "#161616"},
      "lossy": true,
      "omitted_fields": ["appearance.colors[1:]", "appearance.finish"],
      "write_blockers": []
    }
  }
}
```

### `metadata_status`

- `assigned` — metadata exists and the lane is physically occupied;
- `stale` — metadata exists but the lane is physically empty;
- `none` — no useful metadata is known.

A frontend MUST visually prioritize physical emptiness over stale metadata. A
physically empty slot that still contains old `TPU / #161616` metadata must
render as **empty**, not as an installed black TPU spool.

## 6. Spool metadata

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

Plugins AD5X provides a manual metadata overlay without directly modifying stock
Flashforge/Z-Mod metadata files.

Runtime path:

```text
/opt/config/mod_data/ad5x_custom/ifs_metadata.json
```

The store is versioned with `schema_version: "1.0"` and contains per-slot
`spool` + `appearance` records. Manual metadata overrides effective rich
presentation for that slot, while physical presence, active slot and tool mapping
remain independent truth domains.

Authenticated write endpoint:

```text
POST /server/plugins_ad5x/ifs/metadata
RPC  server.plugins_ad5x.ifs.metadata
```

Supported operations:

- update one slot with normalized `spool` and `appearance` objects;
- `clear=true` to remove the manual overlay for one slot and return to the
  Flashforge/Z-Mod fallback.

The store is written atomically (temporary file + fsync + replace). A corrupt or
unsupported store is reported as `metadata_store.status = "invalid"`; physical
IFS state remains available, but metadata writes fail closed rather than
silently overwriting the damaged file.

Metadata editing is non-mechanical and emits no filament-operation G-code.

Hardware evidence has already proved on a real AD5X that metadata save and clear
complete successfully and clear restores Flashforge/Z-Mod fallback.

## 7. Appearance

Appearance is independent from material type.

### Color mode

Supported schema values:

- `solid`;
- `dual`;
- `tricolor`;
- `gradient`;
- `rainbow`;
- `special`.

`colors` is an ordered array of canonical `#RRGGBB` values. Frontends should
render these visually instead of using hexadecimal text as the primary UI.

### Finish

Supported values:

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

Finish is a semantic appearance field. It MUST NOT silently change material
identity. In particular `material=PLA + finish=silk` does not become Z-Mod
`TYPE=SILK`; `TYPE=SILK` is used only when the rich material itself is explicitly
`SILK`.

### Legacy Flashforge normalization

Current Flashforge metadata provides one `ffmColorN` value. It normalizes to:

```json
{
  "color_mode": "solid",
  "colors": ["#161616"],
  "finish": "standard"
}
```

## 8. Z-Mod compatibility projection

Z-Mod currently represents a lane with a narrower model: one material type and
one RGB color. Plugins AD5X rich metadata is therefore projected lossily.

Source-verified Z-Mod material values currently accepted by `zmod_color` are:

```text
PLA, ABS, PETG, TPU, PLA-CF, PETG-CF, SILK
```

`?` exists internally in Z-Mod but is not a target rich-material identity for
Plugins AD5X projection.

Projection policy:

```text
rich spool.material   -> Z-Mod TYPE, only when representable
appearance.colors[0]  -> Z-Mod HEX primary color
brand                 -> Plugins AD5X only
series                -> Plugins AD5X only
name                  -> Plugins AD5X only
additional colors     -> Plugins AD5X only
finish                -> Plugins AD5X only
Spoolman/RFID fields  -> Plugins AD5X only
```

`PLA+`, vendor-specific compound names or a missing primary color fail closed
instead of being silently coerced to a different Z-Mod material/color.

Current read-only projection states:

- `in_sync` — desired material/primary color equal current Z-Mod compatibility
  state;
- `diverged` — both are known but differ;
- `unknown` — desired projection is valid but no current Z-Mod comparison is
  available;
- `unsupported` — rich data cannot currently be represented by Z-Mod.

`pending_projection` and `error` are reserved for the future write lifecycle.

Current capability is **preview only**. Projection writes remain disabled. When
enabled later, Plugins AD5X must invoke Z-Mod's existing `CHANGE_ZCOLOR` mutation
path instead of writing `Adventurer5M.json` directly.

## 9. Slicer/job requirements and Z-Mod delegated preview

Z-Mod remains the authority for current file scan and auto-assignment semantics.
Plugins AD5X does not implement a second color matcher.

Source-verified Z-Mod implementation uses:

- `zmod_color.get_used_colors(gcmd)` for G-code requirements;
- `save_variables.scan_file_colors` as the scan policy;
- `zmod_color.get_auto_tool_assignments(...)` as the canonical auto-matcher;
- `save_variables.auto_assign_colors` as Z-Mod's normal automatic-assignment
  policy;
- the public `SET_ZCOLOR ... AUTO_ASSIGN=...` flow for the normal Z-Mod UI.

There are no standalone upstream G-code commands literally named
`SCAN_FILE_COLORS` or `AUTO_ASSIGN_COLORS` in the inspected `zmod_color.py`.

### File requirements

Z-Mod can derive `(tool, color, material)` requirements from:

- actual `T<n>` tool use;
- `; filament_colour = ...`;
- `; filament_type = ...`;
- optional prepared `; zmod_color_data = ...`.

Unknown/missing file metadata remains unknown; Plugins AD5X must not substitute
current spool metadata and pretend the file requested it.

### Matching semantics

The canonical Z-Mod matcher:

1. filters available candidates by material equality when file material exists;
2. records material failure and falls back when no material-compatible candidate
   exists;
3. records color failure when file color is absent;
4. converts RGB to CIE LAB and chooses minimum ΔE76 when color exists;
5. marks ΔE76 `>= 15.0` as a weak match;
6. detects duplicate slot assignment across tools.

Current Z-Mod result flags:

```text
AUTO_ASSIGN_ANY_SUCCESS      = 1 << 0
AUTO_ASSIGN_MATERIAL_FAILURE = 1 << 1
AUTO_ASSIGN_COLOR_FAILURE    = 1 << 2
AUTO_ASSIGN_COLOR_WEAK       = 1 << 3
AUTO_ASSIGN_DUPLICATE        = 1 << 4
```

Plugins AD5X MUST NOT invent a per-tool ΔE score because current Z-Mod returns the
aggregate flags/messages, not a normalized per-tool distance.

### Read-only preview adapter

The Klipper bridge provides:

```text
AD5X_IFS_JOB_PREVIEW FILENAME="relative/path.gcode"
```

and the authenticated Moonraker API provides:

```text
POST /server/plugins_ad5x/ifs/job/preview
RPC  server.plugins_ad5x.ifs.job.preview
```

The bridge delegates scan and assignment to the live `zmod_color` object and
publishes a normalized `job_preview`. It temporarily supplies/restores
`zmod_color.file_colors` and does not persist the mapping.

Representative result:

```json
{
  "available": true,
  "source": "zmod",
  "filename": "example.gcode",
  "requirements": [
    {"tool": 0, "color": "#F330F9", "material": "PLA"}
  ],
  "assignments": [
    {"tool": 0, "slot": 3}
  ],
  "auto_assign": {
    "flags": 1,
    "any_success": true,
    "material_failure": false,
    "color_failure": false,
    "weak_color": false,
    "duplicate_slot": false
  },
  "messages": [],
  "error": ""
}
```

The backend rejects unsafe filenames, active IFS operations and preview requests
while printing/paused/unknown print states.

The preview does **not**:

- write `file.json`;
- call `PRINT_ZCOLOR`;
- call `CHANGE_ZCOLOR`;
- start `SDCARD_PRINT_FILE`;
- change the active IFS slot;
- mutate persisted Z-Mod auto-assignment settings.

## 10. Tool mapping and pre-print plan

When Z-Mod starts an IFS print it writes the resolved tool list to:

```text
/usr/data/config/mod_data/file.json
```

`_CHANGE_FILAMENT` later reads that mapping and resolves slicer tool/channel to a
physical spool number.

The current Plugins AD5X capability is **read-only pre-print preview**. Applying
preview mapping and starting a print remain disabled until a separate write
contract and real-printer acceptance gate exist.

Target frontend-neutral pre-print UI:

```text
T0  PLA  [file color] -> Slot 3
T1  PETG [file color] -> Slot 1
T2  PLA  [file color] -> —  warning
```

The UI may eventually offer auto-match, manual remapping and start-print actions,
but those are distinct controlled mutations, not side effects of opening the
preview.

## 11. Capabilities vs runtime permissions

Capabilities answer whether the installed backend/hardware/software combination
implements a feature at all. Permissions answer whether a concrete mutation is
allowed **right now**.

Current important capability state:

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
    "manage": true,
    "preview_job": true
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
    "slicer": true,
    "rfid": false
  },
  "mapping": {
    "tool_to_slot": true,
    "preprint_preview": true,
    "apply_preprint_mapping": false,
    "endless_spool": false
  },
  "compatibility": {
    "zmod_projection_preview": true,
    "zmod_projection_write": false
  }
}
```

`slicer=true` currently means **source-delegated read-only slicer/job preview**;
it does not claim mapping application or print-start ownership.

Current filament-operation fail-closed baseline:

- `printing` → writes blocked;
- `paused` → writes blocked;
- unknown/non-terminal print state → writes blocked;
- non-ready IFS → writes blocked;
- another IFS operation running → writes blocked;
- physically empty slot → select/load blocked;
- unload → only active slot with confirmed filament at toolhead.

Frontends MUST consume backend permissions and must not independently recreate
these hardware safety rules.

## 12. Mechanical action scope

Implemented action namespace currently includes:

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
- pre-print mapping application / print start;
- Z-Mod compatibility projection write.

A frontend must not present unsupported operations as ordinary working buttons.

## 13. Reference frontend UX

KlipperScreen is the first reference consumer; it is not the owner of IFS
business/safety logic.

Current hardware-proven technical prototype provides:

- four **horizontal** lane/spool cards;
- physical empty/present state at a glance;
- distinct active and frontend-selected states;
- visual segmented swatches for mono/multi-color metadata;
- finish/color-mode labels;
- one contextual action bar for the selected slot;
- action sensitivity from backend `slot.permissions`;
- a hardware-path row;
- diagnostics and tool mapping in a Details/Advanced view;
- direct `Катушка` entry into the selected-slot metadata editor;
- a local rich metadata editor using the manual store endpoint;
- no HEX-first main UI.

This UI is explicitly accepted as a **technical prototype**, not final competitor-
class UX. The final design still needs custom touch-first controls, richer spool
visualization, job-plan/mapping presentation and removal of desktop-GTK artifacts.

Frontend selection is local/session UI state and MUST NOT be stored as hardware
`active_slot`.

## 14. Frontend portability

All frontends consume the same normalized state/actions:

- KlipperScreen — reference local UI;
- Fluidd — primary web UI target;
- Mainsail;
- HelixScreen;
- GuppyScreen.

Z-Mod internals, raw IFS protocol state, Flashforge parsing, slicer matching,
safety rules and macro selection stay in Plugins AD5X/backend layers, not in
frontend adapters.

## 15. Resource and failure policy

- no parallel access to the IFS serial device;
- no steady-state high-frequency polling for cosmetic UI;
- no separate heavy daemon for this contract;
- backend failure must not prevent normal Z-Mod printing;
- corrupt/unsupported manual metadata must not erase itself automatically;
- no direct independent write to `Adventurer5M.json` for compatibility sync;
- no second color-matching algorithm competing with Z-Mod;
- CI proof does not replace real-printer acceptance for new mutation paths or
  final local-screen UX.

See also `docs/ZMOD_IFS_JOB_MAPPING_DISCOVERY_2026-08-17.md` for the source-level
Z-Mod discovery supporting the job/mapping and compatibility boundaries.
