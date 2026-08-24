# IFS Manager — Mainsail integration discovery — 2026-08-24

Status: source-verified integration decision for IFS Manager.

## Source pin

Official `mainsail-crew/mainsail`, `develop`, `cce05e4958765b224c4b6c56b21dc76f31216626`.

Evidence: `MmuPanel.vue`, `mixins/mmu.ts`, `mixins/navigation.ts`, `SidebarItem.vue`, `store/files/getters.ts`, `mixins/theme.ts`.

## Findings

Current Mainsail has substantial native Happy Hare/MMU UI: topology, gate/tool mapping, endless-spool groups, print mapping, maintenance and recovery. The panel activates from a Klipper `mmu` object. When enabled it exposes real Happy Hare commands including `MMU_SELECT`, `MMU_CHECK_GATES`, `MMU_STATS`, Spoolman, mapping, recovery and maintenance flows.

Plugins AD5X therefore MUST NOT publish synthetic `mmu`/`mmu_machine` objects merely to obtain Mainsail visuals. That would advertise unsupported semantics and create a command surface that does not safely map to Z-Mod ownership.

Mainsail `.theme` is not a component plugin API: `custom.css` is presentation only and `.theme/navi.json` creates ordinary `href` links. It cannot register an internal Vue route/component or inject an IFS panel.

## Decision

First-party Mainsail support requires a small Mainsail adapter/fork consuming the shared Plugins AD5X backend directly. A `navi.json` external link may be a transition fallback, but does not satisfy native semantic parity.

The adapter MUST NOT emulate Happy Hare, send `MMU_*`, duplicate IFS business logic, bypass Z-Mod provider paths, or expose hardware-gated print/recovery/endless/external mutations.

Minimum scope: native IFS route/navigation; normalized four-slot topology and metadata; backend permissions; Auto/Hybrid/Expert; pre-print preview/draft/prepare; read-only equivalent-spool/diagnostics/Orca/external status; native-display maintenance suspension.

Implementation is blocked only on a writable Mainsail fork/repository; the shared backend contract needs no redesign.
