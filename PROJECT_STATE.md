# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить актуальный контекст без чтения длинной истории чата. История решений хранится в `DECISIONS.md`, история изменений — в Git.

**Последнее обновление:** 2026-08-16  
**Текущая фаза:** Phase 0 foundation + approved parallel product experiment  
**Основной новый work item:** [#13 — CALIBRATION-SUBSYSTEM-002: explainable safe Auto-Z, mesh policy and multi-frontend Calibration Center](https://github.com/genrudko/Plugins_AD5X/issues/13)  
**Рабочая ветка:** `feature/z-calibration-subsystem-v2`  
**База ветки:** `dev` @ `ab25f96c017d56fe3a754ce4d05664c710dd2a80`  
**Последний exact-head с изменением implementation:** `b852f25c2c5f52d62ee65a83ea3f420d4b327bd0`  
**Repository gates для implementation:** `Z Calibration Core` run `31954499638` — compile PASS, shell syntax PASS, **117/117 tests PASS**  
**Platform Foundation issue #8:** остаётся OPEN / coordinator review pending; его принятый backend/managed-copy contract используется как foundation и не переоткрывается автоматически  
**Старый Calibration Center:** issue #5 CLOSED `not_planned`; Draft PR #6 CLOSED / UNMERGED / research-history only

---

## 1. Архитектурная цель и границы

Plugins AD5X — UX/integration layer для Flashforge AD5X поверх Z-Mod/Klipper/Moonraker, а не новая прошивка и не форк Z-Mod.

Основные инварианты:

- GitHub и фактический код — источник истины;
- Z-Mod не форкаем;
- один backend/API обслуживает Fluidd, будущий Mainsail и local screens;
- frontend не определяет hardware/business capabilities самостоятельно;
- UI/existing API/macros предпочтительнее отдельного daemon;
- steady-state polling и тяжёлые сервисы на AD5X не вводятся без доказанной необходимости;
- ошибка Plugins AD5X не должна лишать пользователя базовой печати через Z-Mod;
- install/update/uninstall должны иметь validation, backup и rollback;
- hardware-safety решения проходят source/code verification + model/fake tests + controlled real-printer acceptance.

Главный UX-критерий остаётся прежним:

> **90% повседневных действий должны выполняться без Wiki, SSH, консоли и знания названий макросов.**

---

## 2. Репозитории, ветки и принятые baselines

| Репозиторий | Ветка | Роль / актуальный факт |
|---|---|---|
| `genrudko/Plugins_AD5X` | `main` | стабильная публичная ветка |
| `genrudko/Plugins_AD5X` | `dev` | интеграционная/экспериментальная база |
| `genrudko/Plugins_AD5X` | `feature/z-calibration-subsystem-v2` | новый CALIBRATION-SUBSYSTEM-002 |
| `ghzserg/fluidd` | `develop` | Z-Mod Fluidd upstream |
| `genrudko/fluidd` | `develop` | upstream-sync branch |
| `genrudko/fluidd` | `ad5x-dev` | рабочая ветка UI Plugins AD5X |

Fluidd foundation acceptance:

```text
ghzserg/fluidd:develop   7f024c08aac4093aa8aa2e26e329df5832ebe778
genrudko/fluidd:develop  7f024c08aac4093aa8aa2e26e329df5832ebe778
genrudko/fluidd:ad5x-dev c56cec9a2c846ee5b492242887051c8d2d74eb5a
compare ad5x-dev vs develop at acceptance: ahead_by 11 / behind_by 0
```

Backend contract discovery baseline:

```text
ghzserg/z_ad5x:1.7                 2e32155d00e464094b8c7197e23783ec821a112c
ghzserg/zmod_moonraker:main        a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e
Arksine/moonraker:master            d5ee17128bb88434aacdab90c2e9e990e2b64e4a
```

Physical AD5X runtime previously confirmed:

```text
Moonraker Git HEAD: a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e
Moonraker branch:   main
Moonraker path:     /opt/config/base/moonraker
runtime symlink:    /root/moonraker-env/moonraker -> /opt/config/base/moonraker
Python:             3.12.9
origin:             ghzserg/zmod_moonraker.git
```

Installed stable `ad5x_custom` baseline during prior backend acceptance:

```text
735ef25a42cc6097500bd8177989e7f9656a4dda
```

The exact current printer runtime must still be re-read before any new CALIBRATION-SUBSYSTEM-002 deployment. Repository state never substitutes for live-runtime evidence.

---

## 3. Phase 0 frontend foundation — accepted

Issue #7 is completed. Fluidd integration follows D-018–D-021.

Ownership boundary:

```text
src/ad5x/**
```

Normal upstream Fluidd patch surface is limited to:

```text
src/components/layout/AppNavDrawer.vue
src/router/index.ts
```

The route `/ad5x` is static; the navigation entry is capability-gated. Direct navigation without backend fails safely as `backend unavailable` and does not issue AD5X-specific RPC.

Capability detection is two-stage:

```text
Moonraker server.info.components
        ↓ coarse presence
plugins_ad5x present?
        ↓ yes
server.plugins_ad5x.snapshot
        ↓
version / backend health / module capabilities and state
```

Accepted Fluidd feature-head:

```text
c56cec9a2c846ee5b492242887051c8d2d74eb5a
```

Final downstream CI run `31621932415` succeeded with:

```text
pnpm i --frozen-lockfile   PASS
pnpm run lint --no-fix     PASS
pnpm run type-check        PASS
pnpm run test:unit         PASS
pnpm run circular-check    PASS
pnpm run build             PASS
```

Unit result at acceptance: 20 test files / 415 tests PASS.

**Frontend drift found during CALIBRATION-SUBSYSTEM-002:** the accepted branch still contains an old PoC `plugins_ad5x.get_capabilities` adapter even though the authoritative backend contract is `server.plugins_ad5x.snapshot`. The first Calibration UI slice must replace that stale adapter before rendering module state.

---

## 4. Backend contract v1 — accepted foundation, extended by CALIBRATION-SUBSYSTEM-002

D-022 defines an optional in-process Moonraker component:

```text
component: plugins_ad5x
config:    [plugins_ad5x]
```

Production snapshot contract:

```text
HTTP:     GET /server/plugins_ad5x/snapshot
JSON-RPC: server.plugins_ad5x.snapshot
API:      1.0
backend:  release version, current 0.1.2
```

Snapshot envelope:

```text
api_version
backend_version
revision
backend.health
modules{}
```

`modules.z_calibration` now exposes frontend-neutral runtime/safety/offset state. Current implemented read-only endpoints also include:

```text
POST /server/plugins_ad5x/z_calibration/reconcile
GET  /server/plugins_ad5x/z_calibration/diagnostics
```

State invalidation contract:

```text
internal event:     plugins_ad5x:snapshot_changed
wire notification:  notify_plugins_ad5x_snapshot_changed
```

`revision` is process-local and resets across Moonraker restart. Notification is low-frequency invalidation, not high-rate telemetry. After reconnect the frontend performs a full `server.info → snapshot` resync.

Repository-side components:

```text
moonraker/components/plugins_ad5x.py
moonraker/components/plugins_ad5x_zcalibration.py
```

CALIBRATION-SUBSYSTEM-002 extends this shared backend model; no second daemon/backend was introduced.

---

## 5. Real AD5X backend acceptance — accepted prior evidence only

Managed-copy deployment and mandatory rollback were previously accepted on the actual printer for the Platform Foundation backend primitive.

Observed active state included:

- `plugins_ad5x` present in `server.info.components`;
- absent from `failed_components`;
- `klippy_connected=true`;
- `klippy_state=ready`;
- snapshot API returned the expected v1 envelope;
- Camera 1/2 and IFS remained functional.

Mandatory rollback restored the original baseline, removed the managed backend/config and returned Moonraker/ad5x_custom to clean state.

This acceptance proves the deployment primitive, **not** the new Z Calibration logic/hook/helper. New CALIBRATION-SUBSYSTEM-002 runtime artifacts still require their own controlled real-printer acceptance.

---

## 6. Managed-copy lifecycle — accepted and extended

D-023 remains authoritative.

The unreliable primitive:

```sh
/etc/init.d/S65moonraker restart
```

must not be used for Plugins AD5X backend deployment/update/uninstall/rollback.

Production lifecycle:

```text
stop
↓
observe actual moonraker.py process count == 0
↓
filesystem/config transition
↓
start
↓
wait /server/info
↓
wait klippy_connected=true
↓
wait klippy_state=ready
```

CALIBRATION-SUBSYSTEM-002 now extends the managed runtime artifact set atomically to:

```text
plugins_ad5x.py
plugins_ad5x_zcalibration.py
```

Both files have ownership checks, separate SHA256 state, source/runtime verification, install/uninstall snapshots and rollback restoration. An unknown/foreign Z-calibration helper blocks combined deployment before the existing main backend is replaced.

The installer also prepares the late Klipper extension hook:

```text
[include plugins/ad5x_custom/z_calibration.cfg]
```

which overrides Z-Mod's deliberately empty `_USER_START_PRINT` extension point only after the installer idle/snapshot gates. The hook itself performs no `PROBE`, motion or direct Z-offset write; it reports which Z-Mod offset branch (`global` / `job` / `none`) has already executed.

---

## 7. CALIBRATION-SUBSYSTEM-002 — accepted design baseline

Issue #13 is the new work item. It supersedes the old profile-based CALIBRATION-CENTER-001 product model.

Canonical design sources on this branch:

- `docs/Z_CALIBRATION_SUBSYSTEM_V2.md`;
- `docs/Z_CALIBRATION_REVERSE_ENGINEERING_2026-08-16.md`;
- `docs/Z_CALIBRATION_TEST_PLAN_V2.md`;
- `docs/HANDOFF_Z_CALIBRATION_SUBSYSTEM_V2.md`;
- D-024–D-028 in `DECISIONS.md`.

### 7.1 Effective Z-offset model

```text
Auto-Z alignment
+ persistent user Z trim
+ slicer/job Z offset
+ live babystepping
────────────────────────
= effective Klipper gcode_offset
```

The final runtime value remains standard Klipper state. Backend stores provenance; UI explains it.

### 7.2 No normal persistent Z profile per hotend/nozzle

Changing tool geometry is handled by a fresh validated nozzle↔bed reference. A large confirmed delta becomes `hardware_change_suspected` / full-calibration state, not a blind large Auto-Z correction.

### 7.3 Bed mesh modes

```text
saved
saved+check   ← recommended normal mode
runtime
```

Runtime mesh is job/session-scoped by default and does not overwrite saved/default mesh without explicit user action.

### 7.4 Optional first-layer verification

First-layer verifier is user-invoked/recommended, not mandatory on every print.

Automatic measurement establishes geometry; printed first layer verifies full process quality and user squish preference.

Valid state may therefore be:

```text
Geometry calibration: PASS
First-layer verification: NOT RUN
```

provided safety/metrology gates pass.

### 7.5 Plate protection

Fail-closed core requires bounded search, conservative initial acquisition, slow final approach, repeated sample validation, outlier/drift handling, large-delta escalation, state-safe cancellation and no persistent mutation on failure.

H7/load-cell data is secondary until its latency/stop-distance semantics are separately proven as sufficient for a hard watchdog.

---

## 8. Current implementation status

### Milestone A — core/fake: repository-green

Implemented:

- dependency-free core model;
- offset provenance/composition with replace-not-accumulate Auto-Z;
- state machine and atomic abort/cancel cleanup;
- bounded trusted-reference and explicit initial-acquisition envelopes;
- probe spread/drift/plausibility validation;
- mandatory independent second-series confirmation for large delta;
- saved/saved+check/runtime mesh decisions;
- bounded structured diagnostics;
- H7 secondary-signal model;
- deterministic fake Klipper/Moonraker adapter;
- mutation-sensitive lower-bound test.

### Milestone B — backend lifecycle binding: repository-green

Implemented:

- standard Klipper effective-offset reconciliation;
- explicit `external_unknown` provenance;
- Z-Mod post-`_START_PRINT` adoption for its real three-way `global/job/none` offset semantics;
- idempotent retry: no second offset application;
- mismatch rejection before write;
- terminal job and disconnect cleanup of job/Auto-Z/live transient provenance;
- optional runtime detection of the loaded `_USER_START_PRINT` hook marker;
- internal job-start remote method refuses to operate when that marker is absent/incompatible;
- optional hook query failure does not make the whole backend unavailable;
- Z-offset write gate defaults **closed** and is independent of hook-loaded state;
- calibration motion actions remain disabled.

### Milestone C — installer/config lifecycle: repository-green

Implemented:

- helper source validation and managed-copy deployment;
- foreign destination fail-closed;
- separate main/helper ownership hashes;
- combined source/runtime verification;
- install/uninstall snapshot + rollback for both Moonraker files;
- bytecode cleanup;
- late `_USER_START_PRINT` hook asset and controlled include;
- exact tests proving hook activation ordering after idle/snapshot gates;
- no direct Z/probe/motion command in the hook.

Exact repository evidence for the latest implementation-changing head:

```text
head: b852f25c2c5f52d62ee65a83ea3f420d4b327bd0
compare vs dev at that head: ahead 31 / behind 0
workflow: 31954499638
compile: PASS
shell syntax: PASS
repository tests: 117 / 117 PASS
```

Later commits may update coordination/docs only; they do not supersede the exact implementation gate above unless implementation files change again.

No CALIBRATION-SUBSYSTEM-002 artifact has been deployed to the live AD5X in this work item. No live Z movement or Z-offset mutation has been performed.

---

## 9. Reverse-engineering state — proven vs unresolved

### Proven enough to constrain implementation

- current probe coordinate forms differ by configured `[probe] z_offset=-0.25`;
- `last_probe_position.z` matches user-facing contact estimate;
- `WeightValue` folds sign through `abs()`, raw `H7` preserves sign;
- `LOAD_CELL_TARE` may accept near-zero rather than exact zero;
- current stable repeated center probes converge around the present Bambu Mod geometry;
- bed mesh clear/load, `auto + G28` order and full power-cycle did not reproduce the early ~0.3 mm anomaly;
- `GET_POSITION` did not reveal a hidden software shift of ~0.3 mm;
- H7 has timing/relaxation behaviour and is not proven as instantaneous hard-force signal;
- historical `MESH_DATA` absolute baseline is not valid current-geometry evidence according to owner hardware history.

### Unresolved / must not become architecture assumptions

- exact cause of the early `≈ -1.5167 mm` anomaly;
- whether debris/plastic caused it;
- whether repeated contact always creates mechanical conditioning;
- whether any specific thermal soak law explains map evolution;
- whether `g28_tenz` is necessary;
- universal release-safe numeric thresholds;
- H7 hard-watchdog latency/stop distance.

---

## 10. Old CALIBRATION-CENTER-001 disposition

Issue #5 is CLOSED as superseded/not planned.

Draft PR #6 is CLOSED / NOT MERGED.

Its branch diverged heavily from current `dev` and contained a profile/G92-oriented product model that is no longer accepted.

Useful historical evidence may be inspected, especially:

- repeated measurement/statistics;
- installer isolation;
- cancellation lessons;
- physically rejected first-layer pattern evidence;
- previous safety tests.

Do not cherry-pick the old architecture wholesale.

---

## 11. Current implementation sequence

Completed repository gates:

1. formal core model and fake Klipper/Moonraker adapter;
2. exhaustive repository/model/safety tests;
3. shared `plugins_ad5x` backend runtime/provenance binding;
4. structured bounded diagnostic log;
5. installer/config integration using existing managed-copy lifecycle.

Next:

6. correct the stale Fluidd capabilities PoC to consume `server.plugins_ad5x.snapshot` and add the first read-only Z Calibration status slice using accepted `src/ad5x/**` seams;
7. expand Fluidd to the full Calibration Center only as backend actions become repository-safe;
8. controlled real-printer acceptance gates;
9. optional first-layer verifier physical acceptance;
10. actual nozzle/hotend or plate-change acceptance;
11. later parity adapters for Mainsail, HelixScreen, Guppy and KlipperScreen after its platform acceptance.

`docs/Z_CALIBRATION_TEST_PLAN_V2.md` remains mandatory for implementation/release.

---

## 12. Issue #8 relationship / scope guard

Issue #8 remains OPEN because its coordinator review was not formally closed in the root `dev` state at branch creation.

CALIBRATION-SUBSYSTEM-002 is an owner-approved parallel work item on its own feature branch and may build on already accepted D-022/D-023 backend primitives.

It must **not** silently reinterpret unfinished Platform Foundation questions. If implementation needs a breaking change to the shared backend API/deployment contract, stop and resolve that as an explicit architecture decision instead of burying it in Calibration code.

No merge of this feature into `dev` is implied by merely opening/working the Draft PR.

---

## 13. Context recovery rule for a new implementation chat

Before changing code:

1. read `ROADMAP.md`;
2. read `ARCHITECTURE.md`;
3. read this `PROJECT_STATE.md`;
4. read `DECISIONS.md`, especially D-022–D-028;
5. open issue #13;
6. read all four Z Calibration v2 docs listed in section 7;
7. verify current `dev`, feature branch and Draft PR exact heads/behind state;
8. inspect current backend/installer/tests;
9. verify old PR #6 is closed/unmerged;
10. inspect live printer runtime read-only before any physical deployment;
11. treat repository/code/runtime evidence as more authoritative than old chat history.

No Ready for Review or merge without explicit owner command.
