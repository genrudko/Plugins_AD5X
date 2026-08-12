# Plugins AD5X

Чистые пользовательские интеграции для Flashforge AD5X с Z-Mod.

> **[Roadmap и архитектура проекта](ROADMAP.md)** — цель проекта, UX-принципы, стратегия `main`/`dev`, Hardware Manager, IFS, Calibration Center, Print Preflight и дальнейший план развития.

Плагин `ad5x_custom` переносит локальные изменения из отслеживаемых файлов Z-Mod, Notify и Timelapse в пользовательское хранилище `mod_data`, поэтому штатные репозитории остаются `clean` и обновляются обычным способом.

## Возможности

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

## Тестовая установка Draft PR

```sh
rm -f /tmp/ad5x-custom-install.sh
wget -qO /tmp/ad5x-custom-install.sh \
  "https://raw.githubusercontent.com/genrudko/Plugins_AD5X/codex/3-camera-startup-order-repair/install.sh?cb=$(date +%s)"
chmod +x /tmp/ad5x-custom-install.sh
AD5X_CUSTOM_REF="codex/3-camera-startup-order-repair" /tmp/ad5x-custom-install.sh
```

После установки полностью выключить принтер на 20–30 секунд и включить снова.

## Диагностика

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --status
```

```sh
wget -q -T 5 -O /dev/null "http://127.0.0.1:8080/?action=snapshot" \
  && echo "[OK] Camera 1" || echo "[FAIL] Camera 1"

wget -q -T 5 -O /dev/null "http://127.0.0.1:8081/?action=snapshot" \
  && echo "[OK] Camera 2" || echo "[FAIL] Camera 2"
```

## Удаление интеграции

```sh
/opt/config/mod_data/plugins/ad5x_custom/install.sh --uninstall
```

Удаление не стирает пользовательские данные камер, IFS, таймлапса, логи и резервные копии.

Текущий work item: [CAMERA-STARTUP-ORDER-REPAIR-001](https://github.com/genrudko/Plugins_AD5X/issues/3).
