# IFS Manager — visual and technical reference pack

Status: canonical reference pack for `IFS-MANAGER-001` / issue #15.

This document records the visual, interaction and implementation references used to design Plugins AD5X IFS / Materials Manager. It exists so frontend work is not reconstructed from memory or from screenshots without provenance.

This document is **not** the provider/hardware contract. Z-Mod behavior, AD5X hardware semantics and mutation acceptance remain governed by the dedicated discovery/architecture documents. A reference below is an inspiration or implementation precedent, not permission to copy unsupported semantics into AD5X.

## 1. Canonical reference direction

The existing product requirements remain authoritative:

- **Main IFS dashboard:** HelixScreen AD5X physical topology + Happy Hare information/visual hierarchy, creatively adapted to AD5X.
- **Pre-print mapping:** Happy Hare `Map Tools` / Tool-to-Gate mapping interaction, adapted to the simpler AD5X topology and to Plugins AD5X backend-owned validation.
- **Metadata/provenance/conflict UX:** PAXX Snapmaker U1 Filament Manager is a strong reference for presenting multiple metadata sources without pretending they are the same truth domain.
- **Everyday UX target:** Bambu/AMS-style low-friction operation is a quality target only; it is not an implementation or provider contract.
- **Provider/functionality baseline:** Z-Mod remains the authority for proven AD5X IFS mechanics, matching and print lifecycle.

The resulting product is intentionally not a clone of any one reference.

## 2. Pinned source set

All source repositories below were inspected read-only. SHAs pin the exact implementation state used for this reference pass on 2026-08-24.

| Reference | Repository / ref | Pinned SHA | Primary use |
|---|---|---|---|
| Official Fluidd | `https://github.com/fluidd-core/fluidd.git` / `develop` | `192279a8c6425012e89a245c636a2a47042e9cf0` | Native MMU dashboard and pre-print mapping implementation |
| Happy Hare | `https://github.com/moggieuk/Happy-Hare.git` / `main` | `d5cce9f96991b270ff570b7497bbf6b4463a82b9` | Gate/Slicer Tool/TTG semantics, automapping, MMU behavior vocabulary |
| Happy Hare Fluidd fork | `https://github.com/moggieuk/fluidd-happy-hare-edition.git` / `develop` | `8f492e9e39218ca116f4e9bcdb7425ceffae6a8f` | Historical/latest Happy Hare UI integration reference |
| HelixScreen | `https://github.com/prestonbrown/helixscreen.git` / `main` | `a76c1c5452e1dee9f1c62838d79b75f55b7e2763` | Physical topology, AD5X IFS backend precedent, print-start mapping orchestration |
| PAXX Snapmaker U1 Extended Firmware | `https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware.git` / `develop` | `2f7b3f5e9802956b2ebd58309fc0130cd07524c3` | Four-channel filament metadata, provenance/conflict, Spoolman UX |
| Snapmaker U1 Fluidd | `https://github.com/Snapmaker/u1-fluidd.git` / `main` | `727005d55885dedddb67e69cb7881b0a8dfd0544` | Vendor Fluidd integration precedent |

Web/wiki references:

- Happy Hare Tool and Gate Maps: `https://github.com/moggieuk/Happy-Hare/wiki/Tool-and-Gate-Maps`
- Happy Hare Mainsail / Fluidd Integration: `https://github.com/moggieuk/Happy-Hare/wiki/Mainsail-Fluidd-Integration`
- HelixScreen gallery/repository: `https://github.com/prestonbrown/helixscreen`
- PAXX Extended Firmware release containing Filament Manager: `https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware/releases/tag/v1.5.2-paxx12-21`
- PAXX Filament Manager implementation PR: `https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware/pull/581`

## 3. Reference images

### 3.1 HelixScreen — physical topology

Primary image/reference:

- HelixScreen AMS / multi-filament panel: `https://helixscreen.org/_astro/ams.ClGTsLAD_Z1etjbS.webp`
- Repository gallery: `https://github.com/prestonbrown/helixscreen` (`Screenshots` → `AMS / Filament Management`)

What matters for AD5X:

- physical spools/sources are visually primary;
- sources visibly converge through a selector/path toward the toolhead;
- selected/active path is visually obvious;
- an external/bypass source is a separate path rather than a fake extra numbered slot;
- material/spool information is adjacent to the physical source;
- actions belong to the source or current physical context.

What must **not** be copied blindly:

- topology elements or sensors that do not exist on AD5X;
- generic multi-backend abstractions as user-visible complexity when only IFS is installed;
- assumptions from other AMS/MMU backends that conflict with Z-Mod/AD5X evidence.

### 3.2 Happy Hare Mainsail/Fluidd — information hierarchy and mapping

Primary visual references:

