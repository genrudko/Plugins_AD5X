# Z-Mod IFS color/job mapping discovery — 2026-08-17

Status: source-verified discovery for `IFS-MANAGER-001` / issue #15.

Upstream source of truth inspected for this note:

- repository: `ghzserg/z_ad5x`;
- branch: `1.7`;
- file: `.shell/zmod_color.py`;
- blob SHA: `158338c4f8f6c937e3b1ae6f9ca34261983cc425`.

The purpose of this note is to define the integration boundary. Plugins AD5X must reuse Z-Mod's existing slicer/job semantics instead of maintaining a second color-assignment algorithm.

## 1. Important terminology correction

The current Z-Mod implementation does **not** expose standalone G-code commands named `SCAN_FILE_COLORS` or `AUTO_ASSIGN_COLORS` in `zmod_color.py`.

The source-verified flow is:

- file scanning is performed by `zmod_color.get_used_colors(gcmd)`;
- scanning behavior is controlled by `save_variables.scan_file_colors`;
- automatic assignment is performed by `zmod_color.get_auto_tool_assignments(...)`;
- the default automatic-assignment policy is controlled by `save_variables.auto_assign_colors`;
- the public user flow is driven by `SET_ZCOLOR ...`, including `AUTO_ASSIGN=<value>`.

Plugins AD5X documentation/UI must use this terminology and must not invent a second public Z-Mod command namespace.

## 2. Source-verified file requirements

`get_used_colors(gcmd)` returns tuples:

```text
(tool_id, color, material)
```

For a G-code filename it can derive requirements from:

- actually encountered `T<n>` tool commands;
- `; filament_colour = ...`;
- `; filament_type = ...`;
- optional prepared `; zmod_color_data = ...`.

`save_variables.scan_file_colors` controls whether/how the scan is performed. When scanning is disabled the method returns the allowed tool indexes with empty color/material requirements rather than pretending metadata exists.

This means Plugins AD5X should model **unknown requirement data explicitly** instead of substituting slot metadata or guessing from the current active spool.

## 3. Source-verified automatic assignment

Z-Mod's `get_auto_tool_assignments(...)` is the canonical matching algorithm for the current AD5X stack.

The algorithm:

1. considers only physically available slot records supplied by Z-Mod;
2. if a file material is present, first filters candidates by case-insensitive material equality;
3. if no material candidate exists, records a material failure and falls back to the available slots for color matching;
4. if file color is absent, records a color failure and can still choose the first material-compatible candidate;
5. when color exists, converts file and slot RGB to CIE LAB and compares them with ΔE76;
6. picks the candidate with the smallest ΔE76;
7. marks color matches with ΔE76 `>= 15.0` as weak;
8. detects when multiple tools map to the same slot.

Current bit flags in Z-Mod:

```text
AUTO_ASSIGN_ANY_SUCCESS      = 1 << 0
AUTO_ASSIGN_MATERIAL_FAILURE = 1 << 1
AUTO_ASSIGN_COLOR_FAILURE    = 1 << 2
AUTO_ASSIGN_COLOR_WEAK       = 1 << 3
AUTO_ASSIGN_DUPLICATE        = 1 << 4
```

Plugins AD5X must not reimplement the LAB/ΔE matching independently in every frontend. A thin adapter should delegate preview/matching to the live `zmod_color` object and normalize the result.

## 4. Mapping is a separate truth domain

When Z-Mod starts an IFS print in the non-native-display path, `cmd_PRINT_ZCOLOR` writes the resolved `tools` list to:

```text
/usr/data/config/mod_data/file.json
```

`_CHANGE_FILAMENT` later reads this file and maps a slicer tool/channel to the corresponding physical spool number.

Therefore:

- `file.json` is **job/tool mapping**, not slot occupancy;
- it must not be used to infer whether filament is physically present;
- Plugins AD5X should expose job requirements and proposed/current mapping separately from physical IFS state.

## 5. Z-Mod compatibility projection for rich metadata

