# Plugins AD5X — IFS / Materials Manager discovery — 2026-08-22

Status: **source/community-verified design input for IFS-MANAGER-001 / issue #15**

This document records the 2026-08-22 discovery pass that supersedes several earlier assumptions about IFS UX, Z-Mod parity and OrcaSlicer interoperability. It is evidence for the v2 product architecture; it is not itself a runtime contract.

## 1. Sources reviewed

The discovery pass intentionally did not treat `ghzserg/zmod` as the complete Z-Mod implementation. Relevant behavior is distributed across:

- Z-Mod wiki;
- `ghzserg/zmod`;
- `ghzserg/base`;
- `ghzserg/z_ad5x`, especially the AD5X runtime `.shell` modules;
- Z-Mod Klipper/Moonraker forks and related plugins when applicable;
- OrcaSlicer current 2.4.x Moonraker integration;
- Happy Hare MMU/Moonraker integration;
- HelixScreen filament-management documentation/implementation;
- AFC / Snapmaker U1 Extended Firmware integration patterns;
- community discussion in Telegram group `FF_5M_5M_Pro` on 2026-08-20/21.

Provider behavior that can affect mechanics, print lifecycle or persistent state still requires direct source/runtime verification before its write path is enabled.

## 2. Z-Mod findings that affect the IFS product

### 2.1 Z-Mod remains the hardware/provider authority

The following must remain provider-owned unless an upstream contract is intentionally replaced:

- IFS serial protocol and low-level Fxx timing/retry behavior;
- current material/color scanner and auto matcher;
- material filtering and CIE LAB / ΔE76 color matching;
- established in-print filament-change lifecycle;
- authoritative `PRINT_ZCOLOR` multi-material launch semantics;
- automatic insertion behavior already owned by Z-Mod.

Plugins AD5X wraps those functions through semantic state/actions instead of creating parallel implementations.

### 2.2 Mapping is job-scoped, not the main IFS topology

AD5X has four fixed IFS inputs feeding one selector and one extruder. A slicer job may require `T0/T1/...`, which Z-Mod maps to physical slots 1..4. This mapping is important for a concrete job, but it is not the primary physical object model of the IFS dashboard.

Therefore:

- the main IFS screen is physical topology first;
- tool mapping is contextual in pre-print / active-job flows;
- a permanent large Happy-Hare-style mapping pane is not the default AD5X layout.

### 2.3 Existing equivalent/endless-spool primitive

Z-Mod already provides equivalent-spool behavior through `ANALOG_PRUTOK`: another present spool with compatible material/color can replace the current mapping and the existing filament-change flow can resume. The exact trigger/configuration semantics still require source/hardware acceptance before Plugins AD5X enables an automatic policy.

This means Plugins AD5X should expose a normalized equivalent/endless-spool policy over the provider primitive instead of inventing an independent refill engine.

### 2.4 Runtime remapping and recovery are real capabilities

Z-Mod exposes material/color editing, load/unload, runtime tool/spool mapping and lower-level recovery primitives. Expert mode should expose every meaningful, reliable capability that the supported AD5X/Z-Mod stack can provide, while keeping raw Fxx commands subordinate to semantic recovery actions.

## 3. UX findings

### 3.1 Expert is canonical

There are not three different products or backends.

`Expert` is the canonical capability surface. `Hybrid` and `Auto` are progressively simplified UI/policy presentations over the same state, actions and safety model.

```text
canonical backend / capabilities
            |
         Expert
        /      \
    Hybrid     Auto
```

A frontend may remember a preferred initial expertise level, but changing UI expertise must not change backend truth or remove capabilities from the installed system.

### 3.2 Visual references

Primary references:

- Happy Hare MMU dashboard: visual hierarchy, rich lane/spool information, state/error presentation;
- Happy Hare Map Tools: pre-print tool-to-physical-source interaction model;
- HelixScreen AD5X IFS topology: four IFS sources → selector → single extruder, with bypass/external path as a distinct source;
- QIDI / Snapmaker / AFC material panels: simpler Auto/Hybrid presentation.

These are interaction/visual references, not templates to copy literally. AD5X must not display fake encoder/hub/clog/path telemetry that its hardware does not provide.

### 3.3 Main Expert screen

The canonical Expert dashboard should prioritize:

- four physical IFS slots/spools;
- physical present/empty/error state;
- current/active slot;
- filament-at-toolhead state;
- visual selector/toolhead path;
- external/bypass source as a distinct source when provider/runtime support is verified;
- load/unload/select and contextual recovery actions;
- material/spool identity, appearance and remaining amount when trustworthy;
- warnings and current operation;
- drill-down diagnostics.

### 3.4 Pre-print mapping

The pre-print workflow should adapt the proven Map Tools grammar:

- slicer-required tools/material/colors;
- available physical IFS spools;
- Z-Mod canonical automatic proposal;
- mismatch reasons;
- manual correction when needed;
- explicit ready/warning/blocked result;
- provider-delegated launch only after stale/live revalidation and hardware acceptance.

Auto hides healthy mapping detail. Hybrid shows a compact summary plus `Изменить`. Expert can open the complete mapping editor.

## 4. External / bypass source

An external filament path is not “IFS Slot 5”. It is a separate source class because it does not have IFS lane telemetry or selector semantics.

Target model:

```text
IFS slot 1 --\
IFS slot 2 ---+--> IFS selector --> extruder
IFS slot 3 ---+
IFS slot 4 --/

External / bypass -------------> extruder
```

This is useful for TPU, brittle materials and manual-feed cases. Runtime availability, controls and switching semantics must be provider/source verified before being exposed as working actions.

## 5. OrcaSlicer interoperability

### 5.1 Proven generic Moonraker read path