- Integration page: `https://github.com/moggieuk/Happy-Hare/wiki/Mainsail-Fluidd-Integration`
- Annotated Gate Map Editor image: `https://raw.githubusercontent.com/wiki/moggieuk/Happy-Hare/Mainsail-Fluidd-Integration/mainsail_annotated_gate_editor.png`
- Tool and Gate Maps: `https://github.com/moggieuk/Happy-Hare/wiki/Tool-and-Gate-Maps`

The main MMU panel is useful because it combines, in one hierarchy:

- loaded spool/gate visualization;
- active filament path and current operation;
- current filament details;
- contextual controls;
- compact TTG map;
- error/recovery state.

The Gate Map editor is useful for:

- selecting a physical source first, then editing its filament identity/attributes;
- keeping Spoolman linkage explicit;
- combining material/name/temperature/color with availability;
- showing advanced controls without making them the main dashboard.

Happy Hare sensor visualization is **not** a license to invent AD5X encoder, compression, hub, clog or other states. Only state with an actual AD5X/Z-Mod source may appear.

### 3.3 Happy Hare KlipperScreen — compact touchscreen precedent

Representative public images:

- Happy Hare MMU screen and Tool Picker are documented by the Happy Hare/KlipperScreen ecosystem and are useful for compact 800×480 interaction design.

Use them for:

- large touch targets;
- one-screen tool/source selection;
- color/material-first recognition;
- clear current tool/gate state.

Do not inherit its richer MMU sensor topology when AD5X cannot provide it.

### 3.4 PAXX Snapmaker U1 — provenance and conflict UI

Primary source:

- release screenshot section: `https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware/releases/tag/v1.5.2-paxx12-21#screenshots`
- implementation PR: `https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware/pull/581`

The release describes the `/filament/` Filament Manager as reconciling each channel across:

- Official printer/tag data;
- User-set filament;
- active Spoolman spool;
- raw RFID tag.

The GitHub crawler used during this reference pass did not expose the release image asset URL reliably, so the release screenshot section is pinned rather than inventing an asset URL. If the original user-provided screenshot is recovered, it should be added below with its original conversation/file provenance.

## 4. Official Fluidd implementation — pre-print reference

Happy Hare MMU support is present in current **official Fluidd**, not merely in an external theme or standalone UI.

### 4.1 Files inspected

At Fluidd SHA `192279a8c6425012e89a245c636a2a47042e9cf0`:

- `src/components/widgets/mmu/MmuCard.vue`
- `src/components/widgets/mmu/MmuEditTtgMapDialog.vue`
- `src/mixins/mmu.ts`
- `src/components/widgets/filesystem/FileSystem.vue`

### 4.2 Main MMU card

`MmuCard.vue` composes the MMU experience from dedicated pieces rather than one monolithic stateful component. It exposes:

- physical MMU machine visualization;
- filament status;
- gate/source summary;
- contextual controls;
- compact Tool-to-Gate map;
- error display;
- edit mapping / edit gate map / recover / maintenance actions;
- Spoolman synchronization when supported.

This is a useful structural precedent for Plugins AD5X: dashboard presentation should consume normalized state and capabilities rather than contain provider logic.

### 4.3 Print interception

`FileSystem.vue::handlePrint()` is the strongest direct pre-print UX precedent found in this pass.

For an MMU-enabled printer, Fluidd checks G-code metadata (`referenced_tools`). When the file qualifies as an MMU print, Fluidd:

1. does **not** immediately call ordinary `printerPrintStart`;
2. opens the MMU mapping dialog with the selected filename;
3. returns from the normal print path;
4. only after the user confirms mapping does the mapping dialog continue to print start.

This establishes the interaction pattern we want:

`user presses Print → pre-print mapping/validation → confirmation → production launch`

For Plugins AD5X, the final step must be our provider-owned Z-Mod launch contract, not Fluidd's generic `printerPrintStart`.

### 4.4 Mapping dialog

`MmuEditTtgMapDialog.vue` provides a concrete interaction model:

- dialog becomes `Print`-confirming when opened for a filename;
- shows slicer tools and current tool-to-gate mapping;
- supports selecting a tool and then choosing a physical gate;
- presents what the slicer expects (name/material/color/temperature);
- presents the mapped gate/source;
- shows mismatch alerts;
- keeps a complete local TTG vector;
- supports automatic mapping/reset-style behavior and EndlessSpool groups;
- submits the full map, then launches the file.

Important architectural difference: current Fluidd/Happy Hare computes part of mismatch logic in the frontend and sends provider G-code directly. Plugins AD5X must **not** copy that ownership split. Our frontend is a projection/editor; mapping validation, permissions, live-slot validation and launch gating stay backend-owned.

### 4.5 Happy Hare data semantics behind Fluidd

`src/mixins/mmu.ts` reflects three conceptually separate maps that are important to preserve in our model:

