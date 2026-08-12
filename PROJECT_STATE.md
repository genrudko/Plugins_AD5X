# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить актуальный контекст без чтения длинной истории чата. История решений хранится в `DECISIONS.md`, история изменений — в Git.

**Последнее обновление:** 2026-08-13  
**Текущая фаза:** Phase 0 — Platform Foundation  
**Статус:** Fluidd frontend shell PoC accepted; backend contract v1 accepted; backend repository PoC accepted; real-printer backend/managed-copy/rollback acceptance PASS; production installer lifecycle integration implemented / repository tests PASS; coordinator review pending  
**Активный issue:** [#8 — PLATFORM-FOUNDATION-002: определить Plugins AD5X backend capability/API contract](https://github.com/genrudko/Plugins_AD5X/issues/8)  
**Состояние реального принтера после controlled acceptance:** исходный baseline восстановлен; backend/config удалены; Moonraker и `ad5x_custom` CLEAN; Camera 1/2 и IFS PASS

---

## 1. Архитектурная цель и границы

Plugins AD5X — UX/integration layer для Flashforge AD5X поверх Z-Mod/Klipper/Moonraker, а не новая прошивка и не форк Z-Mod.

Основные инварианты:

- GitHub и фактический код — источник истины;
- Z-Mod не форкаем;
- один backend/API обслуживает Fluidd, будущий Mainsail и local screen;
- frontend не определяет hardware/business capabilities самостоятельно;
- UI/existing API/macros предпочтительнее отдельного daemon;
- steady-state polling и тяжёлые сервисы на AD5X не вводятся без доказанной необходимости;
- ошибка Plugins AD5X не должна лишать пользователя базовой печати через Z-Mod;
- install/update/uninstall должны иметь validation, backup и rollback.

Главный UX-критерий остаётся прежним:

> **90% повседневных действий должны выполняться без Wiki, SSH, консоли и знания названий макросов.**

---

## 2. Репозитории, ветки и принятые baselines

| Репозиторий | Ветка | Роль / актуальный факт |
|---|---|---|
| `genrudko/Plugins_AD5X` | `main` | стабильная публичная ветка |
| `genrudko/Plugins_AD5X` | `dev` | текущая Platform Foundation / integration разработка |
| `ghzserg/fluidd` | `develop` | Z-Mod Fluidd upstream |
| `genrudko/fluidd` | `develop` | upstream-sync branch |
| `genrudko/fluidd` | `ad5x-dev` | рабочая ветка UI Plugins AD5X |

Fluidd foundation acceptance:

```text
ghzserg/fluidd:develop   7f024c08aac4093aa8aa2e26e329df5832ebe778
genrudko/fluidd:develop  7f024c08aac4093aa8aa2e26e329df5832ebe778
genrudko/fluidd:ad5x-dev c56cec9a2c846ee5b492242887051c8d2d74eb5a
compare ad5x-dev vs develop: ahead_by 11 / behind_by 0
```

Backend contract discovery was verified against:

```text
ghzserg/z_ad5x:1.7                 2e32155d00e464094b8c7197e23783ec821a112c
ghzserg/zmod_moonraker:main        a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e
Arksine/moonraker:master            d5ee17128bb88434aacdab90c2e9e990e2b64e4a
```

The physical AD5X runtime was subsequently confirmed directly:

```text
Moonraker Git HEAD: a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e
Moonraker branch:   main
Moonraker path:     /opt/config/base/moonraker
runtime symlink:    /root/moonraker-env/moonraker -> /opt/config/base/moonraker
Python:             3.12.9
origin:             ghzserg/zmod_moonraker.git
```

Installed `ad5x_custom` on the printer during acceptance remained on stable `main` at:

```text
735ef25a42cc6097500bd8177989e7f9656a4dda
```

and remained Git CLEAN. Controlled testing did **not** switch that installed checkout to `dev`.

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

Unit result at acceptance: 20 test files / 415 tests PASS. Dynamic Vuex registration without changes to the Fluidd root store was therefore confirmed.

---

## 4. Backend contract v1 — accepted

D-022 defines an optional in-process Moonraker component:

```text
component: plugins_ad5x
config:    [plugins_ad5x]
```

Production read-only snapshot contract:

```text
HTTP:     GET /server/plugins_ad5x/snapshot
JSON-RPC: server.plugins_ad5x.snapshot
API:      1.0
backend:  release version, currently 0.1.2
```

Minimal snapshot envelope:

```text
api_version
backend_version
revision
backend.health
modules{}
```

State invalidation contract:

```text
internal event:     plugins_ad5x:snapshot_changed
wire notification:  notify_plugins_ad5x_snapshot_changed
```

`revision` is process-local and resets across Moonraker restart. Notification is low-frequency invalidation, not high-rate telemetry. After reconnect the frontend performs a full `server.info → snapshot` resync. No steady-state polling, separate daemon or own DB exists for Platform Foundation.

Repository-side component:

```text
moonraker/components/plugins_ad5x.py
```

Repository PoC commit baseline used for the real printer acceptance:

```text
2b02b7d8b1a8f7421173816cc5ddd93ffd578670
artifact SHA256:
8ae26bc4a9669147274a2b7d1caff86d28a69b70715504f6edd7c4cec1df6c3a
```

The component PoC is deliberately minimal: no hardware providers, polling, daemon, DB or blocking I/O.

---

## 5. Real AD5X backend acceptance — ACCEPTED

Controlled printer acceptance under issue #8 is complete.

### 5.1 Active runtime PASS

Managed-copy deployment was tested on the actual printer:

```text
source artifact
→ validation
→ atomic managed copy
→ /opt/config/base/moonraker/components/plugins_ad5x.py
→ [plugins_ad5x] activation
→ Moonraker load
→ API acceptance
```

Observed active state:

- `plugins_ad5x` present in `server.info.components`;
- `plugins_ad5x` absent from `failed_components`;
- `klippy_connected=true`;
- `klippy_state=ready`;
- `warnings=[]`;
- HTTP snapshot returned exact v1 envelope:

```json
{
  "api_version": "1.0",
  "backend_version": "0.1.2",
  "revision": 1,
  "backend": {"health": "ok"},
  "modules": {}
}
```

Baseline services while backend was active:

```text
Camera 1: PASS
Camera 2: PASS
IFS:      PASS
```

Expected Moonraker Git effect while installed was only the untracked managed runtime component. `ad5x_custom` remained CLEAN.

### 5.2 Mandatory rollback PASS

Controlled rollback was also accepted:

- printer idle precheck PASS;
- actual Moonraker process disappearance observed before filesystem restoration;
- original Moonraker include config restored;
- managed component and `plugins_ad5x*.pyc` removed;
- Moonraker and `ad5x_custom` Git status returned CLEAN;
- Moonraker started once and Klippy reached `ready`;
- `plugins_ad5x` absent after rollback;
- Camera 1/2 and IFS remained PASS;
- original Moonraker and `ad5x_custom` heads were preserved.

Post-test printer state is therefore the original clean baseline; no persistent backend/config from the PoC remains installed.

---

## 6. Lifecycle defect discovered on the real printer

The physical acceptance proved that this is **not** a reliable production primitive:

```sh
/etc/init.d/S65moonraker restart
```

Observed timing:

```text
SIGTERM:         23:50:13.211
Server Shutdown: 23:50:15.565
actual shutdown: ~2.35 s
```

The Z-Mod init script uses a fixed `sleep 2` between stop and start. In the observed run the new start happened while the previous Python process was still alive and reported:

```text
/root/moonraker-env/bin/python3 is already running
```

After the old process then exited, Moonraker was left stopped.

Production lifecycle is therefore fixed by D-023 as:

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

HTTP reachability alone is insufficient. `klippy_state=startup` is not final readiness. No automatic `kill -9` is used.

---

## 7. Production backend deployment integration — implemented in repository

The current issue #8 repository-side productionization integrates the accepted runtime model into the existing `install.sh`, without rewriting the Camera 2 / Notify / Timelapse / IFS contour.

Owned artifacts:

```text
source:
/opt/config/mod_data/plugins/ad5x_custom/moonraker/components/plugins_ad5x.py

runtime managed copy:
/opt/config/base/moonraker/components/plugins_ad5x.py

activation config:
/opt/config/mod_data/plugins/ad5x_custom/plugins_ad5x.moonraker.conf
```

Activation is intentionally separate from notifier ownership:

```ini
[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]
[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]
```

The new backend config contains only:

```ini
[plugins_ad5x]
```

### 7.1 Validation and ownership

Before destination mutation the installer verifies:

- backend source exists and is non-empty;
- Python syntax via `python -B`/AST without `.pyc` generation;
- `API_VERSION == 1.0`;
- `BACKEND_VERSION` matches root `VERSION`;
- runtime Moonraker components directory exists;
- activation config is minimal and valid;
- an existing destination is demonstrably managed by Plugins AD5X.

Unknown existing destination fails safe and is not overwritten.

Runtime ownership is recorded by SHA-256. The managed copy is written to a temporary file **inside the destination directory**, permissions and hash are verified, and only then atomically renamed over the final destination.

### 7.2 Backup and rollback

Existing `snapshot()`, `restore_snapshot()` and installer rollback are extended rather than replaced. Snapshot now covers:

- backend runtime destination, including absent marker;
- backend ownership hash state;
- Moonraker include state;
- user Moonraker config and existing installer-owned state.

Rollback distinguishes service state and avoids recursive restart loops:

- failure before any stop attempt does not interrupt Moonraker unnecessarily;
- failure after stop restores files/config and returns Moonraker to its original running state;
- failure after start but before Klippy readiness performs a controlled stop/wait, restores snapshots, then one controlled start/readiness sequence if Moonraker was originally running.

### 7.3 Update / repair semantics

Managed copy intentionally means:

```text
Git checkout update ≠ runtime code immediately changed
```

The existing explicit apply operation is the deployment/repair primitive:

```sh
install.sh --apply-only
```

It validates the newly checked-out backend artifact, replaces the managed runtime copy atomically and activates it through the observed-stop lifecycle.

`--refresh-only` remains lightweight and only refreshes generated overlays; it does **not** restart/deploy Moonraker during the existing power-on path.

Moonraker hard recovery or `git clean` may delete the untracked runtime component. That is an expected external destructive event. `--apply-only` repairs/reinstalls the component. The Moonraker repo is **not** made artificially CLEAN with `.git/info/exclude` for this runtime file.

### 7.4 Status and uninstall

`install.sh --status` now distinguishes:

```text
backend source
backend runtime file
backend config include
Moonraker component presence / failed component
backend snapshot
Moonraker reachable but Klippy not ready
runtime service unavailable
```

A mere existing file cannot produce a healthy backend status.

`--uninstall` removes backend activation, the owned managed runtime copy, ownership state and `plugins_ad5x*.pyc`; unknown destination ownership fails safe. Existing user camera/IFS/timelapse/log/backup preservation semantics remain intact.

The existing full power-cycle message is retained for the older camera/power-on contour. Backend activation itself uses only the controlled Moonraker lifecycle and does not introduce an extra printer reboot requirement.

### 7.5 Repository verification

Current repository-side verification for this productionization step:

```text
sh -n install.sh                                      PASS
python3 -m unittest discover -s tests -v             PASS (24/24)
```

Breakdown:

```text
existing backend component contract tests: 8/8 PASS
new installer/backend lifecycle tests:      16/16 PASS
```

Coverage includes source validation, managed/unknown destination ownership, atomic path, absent/previous snapshot restoration, exact-once config activation, uninstall cleanup, lifecycle ordering, HTTP-vs-Klippy readiness, `startup` rejection, `ready` acceptance, timeout, explicit apply semantics and prohibition of `S65moonraker restart` in backend deployment lifecycle.

No real-printer write/restart operation is part of this repository-side productionization step.

---

## 8. What is explicitly out of scope now

Until coordinator review of issue #8 completes, do **not** expand this work into:

- another printer installation/SSH write/restart test;
- Fluidd production RPC replacement/deployment;
- Hardware / Mods Manager implementation;
- Side/AUX/PLA Fan implementation;
- IFS Manager UI;
- Calibration Center;
- Print Preflight;
- Camera Manager productization;
- Mainsail/HelixScreen parity;
- module manifest format finalization;
- separate daemon/DB;
- Z-Mod fork or tracked Moonraker/Z-Mod source modifications.

Issue #8 remains OPEN for coordinator review; it is not to be closed by the implementation executor.

---

## 9. Accepted decisions relevant to the current gate

See `DECISIONS.md`. Most important here:

- D-014 — fail-safe is more important than convenience;
- D-018 — Fluidd two-seam integration boundary;
- D-019 — static `/ad5x`, capability-gated navigation;
- D-020 — two-stage backend-owned capability detection;
- D-021 — downstream-only Fluidd CI;
- D-022 — optional Moonraker backend contract v1;
- **D-023 — backend runtime is a managed copy with observed-stop lifecycle.**

D-023 resolves the deployment implementation detail left open by D-022.

---

## 10. Remaining Platform Foundation work after this review

This step does not by itself complete all of Phase 0. Remaining work must be selected by the coordinator after issue #8 review. Candidate unresolved Phase 0 items include:

- replacing the provisional Fluidd RPC seam with the accepted production snapshot API;
- production Fluidd deployment/update strategy;
- minimal module/provider/state contract needed by the first real module;
- storage/state ownership policy where persistent module state is actually required;
- minimal developer guidance for subsequent modules.

The first real hardware use case after Platform Foundation remains Side/AUX/PLA Fan, but it must not be pulled into issue #8.

---

## 11. Context recovery rule

A new coordinator should, before changing anything:

1. read `ROADMAP.md`;
2. read `ARCHITECTURE.md`;
3. read `PROJECT_STATE.md`;
4. read `DECISIONS.md`;
5. open issue #8 including the latest printer-acceptance and implementation comments;
6. verify the current `genrudko/Plugins_AD5X:dev` head and any commits after the state recorded here;
7. treat GitHub/code as authoritative over old chat history;
8. never infer printer state from repository state — physical-runtime claims require observed evidence.
