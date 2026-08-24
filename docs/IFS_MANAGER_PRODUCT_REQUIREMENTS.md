# Plugins AD5X — IFS / Materials Manager product requirements v2

Status: canonical product requirements for `IFS-MANAGER-001` / issue #15.

## 1. Product objective

Create a polished, reliable materials subsystem for Flashforge AD5X + Z-Mod that replaces the **user-facing need** for the stock Z-Mod IFS manager while preserving Z-Mod as the proven provider for hardware protocol, material/color matching and print lifecycle.

The product is designed for **any UI/client built around Klipper/Moonraker**, not for one frontend. First-party native integrations are required for Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen, but the backend must remain independently consumable.

Functional parity with Z-Mod is the minimum bar. Product quality, usability, observability and interoperability should exceed it where the hardware/provider permits.

## 2. Non-negotiable architecture

1. One normalized backend/state model.
2. Z-Mod remains provider authority for proven IFS mechanics/matcher/print lifecycle.
3. Frontends contain presentation and local navigation only, not IFS business logic.
4. Compatibility formats such as Orca `lane_data` are **projections**, not alternate truth stores.
5. Physical state, metadata, job mapping and UI selection remain separate truth domains.
6. No high-rate cosmetic polling and no heavyweight service on the AD5X MIPS host.
7. Backend failure must not make ordinary Z-Mod printing unavailable.
8. Every new mechanical/print mutation remains disabled until source-verified and hardware accepted.

Canonical architecture: `docs/IFS_MANAGER_ARCHITECTURE_V2.md`.

## 3. UI expertise model

### 3.1 Expert is canonical

Expert Mode is the complete capability surface. All meaningful, reliable supported capabilities/states must be discoverable there.

### 3.2 Hybrid

Hybrid is a progressive-disclosure view of Expert:

- routine physical status and actions visible;
- compact job mapping visible when relevant;
- warnings/action recommendations prioritized;
- service diagnostics collapsed but reachable.

### 3.3 Auto

Auto is the most simplified view:

- healthy automatic assignments/details stay hidden;
- user sees ready/problem/action states;
- advanced control is one drill-down away;
- automation never bypasses backend permission/safety policy.

Auto/Hybrid/Expert do not create different backends or different physical behavior.

## 4. Main dashboard UX

Primary visual direction: **Helix AD5X physical topology + Happy Hare information/visual hierarchy**, creatively adapted to AD5X.

Required main Expert presentation:

- four large physical IFS source/spool cards;
- actual present/empty/error state;
- material and representative/rich appearance;
- active/current source;
- visual path through selector to toolhead;
- toolhead filament state;
- external/bypass path shown separately when supported;
- current operation and error/warning state;
- safe select/load/unload actions;
- detail drill-down for full spool metadata, compatibility and diagnostics.

Do not make permanent tool mapping the dominant dashboard object. AD5X has one extruder and four fixed lanes; mapping is primarily a job concern.

Do not display fake Happy-Hare topology sensors such as encoder/hub/compression/clog state unless a real AD5X/provider source exists.

## 5. Pre-print / mapping UX

Primary interaction reference: Happy Hare `Map Tools`, adapted to the simpler AD5X topology.

The pre-print plan must show:

- slicer-required `Tn` tools;
- required material/color when known;
- currently available IFS sources;
- Z-Mod canonical automatic assignment;
- clear mismatch/weak/duplicate/missing reasons;
- manual remap UI when the write path is implemented;
- reset/automatic proposal actions;
- ready/warning/blocked state;
- explicit confirmation before any production launch mutation.

Auto normally collapses successful mapping. Hybrid shows a compact summary. Expert can open full mapping.

Opening a pre-print plan is read-only.

## 6. Physical source requirements

### 6.1 IFS lanes

Exactly four fixed IFS physical sources are modeled.

Each lane must expose when provider data is available:

- physical presence;
- active/current state;
- stall/error state;
- material/color metadata;
- rich spool metadata;
- current permissions;
- compatibility/provenance;
- load/unload/select semantics;
- diagnostics needed for support/recovery.

### 6.2 External / bypass

An external manual filament path is a distinct source, not `Slot 5`.

It may be useful for TPU and brittle filaments. It must not claim IFS presence/stall/selector telemetry. Runtime availability/control stays disabled/unknown until provider behavior is verified.

## 7. Material and spool metadata

The canonical model should support:

- source/provenance;
- brand/vendor;
- series;
- spool name;
- precise material;
- variant;
- remaining grams when trustworthy;
- Spoolman spool ID;
- Spoolman filament ID;
- Orca compatibility material;
- future Orca exact filament/preset IDs;
- optional nozzle/bed temperatures where the data source is trustworthy.

Identifiers must never be overloaded across systems.

