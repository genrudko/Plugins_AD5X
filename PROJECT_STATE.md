# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить контекст без чтения длинной истории чата.

**Последнее обновление:** 2026-08-12  
**Текущая фаза:** Phase 0 — Platform Foundation  
**Статус:** Fluidd frontend shell PoC accepted; backend capability/API contract v1 accepted; следующий шаг — минимальный backend PoC  
**Активный issue:** [#8 — PLATFORM-FOUNDATION-002: определить Plugins AD5X backend capability/API contract](https://github.com/genrudko/Plugins_AD5X/issues/8)  
**Изменения на принтере для текущей фазы:** отсутствуют

---

## 1. Что уже существует

Репозиторий `genrudko/Plugins_AD5X` уже содержит рабочий/экспериментальный integration layer `ad5x_custom`, который решает ряд конкретных задач вокруг камер, IFS, Notify, Timelapse и сохранения upstream-репозиториев в clean-state.

Текущая реализация важна как **рабочий baseline и источник практического опыта**, но её нельзя автоматически считать окончательной архитектурой будущей модульной системы.

Ключевое правило на Phase 0:

> **Не ломать существующий `ad5x_custom` ради красивого рефакторинга, пока новый каркас не имеет чётких границ и миграционного пути.**

---

## 2. Репозитории и ветки

| Репозиторий | Ветка | Роль |
|---|---|---|
| `genrudko/Plugins_AD5X` | `main` | стабильная публичная ветка существующей интеграции |
| `genrudko/Plugins_AD5X` | `dev` | текущая архитектурная и экспериментальная разработка |
| `ghzserg/fluidd` | `develop` | upstream Fluidd для Z-Mod |
| `genrudko/fluidd` | `develop` | наш sync-слой, держать максимально близко к `ghzserg/fluidd:develop` |
| `genrudko/fluidd` | `ad5x-dev` | рабочая ветка UI Plugins AD5X |

На момент Fluidd integration discovery:

- `ghzserg/fluidd:develop` — `7f024c08aac4093aa8aa2e26e329df5832ebe778`;
- `genrudko/fluidd:develop` — `7f024c08aac4093aa8aa2e26e329df5832ebe778`;
- `genrudko/fluidd:ad5x-dev` — `7f024c08aac4093aa8aa2e26e329df5832ebe778`.

Принятый frontend shell PoC после final acceptance:

- base `genrudko/fluidd:develop` — `7f024c08aac4093aa8aa2e26e329df5832ebe778`;
- final head `genrudko/fluidd:ad5x-dev` — `c56cec9a2c846ee5b492242887051c8d2d74eb5a`;
- compare: `ahead_by: 11`, `behind_by: 0`;
- `ghzserg/fluidd:develop` и `genrudko/fluidd:develop` после acceptance остаются на том же base commit;
- upstream unchanged; real conflict rehearsal not applicable.

Backend contract discovery verified against:

- `ghzserg/z_ad5x:1.7` — `2e32155d00e464094b8c7197e23783ec821a112c`;
- configured Moonraker source `ghzserg/zmod_moonraker:main` — discovery head `a5ac2593f5937a0b5fea6d2aeb1fab8c241b0a8e`;
- upstream `Arksine/moonraker:master` — discovery head `d5ee17128bb88434aacdab90c2e9e990e2b64e4a`.

Критичные для backend contract source blobs (`server.py`, `application.py`, `common.py`, `websockets.py`) у исследованных `zmod_moonraker` и upstream heads совпадают по содержимому. Exact commit Moonraker, установленный на реальном AD5X, пока не подтверждён и должен быть проверен read-only перед printer deployment/acceptance.

Z-Mod **не форкаем**.

---

## 3. Зафиксированная цель

Plugins AD5X должен стать **UX/integration layer для Flashforge AD5X поверх Z-Mod**, а не отдельной прошивкой.

Главный пользовательский критерий:

> **90% повседневных действий должны выполняться без Wiki, SSH, консоли и знания названий макросов.**

При этом Advanced-режим и ручная настройка должны сохраняться.

---

## 4. Текущий приоритет разработки

Порядок работ на данный момент:

```text
Phase 0  Platform Foundation
    ↓
Phase 1  Hardware / Mods Manager
    ↓
Phase 2  IFS Manager
    ↓
Phase 3  Calibration Center
    ↓
Phase 4  Print Preflight / Safe Start
    ↓
Phase 5+ Camera / Maintenance / Diagnostics / Health
```

Первый эталонный hardware use case после Platform Foundation — **Side/AUX/PLA Fan**.

Причина выбора: это простой и очень показательный сценарий, где сегодня физически установленное штатно совместимое железо всё равно требует поиска чужих конфигов и ручного редактирования Klipper.

Желаемый UX:

```text
Side / AUX Fan
[✓] Установлен

→ config применяется автоматически
→ система валидирует состояние
→ появляется управление/тест
```

Но реализация Side/AUX/PLA Fan **не входит** в frontend shell/backend foundation PoC.

---

## 5. Активная задача

### [#8 — Platform Foundation: backend capability/API contract](https://github.com/genrudko/Plugins_AD5X/issues/8)

Issue #7 `PLATFORM-FOUNDATION-001` завершён и закрыт как `completed`: Fluidd integration discovery, минимальный frontend shell и его automated acceptance прошли Definition of Done.

Discovery-часть issue #8 выполнена и contract proposal принят координатором с уточнениями; архитектурный результат зафиксирован в D-022.

Принятый backend foundation contract:

```text
optional Moonraker component:
plugins_ad5x

coarse presence:
server.info.components

health/readiness:
backend-owned snapshot

HTTP:
GET /server/plugins_ad5x/snapshot

JSON-RPC:
server.plugins_ad5x.snapshot

API version:
MAJOR.MINOR

state delivery:
atomic snapshot + low-frequency invalidation notification

notification:
notify_plugins_ad5x_snapshot_changed

auth:
Moonraker-owned

steady polling:
NO

separate daemon / own DB in Phase 0:
NO
```

`server.info.components` не является health check: имя может одновременно присутствовать в `components` и `failed_components`, если object загрузился, но `component_init()` завершился ошибкой. Поэтому D-020 coarse presence остаётся первым уровнем, а readiness/health — вторым уровнем snapshot API.

Следующий разрешённый этап по #8 — **минимальный backend PoC** без hardware module functionality. До установки/acceptance на реальном принтере требуется read-only подтверждение фактически установленной Moonraker version/Git HEAD и затем отдельная контролируемая printer-test последовательность.

### 5.1. Найденные integration points Fluidd

Фактическая цепочка:

```text
navigation
→ route
→ page/shell
→ AD5X-local store/API adapter
→ capability/state
→ штатный Fluidd WebSocket transport
→ Moonraker
→ Plugins AD5X backend
```

Ключевые upstream-файлы:

- navigation — `src/components/layout/AppNavDrawer.vue`;
- routing — `src/router/index.ts`;
- общий page shell/layout — `src/App.vue` через штатный `<router-view>`;
- обычные Fluidd pages — `src/views/*.vue`;
- root Vuex registry — `src/store/index.ts`;
- root typed store declarations — `src/store/types.ts`;
- server component capability precedent — `src/store/server/getters.ts`, getter `server/componentSupport(component)`;
- server info lifecycle — `src/store/server/actions.ts`;
- Moonraker RPC façade — `src/api/socketActions.ts`;
- низкоуровневый WebSocket/JSON-RPC transport — `src/plugins/socketClient.ts`.

### 5.2. Согласованный frontend ownership boundary

AD5X-специфичный frontend-код живёт в собственной области `src/ad5x/**`.

В реализованном PoC созданы:

```text
src/ad5x/
├── integration.ts
├── router.ts
├── __tests__/
│   ├── integration.spec.ts
│   └── router.spec.ts
├── api/
│   ├── client.ts
│   ├── types.ts
│   └── __tests__/
│       └── client.spec.ts
├── store/
│   ├── index.ts
│   ├── types.ts
│   └── __tests__/
│       └── index.spec.ts
└── views/
    ├── Ad5xShell.vue
    └── __tests__/
        └── Ad5xShell.spec.ts
```

Не создаются заранее полноценные `hardware/`, `ifs/`, `calibration/`, `manifest/` и другие продуктовые подсистемы до дальнейшего решения по Platform Foundation.

### 5.3. Минимальный upstream patch surface

Фактический PoC изменяет только два существующих Fluidd-файла:

1. `src/components/layout/AppNavDrawer.vue` — один пункт Plugins AD5X и coarse capability gate;
2. `src/router/index.ts` — подключение AD5X route tree.

Не изменены:

- `src/App.vue`;
- существующие `src/views/*`;
- `src/store/index.ts`;
- `src/store/types.ts`;
- `src/store/server/*`;
- `src/api/socketActions.ts`;
- `src/plugins/socketClient.ts`.

Отдельно добавлен downstream infrastructure-файл `.github/workflows/ad5x-ci.yml`; upstream `.github/workflows/build.yml` не изменён.

Final diff review подтвердил соответствие D-018 и D-021.

### 5.4. Согласованная route/navigation policy

Реализовано и подтверждено unit acceptance:

- `/ad5x` регистрируется статически;
- пункт Plugins AD5X в основной навигации capability-gated;
- direct `/ad5x` при отсутствии backend показывает безопасное `Plugins AD5X backend unavailable`;
- absent path возвращается до AD5X-specific API вызова;
- обычная работа Fluidd не зависит от Plugins AD5X frontend/backend.

Coordinator review дополнительно проверил bootstrap lifecycle Fluidd: `serverInfo()` выполняется до перехода socket state в `ready`, а `<router-view>` основного приложения монтируется при `socketReady`, поэтому первоначальный backend presence не должен вычисляться до bootstrap `server.info` в штатном lifecycle.

### 5.5. Capability boundary

Capability detection двухступенчатый:

```text
Moonraker server.info.components
        ↓
есть Plugins AD5X backend object?
        ↓ yes
server.plugins_ad5x.snapshot
        ↓
API/backend version + health + detailed module capabilities/state
```

Coarse detection использует существующий механизм Fluidd `server/componentSupport(...)`.

Production component identifier принят как `plugins_ad5x`. Provisional frontend seam `plugins_ad5x.get_capabilities` не является production API и должен быть заменён на `server.plugins_ad5x.snapshot` на этапе backend integration.

Snapshot contract v1 различает platform metadata и module-owned state. Минимальный envelope:

```text
api_version
backend_version
revision
backend.health
modules{}
```

Common module lifecycle fields:

```text
support
enabled
presence
available
health
capabilities[]
state{}
```

`available` рассчитывается backend/provider; frontend не повторяет hardware/business logic. `unknown`/`not_applicable` допустимы, если состояние нельзя доказательно установить.

### 5.6. Реализация frontend shell PoC

Initial reviewed feature-head:

`c0810f5ec3a2795b9743a48fbf00737ff0c43d0d`

Исходные PoC-коммиты:

- `4e1cfe3534af5fc7eff3a1c18b616dec038ba911` — `feat(ad5x): add local frontend shell foundation`;
- `aa9261eaa5c50aab9f43bc7a8abb0229a1f66918` — `feat(ad5x): register local route tree`;
- `0919b70d4bf5751ffb9ae6192e4896ef3b1a499f` — `feat(ad5x): gate navigation on backend support`;
- `c0810f5ec3a2795b9743a48fbf00737ff0c43d0d` — `fix(ad5x): reset dynamic store with Fluidd lifecycle`.

Downstream CI и acceptance-fix commits:

- `97fa35e9987644142c5dd5d73756e443f84fd62a` — `ci(ad5x): add downstream verification workflow`;
- `f0f590ba945b4bfba4d9bd44d089fc26c4d451a2` — `fix(ad5x): satisfy Fluidd lint rules`;
- `c662cc04fbf993ad39fecb7f7629c03344e1109a` — `fix(ad5x): decouple dynamic store typing from Fluidd root`;
- `69a9f349fc529da74af39963e27c8cdb77893a32` — `fix(ad5x): isolate store tests from Fluidd root types`;
- `1cda7ffacab2d8e0b95e2839e789f0376d1edb98` — `fix(ad5x): type local socket boundary explicitly`;
- `47cddb6c770501bcbd0a284dd6d414ffed4b9f0d` — `fix(ad5x): make socket boundary cast explicit`;
- `c56cec9a2c846ee5b492242887051c8d2d74eb5a` — `test(ad5x): exercise shell through Vuex component getter`.

Final accepted feature-head:

`c56cec9a2c846ee5b492242887051c8d2d74eb5a`

Реализованы и фактически пройдены specs для:

- provisional backend component gate;
- static `/ad5x` route;
- local API adapter через существующий Fluidd socket transport;
- lazy dynamic Vuex registration;
- `ad5x/reset` для участия dynamic module в Fluidd root reset lifecycle;
- backend absent → API/RPC не вызывается;
- backend mocked/present → capability payload проходит API/state boundary и отображается shell.

Dynamic Vuex implementation не потребовала изменений root Fluidd store registry. После успешных `type-check`, unit tests и production build hypothesis формально **CONFIRMED**.

### 5.7. Downstream CI и final automated acceptance

Для `ad5x-dev` добавлен отдельный downstream-only workflow:

```text
.github/workflows/ad5x-ci.yml
```

Triggers:

```text
push → ad5x-dev
workflow_dispatch
```

Upstream `.github/workflows/build.yml` не изменялся.

Final GitHub Actions run:

- run `31621932415`;
- URL: `https://github.com/genrudko/fluidd/actions/runs/31621932415`;
- exact head: `c56cec9a2c846ee5b492242887051c8d2d74eb5a`;
- conclusion: `success`.

Обязательная verification chain:

```text
pnpm i --frozen-lockfile   PASS
pnpm run lint --no-fix     PASS
pnpm run type-check        PASS
pnpm run test:unit         PASS
pnpm run circular-check    PASS
pnpm run build             PASS
```

Unit result: `20 passed` test files, `415 passed` tests. `src/ad5x/views/__tests__/Ad5xShell.spec.ts` — `2 passed`.

Acceptance outcomes:

- Backend absent — **PASS**;
- Backend mocked/present — **PASS**;
- Dynamic Vuex hypothesis — **CONFIRMED**;
- circular dependencies — **none found**;
- production build — **PASS**.

Final `develop → ad5x-dev` diff:

Existing Fluidd product files modified:

```text
src/components/layout/AppNavDrawer.vue
src/router/index.ts
```

AD5X files:

```text
src/ad5x/__tests__/integration.spec.ts
src/ad5x/__tests__/router.spec.ts
src/ad5x/api/__tests__/client.spec.ts
src/ad5x/api/client.ts
src/ad5x/api/types.ts
src/ad5x/integration.ts
src/ad5x/router.ts
src/ad5x/store/__tests__/index.spec.ts
src/ad5x/store/index.ts
src/ad5x/store/types.ts
src/ad5x/views/Ad5xShell.vue
src/ad5x/views/__tests__/Ad5xShell.spec.ts
```

Infrastructure files:

```text
.github/workflows/ad5x-ci.yml
```

Compare:

```text
ahead_by: 11
behind_by: 0
```

Upstream state после acceptance:

```text
ghzserg/fluidd:develop  7f024c08aac4093aa8aa2e26e329df5832ebe778
genrudko/fluidd:develop 7f024c08aac4093aa8aa2e26e329df5832ebe778
```

Upstream unchanged; real conflict rehearsal not applicable.

Frontend shell PoC имеет статус **accepted / Definition of Done complete**. Это не означает завершение всей Phase 0.

---

## 6. Что сейчас НЕ делать

В рамках минимального backend PoC по #8:

- не реализовывать Hardware Manager;
- не реализовывать AUX/PLA Fan;
- не переносить IFS UI;
- не начинать Calibration Center;
- не начинать Print Preflight;
- не рефакторить существующий `ad5x_custom` массово;
- не форкать и не править tracked Z-Mod/Moonraker source;
- не создавать отдельный daemon/agent или собственную DB без доказанного нового требования;
- не переносить hardware/business logic во Fluidd;
- не начинать Mainsail/HelixScreen parity;
- не закреплять окончательный format module manifest;
- не устанавливать backend на реальный принтер до отдельного контролируемого test step;
- не трактовать `server.info.components` как health/readiness.

Разрешён следующий narrow scope: минимальный optional Moonraker component, read-only snapshot endpoint, notification seam, tests/validation и подготовка безопасной deployment/rollback проверки.

---

## 7. Известные архитектурные решения

Уже принято:

- GitHub — источник истины;
- `main` — stable, `dev` — experiment/integration;
- Z-Mod не форкаем;
- Fluidd форкаем от `ghzserg/fluidd`, а не напрямую от `fluidd-core/fluidd`;
- `genrudko/fluidd:develop` держим как upstream-sync branch;
- наши UI-изменения идут в `genrudko/fluidd:ad5x-dev`;
- один backend/API должен обслуживать разные frontend;
- Hardware Manager — registry/UI отдельных модулей, а не монолит;
- IFS должен идентифицировать конкретную катушку, а не угадывать её только по RGB;
- Calibration Center должен хранить контекст валидности Z-offset, а не только число;
- Print Preflight — guard перед штатным стартом, а не новый print engine;
- rollback и сохранение базовой печати через Z-Mod обязательны;
- Fluidd integration использует ownership boundary `src/ad5x/**` и целевой two-seam upstream patch surface;
- `/ad5x` статический, navigation item capability-gated;
- capability detection двухступенчатый: backend presence → backend-owned detailed capabilities/state;
- `ad5x-dev` проверяется отдельным downstream-only CI workflow, не меняющим upstream `build.yml`;
- backend foundation реализуется как optional in-process Moonraker component `plugins_ad5x`, без отдельного daemon/DB на Phase 0;
- production read-only API v1 — `GET /server/plugins_ad5x/snapshot` / `server.plugins_ad5x.snapshot`, Moonraker-authenticated;
- state propagation — atomic snapshot + low-frequency invalidation notification, full resync после reconnect, без steady-state polling.

Подробности: `ARCHITECTURE.md` и `DECISIONS.md`, особенно D-018–D-022.

---

## 8. Открытые вопросы

### 8.1. Backend PoC implementation/deployment

Backend capability/API contract v1 принят в D-022. Implementation ещё не выполнена.

Следующий PoC должен доказать без hardware functionality:

- optional component `plugins_ad5x` загружается и не ломает Moonraker;
- `server.info.components` coarse presence работает фактически;
- read-only `server.plugins_ad5x.snapshot` возвращает v1 envelope с `modules: {}`;
- endpoint явно ограничен HTTP + WEBSOCKET и наследует Moonraker auth;
- notification `notify_plugins_ad5x_snapshot_changed` доставляется по WebSocket;
- frontend provisional adapter можно перевести с `plugins_ad5x.get_capabilities` на production snapshot method без расширения D-018 patch surface;
- component absence/init failure/restart/reconnect остаются fail-safe;
- install/uninstall/update/rollback не загрязняют tracked Z-Mod/Moonraker source.

До printer deployment требуется read-only подтвердить:

```text
server.info.moonraker_version
git -C /opt/config/base/moonraker rev-parse HEAD
```

Exact runtime Moonraker commit пока **unresolved**, хотя исследованные current Z-Mod Moonraker source blobs для contract-critical mechanisms совпадают с upstream.

Deployment detail `symlink vs copy` в Moonraker components не утверждён до реального Z-Mod test.

### 8.2. AD5X-local store registration

PoC реализует local/lazy dynamic Vuex registration внутри `src/ad5x/**` без изменения `src/store/index.ts` и `src/store/types.ts`.

Formal status после downstream CI: **CONFIRMED**. Реальный `type-check`, `415` unit tests, circular-check и production build прошли на exact accepted feature-head `c56cec9a2c846ee5b492242887051c8d2d74eb5a`.

### 8.3. Moonraker update_manager override

В Z-Mod Fluidd обновляется отдельным `[update_manager fluidd]`.

Есть идея переопределить только источник `repo` через пользовательский Moonraker config и направить updater на наш fork, **но точное поведение merge/duplicate sections должно быть подтверждено по актуальной документации/коду Moonraker до реализации**.

Пока это гипотеза, а не утверждённый механизм.

### 8.4. Module manifest format

Нужные поля примерно определены, но конкретный формат (`json/yaml/toml/другое`) пока не выбран.

Сначала нужно проверить минимальный backend provider/registry seam; production manifest format не нужен для foundation PoC.

---

## 9. Критерий завершения Phase 0

Phase 0 можно считать завершённой, когда есть:

- согласованный module contract;
- минимальный frontend shell во Fluidd;
- capability/state API или чётко описанный контракт;
- единый способ хранения module state;
- install/update/uninstall/rollback policy;
- понятная стратегия upstream sync Fluidd;
- подтверждённый способ установки нашей Fluidd-сборки;
- минимальный developer guide для следующего модуля;
- тестовый dummy/module proof-of-concept, не требующий изменения железа.

Минимальный frontend shell и backend capability/API contract теперь приняты; backend PoC, installation lifecycle и остальные критерии Phase 0 остаются отдельной работой.

После завершения Phase 0 первым реальным hardware-модулем становится Side/AUX/PLA Fan.

---

## 10. Правила передачи контекста новому координатору

Новый координатор перед любыми действиями должен:

1. прочитать `ROADMAP.md`;
2. прочитать `ARCHITECTURE.md`;
3. прочитать `PROJECT_STATE.md`;
4. прочитать `DECISIONS.md`;
5. открыть активный issue #8;
6. проверить текущее состояние указанных GitHub-веток;
7. не полагаться на старые чаты, если репозиторий говорит другое;
8. при расхождении документации с кодом сначала зафиксировать расхождение, а не молча «исправлять» историю.

`PROJECT_STATE.md` следует обновлять после завершения значимого этапа, изменения активной задачи или изменения архитектурного решения.