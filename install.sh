#!/bin/sh
set -eu

REPO_URL="https://github.com/genrudko/Plugins_AD5X.git"
PLUGIN_DIR="/opt/config/mod_data/plugins/ad5x_custom"
STATE_DIR="/opt/config/mod_data/ad5x_custom"
GENERATED="$STATE_DIR/generated"
STATE="$STATE_DIR/state"
BACKUPS="$STATE_DIR/backups"
KLIPPER_INCLUDES="/opt/config/mod_data/plugins.cfg"
MOONRAKER_INCLUDES="/opt/config/mod_data/plugins.moonraker.conf"
USER_MOONRAKER="/opt/config/mod_data/user.moonraker.conf"
VARIABLES="/opt/config/mod_data/variables.cfg"
REF="${AD5X_CUSTOM_REF:-main}"
MODE="${1:-}"

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
append_line(){ F="$1"; L="$2"; grep -Fqx "$L" "$F" 2>/dev/null || echo "$L" >>"$F"; }
backup(){ [ -f "$1" ] && cp "$1" "$2/${1##*/}" || true; }
save_lines(){ [ -f "$3" ] && return 0; grep -E "$2" "$1" >"$3" 2>/dev/null || : >"$3"; }
restore_lines(){ [ -f "$2" ] || return 0; while IFS= read -r L; do [ -n "$L" ] && append_line "$1" "$L"; done <"$2"; }
repo_status(){
    ROOT="$1"; NAME="$2"; PATH_="$3"
    if ! chroot "$ROOT" /usr/bin/git -C "$PATH_" rev-parse --git-dir >/dev/null 2>&1; then printf '%-14s N/A\n' "$NAME"; return; fi
    S="$(chroot "$ROOT" /usr/bin/git -C "$PATH_" status --porcelain 2>/dev/null || true)"
    [ -z "$S" ] && printf '%-14s CLEAN\n' "$NAME" || printf '%-14s DIRTY\n' "$NAME"
}

if [ "$MODE" != --apply-only ] && [ "$MODE" != --status ] && [ "$MODE" != --uninstall ] && [ ! -d "$PLUGIN_DIR/.git" ]; then
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    mkdir -p /opt/config/mod_data/plugins
    chroot "$ROOT" /usr/bin/git clone --branch "$REF" --single-branch "$REPO_URL" "$PLUGIN_DIR"
    exec "$PLUGIN_DIR/install.sh" --apply-only
fi

[ -f "$PLUGIN_DIR/VERSION" ] || fail "неполная установка: $PLUGIN_DIR"
mkdir -p "$GENERATED" "$STATE" "$BACKUPS" "$STATE_DIR/log"

if [ "$MODE" = --status ]; then
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    echo "=== AD5X Custom $(cat "$PLUGIN_DIR/VERSION") ==="
    for X in "$GENERATED/notify.cfg" "$GENERATED/notify.moonraker.cfg" "$GENERATED/timelapse.cfg" "$STATE/S99zzcamera2" /etc/init.d/S98ad5x-camera-select /etc/init.d/S66ad5x-ifs-spoolman /etc/init.d/S99zzad5x-camera2; do
        [ -e "$X" ] && echo "[OK] $X" || echo "[FAIL] $X"
    done
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
    remove_lines "$MOONRAKER_INCLUDES" 'plugins/ad5x_custom/|ad5x_custom/generated/'
    restore_lines "$KLIPPER_INCLUDES" "$STATE/original-klipper-includes.lines"
    restore_lines "$MOONRAKER_INCLUDES" "$STATE/original-moonraker-includes.lines"
    if [ -f "$USER_MOONRAKER" ]; then awk 'BEGIN{s=0} /^\[update_manager ad5x_custom\]/{s=1;next} /^\[/{if(s)s=0} !s{print}' "$USER_MOONRAKER" >"$USER_MOONRAKER.tmp"; mv "$USER_MOONRAKER.tmp" "$USER_MOONRAKER"; fi
    [ -f "$VARIABLES" ] && sed -i '/^notify_on[[:space:]]*=/d' "$VARIABLES"
    restore_lines "$VARIABLES" "$STATE/original-notify-on.line"
    rm -f /etc/init.d/S98ad5x-camera-select /etc/init.d/S66ad5x-ifs-spoolman /etc/init.d/S99zzad5x-camera2
    echo 'Интеграция отключена. Данные IFS, backups и сохранённый скрипт камеры 2 оставлены.'
    exit 0
