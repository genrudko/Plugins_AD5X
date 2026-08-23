# Plugins AD5X — Decision Log

> Короткий журнал решений, которые не стоит каждый раз заново обсуждать. Если решение меняется — старую запись не удалять молча, а добавить новую с пометкой `supersedes`.

---

## D-001 — Не форкать Z-Mod

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Z-Mod остаётся upstream-фундаментом. Plugins AD5X не будет отдельным форком Z-Mod.

### Почему

- большая часть низкоуровневой логики уже реализована;
- Z-Mod активно развивается автором;
- форк увеличит стоимость сопровождения;
- наша ценность — UX, интеграция и автоматизация, а не переписывание платформы.

### Следствие

Все изменения по возможности живут в user/plugin/overlay слоях и через поддерживаемые API/config includes.

---

## D-002 — GitHub является источником истины

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Архитектура, текущее состояние и активные задачи должны фиксироваться в репозитории, а не только в истории чата.

### Почему

Длинный AI-чат неизбежно теряет часть контекста. Проект должен быть восстанавливаемым новым координатором по репозиторию.

### Следствие

Минимальный набор контекстных файлов:

- `ROADMAP.md`;
- `ARCHITECTURE.md`;
- `PROJECT_STATE.md`;
- `DECISIONS.md`.

---

## D-003 — Две ветки Plugins AD5X: `main` и `dev`

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

- `main` — стабильный функционал для обычного AD5X + Z-Mod;
- `dev` — личная конфигурация, эксперименты и нестабильные функции.

### Почему

Можно развивать специфичные модификации без риска превращать публичную ветку в набор зависимостей от конкретного принтера.

### Следствие

Экспериментальные функции проектируются как модули/feature flags, чтобы их можно было стабилизировать и перенести в `main` без переписывания.

---

## D-004 — Fluidd форкается от `ghzserg/fluidd`

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Наш frontend fork основан на `ghzserg/fluidd`, а не напрямую на `fluidd-core/fluidd`.

### Ветки

- `genrudko/fluidd:develop` — upstream-sync branch;
- `genrudko/fluidd:ad5x-dev` — наша UI-разработка.

### Почему

Z-Mod уже использует и сопровождает свой Fluidd fork. Нам выгоднее оставаться downstream от этой цепочки и получать Z-Mod-специфичные изменения.

### Следствие

Собственные AD5X-фичи не коммитить напрямую в `develop`.

---

## D-005 — Минимизировать patch surface Fluidd

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

AD5X-специфичный код должен быть максимально локализован в собственной области. В upstream-файлах Fluidd менять только необходимые точки интеграции.

### Почему

Главный риск downstream frontend fork — постоянные merge conflicts при обновлениях.

### Следствие

Перед реализацией Hardware Manager сначала проводится Fluidd integration discovery.

---

## D-006 — Один backend, несколько frontend

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Бизнес-логика и состояние Plugins AD5X живут ниже UI. Fluidd, Mainsail и локальный экран используют общий API/capabilities.

### Почему

Дублирование логики в каждом frontend приведёт к расхождению поведения и утроит сопровождение.

### Следствие

Fluidd не должен становиться скрытым backend Plugins AD5X.

---

## D-007 — UX-правило 90%

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

> 90% повседневных действий должны выполняться без Wiki, SSH, консоли и знания названий макросов.

### Почему

Главная проблема AD5X + Z-Mod — не отсутствие функций, а высокий integration/knowledge tax.

### Следствие

Нормальный сценарий пользователя оформляется как мастер, карточка состояния или понятное действие. Низкоуровневые детали уходят в `Advanced`, но не исчезают.

---

## D-008 — Hardware Manager становится первым крупным модулем

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

После Platform Foundation первым большим модулем будет Hardware / Mods Manager.

### Почему

Аппаратные модификации AD5X часто физически просты, но требуют ручного поиска и редактирования конфигов. Это идеальный кейс для снижения порога входа.

### Первый эталонный use case

Side/AUX/PLA Fan.

---

## D-009 — Hardware Manager является registry, а не монолитом

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Каждая аппаратная модификация оформляется отдельным модулем с manifest/capabilities/validation. Hardware Manager только показывает, включает и управляет ими.

### Почему

