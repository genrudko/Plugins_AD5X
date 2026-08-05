#!/bin/sh
set -eu

REPO_URL="https://github.com/genrudko/Plugins_AD5X.git"
PLUGIN_DIR="/opt/config/mod_data/plugins/ad5x_custom"
STATE_DIR="/opt/config/mod_data/ad5x_custom"
GENERATED="$STATE_DIR/generated"
STATE="$STATE_DIR/state"
BACKUPS="$STATE_DIR/backups"
LOG_DIR="$STATE_DIR/log"
KLIPPER_INCLUDES="/opt/config/mod_data/plugins.cfg"
MOONRAKER_INCLUDES="/opt/config/mod_data/plugins.moonraker.conf"
USER_MOONRAKER="/opt/config/mod_data/user.moonraker.conf"
POWER_ON="/opt/config/mod_data/power_on.sh"
REF="${AD5X_CUSTOM_REF:-main}"
MODE="${1:-}"

if [ -z "${AD5X_CUSTOM_REF+x}" ] && [ -f "$PLUGIN_DIR/.git/HEAD" ]; then
    HEAD_LINE="$(cat "$PLUGIN_DIR/.git/HEAD" 2>/dev/null || true)"
    case "$HEAD_LINE" in ref:\ refs/heads/*) REF="${HEAD_LINE#ref: refs/heads/}" ;; esac
fi

fail(){ echo "ОШИБКА: $*" >&2; exit 1; }
find_root(){
    for P in /proc/[0-9]*; do
        [ -r "$P/cmdline" ] || continue
        CMD="$(tr '\0' ' ' <"$P/cmdline" 2>/dev/null || true)"
        case "$CMD" in *moonraker.py*) [ -d "$P/root" ] && { echo "$P/root"; return 0; };; esac
    done
    [ -d /usr/data/.mod/.zmod ] && { echo /usr/data/.mod/.zmod; return 0; }
    return 1
}
remove_lines(){ F="$1"; P="$2"; [ -f "$F" ] || : >"$F"; grep -Ev "$P" "$F" >"$F.tmp" 2>/dev/null || true; mv "$F.tmp" "$F"; }
append_line(){ F="$1"; L="$2"; [ -f "$F" ] || : >"$F"; grep -Fqx "$L" "$F" 2>/dev/null || echo "$L" >>"$F"; }
backup(){ [ -f "$1" ] && cp -p "$1" "$2/${1##*/}" || true; }
snapshot(){
    FILE="$1"; KEY="$2"
    if [ -e "$FILE" ]; then
        cp -p "$FILE" "$B/$KEY"
    else
        : >"$B/.absent-$KEY"
    fi
}
restore_snapshot(){
    FILE="$1"; KEY="$2"
    if [ -f "$B/.absent-$KEY" ]; then
        rm -f "$FILE"
    elif [ -e "$B/$KEY" ]; then
        cp -p "$B/$KEY" "$FILE"
    fi
}
save_lines(){ [ -f "$3" ] && return 0; [ -f "$1" ] || : >"$1"; grep -E "$2" "$1" >"$3" 2>/dev/null || : >"$3"; }
restore_lines(){ [ -f "$2" ] || return 0; while IFS= read -r L; do [ -n "$L" ] && append_line "$1" "$L"; done <"$2"; }
strip_block(){
    F="$1"; BEGIN_MARK="$2"; END_MARK="$3"
    [ -f "$F" ] || return 0
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
        index($0,b){skip=1;next}
        index($0,e){skip=0;next}
        !skip{print}
    ' "$F" >"$F.tmp"
    mv "$F.tmp" "$F"
}
repo_status(){
    ROOT="$1"; NAME="$2"; PATH_="$3"
    if ! chroot "$ROOT" /usr/bin/git -C "$PATH_" rev-parse --git-dir >/dev/null 2>&1; then printf '%-14s N/A\n' "$NAME"; return; fi
    S="$(chroot "$ROOT" /usr/bin/git -C "$PATH_" status --porcelain 2>/dev/null || true)"
    [ -z "$S" ] && printf '%-14s CLEAN\n' "$NAME" || printf '%-14s DIRTY\n' "$NAME"
}
check_idle(){
    STATE_JSON="$(wget -qO- 'http://127.0.0.1:7125/printer/objects/query?print_stats' 2>/dev/null || true)"
    case "$STATE_JSON" in
        *'"state":"printing"'*|*'"state": "printing"'*|*'"state":"paused"'*|*'"state": "paused"'*)
            fail 'принтер сейчас печатает или стоит на паузе'
            ;;
    esac
}
install_generated(){
    TMP="$1"; OUT="$2"
    if [ -f "$OUT" ] && cmp -s "$TMP" "$OUT"; then
        rm -f "$TMP"
    else
        mv -f "$TMP" "$OUT"
        GENERATED_CHANGED=1
    fi
}