fi

STAMP="$(date +%Y%m%d-%H%M%S)"; B="$BACKUPS/$STAMP"; mkdir -p "$B"
for F in "$KLIPPER_INCLUDES" "$MOONRAKER_INCLUDES" "$USER_MOONRAKER" "$VARIABLES" /opt/config/mod_data/camera.conf; do backup "$F" "$B"; done

if [ ! -f "$STATE/S99zzcamera2" ]; then
    [ -f /opt/config/mod_data/S99zzcamera2 ] || fail 'не найден /opt/config/mod_data/S99zzcamera2'
    cp /opt/config/mod_data/S99zzcamera2 "$STATE/S99zzcamera2"; chmod +x "$STATE/S99zzcamera2"
fi
[ -f "$STATE_DIR/config.sh" ] || cat >"$STATE_DIR/config.sh" <<'CFG'
PRIMARY_CAMERA_NAME="HD Camera"
CAMERA2_SCRIPT="/opt/config/mod_data/ad5x_custom/state/S99zzcamera2"
CFG

# Generate patched configs from the currently installed clean upstream versions.
N=/opt/config/mod_data/plugins/notify/ru/notify.cfg
NM=/opt/config/mod_data/plugins/notify/ru/notify.moonraker.cfg
T=/opt/config/mod_data/plugins/timelapse/timelapse.cfg
[ -f "$N" ] && [ -f "$NM" ] && [ -f "$T" ] || fail 'upstream Notify/Timelapse files not found'

awk '
BEGIN{inside=0;done=0}
/^\[gcode_macro _NOTIFY\]/{inside=1}
/^\[gcode_macro _NOTIFY_ON_PERCENT\]/{inside=0}
{print}
inside && !done && /message=msg\)\}/ {
 print "        {% if photo == 1 and notify_photo == 1 %}"
 print "            {action_call_remote_method(\"notify\","
 print "                                 name=\"notifier_photo_camera2\","
 print "                                 message=msg)}"
 print "        {% endif %}"
 done=1
}' "$N" >"$GENERATED/notify.cfg"
cp "$NM" "$GENERATED/notify.moonraker.cfg"
cat >>"$GENERATED/notify.moonraker.cfg" <<'CFG'

[notifier print_start_camera2]
url: {secrets.notify.url}
events: started
body: {secrets.notify.name}: Принтер начал печатать файл '{event_args[1].filename}' — камера 2
attach: http://127.0.0.1:8081/?action=snapshot

[notifier print_complete_camera2]
url: {secrets.notify.url}
events: complete
body: {secrets.notify.name}: Принтер закончил печатать файл '{event_args[1].filename}' — камера 2
attach: http://127.0.0.1:8081/?action=snapshot

[notifier print_error_camera2]
url: {secrets.notify.url}
events: error
body: {secrets.notify.name}: Ошибка {event_args[1].message} {event_args[1].filename} — камера 2
attach: http://127.0.0.1:8081/?action=snapshot

[notifier print_cancelled_camera2]
url: {secrets.notify.url}
events: cancelled
body: {secrets.notify.name}: Печать отменена {event_args[1].message} {event_args[1].filename} — камера 2
attach: http://127.0.0.1:8081/?action=snapshot

[notifier print_paused_camera2]
url: {secrets.notify.url}
events: paused
body: {secrets.notify.name}: Пауза {event_args[1].message} {event_args[1].filename} — камера 2
attach: http://127.0.0.1:8081/?action=snapshot

[notifier print_resumed_camera2]
url: {secrets.notify.url}
events: resumed
body: {secrets.notify.name}: Продолжение печати {event_args[1].message} {event_args[1].filename} — камера 2
attach: http://127.0.0.1:8081/?action=snapshot

