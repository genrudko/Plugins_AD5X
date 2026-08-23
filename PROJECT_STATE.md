# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить актуальный контекст без чтения длинной истории чата. История решений хранится в `DECISIONS.md`, история изменений — в Git.

**Последнее обновление:** 2026-08-23
**Текущая фаза:** IFS / Materials Manager v2 — `IFS-MANAGER-001`
**Статус:** architecture v2 + Orca `lane_data` + optional full Spoolman backend + Z-Mod-native plugin lifecycle implemented in `feature/ifs-manager-v1`; repository acceptance PASS (140/140 unit tests, lifecycle shell syntax, Python compile, `git diff --check`); hardware write gates remain closed
**Активный work item:** [#15 — IFS-MANAGER-001](https://github.com/genrudko/Plugins_AD5X/issues/15) / Draft PR #16 / `feature/ifs-manager-v1` (base `dev`)
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

Historical managed-copy deployment was tested on the actual printer. This remains hardware evidence for backend load/API compatibility, but its deployment ownership model is superseded by D-024:

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

## 7. Production plugin lifecycle integration — implemented in working tree

Canonical deployment now follows Z-Mod's native plugin lifecycle (D-024). Plugins AD5X source remains in `/opt/config/mod_data/plugins/ad5x_custom`; Klipper/Moonraker receive only plugin-owned symlinks plus normal config includes. No tracked core source file is patched or copied.

Runtime links:

```text
Klipper:
/opt/config/base/klipper/klippy/extras/ad5x_ifs.py
  -> /opt/config/mod_data/plugins/ad5x_custom/klipper/extras/ad5x_ifs.py

Moonraker:
/opt/config/base/moonraker/components/plugins_ad5x.py
/opt/config/base/moonraker/components/plugins_ad5x_ifs_model.py
/opt/config/base/moonraker/components/plugins_ad5x_ifs_interop.py
/opt/config/base/moonraker/components/plugins_ad5x_ifs_spoolman.py
  -> matching files in the Plugins AD5X checkout
```

Local `.git/info/exclude` entries hide only these known link paths from normal core `git status`; they do not modify tracked `.gitignore` and are removed on detach/uninstall. Foreign destinations fail closed. Previous owned managed-copy files are migrated only when legacy ownership can be proven.

### 7.1 Z-Mod hooks

- `install.sh` — initial activation / `ENABLE_PLUGIN`;
- `update.sh` — Update Manager reconciliation;
- `uninstall.sh` — `DISABLE_PLUGIN` runtime detach while retaining plugin checkout + Update Manager registration;
- `install.sh --uninstall` — explicit full unregister.

The update hook does not restart its parent Moonraker process. It re-links/reconciles and creates `runtime-restart-required`; Python changes become active after a normal new process/cold boot. Klipper Python extra changes still require a real new Klippy process; `FIRMWARE_RESTART` alone is not sufficient based on AD5X hardware evidence.

### 7.2 Rollback and recovery

Snapshot/restore preserves symlink identity/target, config includes, local exclude state and previous service state. Installer-owned activation/deactivation keeps the observed stop -> process-count-zero -> filesystem transition -> start -> HTTP -> Klippy-ready lifecycle from D-023.

A destructive core hard recovery/reclone may remove runtime links. Generic Z-Mod startup has not been proven to rerun every enabled plugin's install hook automatically after such a reclone, so explicit `ENABLE_PLUGIN`/`install.sh` repair remains the documented recovery path.

### 7.3 Spoolman consolidation

When the full IFS Manager is active, the legacy `/opt/config/mod_data/ifs_spoolman/start.sh` power-on path is not used. Full-manager Spoolman ownership belongs to Plugins AD5X backend + native Moonraker Spoolman, avoiding a second competing manager/consumption tracker. The standalone bridge remains a separate lightweight product path and is not declared deprecated by this change.

---

## 8. Current IFS v2 gate

Active work is issue #15 / Draft PR #16 on `feature/ifs-manager-v1`. The current checkpoint includes the frontend-neutral IFS model, Orca `lane_data`, optional full Spoolman integration and D-024 plugin lifecycle migration.

Still explicitly gated until source/hardware acceptance:

- production `PRINT_ZCOLOR` / `start_job`;
- applying pre-print mapping;
- Z-Mod material/color write projection;
- automatic equivalent/endless-spool switching;
- new recovery motion;
- automated external/bypass source control.

The full manager is not allowed to start the legacy standalone `/opt/config/mod_data/ifs_spoolman/start.sh` alongside its own backend. The standalone Spoolman bridge remains a separately useful lightweight product path and should evolve toward the same four-slot/active-spool semantics rather than compete with the full manager at runtime.

---

## 9. Current spool identity rule

Physical presence is authoritative. `present=false` outranks cached FlashForge/manual/Spoolman metadata. An empty slot must not expose the old spool as currently installed.

When a previously occupied slot becomes empty, Plugins AD5X removes the slot's current local/Spoolman binding and persists an identity-invalidated tombstone. The external Spoolman entity is never deleted. Re-inserting filament does not resurrect the old exact Spoolman ID: until a new bind/edit occurs, the slot is `unassigned` for exact identity. Provider-observed material/color may still be shown when available, but must not be presented as proof that the previous concrete spool is back.

---

## 10. Accepted decisions relevant to the current gate

See `DECISIONS.md`. Most important here:

- D-014 — fail-safe is more important than convenience;
- D-022 — optional Moonraker backend contract v1;
- D-023 — historical managed-copy + observed-stop evidence; deployment ownership superseded;
- **D-024 — canonical Z-Mod plugin lifecycle + plugin-owned symlinks; no tracked core worktree ownership.**

D-024 supersedes deployment/ownership from D-023 while retaining its observed-stop/readiness evidence for installer-owned service transitions.

---

## 11. Context recovery rule

A new coordinator should, before changing IFS work:

1. read `ROADMAP.md`, `ARCHITECTURE.md`, `PROJECT_STATE.md` and `DECISIONS.md`;
2. read `docs/IFS_MANAGER_ARCHITECTURE_V2.md`, `IFS_MANAGER_CONTRACT.md` and `docs/IFS_MANAGER_DISCOVERY_2026-08-22.md`;
3. open issue #15 and Draft PR #16;
4. verify `origin/dev`, `feature/ifs-manager-v1`, exact HEAD and checks before editing;
5. treat GitHub/code and source/hardware evidence as authoritative over old chat history;
6. never infer physical-printer acceptance from repository tests alone.
