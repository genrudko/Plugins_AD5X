# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить контекст без чтения длинной истории чата.

**Последнее обновление:** 2026-08-12  
**Текущая фаза:** Phase 0 — Platform Foundation  
**Статус:** Fluidd frontend shell PoC архитектурно реализован и прошёл coordinator code review; Definition of Done не закрыт до обязательных проверок exact feature-head  
**Активный issue:** [#7 — PLATFORM-FOUNDATION-001: исследовать точки интеграции Fluidd](https://github.com/genrudko/Plugins_AD5X/issues/7)  
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

Текущий frontend shell PoC:

- base `genrudko/fluidd:develop` — `7f024c08aac4093aa8aa2e26e329df5832ebe778`;
- feature head `genrudko/fluidd:ad5x-dev` — `c0810f5ec3a2795b9743a48fbf00737ff0c43d0d`;
- compare: `ahead_by: 4`, `behind_by: 0`;
- `ghzserg/fluidd:develop` на момент coordinator review оставался на том же base commit.

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

Но реализация Side/AUX/PLA Fan **не входит** в текущий frontend shell proof-of-concept.

---

## 5. Активная задача

### [#7 — Platform Foundation: Fluidd integration discovery](https://github.com/genrudko/Plugins_AD5X/issues/7)

Discovery-часть issue завершена по фактическому коду `genrudko/fluidd:ad5x-dev` и согласована владельцем продукта.

Frontend shell PoC реализован, но acceptance не закрыт до выполнения обязательных проверок exact feature-head.

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

Не создаются заранее полноценные `hardware/`, `ifs/`, `calibration/`, `manifest/` и другие продуктовые подсистемы до завершения базового Platform Foundation acceptance.

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

Coordinator review подтвердил соответствие D-018.

### 5.4. Согласованная route/navigation policy

Реализовано:

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
есть Plugins AD5X backend?
        ↓ yes
Plugins AD5X backend API
        ↓
API/backend version + detailed module capabilities/state
```

Coarse detection использует существующий механизм Fluidd `server/componentSupport(...)`.

В PoC используется provisional component identifier `plugins_ad5x` и provisional capability seam `plugins_ad5x.get_capabilities`. Они нужны для mockable frontend boundary, но **не являются окончательно утверждённым backend public contract**. Окончательные component/RPC names и payload schema должны быть определены отдельным решением Platform Foundation в соответствии с D-020.

### 5.6. Реализация frontend shell PoC

Feature-head:

`c0810f5ec3a2795b9743a48fbf00737ff0c43d0d`

Коммиты:

- `4e1cfe3534af5fc7eff3a1c18b616dec038ba911` — `feat(ad5x): add local frontend shell foundation`;
- `aa9261eaa5c50aab9f43bc7a8abb0229a1f66918` — `feat(ad5x): register local route tree`;
- `0919b70d4bf5751ffb9ae6192e4896ef3b1a499f` — `feat(ad5x): gate navigation on backend support`;
- `c0810f5ec3a2795b9743a48fbf00737ff0c43d0d` — `fix(ad5x): reset dynamic store with Fluidd lifecycle`.

Реализованы unit specs для:

- provisional backend component gate;
- static `/ad5x` route;
- local API adapter через существующий `$socket`;
- lazy dynamic Vuex registration;
- `ad5x/reset` для участия dynamic module в Fluidd root reset lifecycle;
- backend absent → API/RPC не вызывается;
- backend mocked/present → capability payload проходит API/state boundary и отображается shell.

Dynamic Vuex implementation не потребовала изменений root Fluidd store registry. Однако hypothesis ещё не считается формально подтверждённой до реального `type-check/tests/build`.

### 5.7. Текущий acceptance blocker и следующий узкий шаг

Штатный `.github/workflows/build.yml` Fluidd не запускается на push в `ad5x-dev`; его triggers ограничены `develop/master`, тегами `v*` и PR в `develop/master`.

Поэтому exact feature-head `c0810f5e...` пока не имеет выполненных обязательных проверок:

```text
pnpm lint
pnpm type-check
pnpm test:unit
pnpm circular-check
pnpm build
```

Локальные AI execution environments, использованные при реализации и coordinator review, не смогли установить pnpm/dependencies из-за отсутствующего network/DNS access. Зелёные результаты не считаются и не выдумываются.

Следующий узкий этап в рамках issue #7:

1. добавить отдельный downstream-only workflow для `ad5x-dev`;
2. не менять upstream `.github/workflows/build.yml`;
3. запускать workflow минимум на push в `ad5x-dev` и через `workflow_dispatch`;
4. повторить релевантные штатные проверки Fluidd;
5. получить фактический CI result на exact feature-head;
6. при PASS подтвердить/отвергнуть dynamic Vuex hypothesis по фактическим checks;
7. только затем отметить frontend shell PoC как прошедший Definition of Done.

Политика зафиксирована в D-021.

---

## 6. Что сейчас НЕ делать

До закрытия acceptance frontend shell PoC:

- не писать полноценный Hardware Manager;
- не реализовывать AUX/PLA Fan;
- не переносить IFS UI;
- не начинать Calibration Center;
- не рефакторить существующий `ad5x_custom` массово;
- не менять Z-Mod;
- не трогать принтер ради нового UI;
- не создавать бизнес-логику внутри Fluidd;
- не начинать Mainsail/HelixScreen parity;
- не закреплять окончательный формат module manifest;
- не фиксировать окончательный backend RPC/payload contract без отдельного анализа.

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
- предпочтение: UI/macros/events → лёгкий daemon → никогда тяжёлый service на MIPS без крайней необходимости;
- rollback и сохранение базовой печати через Z-Mod обязательны;
- Fluidd integration использует ownership boundary `src/ad5x/**` и целевой two-seam upstream patch surface;
- `/ad5x` статический, navigation item capability-gated;
- capability detection двухступенчатый: backend presence → backend-owned detailed capabilities/state;
- `ad5x-dev` проверяется отдельным downstream-only CI workflow, не меняющим upstream `build.yml`.

Подробности: `ARCHITECTURE.md` и `DECISIONS.md`, особенно D-018, D-019, D-020 и D-021.

---

## 8. Открытые вопросы

### 8.1. Plugins AD5X backend capability/API contract

Frontend extension points изучены, но backend-контракт ещё не определён окончательно.

Нужно отдельно решить и проверить:

- как Plugins AD5X регистрируется как Moonraker component;
- точное имя component;
- имя RPC endpoint/method;
- API versioning;
- минимальную capability/state payload schema;
- поведение при несовместимой версии backend/frontend;
- события/notifications для обновления state без тяжёлого polling.

До этого нельзя считать capability API реализованным.

### 8.2. AD5X-local store registration

PoC реализует local/lazy dynamic Vuex registration внутри `src/ad5x/**` без изменения `src/store/index.ts` и `src/store/types.ts`.

Code review показывает, что lifecycle requirement root reset учтён через локальный `ad5x/reset`. Но formal status остаётся **implementation hypothesis pending CI**, пока не пройдут реальный `type-check`, unit tests и build на exact feature-head.

### 8.3. Moonraker update_manager override

В Z-Mod Fluidd обновляется отдельным `[update_manager fluidd]`.

Есть идея переопределить только источник `repo` через пользовательский Moonraker config и направить updater на наш fork, **но точное поведение merge/duplicate sections должно быть подтверждено по актуальной документации/коду Moonraker до реализации**.

Пока это гипотеза, а не утверждённый механизм.

### 8.4. Module manifest format

Нужные поля примерно определены, но конкретный формат (`json/yaml/toml/другое`) пока не выбран.

Сначала нужно понять реальные потребности backend/frontend и существующий жизненный цикл `ad5x_custom`.

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

После этого первым реальным hardware-модулем становится Side/AUX/PLA Fan.

---

## 10. Правила передачи контекста новому координатору

Новый координатор перед любыми действиями должен:

1. прочитать `ROADMAP.md`;
2. прочитать `ARCHITECTURE.md`;
3. прочитать `PROJECT_STATE.md`;
4. прочитать `DECISIONS.md`;
5. открыть активный issue #7;
6. проверить текущее состояние указанных GitHub-веток;
7. не полагаться на старые чаты, если репозиторий говорит другое;
8. при расхождении документации с кодом сначала зафиксировать расхождение, а не молча «исправлять» историю.

`PROJECT_STATE.md` следует обновлять после завершения значимого этапа, изменения активной задачи или изменения архитектурного решения.