# Plugins AD5X

Чистые пользовательские интеграции для Flashforge AD5X с Z-Mod.

Плагин `ad5x_custom` переносит локальные изменения из отслеживаемых файлов Z-Mod, Notify и Timelapse в отдельный репозиторий и пользовательское хранилище `mod_data`.

## Возможности

- выбор основной камеры по имени до штатного `S99camera`;
- автозапуск сохранённого рабочего скрипта второй камеры;
- уведомления и снимки с двух камер без изменения репозитория `notify`;
- захват второй камеры для timelapse без изменения репозитория `timelapse`;
- автозапуск AD5X IFS Plugin for Spoolman после Moonraker;
- отдельный компонент `ad5x_custom` в Moonraker Update Manager;
- резервные копии и обратимый uninstall.

Патчированные конфиги Notify и Timelapse генерируются в `mod_data/ad5x_custom/generated` из текущих upstream-файлов. Поэтому сами upstream-репозитории остаются `clean` и могут обновляться штатно.

## Установка

```sh
rm -f /tmp/ad5x-custom-install.sh
wget -qO /tmp/ad5x-custom-install.sh \
  "https://raw.githubusercontent.com/genrudko/Plugins_AD5X/main/install.sh?cb=$(date +%s)"
chmod +x /tmp/ad5x-custom-install.sh
/tmp/ad5x-custom-install.sh
```

Проверка ветки Draft PR:

```sh
AD5X_CUSTOM_REF=feature/zmod-clean-customizations-001 /tmp/ad5x-custom-install.sh
```

После установки требуется полное выключение и включение принтера.

## Диагностика

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --status
```
