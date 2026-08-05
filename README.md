# Plugins AD5X

Чистые пользовательские интеграции для Flashforge AD5X с Z-Mod.

Плагин `ad5x_custom` переносит локальные изменения из отслеживаемых файлов Z-Mod, Notify и Timelapse в пользовательское хранилище `mod_data`, поэтому штатные репозитории остаются `clean` и обновляются обычным способом.

## Возможности

- основная камера выбирается по имени `HD Camera`, а не по нестабильному `/dev/videoN`;
- вторая камера запускается штатным пользовательским hook-файлом Z-Mod `power_on.sh`;
- при медленной USB-инициализации Camera 2 автоматически повторно ищется и запускается в фоне до 10 минут, без задержки запуска IFS;
- IFS Spoolman Manager запускается после готовности Z-Mod без изменения `.shell/root/start.sh`;
- Notify отправляет снимки с обеих камер;
- уведомление «Принтер включен» откладывается на 35 секунд без изменения `base.cfg`;
- двухкамерный timelapse сохраняет прежний захват, рендер и Telegram-отправку;
- локальные изменения Notify и Timelapse сохраняются в backup как patch, после чего их Git-репозитории очищаются;
- overlay-конфиги генерируются из текущих чистых upstream-файлов и автоматически обновляются при следующем холодном запуске;
- отдельный компонент `ad5x_custom` появляется в Moonraker Update Manager;
- при любой ошибке установки исходные конфиги и локальные версии Notify/Timelapse автоматически восстанавливаются из snapshot.

## Тестовая установка Draft PR

```sh
rm -f /tmp/ad5x-custom-install.sh
wget -qO /tmp/ad5x-custom-install.sh \
  "https://raw.githubusercontent.com/genrudko/Plugins_AD5X/feature/zmod-clean-customizations-001/install.sh?cb=$(date +%s)"
chmod +x /tmp/ad5x-custom-install.sh
AD5X_CUSTOM_REF="feature/zmod-clean-customizations-001" /tmp/ad5x-custom-install.sh
```

После установки полностью выключить принтер на 20–30 секунд и включить снова.

## Диагностика

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --status
```

## Удаление интеграции

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --uninstall
```

Удаление не стирает пользовательские данные камер, IFS, таймлапса, логи и резервные копии.
