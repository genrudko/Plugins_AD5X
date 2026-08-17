# Plugins AD5X — IFS / Materials Manager product requirements

Status: **owner-approved product direction / implementation contract**  
Work item: `IFS-MANAGER-001` / issue #15  
Applies to: backend, Spoolman integration and every supported frontend adapter.

## 1. Product goal

Plugins AD5X IFS / Materials Manager is intended to become the **complete user-facing replacement for the stock Z-Mod IFS manager** on supported AD5X installations.

This does **not** mean forking or unnecessarily reimplementing Z-Mod. Z-Mod remains a compatible low-level provider where it already owns proven hardware/protocol or print-path semantics. In particular Plugins AD5X should delegate to existing Z-Mod implementations for operations such as IFS protocol handling, slicer color/material matching and the proven multi-color print lifecycle when those implementations remain authoritative and safe.

The acceptance boundary is user-facing: for normal IFS/material operation the user should not need to open the stock Z-Mod manager because a routine or advanced function is missing from Plugins AD5X.

## 2. Product quality target

The subsystem has two simultaneous goals:

1. **maximum useful functionality** for Klipper/AD5X enthusiasts;
2. **consumer-grade clarity and visual quality** comparable to mature multi-material ecosystems such as Bambu Lab AMS and Prusa MMU-class interfaces.

These products are UX/quality references, not designs to copy.

A technically exposed backend feature is not considered complete merely because an RPC, macro or diagnostic control exists.

A user-facing feature is complete only when it has:

- a defined normalized backend contract;
- safe and explainable state transitions;
- appropriate fail-closed behavior;
- clear user workflow;
- understandable visual state and error/warning presentation;
- native presentation in the supported frontend scope for the relevant release;
- hardware acceptance when the feature performs or enables a new mechanical/print mutation.

## 3. Backend-first, frontend-neutral architecture

```text
Z-Mod / Klipper / Flashforge IFS
              │
              ├── Z-Mod compatibility/provider adapter
              ├── optional Spoolman adapter
              └── Plugins AD5X rich metadata/state
                         │
                 IFS Manager backend
                         │
          versioned normalized state/actions/events
                         │
       ┌──────────┬──────────┬──────────┬──────────┬──────────────┐
       │          │          │          │          │              │
    Fluidd     Mainsail   HelixScreen   Guppy   KlipperScreen   future UI
    native      native       native      native       native
```

Hardware semantics, safety rules, Z-Mod macro selection, slicer matching, Spoolman synchronization policy, tool mapping and recovery logic belong to backend/provider layers, not to frontend adapters.

Frontend implementations render normalized semantic state and invoke normalized actions.

## 4. Complete Z-Mod Manager user-facing parity

Before IFS Manager can be called a replacement, the project must maintain an explicit parity matrix for every meaningful function exposed by the current Z-Mod IFS/material UI.

The target includes, where supported by the real hardware/Z-Mod flow:

- physical state of all four IFS lanes;
- active/current lane and filament-at-toolhead state;
- material and color management;
- rich spool metadata and appearance;
- slot selection;
- load/unload and other proven filament operations;
- tool-to-slot mapping;
- slicer/G-code material and color requirement discovery;
- automatic assignment using the canonical Z-Mod matcher;
- manual correction of assignments;
- pre-print validation and plan;
- safe multi-color launch through the correct Z-Mod lifecycle;
- endless/infinite-spool functionality once its real hardware/Z-Mod semantics are proven;
- recovery/error states where Z-Mod exposes safe operations;
- diagnostics sufficient for troubleshooting without polluting the normal workflow.

A function may be intentionally excluded only with an explicit documented reason (hardware unavailable, unsafe, obsolete, or superseded by a better normalized flow).

**No normal or advanced workflow should require the user to fall back to the stock Z-Mod Manager simply because Plugins AD5X did not expose it.**

## 5. Optional full Spoolman integration

Spoolman is optional. IFS Manager must remain fully usable when Spoolman is absent, disabled or temporarily unavailable.

When enabled, the target is **full spool-library integration**, not only a read-only metadata badge.

The target contract includes:

- per-slot binding to a concrete Spoolman spool entity;
- native search/select/bind/unbind workflows;
- ingestion of available manufacturer/vendor, material, color, name/series, weight/remaining amount and other useful supported metadata;
- preservation of Plugins AD5X richer appearance fields when Spoolman cannot represent them;
- normalized representation of Spoolman availability/synchronization state;
- use of the bound physical spool in the frontend-neutral pre-print plan;
- remaining-filament warnings when trustworthy source data makes them possible;
- lifecycle synchronization through supported Spoolman contracts when consumption/update integration is enabled;
- graceful degradation when Spoolman is unreachable;
- no deletion of the external spool entity merely because a physical IFS lane was emptied/unbound.

Source authority must remain explicit. Physical IFS state is never inferred from Spoolman metadata.

## 6. Native UX in every supported Klipper UI

Supported product targets:

1. Fluidd;
2. Mainsail;
3. HelixScreen;
4. GuppyScreen;
5. KlipperScreen.

