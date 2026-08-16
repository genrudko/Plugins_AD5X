# Plugins AD5X — Architecture

> Этот документ фиксирует архитектурные границы проекта. Roadmap отвечает на вопрос «что строим и в каком порядке», этот файл — «как это должно быть устроено, чтобы проект не превратился в набор несвязанных костылей».

## 1. Архитектурная цель

Plugins AD5X — **UX/integration layer для Flashforge AD5X поверх Z-Mod/Klipper/Moonraker**.

Проект не заменяет Z-Mod и не создаёт собственную прошивку. Он должен:

- сделать уже существующие возможности понятными обычному пользователю;
- автоматизировать безопасные рутинные действия;
- интегрировать популярные аппаратные модификации;
- сохранить доступ к низкоуровневым настройкам для продвинутого пользователя;
- переживать обновления Z-Mod с минимальным количеством ручных конфликтов;
- не превращать ограниченную MIPS-платформу принтера в тяжёлый сервер.

Главный UX-инвариант:

> **90% повседневных действий должны выполняться без Wiki, SSH, консоли и знания названий макросов.**

---

## 2. Слои системы

```text
┌──────────────────────────────────────────────────────────┐
│ Пользователь                                             │
├──────────────────────────────────────────────────────────┤
│ Frontend                                                 │
│ Fluidd / Mainsail / HelixScreen / Guppy / KlipperScreen │
├──────────────────────────────────────────────────────────┤
│ Plugins AD5X                                             │
│ capabilities / state / orchestration / API               │
├──────────────────────────────────────────────────────────┤
│ Moonraker / Klipper / Z-Mod                              │
│ штатные API, macros, config, update manager              │
├──────────────────────────────────────────────────────────┤
│ Flashforge AD5X + опциональное железо                    │
└──────────────────────────────────────────────────────────┘
```

### 2.1. Z-Mod — фундамент

Z-Mod остаётся внешним upstream-проектом и источником основной инженерной логики.

**Не делаем собственный форк Z-Mod ради проекта.**

Если нужная возможность уже надёжно реализована через Z-Mod/Klipper/Moonraker, Plugins AD5X должен её использовать, а не переписывать.

### 2.2. Plugins AD5X — интеграционный слой

Репозиторий `genrudko/Plugins_AD5X` отвечает за:

- module manifests;
- конфигурационные overlay;
- лёгкую backend/event-driven логику;
- единое состояние модулей;
- API/capabilities для frontend;
- install/update/uninstall/rollback;
- диагностику и compatibility checks.

### 2.3. Frontend — представление, а не второй backend

Fluidd, Mainsail и локальные экраны не должны содержать независимые копии бизнес-логики.

Frontend должен:

- получать состояние через общий API/Moonraker;
- отображать capabilities;
- запускать понятные пользовательские действия;
- показывать Advanced-информацию;
- корректно переживать отсутствие необязательного backend-модуля.

Для safety-critical функций вроде Z Calibration frontend не имеет права самостоятельно вычислять Auto-Z, safety envelope или acceptance decision: эти решения принадлежат общему backend/core.

---

## 3. Репозитории и ветки

### `genrudko/Plugins_AD5X`

- `main` — стабильная публичная версия;
- `dev` — интеграция, экспериментальные модули и текущая разработка.

### `ghzserg/fluidd`

Upstream Fluidd, используемый/поддерживаемый автором Z-Mod.

- upstream default branch: `develop`.

### `genrudko/fluidd`

Наш fork от `ghzserg/fluidd`.

- `develop` — держим максимально близко к `ghzserg/fluidd:develop`; собственные AD5X-фичи туда напрямую не складываем;
- `ad5x-dev` — рабочая ветка интерфейса Plugins AD5X.

Ожидаемая цепочка обновлений:

```text
fluidd-core/fluidd
        ↓
ghzserg/fluidd:develop
        ↓
genrudko/fluidd:develop
        ↓
genrudko/fluidd:ad5x-dev
```