Это позволяет добавлять новые community mods без разрастания одного огромного special-case файла.

---

## D-010 — IFS идентифицирует катушку, а не RGB

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Главная сущность IFS Manager — конкретная spool. Цвет является атрибутом, но не уникальным идентификатором.

### Почему

Близкие оттенки, dual/tri-color, radial, coextrusion и rainbow делают выбор только по RGB ненадёжным.

### Следствие

Модель должна поддерживать Spoolman ID, материал, производителя, эффекты, несколько цветов и физический IFS slot.

---

## D-011 — Calibration Center хранит валидность калибровки

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Для Z-offset важны не только числовое значение, но и контекст: хотэнд/сопло, дата, состояние проверки первым слоем.

### Почему

Автоматическая процедура сама по себе не гарантирует, что после замены хотэнда первый слой реально корректен.

### Следствие

После смены релевантного hardware calibration state может становиться `stale`, а UI должен предлагать мастер повторной проверки.

---

## D-012 — Print Preflight является guard

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Preflight проверяет состояние и после успеха вызывает штатный механизм старта Z-Mod/Klipper.

### Почему

Создание собственного print engine дублирует существующую систему и увеличивает риск ошибок.

---

## D-013 — UI first, daemon last

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Приоритет реализации:

```text
UI / existing API / macros
→ lightweight event-driven daemon
→ heavy service только вне AD5X
```

### Почему

Вычислительные ресурсы платформы ограничены, а большая часть UX-задач не требует постоянного backend-процесса.

### Следствие

Любой polling, постоянное логирование или background processing должны иметь явное техническое обоснование.

---

## D-014 — Fail-safe важнее удобства

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Ошибка Plugins AD5X не должна лишать пользователя возможности базовой печати через обычный Z-Mod.

### Следствие

Нужны backup, validation, uninstall и rollback; frontend не является обязательным для базовой печати.

---

## D-015 — Специфичное железо сначала живёт в `dev`

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Flook32, Air Manager, нестандартные камеры, хотэнды и прочие личные модификации сначала реализуются/обкатываются в `dev`.

### Почему

Публичный `main` не должен предполагать конкретную личную конфигурацию принтера.

### Следствие

После стабилизации модуль может быть перенесён в `main` как optional hardware module.

---

## D-016 — AI не является источником инженерной истины

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

AI/Codex используется для ускорения разработки, поиска, glue code, UI, тестов и рефакторинга, но критичные утверждения проверяются по исходникам и на железе.

### Правило

> **AI drafts → source/code verification → test on printer → only then ship.**

### Особенно проверять

- GPIO/pin mapping;
- команды, которые меняют конфигурацию;
- update-manager semantics;
- hardware safety;
- поведение при restart/update;
- любые действия, способные нарушить печать.

---

## D-017 — Не кодить Hardware Manager до Fluidd discovery

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Сначала изучить структуру `genrudko/fluidd:ad5x-dev`, определить navigation/route/page/store/API integration points и только затем создавать UI-каркас.

### Почему

Предварительная реализация без знания фактической архитектуры Fluidd почти гарантированно создаст лишний patch surface и последующий рефакторинг.

---

## D-018 — Fluidd интегрируется через две минимальные upstream-точки

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Основная область frontend-кода Plugins AD5X живёт в `src/ad5x/**`. В штатных файлах Fluidd нормальный целевой patch surface ограничивается двумя integration seams:

- `src/components/layout/AppNavDrawer.vue` — одна точка входа в навигации;
- `src/router/index.ts` — подключение AD5X route tree.

`src/App.vue`, существующие `src/views/*`, глобальный Moonraker transport и корневой Vuex registry не следует менять без доказанной необходимости.

### Почему

Фактический Fluidd уже предоставляет общий layout через `<router-view>`, централизованный router, штатный WebSocket/Moonraker transport и capability precedent через `server/componentSupport`. Размазывание AD5X-кода по этим подсистемам не даёт функциональной выгоды, но увеличивает стоимость upstream sync.

### Следствие

Новые AD5X views, API adapters, state и capability helpers создаются внутри `src/ad5x/**`. Если proof-of-concept требует дополнительных upstream-правок, сначала нужно обосновать расширение patch surface.

---

