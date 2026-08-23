# Plugins AD5X

Пользовательские интеграции для Flashforge AD5X с Z-Mod: единый backend для IFS / материалов, калибровки, камер и других возможностей без форка аппаратной логики Z-Mod.

## Ключевой принцип

**Z-Mod остаётся provider-слоем**, а Plugins AD5X превращает его возможности в нормальный продуктовый backend/API и нативные интерфейсы.

Для IFS это означает:

```text
Flashforge IFS
    ↓
Z-Mod provider
    ↓
Plugins AD5X canonical backend
    ├─→ Fluidd
    ├─→ Mainsail
    ├─→ HelixScreen
    ├─→ GuppyScreen
    ├─→ KlipperScreen
    ├─→ любой другой Klipper/Moonraker client
    └─→ compatibility projections (например OrcaSlicer lane_data)
```

Frontend не должен реализовывать собственную аппаратную логику, matcher, safety или print lifecycle.

## Документация проекта

Основной проектный контекст:

- **[ROADMAP.md](ROADMAP.md)** — фазы/приоритеты проекта;
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — общие архитектурные границы;
- **[PROJECT_STATE.md](PROJECT_STATE.md)** — текущее состояние;
- **[DECISIONS.md](DECISIONS.md)** — журнал решений.

IFS / Materials Manager:

- **[IFS_MANAGER_CONTRACT.md](IFS_MANAGER_CONTRACT.md)** — canonical runtime/product contract v2;
- **[docs/IFS_MANAGER_ARCHITECTURE_V2.md](docs/IFS_MANAGER_ARCHITECTURE_V2.md)** — целевая frontend-neutral архитектура;
- **[docs/IFS_MANAGER_PRODUCT_REQUIREMENTS.md](docs/IFS_MANAGER_PRODUCT_REQUIREMENTS.md)** — продуктовые требования;
- **[docs/IFS_MANAGER_DISCOVERY_2026-08-22.md](docs/IFS_MANAGER_DISCOVERY_2026-08-22.md)** — результаты расширенного исследования Z-Mod/Orca/Happy Hare/Helix/AFC;
- **[docs/ZMOD_IFS_MANAGER_PARITY_AUDIT_2026-08-17.md](docs/ZMOD_IFS_MANAGER_PARITY_AUDIT_2026-08-17.md)** — parity floor относительно Z-Mod.

> Источник истины по коду и актуальному состоянию — GitHub/repository state, а не история чата.

## IFS / Materials Manager

Цель — убрать необходимость пользоваться stock Z-Mod IFS manager в обычных и Expert-сценариях, **не переписывая доказанную механику Z-Mod**.

### Expert / Hybrid / Auto

`Expert` — канонический полный capability surface.

`Hybrid` и `Auto` — только progressive-disclosure представления того же backend:

```text
Expert → полный контроль и диагностика
Hybrid → основные действия + контекстный mapping
Auto   → минимум шума, автоматические решения и понятные проблемы
```

Выбор «экспертности» интерфейса не меняет physical truth, capabilities и safety policy.

### Основной UI

Главный IFS экран строится вокруг реальной топологии AD5X:

- 4 физических IFS-слота;
- selector;
- один extruder/toolhead;
- отдельный external/bypass source, если его runtime/provider semantics подтверждены.

Tool mapping (`T0/T1/... → slot`) — прежде всего состояние конкретной печати и показывается контекстно в pre-print/active-job workflow.

### Provider parity

Plugins AD5X должен охватить все надёжные возможности Z-Mod, включая physical state, load/unload/select, scan/auto assignment, mismatch diagnostics, print/change-filament lifecycle, recovery primitives и equivalent/endless-spool semantics. Там, где Z-Mod уже имеет зрелую механику, Plugins AD5X делает semantic wrapper/UX, а не вторую реализацию.

## OrcaSlicer: синхронизация материалов из IFS

Целевой первый compatibility baseline: **OrcaSlicer 2.4.2**.

Orca умеет забирать material/color физического multi-material устройства через Moonraker namespace `lane_data`. Plugins AD5X использует этот стандартный путь — **форк Orca не требуется**.

### Обязательная настройка Orca

В настройках физического принтера должно быть:

```text
Тип хоста:      Octo/Klipper
Сетевой агент:  Moonraker
Имя хоста/IP:   <IP принтера>:7125
```

Если выбран другой сетевой агент, generic Moonraker `lane_data` sync работать не будет.

### Что синхронизируется

Plugins AD5X публикует 4 стабильные записи `lane1..lane4` с внутренними lane `"0".."3"`.

Для текущей Orca полезны прежде всего:

- physical lane;
- material;
- representative color;
- optional nozzle/bed temperatures.

Проверить printer-side projection можно напрямую:

```text
http://<IP-принтера>:7125/server/database/item?namespace=lane_data
```

### Ограничение exact filament preset

На текущем generic Moonraker path Orca ещё не гарантирует детерминированный выбор **конкретного пользовательского filament preset**.

Поэтому Plugins AD5X:

- не выдаёт Spoolman filament ID за Orca `filament_id`;
- хранит Spoolman spool/filament IDs отдельно;
- хранит будущую exact Orca identity отдельно;
- не угадывает specialty material (`ASA-GF`, `PLA Matte`, etc.) как generic material, если нет явной безопасной compatibility mapping.