Z-Mod's current slot model is intentionally narrower than Plugins AD5X's rich spool model. Z-Mod writes/reads:

```text
FFMInfo.ffmTypeN
FFMInfo.ffmColorN
```

and supports changing them through the existing `CHANGE_ZCOLOR SLOT=<n> TYPE=<...> HEX=<RRGGBB>` flow. In the Z-Mod non-native-display path that command ultimately calls `set_printer_data_detail(...)`; in display mode it uses the stock printer control API.

Plugins AD5X therefore must not write `Adventurer5M.json` directly as an independent implementation. The compatibility projection should call the Z-Mod-owned mutation path.

Projection policy for a rich Plugins AD5X spool:

```text
rich material       -> Z-Mod TYPE
primary colors[0]   -> Z-Mod HEX
brand               -> Plugins AD5X only
series              -> Plugins AD5X only
name                -> Plugins AD5X only
additional colors   -> Plugins AD5X only
finish              -> Plugins AD5X only
Spoolman/RFID data  -> Plugins AD5X only
```

The projection is intentionally lossy and must be reported as such when rich metadata contains information Z-Mod cannot represent.

## 6. Source precedence / synchronization target

Target model:

```text
physical IFS state ----------- Z-Mod/IFS authority
active slot ------------------ Z-Mod/FFMInfo authority
current print tool mapping --- Z-Mod/file.json authority
job scan/matching ------------ Z-Mod zmod_color authority
legacy material+primary color- Z-Mod/FFMInfo compatibility projection
rich spool metadata ---------- Plugins AD5X overlay authority
```

Manual rich metadata must not permanently mask external Z-Mod changes without indicating that a compatibility projection is stale or divergent. The backend should publish projection/sync state explicitly.

Proposed states for the future implementation:

- `in_sync` — rich material/primary color and Z-Mod projection agree;
- `pending_projection` — rich metadata changed but has not yet been projected;
- `diverged` — Z-Mod material/primary color changed externally after the rich assignment;
- `unsupported` — no usable Z-Mod color component is available;
- `error` — projection attempt failed.

These names are Plugins AD5X contract states; they are not claimed as upstream Z-Mod fields.

## 7. Read-only job preview adapter

The first safe integration increment should be **read-only**:

1. Plugins AD5X bridge looks up the existing `zmod_color` object at `klippy:ready`;
2. a dedicated preview command asks `zmod_color.get_used_colors(...)` for file requirements;
3. the same adapter asks `zmod_color.get_printer_data_detail()` + `parse_printer_response(...)` for the currently available Z-Mod slot records;
4. it delegates proposed assignment to `zmod_color.get_auto_tool_assignments(...)`;
5. it restores any temporary `zmod_color.file_colors` value after preview;
6. it publishes only a normalized preview result through `ad5x_ifs` status;
7. it does **not** write `file.json`, start a print, change a slot, or change FFMInfo.

This gives every frontend a common pre-print view without duplicating Z-Mod's matcher.

## 8. Normalized job preview target

The first frontend-neutral shape should intentionally avoid fake precision that Z-Mod does not currently return per tool:

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

Do not fabricate a per-tool ΔE score unless the Z-Mod adapter is later extended to expose it directly.

## 9. Pre-print UX target

Frontends should eventually render a job plan, not just four static spool cards:

```text
T0  PLA  [file color] -> Slot 3
T1  PETG [file color] -> Slot 1
T2  PLA  [file color] -> —  warning
```

The UI may offer `Автоподбор`, manual mapping and `Начать печать`, but application of mapping/print-start must remain a separate controlled action from read-only preview.

## 10. Safety boundary

This discovery authorizes no new mechanical hardware action.

The read-only preview adapter must not:

- access `/dev/ttyS4`;
- write `file.json`;
- call `PRINT_ZCOLOR`;
- call `CHANGE_ZCOLOR`;
- start `SDCARD_PRINT_FILE`;
- change the active IFS slot;
- mutate Z-Mod's persisted auto-assignment settings.

Compatibility projection and job-map application require their own backend permissions, tests and real-printer acceptance gates.