## D-019 — AD5X route статический, навигация capability-gated

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Маршрут `/ad5x` регистрируется статически вместе с Fluidd router, а пункт `Plugins AD5X` в основной навигации показывается только при подтверждённом наличии backend-компонента.

При прямом переходе на `/ad5x` без backend страница должна безопасно показать состояние `backend unavailable` и не выполнять AD5X-specific RPC.

### Почему

Динамическая регистрация маршрута зависит от асинхронного lifecycle `server.info` и создаёт ненужную гонку между router initialization и capability detection. Статический route проще, предсказуемее и полезнее для диагностики.

### Следствие

Отсутствие Plugins AD5X backend не должно менять штатную работу Fluidd: навигационный пункт скрыт, базовые страницы и печать продолжают работать как обычно.

---

## D-020 — Capability detection двухступенчатый и принадлежит backend

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Capability detection разделяется на два уровня:

1. coarse detection — наличие самого Plugins AD5X backend через Moonraker `server.info.components` / существующий Fluidd getter `server/componentSupport(...)`;
2. detailed capabilities/state — отдельный backend-owned Plugins AD5X API contract, возвращающий API/backend version и поддерживаемые module capabilities/state.

Frontend не должен самостоятельно выводить наличие модулей из Klipper config, GPIO, макросов, USB-устройств или других низкоуровневых признаков.

### Почему

`server.info.components` отвечает только на вопрос «backend загружен», но не описывает установленное железо, совместимость, управляемость или текущее состояние. Самостоятельный detection во Fluidd превратит frontend в второй backend и нарушит принцип одного API для Fluidd/Mainsail/local screen.

### Следствие

Конкретное имя RPC method и окончательная схема capability payload пока не фиксируются. Они должны быть определены отдельным узким решением Platform Foundation после проверки backend-требований. Текущий `ad5x_custom` не считается уже имеющим такой API только на основании frontend discovery.

---

## D-021 — `ad5x-dev` получает отдельный downstream CI workflow

**Дата:** 2026-08-12
**Статус:** accepted

### Решение

Для `genrudko/fluidd:ad5x-dev` создаётся отдельный downstream-only GitHub Actions workflow, который проверяет feature-head напрямую и не изменяет штатный upstream `.github/workflows/build.yml`.

Workflow должен запускаться минимум на push в `ad5x-dev` и вручную через `workflow_dispatch`, повторяя релевантные штатные проверки Fluidd: dependency install с lockfile, lint, type-check, unit tests, circular references check и production build.

### Почему

Штатный Fluidd `BUILD` запускается только для `develop/master`, тегов `v*` и PR в `develop/master`. Поэтому feature-head `ad5x-dev` сейчас может содержать непроверенные изменения, а запуск проверки через временный PR, тег или перенос feature-кода в `develop` нарушает принятую веточную модель.

Отдельный downstream workflow даёт постоянную проверку нашей рабочей ветки без расширения product patch surface и без изменения upstream CI semantics.

### Следствие

- upstream `build.yml` не менять ради Plugins AD5X;
- CI-файл является downstream infrastructure и может жить отдельно в `ad5x-dev`;
- frontend shell PoC не считается полностью прошедшим Definition of Done, пока exact feature-head не получил успешные обязательные проверки;
- после успешного CI dynamic Vuex hypothesis можно подтвердить или отвергнуть по фактическому `type-check/tests/build`;
- результаты acceptance фиксируются в `PROJECT_STATE.md` только после реального выполнения workflow.

---

## D-022 — Backend contract v1 строится как optional Moonraker component

**Дата:** 2026-08-12
**Статус:** accepted
**Уточняет:** D-013, D-014, D-020

### Решение

Plugins AD5X backend для Platform Foundation реализуется как **optional in-process Moonraker component** с production component name:

```text
plugins_ad5x
```

Связь имён:

```text
Moonraker component file: components/plugins_ad5x.py
Moonraker config section: [plugins_ad5x]
server.info.components: "plugins_ad5x"
```

Отдельный daemon/agent и собственная база данных для Platform Foundation не создаются без нового доказанного требования.