Наша задача — держать patch surface как можно меньше.

---

## 4. Модульная модель

Любая новая возможность должна оформляться как модуль, а не как случайный набор правок.

Минимальный контракт модуля:

```text
module
├── manifest
├── capability/state
├── config requirements
├── optional backend logic
├── frontend representation
├── install/enable
├── disable/uninstall
├── validation
└── rollback
```

### 4.1. Manifest

Manifest должен уметь описать минимум:

- `id`;
- имя и версию;
- совместимые модели/ревизии;
- зависимости;
- конфликты;
- требуемые Klipper/Moonraker include;
- используемые устройства/GPIO, если применимо;
- способ detection/validation;
- capabilities для UI;
- наличие background service;
- install/uninstall hooks;
- experimental/stable status.

Формат manifest пока **не зафиксирован**. Его следует выбрать после анализа требований реальных модулей, а не заранее ради абстрактной схемы.

### 4.2. Capability-first UI

Frontend не должен жёстко предполагать наличие железа или конкретного плагина.

Предпочтительная схема:

```text
backend сообщает:
  module = aux_fan
  available = true
  installed = true
  controllable = true
  capabilities = [speed, test]

frontend отображает только доступные действия
```

Это позволяет одной UI-сборке работать как со стоковым AD5X, так и с модифицированным.

---

## 5. Хранение состояния и конфигураций

### 5.1. Не загрязнять upstream

По возможности пользовательские изменения должны жить в `mod_data`/overlay-слое и не оставлять отслеживаемые upstream-репозитории Z-Mod, Notify, Timelapse и других компонентов в dirty-state.

Существующий `ad5x_custom` уже следует этому направлению; новая архитектура должна его сохранить, а не откатиться к прямому редактированию upstream-файлов.

### 5.2. Генерируемые конфиги

Если модулю требуется Klipper/Moonraker-конфиг:

1. определить требуемое состояние;
2. сформировать overlay/include;
3. сохранить backup предыдущего состояния;
4. проверить синтаксис/совместимость настолько рано, насколько это возможно;
5. применить изменение;
6. проверить результат;
7. при ошибке выполнить rollback.

### 5.3. Ручные overrides

Автоматизация не должна блокировать продвинутого пользователя.

В `Advanced` должны быть доступны:

- фактический config;
- pin/device mapping;
- вызванные macros/API;
- текущие detected capabilities;
- ручной override там, где он безопасен.

Для Z Calibration внешний стандартный Klipper `gcode_offset`, `GET_POSITION`, обычные Z-adjust/babystepping и консоль остаются наблюдаемыми и совместимыми; Plugins AD5X не подменяет их отдельной скрытой системой координат.

---

## 6. Backend policy и бюджет ресурсов

По умолчанию выбираем самый лёгкий подход.

| Класс | Механизм | Политика |
|---|---|---|
| A | UI + Moonraker API + существующие macros | предпочтительно |
| B | лёгкий event-driven daemon/component logic | только при необходимости |
| C | тяжёлый постоянный service | на AD5X не ставим |

Правила:

- event-driven лучше polling;
- если polling нужен — частота должна быть обоснована;
- не писать логи в цикле без необходимости;
- не делать постоянную обработку изображений;
- не перекодировать видео на принтере;
- не размещать на AD5X тяжёлую аналитику/AI;
- функция UI не должна создавать постоянную нагрузку только ради красивого dashboard;
- safety-critical module может вести bounded structured event log, но не high-rate telemetry без отдельного доказанного требования.

---

## 7. Frontend integration policy

### 7.1. Fluidd — первый frontend

Принятые integration seams:

```text
navigation
→ route
→ page/shell
→ store/API adapter
→ module capability
```

Основной AD5X-код локализуется в `src/ad5x/**`; штатный Fluidd patch surface сохраняется минимальным по D-018–D-021.

Желаемый результат — отдельная локализованная область проекта плюс минимальное количество изменений в upstream-файлах навигации/роутинга.

