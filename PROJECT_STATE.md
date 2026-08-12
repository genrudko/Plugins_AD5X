# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить контекст без чтения длинной истории чата.

**Последнее обновление:** 2026-08-12  
**Текущая фаза:** Phase 0 — Platform Foundation  
**Статус:** Fluidd integration discovery завершён и архитектурный план согласован; реализация frontend shell proof-of-concept ещё не начата  
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

Следовательно, `ad5x-dev` на старте discovery не содержал собственных AD5X-патчей и являлся чистым baseline для минимального downstream patch surface.

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

AD5X-специфичный frontend-код должен жить в собственной области:

```text
src/ad5x/
├── router.ts
├── views/
│   └── Ad5xShell.vue
├── api/
│   ├── client.ts
│   └── types.ts
└── store/
    ├── index.ts
    └── types.ts
```

Структура может уточниться по результатам PoC, но ownership boundary `src/ad5x/**` считается принятым.

Не следует заранее создавать полноценные `hardware/`, `ifs/`, `calibration/`, `manifest/` и другие продуктовые подсистемы до проверки базового shell.

### 5.3. Минимальный upstream patch surface

Целевой нормальный patch surface ограничен двумя файлами:

1. `src/components/layout/AppNavDrawer.vue` — один пункт Plugins AD5X и coarse capability gate;
2. `src/router/index.ts` — подключение AD5X route tree.

Без доказанной необходимости **не менять**:

- `src/App.vue`;
- существующие `src/views/*`;
- `src/store/index.ts`;
- `src/store/types.ts`;
- `src/store/server/*`;
- `src/api/socketActions.ts`;
- `src/plugins/socketClient.ts`.

Если proof-of-concept потребует дополнительных upstream-изменений, расширение patch surface сначала должно быть технически обосновано.

### 5.4. Согласованная route/navigation policy

- `/ad5x` регистрируется статически;
- пункт Plugins AD5X в основной навигации показывается только при подтверждённом наличии backend;
- прямой `/ad5x` при отсутствии backend показывает безопасное `backend unavailable` состояние;
- при отсутствии backend не выполняются AD5X-specific RPC;
- штатная работа Fluidd и базовая печать не должны зависеть от Plugins AD5X frontend/backend.

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

Detailed capability/state принадлежит Plugins AD5X backend. Frontend **не должен** самостоятельно определять наличие модулей по Klipper config, GPIO, макросам, USB-устройствам или другим низкоуровневым признакам.

Важно: текущий `ad5x_custom` ещё не содержит подтверждённого Moonraker component/API с таким контрактом. Конкретное имя backend component/RPC method и окончательная payload schema пока не зафиксированы.

### 5.6. Следующий этап issue #7 — frontend shell PoC

После согласования discovery следующий узкий этап:

1. создать минимальную область `src/ad5x/**` в `genrudko/fluidd:ad5x-dev`;
2. добавить один route и один capability-gated nav item;
3. реализовать только диагностический shell, без Hardware Manager;
4. проверить два режима: backend absent и mocked/present;
5. прогнать штатные проверки Fluidd: `pnpm lint`, `pnpm type-check`, `pnpm test:unit`, `pnpm build`;
6. проверить фактический diff и сохранить upstream patch surface минимальным;
7. затем провести upstream-sync rehearsal и оценить реальные конфликты.

Только после успешного PoC переходить к отдельному backend capability/API contract и последующим модулям.

---

## 6. Что сейчас НЕ делать

В рамках текущего frontend shell PoC:

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
- capability detection двухступенчатый: backend presence → backend-owned detailed capabilities/state.

Подробности: `ARCHITECTURE.md` и `DECISIONS.md`, особенно D-018, D-019 и D-020.

---

## 8. Открытые вопросы

### 8.1. Plugins AD5X backend capability/API contract

Frontend extension points теперь изучены, но backend-контракт ещё не определён окончательно.

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

Root Vuex registry Fluidd статически типизирован через `src/store/index.ts` и `src/store/types.ts`. Статическое добавление AD5X store увеличивает upstream patch surface.

Предпочтительная гипотеза для PoC — локальная/lazy dynamic registration внутри `src/ad5x/**`, но она ещё должна быть подтверждена реальным `type-check`, unit tests и build. Это пока implementation hypothesis, а не отдельное архитектурное решение.

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