generate_notify(){
    SOURCE="/opt/config/mod_data/plugins/notify/ru/notify.cfg"
    TMP="$GENERATED/notify.cfg.tmp.$$"
    [ -f "$SOURCE" ] || fail "не найден $SOURCE"

    awk '
BEGIN{inside=0;gate=0;camera=0}
/^\[gcode_macro _NOTIFY\]$/ {inside=1; print; next}
inside && /^\[/ {
    if (gate) print "    {% endif %} # AD5X_CUSTOM_NOTIFY_GATE_END"
    inside=0
    print
    next
}
{
    if (inside && !gate && /set type = params.TYPE/) {
        print
        print ""
        print "    {% set delayed = params.DELAYED|default(0)|int %}"
        print ""
        print "    # AD5X_CUSTOM_NOTIFY_GATE_BEGIN"
        print "    {% if type == \"on\" and delayed == 0 %}"
        print "        UPDATE_DELAYED_GCODE ID=ad5x_custom_power_on_notify DURATION=35"
        print "    {% else %}"
        gate=1
        next
    }
    print
    if (inside && gate && !camera && /message=msg\)\}/) {
        print "        {% if photo == 1 and notify_photo == 1 %}"
        print "            {action_call_remote_method(\"notify\","
        print "                                 name=\"notifier_photo_camera2\","
        print "                                 message=msg)}"
        print "        {% endif %}"
        camera=1
    }
}
END{
    if (inside && gate) print "    {% endif %} # AD5X_CUSTOM_NOTIFY_GATE_END"
    if (!gate || !camera) exit 42
}' "$SOURCE" >"$TMP" || { rm -f "$TMP"; fail 'не удалось сгенерировать notify overlay'; }

    grep -q 'AD5X_CUSTOM_NOTIFY_GATE_BEGIN' "$TMP" || fail 'в notify overlay отсутствует задержка включения'
    grep -q 'notifier_photo_camera2' "$TMP" || fail 'в notify overlay отсутствует камера 2'
    install_generated "$TMP" "$GENERATED/notify.cfg"
}