### 7.2. Mainsail

Добавляется после стабилизации общего backend API. Не является отдельной реализацией Plugins AD5X.

### 7.3. HelixScreen / Guppy / KlipperScreen

Локальные экраны используют те же capabilities/state/actions.

- HelixScreen и Guppy получают адаптеры после стабилизации конкретного module API;
- KlipperScreen получает адаптер только после отдельной успешной AD5X runtime/platform acceptance;
- pixel-perfect parity не требуется, semantic/safety parity обязателен.

---

## 8. Hardware Manager как первый потребитель архитектуры

Hardware / Mods Manager — крупный модуль после Platform Foundation.

Ключевой сценарий:

```text
Пользователь установил физический мод
→ открыл Hardware Manager
→ включил «Установлен»
→ система применила известную конфигурацию
→ провела validation
→ показала тест/управление
```

Первый эталонный кейс — Side/AUX/PLA Fan: физическая установка не должна требовать поиска чужого конфига и ручного редактирования Klipper-файлов.

Hardware Manager не должен превращаться в огромный монолит. Он является UI/registry для отдельных hardware modules.

---

## 9. IFS policy

IFS Manager должен оперировать **конкретной катушкой**, а не только парой `material + RGB`.

Основной принцип:

> Цвет — атрибут катушки, но не её идентификатор.

Модель должна допускать:

- производителя/серию;
- материал и модификацию;
- несколько цветов;
- dual/tri/radial/coextrusion/rainbow;
- эффекты;
- Spoolman ID;
- физический слот IFS;
- профиль печати/температуры.

Автоматический выбор по близкому RGB без однозначной идентификации считается плохим UX.

---

## 10. Z Calibration Subsystem policy

D-024–D-028 и `docs/Z_CALIBRATION_SUBSYSTEM_V2.md` являются текущим контрактом и supersede старую profile-based Calibration Center модель.

### 10.1. Цель

Обычный пользователь после замены сопла/хотэнда/пластины должен иметь возможность запустить безопасную калибровку или обычную печать с автоматической проверкой и получить корректный первый слой без знания внутренних `MESH_TEST`/macro layers.

### 10.2. Стандартная Klipper-модель наружу

Внутренний provenance:

```text
Auto-Z alignment
+ persistent user Z trim
+ slicer/job Z offset
+ live babystepping
────────────────────────
= effective Klipper gcode_offset
```

Итоговое runtime-значение остаётся нормальным Klipper `gcode_offset` и наблюдаемо обычными инструментами.

Automation не перезаписывает persistent user trim без явного действия пользователя. Job offset имеет scope задания. Live adjustment можно явно сохранить в persistent user trim либо оставить transient.

### 10.3. Нет обязательных Z-профилей под каждый хотэнд

Смена длины инструмента компенсируется новой измеренной nozzle↔bed reference.

Большой подтверждённый reference delta означает `hardware_change_suspected` / full calibration, а не разрешение на огромный скрытый offset.

### 10.4. Bed mesh modes

```text
saved
saved+check   ← recommended
runtime
```

Runtime map не перезаписывает saved/default mesh автоматически. Сохранение текущей карты как основной — отдельное явное действие.

### 10.5. First-layer verifier

First-layer test является optional process/quality verification, а не обязательным шагом каждой печати и не safety interlock.

Допустимое состояние:

```text
Geometry calibration: PASS
First-layer verification: NOT RUN
```

если metrology/safety gates валидны.

Тест рекомендуется при первом включении, крупной смене hardware/plate, подтверждённом большом reference change, настройке persistent user trim или явном запросе пользователя.

### 10.6. Safety

Z Calibration обязана работать fail-closed:

- bounded search envelope;
- conservative initial-acquisition path;
- fast approach только до доказанно безопасной зоны;
- slow bounded final contact search;
- repeated sample validation;
- spread/drift/plausibility gates;
- early trigger / no trigger / communication fault → abort;
- large delta → revalidation/full calibration, не blind correction;
- failure/cancel не меняет persistent user trim и saved mesh;
- retract on abort, когда это безопасно;
- H7 является secondary signal, пока latency/stop-distance не доказаны;
- safety thresholds принимаются только после source + hardware evidence + margin.

### 10.7. Diagnostics

Backend ведёт lightweight bounded structured event log, достаточный для восстановления измерений, offset provenance, mesh decision, safety reason и результата. High-rate idle polling/telemetry не вводится.

### 10.8. Реализация

Один common backend/core обслуживает Fluidd, Mainsail, HelixScreen, Guppy и KlipperScreen. Frontend не считает Auto-Z.

Подробный test/release contract: `docs/Z_CALIBRATION_TEST_PLAN_V2.md`.

---

## 11. Print Preflight policy

Preflight — guard, а не собственный print engine.

Он проверяет состояние системы и после успешной проверки передаёт старт штатному механизму Z-Mod/Klipper.

Для Z Calibration Preflight использует backend-owned readiness/state и выбранную mesh policy; он не повторяет Auto-Z математику самостоятельно.

Не допускается создание параллельного механизма печати, который дублирует Z-Mod.

---

## 12. Fail-safe и rollback

Для каждого модуля действует правило:

> **Ошибка Plugins AD5X не должна лишать пользователя базовой возможности печатать через обычный Z-Mod.**

Минимальные требования:

- backup до мутации конфигурации;
- идемпотентная повторная установка там, где возможно;
- понятный `--status`;
- понятный disable/uninstall;
- rollback;
- отсутствие обязательной зависимости от frontend для базовой печати;
- отсутствие скрытых автоматических рестартов во время печати;
- safety-critical runtime state must fail closed rather than guess after backend/frontend disconnect.

---

## 13. Update strategy

Plugins AD5X и frontend должны обновляться отдельно от Z-Mod.

Требования:

- Z-Mod продолжает получать свои upstream-обновления;
- наш integration layer имеет собственную версию;
- frontend forks/adapters имеют собственные каналы разработки;
- upstream sync не должен автоматически попадать на принтер без build/test;
- желательно иметь compatibility matrix вида `Plugins AD5X version ↔ minimum Z-Mod version ↔ frontend base`;
- safety-critical Z Calibration compatibility must be revalidated against material Z-Mod/Klipper probe/mesh changes before public release.

### Backend deployment

D-023 managed-copy + observed-stop lifecycle является принятым production primitive для Plugins AD5X Moonraker component.

---

## 14. Development workflow

Для каждой функции:

```text
problem/use case
→ issue с границами задачи
→ архитектурное решение
→ pure/fake tests where safety/state applies
→ реализация в feature branch
→ build/static checks
→ code review
→ controlled install on test printer
→ real scenario acceptance
→ fixes
→ candidate into dev/main according to maturity
```

AI/Codex допускается как инструмент разработки, но действует правило:

> **AI drafts → source/code verification → test on printer → only then ship.**

Ни один сгенерированный конфиг, GPIO mapping, probing threshold или опасная hardware-команда не считается истинной только потому, что выглядит убедительно.

---

## 15. Критерии хорошей архитектуры

Архитектура считается движущейся в правильную сторону, если:

- новый hardware mod можно добавить отдельным модулем;
- frontend не знает лишних деталей реализации;
- удаление модуля возвращает систему в предсказуемое состояние;
- обновление Z-Mod не требует заново вручную патчить его файлы;
- отсутствие модуля не ломает UI;
- продвинутый пользователь не теряет доступ к низкоуровневой настройке;
- обычный пользователь не обязан эту низкоуровневую настройку понимать;
- safety-critical решение можно объяснить по state + structured diagnostics;
- Z Calibration не может молча превратить один аномальный sample в большой опасный offset;
- один и тот же Z Calibration backend ведёт себя одинаково независимо от выбранного frontend.