- Gate Map: what is physically/semantically loaded at each source;
- Slicer Tool Map: what the selected job expects for each `Tn`;
- TTG Map: which required `Tn` resolves to which physical gate/source.

That separation maps cleanly to Plugins AD5X's domains:

- live IFS source state + metadata;
- provider job requirements;
- `resolved_tool_map` / manual draft.

## 5. HelixScreen implementation — AD5X-specific precedent

### 5.1 Files inspected

At HelixScreen SHA `a76c1c5452e1dee9f1c62838d79b75f55b7e2763`:

- `src/ui/ui_ams_detail.cpp`
- `src/ui/ui_print_start_controller.cpp`
- `src/printer/ams_backend_ad5x_ifs.cpp`
- `docs/devel/FILAMENT_MANAGEMENT.md` as supporting design documentation.

### 5.2 Physical IFS presentation

`ui_ams_detail.cpp` builds slot/source widgets from backend system information, lays them out as a physical tray, draws the filament path, handles external spool presentation separately and routes contextual actions through backend capabilities.

This is the primary topology reference for the Plugins AD5X Expert dashboard.

### 5.3 Print-start mapping orchestration

`ui_print_start_controller.cpp` demonstrates that mapping is a **job-scoped print-start concern**, not merely a permanent dashboard configuration:

- reads user mappings from the print detail view;
- distinguishes automatic vs explicit mappings;
- checks backend mapping capabilities;
- can snapshot current firmware mapping before a temporary remap;
- restores mapping after terminal print states where appropriate;
- persists pending restore state and handles temporarily unavailable Klipper/backend state.

Plugins AD5X should adopt the job-scoped mindset, but not Helix's generic temporary-remap algorithm where Z-Mod provides a more appropriate provider-owned `PRINT_ZCOLOR` launch contract.

### 5.4 AD5X hardware evidence

`ams_backend_ad5x_ifs.cpp` is especially valuable because it contains real AD5X/Z-Mod operational knowledge, including physical presence and seated-channel handling around `IFS_STATUS` and multiple recovery/operation edge cases.

It is an implementation precedent and evidence source, but our own Z-Mod discovery and real-printer acceptance remain canonical before enabling mutations.

## 6. PAXX Snapmaker U1 Filament Manager implementation

### 6.1 Files inspected

At PAXX SHA `2f7b3f5e9802956b2ebd58309fc0130cd07524c3`:

- `overlays/firmware-extended/68-app-filament-ui/root/usr/local/filament-ui/html/index.html`
- `overlays/firmware-extended/68-app-filament-ui/root/usr/local/filament-ui/html/script.js`
- `overlays/firmware-extended/68-app-filament-ui/root/usr/local/filament-ui/html/style.css`
- `docs/spoolman.md`

Also inspected PR #581, which introduced the Filament Manager.

### 6.2 Useful UX concepts

The app builds four channel cards and distinguishes source/provenance explicitly. A channel can expose badges such as:

- `Official`
- `Spoolman`
- `User`
- `Unknown`
- `RFID`
- `Detecting`
- `Mismatch`

The channel detail can show material, rich/multiple colors, Spoolman ID, remaining weight and tag UID. Actions include refresh, user edit, reset and Spoolman spool selection.

A dedicated mismatch dialog compares raw RFID data against Spoolman or printer configuration field-by-field. Manual editing warns the user when it will override data currently coming from RFID or Spoolman.

This is an excellent precedent for **making provenance visible without conflating it with physical presence**.

### 6.3 Architecture we do not copy

The PAXX web app performs substantial reconciliation and mutation logic directly in browser JavaScript and sends G-code itself. Plugins AD5X intentionally does not follow this model:

- frontend does not become physical truth;
- frontend does not own mismatch/safety policy;
- frontend does not directly implement provider write sequences;
- all first-party UIs consume the same normalized backend contract.

Snapmaker U1 also has four independent toolheads/channels, while AD5X has one extruder with four IFS lanes. U1 semantics must not be projected onto AD5X merely because both UIs show four filament sources.

## 7. Additional Fluidd / FilaMan source-patch reference

PAXX PR #606 contains a reference-only source patch derived from `ManuelW77/fluidd` for embedding a FilaMan dashboard card, settings, AFC lane integration and spool selection into Fluidd's native Vue UI.

This is useful primarily as an **integration/packaging precedent**: filament management can appear as a first-class Fluidd component rather than a detached iframe or unrelated page.

It is not used as a canonical business-logic reference, and at the time inspected the PAXX README explicitly states that this source patch is not yet wired into their binary Fluidd packaging flow.

## 8. What Plugins AD5X deliberately borrows

### Main IFS dashboard

Borrow from Helix + Happy Hare:

1. Four physical source/spool cards are visually dominant.
2. Empty/present/error/active are immediately recognizable.
3. Material and representative rich appearance are visible on the source.
4. Physical path from the selected lane through selector to toolhead is understandable at a glance.
5. External/bypass is a separate source/path, not `Slot 5`.
6. Routine source actions are contextual; service/recovery detail is secondary.
7. Compact job mapping may be shown when relevant but does not dominate idle dashboard UX.

### Pre-print mapping

Borrow from Happy Hare / official Fluidd:

1. Normal `Print` is intercepted when IFS mapping is relevant.
2. Start from provider automatic proposal.
3. Show each required `Tn` with slicer-required material/color/name when known.
4. Show the proposed/selected physical IFS source alongside it.
5. Allow selecting a tool and remapping it to one of four physical lanes.
6. Keep/edit a **complete** mapping vector, not only currently visible rows.
7. Show ready/warning/blocked clearly.
8. One explicit confirmation leads to production launch.

Plugins AD5X difference: the backend evaluates the draft against the current provider preview and live IFS state. The UI must not independently reimplement matcher or launch safety rules.

### Filament metadata

Borrow from PAXX U1 + Happy Hare:

1. Make provenance discoverable with compact badges/labels.
2. Keep physical presence separate from metadata identity.
3. Make Spoolman binding explicit.
4. Show conflicts as conflicts, not as silently selected truth.
5. Allow user override only through an explicit edit flow with consequences visible.
6. Support richer color/finish metadata internally even when compatibility projections need one representative color.

## 9. What Plugins AD5X must not copy

- No fabricated encoder/hub/compression/clog/selector sensors from Happy Hare.
- No U1 assumption that four sources mean four independent extruders/toolheads.
- No permanent TTG mapping as the central idle-dashboard object.
- No client-side hardware authority or independent safety policy.
- No direct browser G-code sequence as the canonical write path.
- No direct `file.json` manipulation for Z-Mod print mapping.
- No independent duplicate matcher when Z-Mod already supplies canonical job matching.
- No real `PRINT_ZCOLOR`, physical mapping mutation, automatic equivalent-spool switch or unproven recovery motion before exact-SHA real-AD5X hardware acceptance.

## 10. Reference-derived IFS UX contract

This section is the implementation checkpoint to use before further frontend work.

### 10.1 Idle / dashboard

Expert view:

`IFS source cards → selector/path → toolhead`

Each of the four source cards should expose at minimum:

- lane number;
- physical present/empty/error;
- active/current indication;
- material;
- representative appearance;
- spool identity/remaining amount when trustworthy;
- provenance/detail drill-down;
- backend-authorized contextual actions.

Auto and Hybrid are progressive-disclosure views of the same backend state, not separate semantics.

### 10.2 Print-start

Canonical interaction:

`Print → provider job preview → automatic proposal → optional manual remap → backend revalidation → confirmation → provider-owned launch`

For the current hardware-gated stage, the last step remains disabled; UI work may progress through read-only preview and manual draft evaluation only.

A manual edit changes the complete `resolved_tool_map`. The backend re-evaluates:

- exact preview identity/token;
- required tool coverage;
- selected lane validity;
- live physical presence;
- mismatch/warning/blocker state;
- launch candidate state and permissions.

A frontend may choose how much of that to reveal in Auto/Hybrid/Expert, but it must not create different truth.

### 10.3 Metadata/provenance

Provenance should answer a simple user question: **“Why does the manager believe this is this spool/material?”**

The UI may show provider-observed metadata, local/user metadata, Spoolman identity and compatibility projections, but must preserve the distinction. `present=false` is physical truth and therefore an old concrete spool binding cannot remain displayed as the currently loaded spool.

## 11. Screenshot archive policy

From this point forward, visual references used for IFS implementation must be recorded here with:

- source URL or user-provided artifact identifier;
- date captured;
- upstream project/version/SHA where meaningful;
- what exact interaction or visual decision the image supports;
- whether it is authoritative evidence, an implementation precedent, or only visual inspiration.

### User-provided references

The original screenshots previously supplied in ChatGPT were not separately committed into this repository. When recovered by the user, add them here (or into a dedicated repository-owned reference-assets directory if redistribution/storage is appropriate) with an explicit `user-provided` provenance note. Do not silently substitute a similar public screenshot and claim it is the original.

## 12. Frontend implementation gate

Before continuing material changes to the IFS frontend:

1. compare the intended screen against this reference pack;
2. reconcile any recovered user screenshots with the upstream implementations above;
3. confirm which reference supplies each major interaction rather than designing from memory;
4. preserve the existing backend-owned state/mapping/safety architecture;
5. keep all real IFS write/launch operations hardware-gated until accepted on AD5X.

This gate is intended to prevent visual implementation from drifting away from the source material that motivated the product requirements.