`server.info.components` используется только как coarse presence signal. Наличие `plugins_ad5x` в `components` **не означает health/readiness**: Moonraker может одновременно держать имя в `components` и `failed_components`, если object был создан, но `component_init()` завершился ошибкой. Detailed readiness/health принадлежит Plugins AD5X snapshot API.

### API v1

Минимальный read-only snapshot endpoint:

```text
HTTP:      GET /server/plugins_ad5x/snapshot
JSON-RPC:  server.plugins_ad5x.snapshot
```

Endpoint использует Moonraker authentication (`auth_required=true`) и при реализации должен **явно ограничить transports до HTTP + WEBSOCKET**, а не использовать default `TransportType.all()`, который также включает MQTT/INTERNAL.

Минимальный platform envelope snapshot:

```text
api_version
backend_version
revision
backend.health
modules{}
```

Общий module envelope различает как разные смыслы:

```text
support
enabled
presence
available
health
capabilities[]
state{}
```

Допустимы `unknown` / `not_applicable`, когда backend не может доказательно установить конкретное состояние. `available` вычисляется backend/module provider, а не frontend.

`api_version` имеет формат `MAJOR.MINOR`: major меняется при breaking semantics/schema/endpoint change, minor — при backward-compatible additions. `backend_version` остаётся release version Plugins AD5X и не заменяет API version.

### State propagation

После initial snapshot используется одна низкочастотная invalidation-схема:

```text
internal event: plugins_ad5x:snapshot_changed
wire notification: notify_plugins_ad5x_snapshot_changed
```

Notification сообщает, что snapshot устарел; source of truth остаётся snapshot endpoint. `revision` — монотонный номер **только в пределах одного процесса Moonraker** и не является persistent counter.

После WebSocket reconnect frontend выполняет полный resync:

```text
server.info → coarse presence → fresh snapshot
```

Steady-state polling не используется. `snapshot_changed` предназначен для смысловых lifecycle/capability/control-state изменений, а не для будущей высокочастотной telemetry; при появлении high-rate data для неё должен быть отдельный доказанно необходимый механизм.

### Почему

Фактический `ghzserg/zmod_moonraker` использует тот же исследованный component/API lifecycle, что и текущий upstream Moonraker: optional component может не загрузиться без остановки всего Moonraker, endpoints регистрируются через штатный API definition, notification bridge уже существует, а authentication обслуживается Moonraker. Это позволяет получить единый frontend-neutral backend без второго процесса, второго auth contour и постоянного polling.

### Следствие

- provisional frontend method `plugins_ad5x.get_capabilities` не становится production contract и должен быть заменён на `server.plugins_ad5x.snapshot` при backend PoC integration;
- ожидаемые module/hardware failures выражаются через snapshot health/state, а не должны валить весь Moonraker;
- constructor/load path компонента должен оставаться минимальным, а blocking I/O на Moonraker event loop запрещён;
- deployment способ (`symlink`/`copy`) в Moonraker components остаётся implementation detail до проверки на реальном Z-Mod на import, update, uninstall, rollback и clean-state;
- exact установленный Moonraker runtime commit на реальном AD5X пока не доказан и должен быть проверен read-only перед printer deployment/acceptance;
- Hardware Manager, AUX Fan и другие module implementations не входят в backend foundation PoC.

---

## D-023 — Backend runtime component deploys as managed copy with observed-stop lifecycle

**Дата:** 2026-08-13
**Статус:** superseded by D-024
**Уточняет:** D-014, D-022

> Deployment/ownership часть этого решения историческая и superseded D-024. Hardware evidence и observed-stop/readiness выводы сохраняются.

### Решение

Production runtime Plugins AD5X backend развёртывается как **managed copy** в Moonraker components:

```text
installed Plugins_AD5X checkout
        ↓
validate exact source artifact/version
        ↓
atomic managed copy
        ↓
/opt/config/base/moonraker/components/plugins_ad5x.py
```

Plugins AD5X checkout не является runtime import target и не связывается с Moonraker через symlink. Изменение Git checkout само по себе не должно немедленно менять исполняемый runtime-код.

До replacement installer проверяет backend artifact, API/backend versions, runtime destination directory и ownership существующего destination. Неизвестный существующий destination не перезаписывается. Managed copy создаётся через temporary file в том же destination directory, permissions/hash verification и atomic rename.