Physical presence must never be inferred from metadata.

## 8. Appearance

Required canonical appearance modes:

- solid;
- dual;
- tricolor;
- gradient;
- rainbow;
- special.

Finish must be separately representable (standard/matte/silk/satin/metallic/transparent/translucent/glitter/glow/wood/carbon_fiber/other).

Compatibility projections may use one representative primary color but must not destroy the full model.

## 9. Z-Mod parity requirements

Expert completion requires user-facing access to every reliable Z-Mod IFS capability that can be normalized safely, including:

- physical IFS state;
- active source;
- material/color editing through the provider path;
- load/unload/select;
- G-code color/tool scan;
- automatic assignment;
- mismatch/weak/duplicate diagnostics;
- job mapping and, where supported, runtime remapping;
- print with/without IFS semantics;
- provider auto insertion;
- filament-change/recovery flow;
- purge behavior;
- reset/stop/unlock recovery semantics;
- equivalent/endless-spool behavior based on provider primitives;
- source-relevant IFS motion/head-switch diagnostics.

Raw Fxx commands are implementation/provider details and should be surfaced only under bounded diagnostics/service flows, not as ordinary controls.

## 10. OrcaSlicer interoperability

### 10.1 User-visible requirement

When OrcaSlicer physical-printer connection is configured as:

```text
Host type:     Octo/Klipper
Network agent: Moonraker
```

IFS material/color state should synchronize to Orca through its generic Moonraker integration.

Initial acceptance target: **OrcaSlicer 2.4.2**.

README must state that this feature does not work through the generic `lane_data` path when another Orca network agent is selected.

### 10.2 Backend contract

Publish Moonraker namespace:

```text
lane_data
```

with stable `lane1..lane4` records and zero-based string `lane` values.

Current required interoperability values:

- `lane`;
- conservative `material`;
- representative `color`;
- optional `nozzle_temp`;
- optional `bed_temp`.

Future-proof non-authoritative aliases may include vendor/name/spool identity, but current Orca behavior must not be overstated.

### 10.3 Exact filament preset identity

Current generic Orca Moonraker matching is not a reliable exact custom-preset binding.

Requirements:

- do not populate Orca `filament_id` from Spoolman filament ID;
- keep Spoolman and Orca IDs separate;
- when exact Orca identity is unknown, leave it null/absent;
- preserve exact specialty material separately from conservative Orca wire material;
- do not guess `ASA-GF`, `PLA Matte`, etc. into a generic match unless an explicit compatibility mapping exists.

### 10.4 Shared `lane_data`

`lane_data` may have other writers/readers.

Plugins AD5X must:

- preserve unknown fields in owned `laneN` records where practical;
- avoid clearing the namespace;
- detect duplicate records for the same inner lane and fail closed rather than publish ambiguity;
- write only on meaningful state/metadata changes and reconnect/reconciliation;
- avoid a background polling daemon.

## 11. Spoolman requirements

Spoolman is optional but the integration is product-level, not metadata decoration.

Required full-manager behavior:

- detect/report availability;
- search/browse/select library spools;
- bind/unbind each of the four physical sources to a concrete spool;
- import useful material/vendor/color/name/weight fields;
- drive native Moonraker `active_spool` automatically from the real active IFS source and reuse Moonraker consumption accounting;
- distinguish spool entity from filament entity;
- never delete the external Spoolman record merely because a lane becomes empty;
- gracefully degrade when Spoolman is absent or unavailable.

IFS remains physical truth. Therefore `present=false` MUST hide the old concrete spool as current, invalidate/remove its local slot binding and persist that invalidation. A subsequent insertion without verified identity MUST be `unassigned` and MUST NOT silently reuse the old Spoolman ID. Provider material/color may be shown as observed metadata only. Explicit new bind/edit establishes the new current identity.

The standalone IFS/Spoolman bridge remains a supported lightweight product direction. Its v2 target is four slot bindings + automatic active-spool tracking on shared semantics. Full and standalone implementations MUST NOT run concurrently as competing owners on one printer.

## 12. Equivalent / endless spool requirements

Use Z-Mod's existing equivalent/analogous-spool primitives where source-verified.

Expert target:

- show fallback/equivalent relationships;
- explain why a spool is considered compatible;
- allow explicit policy/priority when supported;
- show transition/recovery state;
- do not silently switch to materially incompatible spool.

Automatic transition stays hardware-gated until real AD5X acceptance.

## 13. Recovery and diagnostics

Expert should provide semantic recovery around real provider evidence:

- current operation;
- last relevant failure;
- physical lane/presence/stall state;
- toolhead filament state;
- IFS motion state when available;
- source/provider state code;
- matcher/assignment result;
- compatibility projection status;
- bounded raw diagnostics for support.