Это защищает от ситуации, когда цвет/тип синхронизировались, но Orca выбрала неправильный профиль прутка.

## Spoolman

Spoolman — опциональная library/inventory интеграция, а не источник физической истины. Full IFS Manager использует четыре постоянных slot bindings, но отдаёт учёт расхода штатному Moonraker Spoolman для одной реально активной катушки/экструдера.

Full IFS Manager умеет:

- искать и выбирать реальные Spoolman spools;
- bind/unbind конкретную spool ↔ физический IFS Slot 1–4;
- импортировать vendor/material/color/name/remaining и поддерживаемые температуры;
- автоматически переводить native Moonraker `active_spool` вслед за реально активным IFS-слотом;
- не запускать второй consumption daemon;
- не удалять Spoolman entity при физическом извлечении катушки;
- нормально работать без Spoolman.

### Физическая замена катушки

`present=false` сильнее любой сохранённой metadata. Как только ранее занятый слот подтверждённо становится пустым, старая concrete spool больше не является установленной: локальный current binding удаляется, а persistent identity tombstone не даёт старому Spoolman ID воскреснуть при следующей вставке. Сама катушка остаётся в библиотеке Spoolman.

После новой вставки без RFID/другого доказанного идентификатора exact spool state — `unassigned`. Z-Mod provider material/color можно показывать как наблюдаемые свойства, но они не доказывают, что вернулась прежняя concrete spool. Новый bind/edit снимает tombstone.

### Standalone Spoolman bridge

Существующий lightweight IFS/Spoolman сценарий сохраняется как отдельный полезный product path для пользователей, которым не нужен полный Materials Manager. Его целевое развитие — те же четыре slot bindings + automatic active-spool tracking на общем semantic core.

На одном принтере не должно быть двух runtime owners. Full Plugins AD5X поэтому не запускает legacy `/opt/config/mod_data/ifs_spoolman/start.sh` параллельно своему backend; это не означает отказ от standalone продукта или удаление пользовательских Spoolman данных.

## Текущая safety boundary IFS

Реально проверенные select/load/unload остаются под backend permission gates.

До отдельной source + hardware acceptance остаются выключены:

```text
apply_preprint_mapping = false
start_job / PRINT_ZCOLOR = false
zmod material/color projection writes = false
automatic equivalent/endless spool = false
unproven recovery motion = false
automated external/bypass switching = false
```

CI и документация не заменяют hardware proof.

## Камеры

Текущая camera integration сохраняет следующие принципы:

- основная камера выбирается по USB identity/name (`HD Camera`), а не по нестабильному `/dev/videoN`;
- штатная Camera 1 остаётся под управлением Z-Mod `S99camera`;
- Camera 2 не должна ломать Camera 1/IFS/startup при отсутствии или медленной USB-инициализации;
- recovery Camera 2 не рестартует Camera 1, Wi-Fi или USB hub;
- Notify/Timelapse могут использовать обе камеры через существующий managed overlay.

## Z-Mod plugin lifecycle / установка

`ad5x_custom` устанавливается как штатный Z-Mod plugin. Единственный source checkout живёт в `/opt/config/mod_data/plugins/ad5x_custom`; Python extras/components подключаются plugin-owned symlink-ами и не требуют tracked patches в Git worktree Klipper/Moonraker. Это сохраняет штатную обновляемость Z-Mod, Klipper, Moonraker и соседних plugins.

Lifecycle:

- `ENABLE_PLUGIN NAME=ad5x_custom` / `install.sh` — activation;
- `update.sh` — post-update re-link/reconcile из Moonraker Update Manager без self-restart Moonraker;
- `DISABLE_PLUGIN NAME=ad5x_custom` / `uninstall.sh` — detach runtime, repository и Update Manager registration сохраняются;
- `install.sh --uninstall` — полный unregister.

Runtime link paths добавляются только в локальный `.git/info/exclude` core repositories и удаляются при detach/uninstall. Legacy owned managed-copy installation мигрирует в symlink; неизвестный существующий destination не перезаписывается.

Destructive hard recovery/reclone core repository может удалить symlink. Автоматический rerun `install.sh` для каждого enabled plugin после такого recovery Z-Mod не гарантирует; поддерживаемое восстановление — повторный `ENABLE_PLUGIN`/`install.sh`.

### Status

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --status
```

### Полное удаление

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --uninstall
```

Пользовательские данные камер, IFS, таймлапса, логи и резервные копии при detach/uninstall не должны стираться.

## Важное про Python Klipper extras на AD5X

Если обновился managed Python extra Klipper (например `ad5x_ifs.py`), `FIRMWARE_RESTART` не гарантирует загрузку нового Python-модуля в уже живом host process.

Для hardware acceptance после такого изменения нужен **реальный новый Klippy process**. Пока безопасный доказанный путь на AD5X — полный power cycle/cold boot, если отдельно не доказан корректный OS-level process restart.

## Разработка

Активные feature work items ведутся в своих существующих issue/branch/Draft PR контурах. Не создавать параллельные ветки/PR и не merge/Ready-for-Review без явного решения владельца.