With the physical printer configured in OrcaSlicer to use:

- host type: `Octo/Klipper`;
- network agent: `Moonraker`;

OrcaSlicer can read filament lane information from Moonraker database namespace:

```text
/server/database/item?namespace=lane_data
```

This does not require an Orca fork or a separate mandatory AD5X printer preset.

### 5.2 Current Orca 2.4.x lane contract

Current generic Moonraker integration reads at least:

- `lane` — a zero-based lane number encoded as a string;
- `material`;
- `color`;
- `nozzle_temp`;
- `bed_temp`.

The stable outer keys should be `lane1`..`lane4`, while the inner lane values are `"0"`..`"3"`.

Current generic preset selection is material-oriented and does not yet provide a reliable exact custom filament-preset identity. Temperature fields are read but are not a substitute for exact preset identity.

### 5.3 Exact identity and `filament_id`

Do not overload identifiers.

Plugins AD5X must distinguish:

- Spoolman spool ID;
- Spoolman filament ID;
- Orca filament/preset identity when a stable upstream contract exists.

Happy Hare currently exposes a `filament_id` associated with its spool/Spoolman data. That must not be blindly reinterpreted as an Orca preset ID. Until Orca defines/consumes a deterministic compatible identifier, Plugins AD5X should omit/null the Orca-facing `filament_id` rather than publish a false identity.

### 5.4 Precise material vs Orca wire material

A rich exact material identity such as `ASA-GF`, `PLA Matte` or a vendor compound must not automatically force Orca to choose an incorrect generic preset.

The canonical model therefore needs two concepts:

- precise material identity used by Plugins AD5X / Spoolman / user metadata;
- optional conservative Orca wire material used only when the mapping is known to be safe.

If a safe projection is unknown, omit the Orca `material` value rather than guessing.

### 5.5 Empty slots and representative color

`lane_data` represents physical availability for Orca. Therefore a physically empty IFS slot must publish null/empty material and color even if Plugins AD5X intentionally preserves stale metadata for later reuse.

Rich multi-color appearance is projected lossily to one representative/primary color. Full dual/tricolor/gradient/rainbow metadata remains in the Plugins AD5X API.

### 5.6 Shared namespace / writer ownership

`lane_data` is an interoperability namespace and may already be touched by Helix, AFC, Happy Hare or other components.

Plugins AD5X must:

- merge with existing records instead of deleting the namespace;
- preserve unknown fields where practical;
- own only its four AD5X IFS lane records;
- avoid duplicate records for the same inner lane;
- publish on semantic change / reconnect, not with a high-rate polling daemon.

The long-term AD5X architecture makes Plugins AD5X the canonical metadata writer. First-party frontends should edit the common backend, not maintain separate spool databases.

## 6. Spoolman relationship

Spoolman remains optional. When enabled it is a spool-library/data source, not the authority for physical presence.

Target flow:

```text
physical IFS state ---- Z-Mod/IFS
rich metadata ---------- Plugins AD5X
optional spool identity  Spoolman adapter
                              |
                              v
                    canonical IFS model
                       /           \
                 native UIs     lane_data → Orca
```

A slot being physically emptied must not delete the external Spoolman spool entity.

## 7. Cross-UI architecture

The product is not limited to five named frontends. The canonical backend is for any Klipper/Moonraker UI or client that can consume the normalized API or a supported interoperability projection.

First-party native adapter targets remain:

- Fluidd;
- Mainsail;
- HelixScreen;
- GuppyScreen;
- KlipperScreen.

Additional Klipper UIs should be able to integrate without reimplementing hardware semantics. Where an existing native UI already understands a stable external contract (for example `lane_data`, AFC/MMU-style contracts), a compatibility projection may be preferable to a frontend fork.

## 8. Implementation consequences

The v2 implementation should:

1. preserve one canonical backend and the existing hardware-proven state bridge;
2. make Expert the complete canonical UI capability model;
3. represent Auto/Hybrid as progressive-disclosure policies;
4. keep physical topology separate from job mapping;
5. add frontend-neutral external/bypass source semantics without inventing runtime facts;
6. add event-driven Orca `lane_data` publication;
7. keep precise and compatibility material identities separate;
8. keep Spoolman and Orca identifiers separate;
9. preserve/merge shared `lane_data` records safely;
10. retain Z-Mod as provider for scanner/matcher/IFS mechanics/print lifecycle;
11. close Z-Mod parity gaps before calling the manager a complete replacement;
12. maintain native first-party UI adapters while allowing any Klipper UI to consume the common backend.

## 9. Safety boundary

This discovery does not enable any previously disabled mechanical or print mutation.

The following remain hardware-gated until separately accepted:

- applying manual pre-print mapping;
- `PRINT_ZCOLOR` start;
- automatic equivalent/endless-spool fallback;
- recovery primitives not already proven in the normal action path;
- Z-Mod material/color compatibility writes;
- external/bypass mechanical switching if any automated path is introduced.

## 10. Z-Mod plugin lifecycle discovery — 2026-08-23

Source review of Z-Mod plugin documentation/runtime and `zmod_moonraker` confirmed: `ENABLE_PLUGIN` invokes plugin `install.sh`, `DISABLE_PLUGIN` invokes `uninstall.sh`, Moonraker Update Manager invokes executable `update.sh` for enabled plugins after update, and Z-Mod itself uses symlink-style Klipper extras integration.

Consequence: Plugins AD5X must keep source in its own plugin checkout and expose Klipper/Moonraker Python files through owned links rather than copied/edited core files. Update hooks must not kill their parent Moonraker Update Manager process. Generic startup was not proven to rerun every plugin install hook after destructive core reclone, so automatic post-reclone repair is not claimed.