The implementation MUST be native to each frontend's own component/navigation/dialog/notification model.

The following are specifically **not accepted as final integrations**:

- iframe embedding;
- WebView embedding of a standalone manager;
- an external page opened from a thin frontend button;
- duplicated standalone mini-apps with their own business logic;
- frontend-local reimplementation of safety or mapping semantics.

The existing/legacy Fluidd-style embedded IFS/Spoolman approach is therefore an anti-pattern for the new manager, not the target architecture.

Native does not mean pixel-identical. Each UI should use its own native primitives while preserving the same product concepts, terminology, capabilities, warnings, actions and outcomes.

## 7. Cross-frontend feature parity

Core operational features must not exist only in one privileged frontend.

The product should converge on feature parity for:

- lane/spool state;
- rich material metadata;
- Spoolman binding when enabled;
- operational actions;
- tool mapping;
- slicer/job preview;
- pre-print plan;
- warnings/blockers;
- safe multi-color start;
- endless/infinite-spool functions when enabled;
- diagnostics/advanced state appropriate to that UI.

Release staging may temporarily introduce a reference implementation first, but missing adapters remain unfinished product scope, not a completed feature.

## 8. UX model — progressive disclosure

Maximum functionality must not turn the main screen into a developer/debug panel.

### Primary level

Optimized for immediate recognition and routine operation:

- four physical lanes/spools;
- color/multi-color appearance;
- material;
- useful spool name/vendor information;
- remaining amount when known;
- physical presence;
- active/current state;
- warnings/errors;
- obvious contextual actions.

### Pre-print level

The user should understand the job before starting it:

```text
T0  PLA  [requested appearance] -> Slot 3  [physical spool]
T1  PETG [requested appearance] -> Slot 1  [physical spool]
T2  PLA  [requested appearance] -> —       [action required]
```

Simple healthy case: a clear ready state and one obvious continuation action.

Problem case: explain what is wrong and offer the relevant correction workflow instead of only displaying an opaque error code.

### Advanced level

For experienced users:

- manual tool mapping;
- source/metadata overrides;
- Spoolman binding details;
- endless-spool configuration;
- compatibility/synchronization controls;
- other expert operations.

### Diagnostics level

Technical evidence remains available but visually subordinate:

- raw/provider states;
- compatibility projection details;
- source/provenance;
- failure codes;
- hardware/runtime diagnostics.

Principle: **expert functionality must be discoverable, not dominant**.

## 9. Visual/product acceptance

The current KlipperScreen four-card GTK implementation is a proven technical reference only.

Final product UX must be deliberately designed for the target surface (including AD5X 800×480 local display) and must remove desktop-GTK artifacts that are unsuitable for touch.

Acceptance should judge at least:

- at-a-glance lane recognition;
- touch target size;
- information hierarchy;
- multi-color/finish visualization;
- selected vs active vs empty vs error differentiation;
- minimal text density in routine mode;
- clear transitions between normal, warning and blocked states;
- consistent native interaction within each host UI;
- no HEX-first color identification in normal use;
- no requirement to understand Klipper/Z-Mod internals for routine operations.

## 10. Implementation order

The implementation should reuse the already hardware-proven backend and KlipperScreen work rather than restart from scratch.

Recommended sequence:

1. finish the frontend-neutral pre-print/tool-map contract;
2. complete the controlled Z-Mod compatibility/write and correct `PRINT_ZCOLOR` launch contract behind safety gates;
3. perform hardware acceptance of the new mapping/launch path before enabling production writes;
4. audit and close functional parity gaps against the stock Z-Mod Manager;
5. implement optional full Spoolman integration in the common backend;
6. expose/prove endless/infinite-spool and remaining safe Z-Mod functions through normalized actions;
7. build the product-grade native reference UX;
8. implement native Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen adapters against the same backend contract;
9. perform functional + visual acceptance per frontend.

Steps may overlap where safe, but backend semantics must not be duplicated in frontend code.

## 11. Non-negotiable safety/maintenance constraints

- no Z-Mod fork as the normal integration strategy;
- no parallel serial ownership of the IFS device;
- no second slicer color matcher when Z-Mod provides the canonical matcher;
- no new mechanical/write operation considered proven by CI alone;
- no frontend-owned hardware safety policy;
- no Spoolman dependency for base printing/IFS availability;
- no merge/Ready for Review without explicit owner acceptance under the project workflow.

## 12. Definition of product completion

IFS / Materials Manager is product-complete only when:

- normal users can operate the IFS without the stock Z-Mod Manager;
- expert functionality remains available without dominating the normal workflow;
- optional Spoolman integration behaves as a real spool-library integration;
- supported UI integrations are native rather than embedded standalone pages;
- core feature semantics are consistent across Fluidd, Mainsail, HelixScreen, GuppyScreen and KlipperScreen;
- final UX is understandable, attractive and touch-appropriate while preserving advanced Klipper flexibility;
- every enabled mechanical/print mutation has passed its required real-printer acceptance gate.
