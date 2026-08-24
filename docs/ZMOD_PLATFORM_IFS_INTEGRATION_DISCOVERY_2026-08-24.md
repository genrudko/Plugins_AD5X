# Z-Mod platform / IFS integration discovery — 2026-08-24

Status: **canonical implementation evidence for IFS-MANAGER-001 / issue #15**

This document is a mandatory implementation gate for Plugins AD5X IFS work. It records the live Z-Mod behavior that our backend and frontends must preserve.

## 1. Source provenance

Inspected live upstreams:

| Source | Revision | Purpose |
| --- | --- | --- |
| `ghzserg/zmod` docs/wiki source | `97366a531ddad0bf01e1dc055cb58b81e07cc892` | platform, AD5X, plugin lifecycle, display modes, changelog |
| Z-Mod AD5X source (`1.7`) | `da8c94c9edd6b16253fed7e0e35d171c2adf256a` | IFS/color implementation and print macros |
| Z-Mod Moonraker fork | `a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e` | Moonraker print/update behavior |

Primary files read include Z-Mod `Plugin.md`, `AD5X.md`, `Setup.md`, `System.md`, `Global.md`, `Recommendations.md`, `FAQ.md`, `Zmod.md`, `Main.md`, `Changelog.md`, `.shell/zmod_color.py`, `.shell/zmod_ifs.py`, `.shell/plugins.sh`, `.shell/enable_extra_plugins.sh`, AD5X macros/config, and the Z-Mod Moonraker `klippy_apis.py` and update-manager implementation.

Latest documented release inspected: Z-Mod `1.7.2` dated 2026-08-16. Live docs were newer, at the 2026-08-21 revision above.
The current `1.7` head advanced on 2026-08-23; `.shell/zmod_color.py` is unchanged from the previously audited `b5cbda363adcd4c608bf67feef030e226b2b9e37`, so the IFS/color semantics cited below remain source-current.

## 2. Z-Mod is the platform boundary

AD5X + Z-Mod is not generic upstream Klipper with one invariant hardware path.

Z-Mod has two materially different operating modes:

```text
native display ON  -> stock Flashforge owns native IFS transport/control
DISPLAY_OFF        -> Z-Mod direct IFS implementation owns /dev/ttyS4
```

Plugins AD5X MUST NOT open `/dev/ttyS4`, create a parallel IFS transport, bypass Z-Mod's matcher, or replace its print lifecycle.

## 3. IFS serial ownership is exclusive

Z-Mod documentation explicitly warns that native display access and mod-side direct IFS access can collide on the serial interface. `.shell/zmod_ifs.py` enforces the same boundary in code: when `zmod_color.get_display()` is true, it returns before creating direct `ifs_data`, registering direct IFS commands or starting its serial reader.

Therefore absence of `zmod_ifs.ifs_data` can mean **native display owns IFS**, not necessarily missing/broken hardware.

## 4. Product support boundary

Plugins AD5X IFS Manager v1 is **fully supported only in `DISPLAY_OFF` mode**.

The actual user workflow uses native display only temporarily for maintenance tasks such as obtaining native calibration/MESH data, reconnecting Wi-Fi or using engineering-menu calibration. Full IFS Manager parity in that temporary mode would add a second provider adapter with little product value.

Canonical behavior:

```text
DISPLAY_OFF -> full Plugins AD5X IFS Manager
native screen ON -> maintenance compatibility mode; IFS Manager suspended
```

When native display is active, Plugins AD5X must:

- detect that direct Z-Mod IFS ownership is unavailable;
- report a distinct maintenance-suspended/provider-mode state rather than fake physical absence;
- disable Plugins AD5X mechanical IFS actions;
- disable Plugins AD5X custom pre-print mapping/start interception;
- never open the serial port or compete with the stock process;
- leave normal Z-Mod/Flashforge printing and maintenance workflows untouched.

A full `/detail`-based native-display IFS backend is **not a v1 requirement**. Optional read-only native diagnostics may be added later only if they solve a concrete maintenance need.

## 5. State source in the supported mode

With `DISPLAY_OFF`, Z-Mod owns the direct IFS runtime and exposes `zmod_ifs`. Plugins AD5X may normalize that in-memory provider state but must not become a second serial owner.

Current `klipper/extras/ad5x_ifs.py` behavior is therefore directionally correct for the supported mode, but its normalized result must distinguish:

```text
DISPLAY_OFF + zmod_ifs ready  -> IFS Manager operational
native display active         -> maintenance-suspended
actual missing/broken provider -> unavailable/error
```

