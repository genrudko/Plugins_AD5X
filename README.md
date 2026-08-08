# Plugins AD5X

Чистые пользовательские интеграции для Flashforge AD5X с Z-Mod.

Canonical-принцип проекта: наши плагины и пользовательские интеграции живут в `mod_data`/отдельных checkout и не требуют постоянных ручных правок tracked-файлов Z-Mod, Klipper, Moonraker, Notify или Timelapse. Штатные upstream-репозитории должны оставаться `clean` и нормально обновляться.

## Модули

### `ad5x_custom`

Существующий интеграционный модуль камер/Notify/Timelapse и IFS startup customizations.

- основная камера выбирается по имени `HD Camera`, а не по нестабильному `/dev/videoN`;
- штатная Camera 1 полностью остаётся под управлением Z-Mod `S99camera`;
- Camera 2 запускается только после фактической готовности Camera 1 на порту `8080`;
- recovery Camera 2 не вызывает `S99camera restart`, не трогает Camera 1, Wi-Fi и USB-хаб;
- при медленной USB-инициализации Camera 2 автоматически повторно ищется и запускается в фоне до 10 минут;
- отсутствие Camera 2 не блокирует Camera 1, IFS и завершение загрузки;
- IFS Spoolman Manager запускается без изменения `.shell/root/start.sh`;
- Notify отправляет снимки с обеих камер;
- уведомление «Принтер включен» откладывается на 35 секунд без изменения `base.cfg`;
- двухкамерный timelapse сохраняет прежний захват, рендер и Telegram-отправку;
- локальные изменения Notify и Timelapse сохраняются в backup как patch, после чего их Git-репозитории очищаются;
- overlay-конфиги генерируются из текущих чистых upstream-файлов;
- отдельный компонент `ad5x_custom` появляется в Moonraker Update Manager;
- установка транзакционная и сохраняет диагностический backup.

Диагностика установленного модуля:

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --status
```

Удаление:

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --uninstall
```

### `calibration_center` — CALIBRATION-CENTER-001

Отдельный лёгкий модуль автоматической Z-reference калибровки и профилей хотэндов/сопел. Он намеренно не объединён с IFS, Camera Manager или другими функциями.

Ключевые свойства текущего Draft:

- reverse engineering фактической цепочки AD5X/Z-Mod выполнен до разработки интерфейса;
- физический contact reference отделён от print/process correction;
- автоматическая процедура использует 5 независимых `LOAD_CELL_TARE → PROBE` измерений;
- считается median/mean/range, нестабильная серия fail-closed отклоняется;
- ранее проверенный профиль не уничтожается неудачной повторной калибровкой;
- поддерживаются persistent hotend/nozzle profiles и previous-known-good rollback;
- `AUTO MEASURED` и `USER VERIFIED` не смешиваются;
- интеграция печати использует документированный Z-Mod `_USER_START_PRINT` hook;
- Z-Mod AutoZOffset `MESH_TEST=3/4` не дублируется второй геометрической коррекцией;
- нет фонового daemon/polling;
- нет MCU firmware operations и USB reset/unbind/bind;
- установка/обновление/удаление выполняются через отдельный `mod_data` checkout и Update Manager;
- stock Z-Mod calibration остаётся fallback.

Подробности:

- [`calibration_center/README.md`](calibration_center/README.md)
- [`calibration_center/docs/REVERSE_ENGINEERING.md`](calibration_center/docs/REVERSE_ENGINEERING.md)
- [`calibration_center/docs/ALGORITHM_AND_SAFETY.md`](calibration_center/docs/ALGORITHM_AND_SAFETY.md)
- [`calibration_center/docs/ACCEPTANCE.md`](calibration_center/docs/ACCEPTANCE.md)

Текущий work item: [CALIBRATION-CENTER-001 / issue #5](https://github.com/genrudko/Plugins_AD5X/issues/5), реализация ведётся только в Draft PR #6 до явного разрешения владельца на merge.

## Общие правила безопасности

- GitHub — canonical source кода и документации; принтер — только runtime/test environment.
- Не править tracked upstream ради пользовательских модификаций, если существует `mod_data`/plugin/overlay путь.
- Не выполнять массовые `Update all` / `Recover` как часть установки наших плагинов.
- Не выполнять MCU firmware rollback/flash ради пользовательского плагина.
- Не выполнять USB hub reset/unbind/bind: камеры и Wi-Fi могут находиться на общем hub.
- Изменения конфигурации должны быть idempotent, backup-aware и uninstallable.
- Для слабой платформы AD5X предпочтителен class A: UI/macros/event-driven logic с практически нулевой idle-нагрузкой.
