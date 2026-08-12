# Plugins AD5X — Project State

> Оперативный снимок состояния проекта. Этот файл должен позволять новому координатору или разработчику быстро восстановить контекст без чтения длинной истории чата.

**Последнее обновление:** 2026-08-12  
**Текущая фаза:** Phase 0 — Platform Foundation  
**Статус:** архитектура зафиксирована; создан активный discovery work item; код нового каркаса ещё не начат  
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

---

## 5. Активная задача

### [#7 — Platform Foundation: Fluidd integration discovery](https://github.com/genrudko/Plugins_AD5X/issues/7)

**Цель:** изучить `genrudko/fluidd:ad5x-dev` и определить минимальный patch surface для Plugins AD5X.

Нужно найти и документировать фактические точки интеграции:

```text
navigation
→ route
→ page/shell
→ store/API adapter
→ capability/state
```

### Что должно получиться

Не готовый Hardware Manager и не полноценный плагин, а **архитектурный shell**, который подтверждает, что мы можем:

1. добавить отдельный раздел Plugins AD5X в UI;
2. локализовать почти весь наш код в собственной области;
3. получить данные через Moonraker/API без дублирования backend-логики во frontend;
4. скрывать модуль, если capability отсутствует;
5. переживать upstream sync с минимальными конфликтами.

Порядок выполнения issue: **сначала discovery и план с конкретными путями файлов, затем код proof-of-concept после согласования**.

---

## 6. Что сейчас НЕ делать

До завершения Fluidd integration discovery:

- не писать полноценный Hardware Manager;
- не переносить IFS UI;
- не рефакторить существующий `ad5x_custom` массово;
- не менять Z-Mod;
- не трогать принтер ради нового UI;
- не создавать отдельную backend-логику внутри Fluidd;
- не начинать Mainsail/HelixScreen parity;
- не закреплять формат module manifest без анализа требований.

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
- rollback и сохранение базовой печати через Z-Mod обязательны.

Подробности: `ARCHITECTURE.md` и `DECISIONS.md`.

---

## 8. Открытые вопросы

### 8.1. Fluidd extension points

Пока не изучены фактические файлы/компоненты `ghzserg/fluidd`, поэтому нельзя заранее утверждать, где именно должны жить:

- route;
- nav item;
- AD5X module registry;
- store/API adapter;
- feature/capability detection.

Это и есть активная задача #7.

### 8.2. Moonraker update_manager override

В Z-Mod Fluidd обновляется отдельным `[update_manager fluidd]`.

Есть идея переопределить только источник `repo` через пользовательский Moonraker config и направить updater на наш fork, **но точное поведение merge/duplicate sections должно быть подтверждено по актуальной документации/коду Moonraker до реализации**.

Пока это гипотеза, а не утверждённый механизм.

### 8.3. Module manifest format

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