Those states must not collapse into one `available=false` meaning.

## 6. Provider-owned load/unload semantics

Z-Mod exposes `IN_ZCOLOR SLOT=<n> NAPR=<0|1>` as its semantic load/unload wrapper.

Internally it does:

```text
native display ON -> Flashforge /control ms_cmd load/unload
DISPLAY_OFF       -> INSERT_PRUTOK_IFS / REMOVE_PRUTOK_IFS
```

Even though Plugins AD5X v1 operates only in `DISPLAY_OFF`, provider-level semantic wrappers are preferred where they already exist because they preserve Z-Mod behavior and reduce coupling to lower-level macros.

Standalone slot selection is different from loading filament. `_SET_EXTRUDER_SLOT` rejects native-display mode; Plugins AD5X must therefore expose `select_slot` only when the supported direct provider mode proves that operation is available.

## 7. Provider-owned print entrypoint

Z-Mod's Moonraker fork changes `KlippyAPI.start_print()`.

For `/printer/print/start` it dispatches according to Z-Mod configuration:

```text
DISPLAY_OFF configured -> _ZSDCARD_PRINT_FILE
native display path     -> _PRINT_FILE
```

On AD5X both are Z-Mod-specific print flows and converge into `SET_ZCOLOR`, not plain generic `SDCARD_PRINT_FILE` behavior.

Ordinary Fluidd/Mainsail Print is therefore already inside the Z-Mod provider lifecycle.

## 8. `SET_ZCOLOR` is the canonical pre-print engine

`SET_ZCOLOR` owns:

- file requirement scan;
- prepared `zmod_color_data` and slicer color/material handling;
- `SCAN_FILE_COLORS` behavior;
- material filtering;
- CIE LAB / ΔE76 color matching;
- `AUTO_ASSIGN_COLORS` logic and result flags;
- T-to-slot proposal;
- Z-Mod's own mapping prompt;
- transition to `PRINT_ZCOLOR`.

Plugins AD5X MUST reuse this analysis and MUST NOT introduce a second G-code scanner or color matcher.

## 9. `PRINT_ZCOLOR` is the canonical explicit launch adapter

`PRINT_ZCOLOR FILENAME=... LEVELING=... ALLOWED_TOOL_COUNT=... T0=... Tn=...` validates an explicit complete mapping, then preserves Z-Mod's provider mode.

With native display ON Z-Mod delegates to Flashforge `/printGcode`. With `DISPLAY_OFF`, Z-Mod writes its own provider-owned `file.json`, selects the first tool and starts `SDCARD_PRINT_FILE`.

Therefore Plugins AD5X MUST NOT independently write `file.json`, call `/printGcode`, or replace provider launch with its own `SDCARD_PRINT_FILE` call.

After real-printer acceptance, the Plugins AD5X launch adapter may call validated `PRINT_ZCOLOR` with the complete mapping. That replaces only the presentation of Z-Mod's mapping prompt, not its print lifecycle.

## 9.1 Inert provider launch plan

Reverified against `ghzserg/z_ad5x` branch `1.7` at `da8c94c9edd6b16253fed7e0e35d171c2adf256a`: `PRINT_ZCOLOR` accepts `FILENAME`, `LEVELING` (`0|1`), `ALLOWED_TOOL_COUNT`, and the complete `T0..Tn` slot vector; every slot value is validated as `1..4`. Z-Mod itself owns the subsequent native-display or DISPLAY_OFF launch lifecycle.

Plugins AD5X may therefore prepare a structured, non-executing provider plan from a validated preview/draft. The plan must preserve the complete `T0..Tn` vector and must not guess `LEVELING`; until an explicit caller supplies `0` or `1`, it remains a required parameter. The plan is evidence/contract data only: `execution_enabled=false`, `start_job=false`, and `apply_preprint_mapping=false` remain unchanged until controlled real-AD5X acceptance.

### 9.2 Provider-owned leveling default

Z-Mod persists the last/default leveling choice in `save_variables.variables.print_leveling`. Plugins AD5X may expose that value read-only when Klipper publishes the optional `save_variables` object. Only `0` or `1` is valid; missing or malformed state remains unknown and must not degrade IFS availability.

This reflected setting is a UI default/source hint, not implicit launch consent. The inert `provider_launch_plan` still requires explicit `LEVELING`; Plugins AD5X does not write `print_leveling` or other Z-Mod save variables.