Do not turn diagnostics into an always-on high-rate logger.

The normalized backend may expose source-verified recovery primitives and provider-observed failure sequences as a **read-only recovery preview**. For Z-Mod `DISPLAY_OFF`, the currently verified primitives are driver reset (`IFS_F15`), force-stop motion (`IFS_F112`), unlock all (`IFS_F18`) and per-slot unlock (`IFS_F39 PRUTOK=n`). Z-Mod itself uses `IFS_F15` for driver-error retry (`FFS_state=127`) and `IFS_F112` + `IFS_F18` on timeout/error cleanup. Publishing these semantics does not enable execution: `actions.recovery=false`, recovery execution remains hardware-gated, and raw stall bits alone must never manufacture a recommended recovery action.

## 14. Capability/permission UX

Frontend button availability comes from backend permissions.

Installed capability and momentary permission are different things.

A disabled action should expose a stable reason such as:

- `unsafe_print_state`;
- `ifs_not_ready`;
- `operation_in_progress`;
- `slot_empty`;
- `slot_not_selected`;
- `filament_not_at_toolhead`;
- feature-specific hardware gate.

## 15. First-party frontend requirements

Implementation order is explicit: **Fluidd → Mainsail → GuppyScreen → HelixScreen → KlipperScreen**. KlipperScreen work is gated on completion of the underlying AD5X KlipperScreen port; the existing hardware PoC is not a canonical IFS frontend base.

### Fluidd

Must receive a full native manager/dashboard/pre-print experience or use a source-verified native compatibility component where this produces accurate semantics.

### Mainsail

Must reach semantic parity with Fluidd while following Mainsail's native presentation conventions. Source verification against official Mainsail `develop@cce05e4958765b224c4b6c56b21dc76f31216626` rejects a synthetic Happy Hare `mmu` compatibility object: Mainsail treats it as an actionable MMU command surface, not a read-only visualization contract. `.theme/navi.json` is link-only and cannot inject a route/component. First-party parity therefore requires a small native Mainsail adapter/fork consuming the shared Plugins AD5X backend directly. See `docs/IFS_MAINSAIL_INTEGRATION_DISCOVERY_2026-08-24.md`.

### HelixScreen

Should retain its excellent physical-topology strengths but move metadata/business truth to the shared Plugins AD5X backend. Long term it must not be an independent AD5X `lane_data` source of truth.

### GuppyScreen

Must consume the same backend/capabilities and fit Guppy's navigation/state conventions.

### KlipperScreen

Must use native GTK/KlipperScreen panels and the shared backend. Existing hardware PoC is not the final visual target.

## 16. Other Klipper UIs

The product must be integrable by an unanticipated Klipper/Moonraker UI without changing hardware/provider code.

A third-party client should be able to obtain:

- normalized IFS snapshot;
- semantic permissions;
- job preview/pre-print plan;
- events/revision invalidation;
- compatibility projections where appropriate.

No third-party client should need to understand Flashforge IFS binary/serial protocol.

## 17. Performance requirements

- no new high-rate idle poller;
- event-driven recomputation/publication;
- bounded JSON/status payloads;
- no image processing or other heavy task in IFS backend;
- no duplicate color matcher;
- no parallel serial owner;
- low memory footprint appropriate for AD5X.

## 18. Safety requirements

Current write restrictions remain until independently accepted:

- editable mapping application: disabled;
- production `PRINT_ZCOLOR`: disabled;
- Z-Mod material/color write projection: disabled;
- automatic equivalent/endless-spool transition: disabled;
- unproven recovery motion: disabled;
- automated external/bypass switching: disabled.

Hardware acceptance must use exact repository SHA and real-printer evidence. CI/docs alone are insufficient.

## 19. Definition of done

IFS / Materials Manager 1.0/v2 architecture is done only when:

- Expert covers the complete reliable provider capability set;
- Auto/Hybrid are coherent simplified views;
- stock Z-Mod IFS UI is not required for normal use;
- full optional Spoolman integration works;
- Orca 2.4.2 material/color sync works via Moonraker `lane_data` and documented setup;
- the five first-party native frontends converge on one backend;
- arbitrary Klipper/Moonraker clients can integrate from the same contract;
- no unsupported sensor/telemetry is fabricated;
- all enabled mechanical/print mutations have hardware acceptance evidence.

## 20. Upgradeability requirement

Installing or updating IFS / Materials Manager must not make normal Z-Mod, Klipper, Moonraker or other plugin updates depend on removing Plugins AD5X patches. Product installation therefore uses the native Z-Mod plugin lifecycle and plugin-owned runtime links, with no tracked core-file mutation. Legacy owned copies may be migrated; foreign files fail closed. Disable, update and full uninstall are distinct lifecycle operations.