generate_timelapse(){
    SOURCE="/opt/config/mod_data/plugins/timelapse/timelapse.cfg"
    TMP1="$GENERATED/timelapse.step1.$$"
    TMP2="$GENERATED/timelapse.cfg.tmp.$$"
    [ -f "$SOURCE" ] || fail "не найден $SOURCE"

    awk '
BEGIN{inside=0;inserted=0}
/^\[gcode_macro _TIMELAPSE_NEW_FRAME\]$/ {inside=1}
inside && /action_call_remote_method\("timelapse_newframe"/ && !inserted {
    print " RUN_SHELL_COMMAND CMD=ad5x_timelapse_camera2_capture"
    inserted=1
}
{print}
inside && /^\[/ && $0 != "[gcode_macro _TIMELAPSE_NEW_FRAME]" {inside=0}
END{if(!inserted)exit 42}
' "$SOURCE" >"$TMP1" || { rm -f "$TMP1"; fail 'не удалось добавить кадр камеры 2'; }

    awk '
BEGIN{inside=0;inserted=0}
/^\[gcode_macro TIMELAPSE_RENDER\]$/ {inside=1}
inside && /action_call_remote_method\("timelapse_render"/ && !inserted {
    print "  RUN_SHELL_COMMAND CMD=ad5x_timelapse_telegram_start"
    inserted=1
}
{print}
inside && /^\[/ && $0 != "[gcode_macro TIMELAPSE_RENDER]" {inside=0}
END{if(!inserted)exit 43}
' "$TMP1" >"$TMP2" || { rm -f "$TMP1" "$TMP2"; fail 'не удалось добавить watcher таймлапса'; }
    rm -f "$TMP1"

    grep -q 'CMD=ad5x_timelapse_camera2_capture' "$TMP2" || fail 'в timelapse overlay отсутствует захват камеры 2'
    grep -q 'CMD=ad5x_timelapse_telegram_start' "$TMP2" || fail 'в timelapse overlay отсутствует watcher'
    install_generated "$TMP2" "$GENERATED/timelapse.cfg"
}

generate_configs(){
    mkdir -p "$GENERATED" "$STATE"
    GENERATED_CHANGED=0
    generate_notify
    generate_timelapse
    if [ "$GENERATED_CHANGED" -eq 1 ]; then
        touch "$STATE_DIR/refresh.changed"
    else
        rm -f "$STATE_DIR/refresh.changed"
    fi
}

install_power_on_hook(){
    [ -f "$POWER_ON" ] || printf '#!/bin/sh\n# Enter Poweron code here\n' >"$POWER_ON"
    [ -f "$STATE/original-power_on.sh" ] || cp -p "$POWER_ON" "$STATE/original-power_on.sh"

    strip_block "$POWER_ON" 'CAMERA2_AUTOSTART_BEGIN' 'CAMERA2_AUTOSTART_END'
    strip_block "$POWER_ON" 'AD5X_CUSTOM_POWER_ON_BEGIN' 'AD5X_CUSTOM_POWER_ON_END'
    remove_lines "$POWER_ON" '^[[:space:]]*/(opt/config|usr/data/config)/mod_data/S99zzcamera2[[:space:]]+start([[:space:]]|$)'

    cat >>"$POWER_ON" <<'HOOK'

# AD5X_CUSTOM_POWER_ON_BEGIN
/opt/config/mod_data/plugins/ad5x_custom/runtime.sh power-on
# AD5X_CUSTOM_POWER_ON_END
HOOK
    chmod +x "$POWER_ON"
    sh -n "$POWER_ON" || fail 'ошибка синтаксиса power_on.sh'
}

remove_update_manager_section(){
    [ -f "$USER_MOONRAKER" ] || return 0
    awk 'BEGIN{s=0} /^\[update_manager ad5x_custom\]/{s=1;next} /^\[/{if(s)s=0} !s{print}' \
        "$USER_MOONRAKER" >"$USER_MOONRAKER.tmp"
    mv "$USER_MOONRAKER.tmp" "$USER_MOONRAKER"
}

# Bootstrap clone.
if [ "$MODE" != --apply-only ] && [ "$MODE" != --refresh-only ] && [ "$MODE" != --status ] && [ "$MODE" != --uninstall ] && [ ! -d "$PLUGIN_DIR/.git" ]; then
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    mkdir -p /opt/config/mod_data/plugins
    chroot "$ROOT" /usr/bin/git clone --branch "$REF" --single-branch "$REPO_URL" "$PLUGIN_DIR"
    exec "$PLUGIN_DIR/install.sh" --apply-only
fi

# Re-running downloaded installer switches an existing install to REF.
if [ "$MODE" = "" ] && [ -d "$PLUGIN_DIR/.git" ]; then
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    S="$(chroot "$ROOT" /usr/bin/git -C "$PLUGIN_DIR" status --porcelain)"
    [ -z "$S" ] || fail 'ad5x_custom содержит локальные изменения; переключение ветки запрещено'
    chroot "$ROOT" /usr/bin/git -C "$PLUGIN_DIR" fetch origin "refs/heads/$REF:refs/remotes/origin/$REF"
    chroot "$ROOT" /usr/bin/git -C "$PLUGIN_DIR" checkout -B "$REF" "origin/$REF"
    exec "$PLUGIN_DIR/install.sh" --apply-only
fi

[ -f "$PLUGIN_DIR/VERSION" ] || fail "неполная установка: $PLUGIN_DIR"
mkdir -p "$GENERATED" "$STATE" "$BACKUPS" "$LOG_DIR"

if [ "$MODE" = --refresh-only ]; then
    generate_configs
    exit 0
fi

if [ "$MODE" = --status ]; then
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    echo "=== AD5X Custom $(cat "$PLUGIN_DIR/VERSION") ==="
    for X in "$GENERATED/notify.cfg" "$GENERATED/timelapse.cfg" "$STATE/S99zzcamera2" "$POWER_ON" \
        /opt/config/mod_data/timelapse_camera2_capture.sh \
        /opt/config/mod_data/start_timelapse_watcher.sh \
        /opt/config/mod_data/wait_and_send_timelapse.sh \
        /opt/config/mod_data/send_timelapse_telegram.sh; do
        [ -e "$X" ] && echo "[OK] $X" || echo "[FAIL] $X"
    done
    grep -q 'AD5X_CUSTOM_POWER_ON_BEGIN' "$POWER_ON" && echo '[OK] power_on hook' || echo '[FAIL] power_on hook'
    wget -qO- http://127.0.0.1:7125/server/info >/dev/null 2>&1 && echo '[OK] Moonraker' || echo '[FAIL] Moonraker'
    wget -qO- 'http://127.0.0.1:8080/?action=snapshot' >/dev/null 2>&1 && echo '[OK] Camera 1' || echo '[FAIL] Camera 1'
    wget -qO- 'http://127.0.0.1:8081/?action=snapshot' >/dev/null 2>&1 && echo '[OK] Camera 2' || echo '[FAIL] Camera 2'
    wget -qO- http://127.0.0.1:7913/api/health >/dev/null 2>&1 && echo '[OK] IFS' || echo '[FAIL] IFS'
    echo '=== Git ==='
    repo_status "$ROOT" Z-Mod /opt/config/mod
    repo_status "$ROOT" klippy /opt/config/base/klipper
    repo_status "$ROOT" moon /opt/config/base/moonraker
    repo_status "$ROOT" notify /opt/config/mod_data/plugins/notify
    repo_status "$ROOT" timelapse /opt/config/mod_data/plugins/timelapse
    repo_status "$ROOT" ad5x_custom /opt/config/mod_data/plugins/ad5x_custom
    exit 0
fi

if [ "$MODE" = --uninstall ]; then
    remove_lines "$KLIPPER_INCLUDES" 'plugins/ad5x_custom/|ad5x_custom/generated/'
    remove_lines "$MOONRAKER_INCLUDES" 'plugins/ad5x_custom/'
    restore_lines "$KLIPPER_INCLUDES" "$STATE/original-klipper-includes.lines"
    remove_update_manager_section
    if [ -f "$STATE/original-power_on.sh" ]; then
        cp -p "$STATE/original-power_on.sh" "$POWER_ON"
    else
        strip_block "$POWER_ON" 'AD5X_CUSTOM_POWER_ON_BEGIN' 'AD5X_CUSTOM_POWER_ON_END'
    fi
    echo 'Интеграция отключена. Исходный power_on.sh восстановлен; пользовательские камеры, IFS, таймлапсы, логи и backups сохранены.'
    exit 0
fi

check_idle
STAMP="$(date +%Y%m%d-%H%M%S)"; B="$BACKUPS/$STAMP"; mkdir -p "$B/upstream"
SUCCESS=0

rollback_install(){
    set +e
    echo "ОШИБКА: установка не завершена, выполняется автоматический rollback." >&2
    restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg
    restore_snapshot "$MOONRAKER_INCLUDES" plugins.moonraker.conf
    restore_snapshot "$USER_MOONRAKER" user.moonraker.conf
    restore_snapshot "$POWER_ON" power_on.sh
    restore_snapshot /opt/config/mod_data/camera.conf camera.conf
    restore_snapshot "$GENERATED/notify.cfg" generated-notify.cfg
    restore_snapshot "$GENERATED/timelapse.cfg" generated-timelapse.cfg
    [ -f "$B/upstream/notify.cfg" ] && cp -p "$B/upstream/notify.cfg" /opt/config/mod_data/plugins/notify/ru/notify.cfg
    [ -f "$B/upstream/notify.moonraker.cfg" ] && cp -p "$B/upstream/notify.moonraker.cfg" /opt/config/mod_data/plugins/notify/ru/notify.moonraker.cfg
    [ -f "$B/upstream/timelapse.cfg" ] && cp -p "$B/upstream/timelapse.cfg" /opt/config/mod_data/plugins/timelapse/timelapse.cfg
    echo "Rollback завершён. Диагностический backup: $B" >&2
}
finish_install(){
    RC=$?
    trap - EXIT HUP INT TERM
    if [ "$SUCCESS" -ne 1 ]; then
        rollback_install
        [ "$RC" -ne 0 ] || RC=1
    fi
    exit "$RC"
}
trap finish_install EXIT HUP INT TERM

snapshot "$KLIPPER_INCLUDES" plugins.cfg
snapshot "$MOONRAKER_INCLUDES" plugins.moonraker.conf
snapshot "$USER_MOONRAKER" user.moonraker.conf
snapshot "$POWER_ON" power_on.sh
snapshot /opt/config/mod_data/camera.conf camera.conf
snapshot "$GENERATED/notify.cfg" generated-notify.cfg
snapshot "$GENERATED/timelapse.cfg" generated-timelapse.cfg
[ -f /opt/config/mod_data/plugins/notify/ru/notify.cfg ] && cp -p /opt/config/mod_data/plugins/notify/ru/notify.cfg "$B/upstream/notify.cfg"
[ -f /opt/config/mod_data/plugins/notify/ru/notify.moonraker.cfg ] && cp -p /opt/config/mod_data/plugins/notify/ru/notify.moonraker.cfg "$B/upstream/notify.moonraker.cfg"
[ -f /opt/config/mod_data/plugins/timelapse/timelapse.cfg ] && cp -p /opt/config/mod_data/plugins/timelapse/timelapse.cfg "$B/upstream/timelapse.cfg"

for REQUIRED in \
    /opt/config/mod_data/S99zzcamera2 \
    /opt/config/mod_data/timelapse_camera2_capture.sh \
    /opt/config/mod_data/start_timelapse_watcher.sh \
    /opt/config/mod_data/wait_and_send_timelapse.sh \
    /opt/config/mod_data/send_timelapse_telegram.sh; do
    [ -f "$REQUIRED" ] || fail "не найден пользовательский компонент: $REQUIRED"
done

if [ ! -f "$STATE/S99zzcamera2" ]; then
    cp -p /opt/config/mod_data/S99zzcamera2 "$STATE/S99zzcamera2"
fi
chmod +x "$STATE/S99zzcamera2" "$PLUGIN_DIR/install.sh" "$PLUGIN_DIR/runtime.sh"

# Save dirty diffs and restore tracked plugin repositories to HEAD.
ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
for S in notify:/opt/config/mod_data/plugins/notify timelapse:/opt/config/mod_data/plugins/timelapse; do
    NAME="${S%%:*}"; P="${S#*:}"
    chroot "$ROOT" /usr/bin/git -C "$P" rev-parse --git-dir >/dev/null 2>&1 || fail "не найден Git-репозиторий $NAME"
    chroot "$ROOT" /usr/bin/git -C "$P" diff >"$B/$NAME.patch" 2>/dev/null || true
    chroot "$ROOT" /usr/bin/git -C "$P" reset --hard HEAD >/dev/null
 done

generate_configs

save_lines "$KLIPPER_INCLUDES" 'plugins/notify/.*/notify\.cfg|plugins/timelapse/timelapse\.cfg' "$STATE/original-klipper-includes.lines"
remove_lines "$KLIPPER_INCLUDES" 'plugins/ad5x_custom/|ad5x_custom/generated/|plugins/notify/.*/notify\.cfg|plugins/timelapse/timelapse\.cfg'
append_line "$KLIPPER_INCLUDES" '[include plugins/ad5x_custom/ad5x_custom.cfg]'
append_line "$KLIPPER_INCLUDES" '[include ad5x_custom/generated/notify.cfg]'
append_line "$KLIPPER_INCLUDES" '[include ad5x_custom/generated/timelapse.cfg]'

remove_lines "$MOONRAKER_INCLUDES" 'plugins/ad5x_custom/'
append_line "$MOONRAKER_INCLUDES" '[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]'

[ -f "$USER_MOONRAKER" ] || : >"$USER_MOONRAKER"
remove_update_manager_section
cat >>"$USER_MOONRAKER" <<CFG

[update_manager ad5x_custom]
type: git_repo
channel: dev
path: /root/printer_data/config/mod_data/plugins/ad5x_custom
origin: $REPO_URL
is_system_service: False
primary_branch: $REF
CFG

install_power_on_hook
rm -f /etc/init.d/S99zzcamera2 /etc/init.d/S59ad5x-custom-refresh /etc/init.d/S66ad5x-ifs-spoolman /etc/init.d/S98ad5x-camera-select /etc/init.d/S99zzad5x-camera2 2>/dev/null || true

SUCCESS=1
echo "AD5X Custom применён. Backup: $B"
echo 'Для активации требуется полное выключение и включение принтера.'
