# KlipperScreen / Z-Mod IFS print-path discovery — 2026-08-17

Status: source-verified discovery for `IFS-MANAGER-001` / issue #15.

## Sources inspected

KlipperScreen:

- repository `KlipperScreen/KlipperScreen`;
- pinned Stage 4 ref `ed40799f92f8a5044082aee75b832a9e97084c7f`;
- `panels/gcodes.py`, blob `60f31ea56f20c75cd56c01c1be8e39d1a9106cc7`.

Z-Mod:

- repository `ghzserg/z_ad5x`;
- branch `1.7`;
- `.shell/zmod_color.py`, blob `158338c4f8f6c937e3b1ae6f9ca34261983cc425`.

## 1. Upstream KlipperScreen print start

In the pinned upstream KlipperScreen, selecting a G-code file calls
`Panel.confirm_print(...)`. The ordinary confirmation dialog's OK response calls:

```python
self._screen._ws.api.print_start(filename)
```

That is the ordinary Moonraker/Klipper virtual-SD print-start path. KlipperScreen
does not know AD5X IFS tool mapping or Z-Mod `PRINT_ZCOLOR` semantics.

## 2. Z-Mod IFS print start

Z-Mod's non-native-display IFS path is materially different.

`SET_ZCOLOR`:

- scans/loads the file tool/color/material requirements;
- obtains available IFS slot metadata;
- optionally calls the canonical `get_auto_tool_assignments(...)` matcher;
- validates the selected physical slot IDs;
- presents or applies the mapping.

`PRINT_ZCOLOR` then:

- validates `FILENAME`, `LEVELING`, `ALLOWED_TOOL_COUNT` and every `Tn` slot;
- constructs material mappings;
- persists `print_leveling`;
- in the non-native-display path writes the resolved `tools` array to:

```text
/usr/data/config/mod_data/file.json
```

- calls `find_t_code(filename)` to establish the initial current filament tool;
- finally starts the file with `SDCARD_PRINT_FILE`.

During the print, `_CHANGE_FILAMENT` reads `file.json` and maps each slicer tool
channel to the resolved physical spool before loading/changing filament.

## 3. Consequence

The current Stage 4 KlipperScreen shell is hardware-proven as a display/runtime
and IFS Manager prototype, but its upstream `Print` confirmation **must not be
claimed as the final AD5X IFS/multi-color launch path**.

Direct upstream `print_start(filename)` does not, by itself, establish the Z-Mod
`Tn -> physical slot` mapping that `_CHANGE_FILAMENT` consumes.

This is a semantic blocker, not a UI-polish issue.

## 4. Required architecture

Plugins AD5X must own a frontend-neutral pre-print/launch contract:

```text
selected G-code file
        ↓
Z-Mod delegated requirements + auto-match preview
        ↓
Plugins AD5X normalized preprint_plan
        ↓
user review / optional manual mapping
        ↓
controlled backend launch action
        ↓
Z-Mod PRINT_ZCOLOR / SET_ZCOLOR semantics
        ↓
file.json + initial tool + SDCARD_PRINT_FILE
```

KlipperScreen, Fluidd, Mainsail, Helix and Guppy must consume the same plan/action
instead of independently starting an IFS job.

## 5. Current repository gate

Implemented and read-only:

- Z-Mod delegated file requirement scan;
- Z-Mod delegated auto-assignment preview;
- normalized `job_preview`;
- normalized `preprint_plan`;
- rich slot metadata and physical presence join.

Still intentionally disabled:

- `mapping.apply_preprint_mapping`;
- actual pre-print mapping mutation;
- actual IFS print-start action;
- Z-Mod compatibility projection writes.

The UI may render and review a plan now, but it must not connect a new `Start`
button to ordinary upstream `print_start` and call that IFS-safe.

## 6. Future launch action requirements

Before enabling a launch endpoint it must:

1. require safe printer/IFS state;
2. validate the selected filename and mapping;
3. ensure every required tool has one valid, physically present slot;
4. preserve Z-Mod's allowed tool count and slot-range constraints;
5. re-check physical state immediately before mutation;
6. invoke the Z-Mod-owned launch path, not write `file.json` directly;
7. expose mapping/source/provenance in the response and diagnostics;
8. fail closed on stale preview, missing slots, mismatches or Z-Mod errors;
9. have explicit real-printer acceptance before `capabilities.mapping.apply_preprint_mapping`
   or a start capability becomes true.

Whether the first write implementation should call `SET_ZCOLOR SILENT=1 ...` or
`PRINT_ZCOLOR ... Tn=slot` is intentionally left open until the exact desired
user-review/strictness semantics are fixed and tested. Both are Z-Mod-owned paths;
ordinary KlipperScreen `print_start` is not the replacement.

## 7. Reference KlipperScreen integration target

The clean insertion point is the file-selection/confirmation flow in
`panels/gcodes.py`, because that is where the filename is known before the current
standard print-start call.

The first safe UI increment can replace/augment the confirmation with a **read-only
pre-print plan**. The final `Start` control must remain unavailable until the
backend launch contract above is implemented and hardware-accepted.

No upstream KlipperScreen fork is required: the AD5X Stage 4 compose step may
install a narrow compatibility adapter/panel while keeping the upstream pin
pristine.