Для backend deployment/update/uninstall/rollback запрещено использовать:

```sh
/etc/init.d/S65moonraker restart
```

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
wait HTTP /server/info
↓
wait klippy_connected=true
↓
wait klippy_state=ready
```

HTTP reachability сама по себе не является readiness; `klippy_state=startup` также не является final ready. Bounded timeout приводит к failure/rollback. Автоматический `kill -9` не используется.

Moonraker hard recovery / `git clean` может удалить untracked managed runtime component. Это ожидаемый destructive external event: Plugins AD5X apply/repair обязан восстановить runtime artifact из exact installed checkout. Untracked component в Moonraker tree является известным trade-off и **не маскируется** через `.git/info/exclude`.

Uninstall удаляет только доказанно owned runtime component, backend activation и `plugins_ad5x*.pyc`; неизвестный destination оставляется нетронутым с fail-safe error. Rollback восстанавливает exact pre-operation backend/config state и исходное running-state Moonraker без рекурсивных restart loops.

### Почему

Controlled acceptance на физическом AD5X доказал managed-copy load/API compatibility и clean rollback. Одновременно был обнаружен lifecycle race штатного Z-Mod `S65moonraker restart`: SIGTERM наблюдался в `23:50:13.211`, shutdown завершился только в `23:50:15.565` (~2.35 s), тогда как init script ждёт фиксированные 2 секунды. `start` сработал до завершения старого Python и сообщил, что `/root/moonraker-env/bin/python3 is already running`; после завершения старого процесса Moonraker остался выключенным.

Следовательно, fixed sleep не может быть критерием shutdown/readiness. Нужна наблюдаемая граница по фактическому процессу и фактическому Klippy state.

### Следствие

- deployment detail, оставленный открытым D-022, разрешён в пользу managed copy;
- Git checkout update ≠ runtime update — это намеренное свойство;
- `install.sh --apply-only` является явной apply/repair operation после update/hard recovery;
- `--refresh-only` остаётся лёгким overlay-refresh и не запускает backend service transition;
- backend runtime/config входят в существующий snapshot/rollback contour;
- `--status` различает source/runtime/config/component/snapshot и service-unavailable state;
- production installer не скрывает managed runtime artifact из Moonraker Git status.

---

## D-024 — Plugins AD5X использует штатный Z-Mod plugin lifecycle и не владеет core worktree

**Дата:** 2026-08-23
**Статус:** accepted
**Supersedes:** deployment/ownership часть D-023
**Уточняет:** D-001, D-014, D-022

### Решение

Canonical source Plugins AD5X живёт только в `/opt/config/mod_data/plugins/ad5x_custom`. Интеграция с Klipper/Moonraker выполняется plugin-owned symlink-ами, а не копированием или patch tracked core files. Runtime link paths локально исключаются через `.git/info/exclude`; uninstall/detach удаляет только наши links/exclude entries.

Z-Mod lifecycle используется напрямую:

- `install.sh` — initial activation / `ENABLE_PLUGIN`;
- `update.sh` — post-update reconciliation из Moonraker Update Manager;
- `uninstall.sh` — runtime detach / `DISABLE_PLUGIN`;
- ручной `install.sh --uninstall` — полный unregister.

Moonraker links: `plugins_ad5x.py`, `plugins_ad5x_ifs_model.py`, `plugins_ad5x_ifs_interop.py`, `plugins_ad5x_ifs_spoolman.py`. Klipper link: `klippy/extras/ad5x_ifs.py`. Все targets указывают в Plugins AD5X checkout.

### Ownership и migration

Отсутствующий destination можно создать. Exact symlink на installed checkout считается owned. Legacy managed-copy artifact с доказанным ownership hash или точным совпадением current source безопасно мигрируется в link. Любой другой existing file/link считается foreign и не перезаписывается. Backup/rollback сохраняет тип symlink и target.

### Update semantics

`update.sh` не останавливает и не запускает Moonraker: hook выполняется дочерним процессом Update Manager и не должен убивать родителя. Он re-links/reconciles config и ставит `runtime-restart-required`; новый Python-код применяется после нормального нового host process/cold boot. `DISABLE_PLUGIN` сохраняет checkout и Update Manager registration.

### Почему

Source audit Z-Mod подтвердил `ENABLE_PLUGIN`, `DISABLE_PLUGIN`, `install.sh`, `uninstall.sh`, Update Manager `update.sh` и symlink precedent для Klipper Python extras. Такая схема не требует tracked patches в Z-Mod/Klipper/Moonraker и минимизирует риск блокировки их штатных обновлений.

### Hard recovery boundary

Destructive hard recovery/reclone core repository может удалить runtime symlinks вместе с пересозданным tree. Общий Z-Mod startup не доказан как автоматически повторно запускающий `install.sh` каждого enabled plugin после такого recovery, поэтому automatic self-repair не обещается. Поддерживаемый recovery — повторный `ENABLE_PLUGIN`/`install.sh` (explicit repair).

### Следствия

При активном полном IFS Manager legacy `/opt/config/mod_data/ifs_spoolman/start.sh` не запускается параллельно: Spoolman runtime ownership принадлежит Plugins AD5X backend + native Moonraker Spoolman. Это не отменяет standalone IFS/Spoolman как отдельный lightweight product path. Любой будущий Python extra/component Plugins AD5X обязан использовать тот же lifecycle; прямой copy/patch в core worktree требует нового явного решения. Observed-stop часть D-023 остаётся применимой к installer-owned service transitions, но не к Update Manager hook.

---

## D-025 — Физическое присутствие сильнее cached spool identity; standalone Spoolman сохраняется как отдельный product path

**Дата:** 2026-08-23
**Статус:** accepted
**Уточняет:** D-010, D-014, D-024

### Решение

Для полного IFS Manager `present=false` является авторитетным фактом: пустой физический слот не может отображать прежнюю concrete spool как установленную. При подтверждённом occupied→empty переходе current local/Spoolman binding удаляется, а persistent identity-invalidated tombstone запрещает автоматическое воскрешение прежнего exact spool ID после следующей вставки. External Spoolman entity не удаляется.

После новой вставки без RFID/другого проверенного identity provider exact identity остаётся `unassigned` до нового bind/edit. Z-Mod material/color могут отображаться как provider-observed metadata, но не являются доказательством возврата прежней concrete spool.

Существующий standalone IFS/Spoolman сценарий не объявляется deprecated только потому, что полный IFS Manager получил собственную Spoolman интеграцию. Он сохраняется как отдельный lightweight product path для пользователей, которым нужен только IFS↔Spoolman. Целевой standalone v2 должен использовать те же четыре slot bindings и automatic native Moonraker active-spool semantics, предпочтительно на общем semantic core. На одном принтере full и standalone режимы не должны одновременно владеть runtime.
---

## D-026 — Frontend IFS реализуется Fluidd-first; KlipperScreen последним

**Дата:** 2026-08-24
**Статус:** accepted
**Уточняет:** D-004, D-005, D-017, D-018

### Решение

Порядок first-party IFS frontend implementation: `Fluidd → Mainsail → GuppyScreen → HelixScreen → KlipperScreen`. Fluidd является первым каноническим UI. Mainsail следует после стабилизации Fluidd UX/contract. Guppy и Helix используют тот же backend/API. KlipperScreen возвращается в активную разработку только после завершения нормального AD5X-порта самого KlipperScreen.

Существующие IFS panels в `tools/ad5x-display-spike/klipperscreen/` считаются PoC/test evidence и не являются канонической UX-базой.

### Почему

Fluidd уже принят как первый frontend Plugins AD5X и имеет существующую `src/ad5x/**` UI-базу. Source review Happy Hare/official Fluidd подтвердил зрелый native pre-print mapping precedent. Текущий AD5X KlipperScreen остаётся экспериментальным портом, поэтому развитие IFS на нём сейчас создаёт лишнюю повторную переделку.

### Следствия

- незакоммиченный KlipperScreen mapping-editor draft отменён;
- frontend-neutral manual mapping draft/preview token остаются частью backend contract;
- следующий UI increment выполняется в `genrudko/fluidd:ad5x-dev` и начинается с сверки существующего `src/ad5x/**` с Happy Hare/official Fluidd/Helix/PAXX reference pack;
- KlipperScreen не используется как design proving ground до готовности его базового AD5X-порта.