[notifier notifier_photo_camera2]
url: {secrets.notify.url}
events: gcode
body: {secrets.notify.name}: {event_message} — камера 2
attach: http://127.0.0.1:8081/?action=snapshot
CFG
awk 'BEGIN{inside=0;done=0} /^\[gcode_macro _TIMELAPSE_NEW_FRAME\]/{inside=1} {print} inside && !done && /^gcode:/{print " RUN_SHELL_COMMAND CMD=timelapse_camera2_capture"; done=1; inside=0}' "$T" >"$GENERATED/timelapse.cfg"

grep -q 'notifier_photo_camera2' "$GENERATED/notify.cfg" || fail 'notify patch generation failed'
grep -q 'timelapse_camera2_capture' "$GENERATED/timelapse.cfg" || fail 'timelapse patch generation failed'

save_lines "$KLIPPER_INCLUDES" 'plugins/notify/.*/notify\.cfg|plugins/timelapse/timelapse\.cfg' "$STATE/original-klipper-includes.lines"
save_lines "$MOONRAKER_INCLUDES" 'plugins/notify/.*/notify\.moonraker\.cfg' "$STATE/original-moonraker-includes.lines"
remove_lines "$KLIPPER_INCLUDES" 'plugins/ad5x_custom/|ad5x_custom/generated/|plugins/notify/.*/notify\.cfg|plugins/timelapse/timelapse\.cfg'
append_line "$KLIPPER_INCLUDES" '[include plugins/ad5x_custom/ad5x_custom.cfg]'
append_line "$KLIPPER_INCLUDES" '[include ad5x_custom/generated/notify.cfg]'
append_line "$KLIPPER_INCLUDES" '[include ad5x_custom/generated/timelapse.cfg]'
remove_lines "$MOONRAKER_INCLUDES" 'plugins/ad5x_custom/|ad5x_custom/generated/|plugins/notify/.*/notify\.moonraker\.cfg'
append_line "$MOONRAKER_INCLUDES" '[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]'

[ -f "$USER_MOONRAKER" ] || : >"$USER_MOONRAKER"
awk 'BEGIN{s=0} /^\[update_manager ad5x_custom\]/{s=1;next} /^\[/{if(s)s=0} !s{print}' "$USER_MOONRAKER" >"$USER_MOONRAKER.tmp"; mv "$USER_MOONRAKER.tmp" "$USER_MOONRAKER"
cat >>"$USER_MOONRAKER" <<CFG

[update_manager ad5x_custom]
type: git_repo
channel: stable
path: /root/printer_data/config/mod_data/plugins/ad5x_custom
origin: $REPO_URL
is_system_service: False
primary_branch: $REF
CFG

if [ -f "$VARIABLES" ]; then
    [ -f "$STATE/original-notify-on.line" ] || { grep -E '^notify_on[[:space:]]*=' "$VARIABLES" >"$STATE/original-notify-on.line" 2>/dev/null || : >"$STATE/original-notify-on.line"; }
    if grep -qE '^notify_on[[:space:]]*=' "$VARIABLES"; then sed -i 's/^notify_on[[:space:]]*=.*/notify_on = 0/' "$VARIABLES"; else echo 'notify_on = 0' >>"$VARIABLES"; fi
fi

chmod +x "$PLUGIN_DIR/install.sh" "$PLUGIN_DIR/runtime.sh" "$STATE/S99zzcamera2"
ln -sf "$PLUGIN_DIR/runtime.sh" /etc/init.d/S98ad5x-camera-select
ln -sf "$PLUGIN_DIR/runtime.sh" /etc/init.d/S66ad5x-ifs-spoolman
ln -sf "$PLUGIN_DIR/runtime.sh" /etc/init.d/S99zzad5x-camera2

ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
for S in notify:/opt/config/mod_data/plugins/notify timelapse:/opt/config/mod_data/plugins/timelapse; do
    NAME="${S%%:*}"; P="${S#*:}"
    if chroot "$ROOT" /usr/bin/git -C "$P" rev-parse --git-dir >/dev/null 2>&1; then
        chroot "$ROOT" /usr/bin/git -C "$P" diff >"$B/$NAME.patch" 2>/dev/null || true
        chroot "$ROOT" /usr/bin/git -C "$P" reset --hard HEAD >/dev/null
    fi
done

echo "AD5X Custom применён. Backup: $B"
echo 'Требуется полное выключение и включение принтера.'