### 9.3 Explicit leveling dry-run

The read-only mapping-draft endpoint may accept an explicit `leveling` value and use it only to materialize the inert `provider_launch_plan`. A valid `0|1` makes that provider plan structurally complete; invalid values block the launch candidate. This remains a dry-run: the endpoint emits no G-code and `execution_enabled`, `start_job`, and mapping write capabilities stay false.

### 9.4 Explicit hardware-acceptance gate

`launch_gate` exposes a read-only `hardware_acceptance` object. Until exact-SHA real-AD5X evidence exists it is always `required=true`, `accepted=false`, `reason=hardware_acceptance_required`, and `exact_sha_required=true`. The semantic launch candidate may still be structurally ready, but write/start capabilities remain disabled.

## 10. Avoiding duplicate pre-print dialogs

A native Fluidd mapping dialog cannot simply run before the ordinary Moonraker print endpoint and then call that endpoint unchanged, because `SET_ZCOLOR` would open the provider mapping flow again.

Target supported-mode flow after hardware acceptance:

```text
Fluidd/Mainsail Print
 -> Plugins AD5X provider preview (Z-Mod scanner/matcher)
 -> Plugins AD5X mapping editor
 -> backend revalidation against exact preview token + live DISPLAY_OFF IFS state
 -> explicit provider-owned PRINT_ZCOLOR launch
 -> Z-Mod continues normal print lifecycle
```

Until this is accepted on a real AD5X, `start_job=false` remains correct and normal Z-Mod printing must remain available without Plugins AD5X interception.

## 11. Z-Mod settings remain provider settings

Settings such as `SILENT`, `SCAN_FILE_COLORS`, `AUTO_ASSIGN_COLORS`, `ALLOWED_TOOL_COUNT`, `COLOR_MENU_1_BASED` and `PRINT_LEVELING` belong to Z-Mod behavior/configuration. Plugins AD5X may reflect relevant values/capabilities but must not silently rewrite them or directly edit Z-Mod variable storage.

## 12. Plugin lifecycle contract

Z-Mod plugin lifecycle is source-proven.

`ENABLE_PLUGIN NAME=<name>` ultimately:

1. finds `[update_manager <name>]`;
2. clones/pulls into `mod_data/plugins/<name>`;
3. requires `<name>.cfg`;
4. includes it from `mod_data/plugins.cfg`;
5. runs plugin `install.sh` when present;
6. requests `FIRMWARE_RESTART`.

`DISABLE_PLUGIN` removes the include, runs `uninstall.sh` and restarts Klipper. Z-Mod's Moonraker update-manager integration runs plugin `update.sh` after an enabled plugin repo update.

`ad5x_custom.cfg` is therefore part of the required Z-Mod plugin contract. Plugins AD5X should continue to own only its checkout and plugin-created integration links; tracked Z-Mod/Klipper/Moonraker core files remain provider-owned.

## 13. Frontend implications

GuppyScreen and HelixScreen operate in the `DISPLAY_OFF` family of Z-Mod modes, which aligns with the IFS Manager supported runtime.

Fluidd and Mainsail themselves may remain usable when native display is temporarily enabled, but Plugins AD5X IFS controls/pre-print integration must be capability-gated off until the backend again proves the supported `DISPLAY_OFF` runtime.

## 14. Required implementation corrections before Fluidd IFS continuation

1. publish/detect the provider/control mode;
2. define `DISPLAY_OFF` as the v1 supported IFS Manager runtime;
3. represent native display as maintenance-suspended, not as missing IFS;
4. keep direct state sourced from `zmod_ifs` without parallel serial access;
5. make all mechanical IFS permissions false outside the supported mode;
6. prefer Z-Mod semantic wrappers where they already own the operation;
7. keep preview/matching provider-owned and available only in the supported IFS Manager runtime;
8. keep `PRINT_ZCOLOR` launch disabled until controlled real-AD5X acceptance;
9. do not intercept Fluidd/Mainsail Print until that explicit launch adapter is accepted;
10. preserve ordinary Z-Mod/native-screen printing and maintenance workflows while IFS Manager is suspended.

## 15. Canonical rule

**Z-Mod owns IFS transport, matcher and print launch. Plugins AD5X IFS Manager is operational only in Z-Mod `DISPLAY_OFF` mode; native display is a maintenance compatibility state in which Plugins AD5X suspends IFS control. Plugins AD5X owns normalization, metadata enrichment, validation/policy and UI presentation, and never bypasses provider launch.**
