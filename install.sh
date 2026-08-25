#!/bin/sh
set -eu

REPO_URL="https://github.com/genrudko/Plugins_AD5X.git"
PLUGIN_DIR="${AD5X_PLUGIN_DIR:-/opt/config/mod_data/plugins/ad5x_custom}"
STATE_DIR="${AD5X_STATE_DIR:-/opt/config/mod_data/plugins/ad5x_custom}"
GENERATED="$STATE_DIR/generated"
STATE="$STATE_DIR/state"
BACKUPS="$STATE_DIR/backups"
LOG_DIR="$STATE_DIR/log"
KLIPPER_INCLUDES="${AD5X_KLIPPER_INCLUDES:-/opt/config/mod_data/plugins.cfg}"
MOONRAKER_INCLUDES="${AD5X_MOONRAKER_INCLUDES:-/opt/config/mod_data/plugins.moonraker.conf}"
USER_MOONRAKER="${AD5X_USER_MOONRAKER:-/opt/config/mod_data/user.moonraker.conf}"
POWER_ON="${AD5X_POWER_ON:-/opt/config/mod_data/power_on.sh}"
BACKEND_SOURCE="$PLUGIN_DIR/moonraker/components/plugins_ad5x.py"
BACKEND_DEST="${AD5X_BACKEND_DEST:-/opt/config/base/moonraker/components/plugins_ad5x.py}"
BACKEND_CONFIG="$PLUGIN_DIR/plugins_ad5x.moonraker.conf"
BACKEND_HASH_STATE="$STATE/backend-runtime.sha256"
ZCAL_RUNTIME_HELPER="$PLUGIN_DIR/installer/z_calibration_runtime.sh"
MOONRAKER_COMPONENTS_DIR="${AD5X_MOONRAKER_COMPONENTS_DIR:-${BACKEND_DEST%/*}}"
MOONRAKER_HTTP_BASE="${AD5X_MOONRAKER_HTTP_BASE:-http://127.0.0.1:7125}"
MOONRAKER_STOP_TIMEOUT="${AD5X_MOONRAKER_STOP_TIMEOUT:-30}"
MOONRAKER_READY_TIMEOUT="${AD5X_MOONRAKER_READY_TIMEOUT:-90}"
REF="${AD5X_CUSTOM_REF:-main}"
MODE="${1:-}"
MOONRAKER_WAS_RUNNING=0
MOONRAKER_TRANSITION_STARTED=0
ROOT=""

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
ad5x_curl_bin(){
    if [ -n "${AD5X_CURL_BIN:-}" ]; then
        [ -x "$AD5X_CURL_BIN" ] || return 1
        printf '%s\n' "$AD5X_CURL_BIN"
    elif command -v curl >/dev/null 2>&1; then
        command -v curl
    elif [ -x /usr/bin/curl ]; then
        printf '%s\n' /usr/bin/curl
    elif [ -x /usr/prog/curl-7.55.1-https/bin/curl ]; then
        printf '%s\n' /usr/prog/curl-7.55.1-https/bin/curl
    else
        return 1
    fi
}
ad5x_http_get(){
    TIMEOUT="$1"; URL="$2"
    CURL_BIN="$(ad5x_curl_bin)" || return 1
    "$CURL_BIN" -f -sS -m "$TIMEOUT" "$URL"
}
remove_lines(){ F="$1"; P="$2"; [ -f "$F" ] || : >"$F"; grep -Ev "$P" "$F" >"$F.tmp" 2>/dev/null || true; mv "$F.tmp" "$F"; }
append_line(){ F="$1"; L="$2"; [ -f "$F" ] || : >"$F"; grep -Fqx "$L" "$F" 2>/dev/null || echo "$L" >>"$F"; }
backup(){ [ -f "$1" ] && cp -p "$1" "$2/${1##*/}" || true; }
snapshot(){
    FILE="$1"; KEY="$2"
    if [ -e "$FILE" ] || [ -L "$FILE" ]; then
        cp -p "$FILE" "$B/$KEY"
    else
        : >"$B/.absent-$KEY"
    fi
}
restore_snapshot(){
    FILE="$1"; KEY="$2"
    if [ -f "$B/.absent-$KEY" ]; then
        rm -f "$FILE"
    elif [ -e "$B/$KEY" ] || [ -L "$B/$KEY" ]; then
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
    ROOT_="$1"; NAME="$2"; PATH_="$3"
    if ! chroot "$ROOT_" /usr/bin/git -C "$PATH_" rev-parse --git-dir >/dev/null 2>&1; then printf '%-14s N/A\n' "$NAME"; return; fi
    S="$(chroot "$ROOT_" /usr/bin/git -C "$PATH_" status --porcelain 2>/dev/null || true)"
    [ -z "$S" ] && printf '%-14s CLEAN\n' "$NAME" || printf '%-14s DIRTY\n' "$NAME"
}
check_idle(){
    if ! STATE_JSON="$(ad5x_http_get 3 "$MOONRAKER_HTTP_BASE/printer/objects/query?print_stats" 2>/dev/null)"; then
        fail 'не удалось подтвердить idle state: Moonraker print_stats недоступен'
    fi
    [ -n "$STATE_JSON" ] || fail 'не удалось подтвердить idle state: пустой ответ Moonraker print_stats'
    PY="$(python_bin)" || fail 'не удалось подтвердить idle state: Python недоступен'
    PRINT_STATE="$(printf '%s' "$STATE_JSON" | "$PY" -B -c '
import json
import sys
try:
    data = json.load(sys.stdin)
    state = data["result"]["status"]["print_stats"]["state"]
except (json.JSONDecodeError, KeyError, TypeError):
    raise SystemExit(1)
if not isinstance(state, str) or not state:
    raise SystemExit(1)
sys.stdout.write(state)
')" || fail 'не удалось подтвердить idle state: невалидный Moonraker print_stats response'
    case "$PRINT_STATE" in
        standby|complete|error|cancelled) return 0 ;;
        printing|paused) fail 'принтер сейчас печатает или стоит на паузе' ;;
        *) fail "не удалось подтвердить idle state: неизвестное print_stats.state=$PRINT_STATE" ;;
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

python_bin(){
    if [ -n "${AD5X_PYTHON_BIN:-}" ] && [ -x "$AD5X_PYTHON_BIN" ]; then
        echo "$AD5X_PYTHON_BIN"
    elif command -v python3 >/dev/null 2>&1; then
        command -v python3
    elif [ -x /root/moonraker-env/bin/python3 ]; then
        echo /root/moonraker-env/bin/python3
    else
        return 1
    fi
}
sha256_file(){ sha256sum "$1" | awk '{print $1}'; }
load_zcal_runtime_helper(){
    [ -f "$ZCAL_RUNTIME_HELPER" ] || return 1
    if ! command -v zcal_core_init_paths >/dev/null 2>&1; then
        . "$ZCAL_RUNTIME_HELPER"
    fi
    zcal_core_init_paths
}
backend_constant(){
    NAME="$1"
    sed -n "s/^$NAME = \"\([^\"]*\)\"/\\1/p" "$BACKEND_SOURCE" | head -n 1
}
backend_source_valid(){
    [ -s "$BACKEND_SOURCE" ] || return 1
    [ -f "$PLUGIN_DIR/VERSION" ] || return 1
    [ -d "$MOONRAKER_COMPONENTS_DIR" ] || return 1
    [ -s "$BACKEND_CONFIG" ] || return 1
    [ "$(grep -c '^\[plugins_ad5x\]$' "$BACKEND_CONFIG" 2>/dev/null || true)" -eq 1 ] || return 1
    [ "$(grep -Ec '^\[[^]]+\]$' "$BACKEND_CONFIG" 2>/dev/null || true)" -eq 1 ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B - "$BACKEND_SOURCE" <<'PY' >/dev/null 2>&1 || return 1
import ast
import pathlib
import sys
ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"), filename=sys.argv[1])
PY
    API_VERSION_="$(backend_constant API_VERSION)"
    BACKEND_VERSION_="$(backend_constant BACKEND_VERSION)"
    ROOT_VERSION_="$(tr -d '\r\n' <"$PLUGIN_DIR/VERSION")"
    [ "$API_VERSION_" = "1.0" ] || return 1
    [ -n "$BACKEND_VERSION_" ] || return 1
    [ "$BACKEND_VERSION_" = "$ROOT_VERSION_" ] || return 1
    load_zcal_runtime_helper || return 1
    zcal_core_source_valid || return 1
}
validate_backend_source(){ backend_source_valid || fail 'backend source/config validation failed'; }
backend_destination_owned(){
    [ -e "$BACKEND_DEST" ] || [ -L "$BACKEND_DEST" ] || return 0
    [ -f "$BACKEND_DEST" ] || return 1
    [ ! -L "$BACKEND_DEST" ] || return 1
    DEST_HASH="$(sha256_file "$BACKEND_DEST" 2>/dev/null || true)"
    [ -n "$DEST_HASH" ] || return 1
    SOURCE_HASH="$(sha256_file "$BACKEND_SOURCE" 2>/dev/null || true)"
    if [ -f "$BACKEND_HASH_STATE" ] && [ "$(cat "$BACKEND_HASH_STATE" 2>/dev/null || true)" = "$DEST_HASH" ]; then
        return 0
    fi
    [ -n "$SOURCE_HASH" ] && [ "$DEST_HASH" = "$SOURCE_HASH" ]
}
validate_backend_destination_ownership(){
    backend_destination_owned || fail "неизвестный файл в backend destination: $BACKEND_DEST"
    load_zcal_runtime_helper || fail 'Z Calibration runtime helper отсутствует'
    validate_zcal_core_destination_ownership
}
remove_backend_bytecode(){
    rm -f "$MOONRAKER_COMPONENTS_DIR/__pycache__/plugins_ad5x"*.pyc 2>/dev/null || true
}
deploy_backend_managed_copy(){
    validate_backend_source
    validate_backend_destination_ownership
    SOURCE_HASH="$(sha256_file "$BACKEND_SOURCE")"
    TMP="$MOONRAKER_COMPONENTS_DIR/.plugins_ad5x.py.tmp.$$"
    rm -f "$TMP"
    cp "$BACKEND_SOURCE" "$TMP" || { rm -f "$TMP"; return 1; }
    chmod 0644 "$TMP" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$TMP")" = "$SOURCE_HASH" ] || { rm -f "$TMP"; return 1; }
    mv -f "$TMP" "$BACKEND_DEST" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$BACKEND_DEST")" = "$SOURCE_HASH" ] || return 1
    remove_backend_bytecode
    HASH_TMP="$BACKEND_HASH_STATE.tmp.$$"
    printf '%s\n' "$SOURCE_HASH" >"$HASH_TMP"
    mv -f "$HASH_TMP" "$BACKEND_HASH_STATE"
    zcal_core_deploy_managed_copy || return 1
}
backend_runtime_matches_source(){
    load_zcal_runtime_helper || return 1
    [ -f "$BACKEND_DEST" ] || return 1
    [ ! -L "$BACKEND_DEST" ] || return 1
    [ -f "$BACKEND_HASH_STATE" ] || return 1
    SOURCE_HASH="$(sha256_file "$BACKEND_SOURCE" 2>/dev/null || true)"
    DEST_HASH="$(sha256_file "$BACKEND_DEST" 2>/dev/null || true)"
    RECORDED_HASH="$(cat "$BACKEND_HASH_STATE" 2>/dev/null || true)"
    [ -n "$SOURCE_HASH" ] && [ "$SOURCE_HASH" = "$DEST_HASH" ] && [ "$DEST_HASH" = "$RECORDED_HASH" ] || return 1
    zcal_core_runtime_matches_source
}
backend_include_ok(){
    [ -s "$BACKEND_CONFIG" ] || return 1
    [ "$(grep -Fxc '[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]' "$MOONRAKER_INCLUDES" 2>/dev/null || true)" -eq 1 ]
}
zcal_hook_include_ok(){
    [ "$(grep -Fxc '[include plugins/ad5x_custom/z_calibration.cfg]' "$KLIPPER_INCLUDES" 2>/dev/null || true)" -eq 1 ]
}
configure_moonraker_includes(){
    remove_lines "$MOONRAKER_INCLUDES" 'plugins/ad5x_custom/'
    append_line "$MOONRAKER_INCLUDES" '[include plugins/ad5x_custom/ad5x_custom.moonraker.conf]'
    append_line "$MOONRAKER_INCLUDES" '[include plugins/ad5x_custom/plugins_ad5x.moonraker.conf]'
}
moonraker_process_count(){
    COUNT=0
    for P in /proc/[0-9]*; do
        [ -r "$P/cmdline" ] || continue
        CMD="$(tr '\0' ' ' <"$P/cmdline" 2>/dev/null || true)"
        case "$CMD" in *moonraker.py*) COUNT=$((COUNT + 1));; esac
    done
    echo "$COUNT"
}
stop_moonraker(){
    [ -n "$ROOT" ] || ROOT="$(find_root)" || return 1
    chroot "$ROOT" /etc/init.d/S65moonraker stop
}
wait_moonraker_stopped(){
    LIMIT="${1:-$MOONRAKER_STOP_TIMEOUT}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        [ "$(moonraker_process_count)" -eq 0 ] && return 0
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}
start_moonraker(){
    [ -n "$ROOT" ] || ROOT="$(find_root)" || return 1
    [ "$(moonraker_process_count)" -eq 0 ] || return 1
    chroot "$ROOT" /etc/init.d/S65moonraker start
}
moonraker_server_info(){ ad5x_http_get 3 "$MOONRAKER_HTTP_BASE/server/info" 2>/dev/null; }
wait_moonraker_http(){
    LIMIT="${1:-$MOONRAKER_READY_TIMEOUT}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        moonraker_server_info >/dev/null 2>&1 && return 0
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}
klippy_ready_from_json(){
    COMPACT="$(printf '%s' "$1" | tr -d '[:space:]')"
    case "$COMPACT" in *'"klippy_connected":true'*) : ;; *) return 1 ;; esac
    case "$COMPACT" in *'"klippy_state":"ready"'*) return 0 ;; *) return 1 ;; esac
}
wait_klippy_ready(){
    LIMIT="${1:-$MOONRAKER_READY_TIMEOUT}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        INFO="$(moonraker_server_info 2>/dev/null || true)"
        [ -n "$INFO" ] && klippy_ready_from_json "$INFO" && return 0
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}
backend_component_state(){
    INFO="${1:-$(moonraker_server_info 2>/dev/null || true)}"
    [ -n "$INFO" ] || return 2
    PY="$(python_bin)" || return 2
    printf '%s' "$INFO" | "$PY" -B -c '
import json, sys
try:
    data=json.load(sys.stdin); data=data.get("result", data)
    components=data.get("components") or []
    failed=data.get("failed_components") or []
    if "plugins_ad5x" in failed: print("failed")
    elif "plugins_ad5x" in components: print("ok")
    else: print("absent")
except Exception:
    print("invalid")
'
}
backend_snapshot_valid(){
    SNAPSHOT="$(ad5x_http_get 3 "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/snapshot" 2>/dev/null || true)"
    [ -n "$SNAPSHOT" ] || return 1
    PY="$(python_bin)" || return 1
    EXPECTED_VERSION="$(tr -d '\r\n' <"$PLUGIN_DIR/VERSION")"
    printf '%s' "$SNAPSHOT" | "$PY" -B -c '
import json, sys
expected=sys.argv[1]
try:
    data=json.load(sys.stdin); data=data.get("result", data)
    ok=(data.get("api_version")=="1.0" and
        data.get("backend_version")==expected and
        (data.get("backend") or {}).get("health")=="ok" and
        isinstance(data.get("modules"), dict) and
        isinstance((data.get("modules") or {}).get("z_calibration"), dict))
except Exception:
    ok=False
raise SystemExit(0 if ok else 1)
' "$EXPECTED_VERSION"
}
verify_backend_runtime(){
    [ "$(backend_component_state 2>/dev/null || true)" = ok ] || return 1
    backend_runtime_matches_source || return 1
    backend_snapshot_valid
}
verify_backend_absent(){ [ "$(backend_component_state 2>/dev/null || true)" = absent ]; }

remove_update_manager_section(){
    [ -f "$USER_MOONRAKER" ] || return 0
    awk 'BEGIN{s=0} /^\[update_manager ad5x_custom\]/{s=1;next} /^\[/{if(s)s=0} !s{print}' \
        "$USER_MOONRAKER" >"$USER_MOONRAKER.tmp"
    mv "$USER_MOONRAKER.tmp" "$USER_MOONRAKER"
}
configure_update_manager(){
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
}
backend_install_transition(){
    configure_moonraker_includes
    configure_update_manager
    deploy_backend_managed_copy
}
backend_uninstall_transition(){
    remove_lines "$MOONRAKER_INCLUDES" 'plugins/ad5x_custom/'
    remove_update_manager_section
    load_zcal_runtime_helper || return 1
    zcal_core_uninstall_managed_copy || return 1
    if [ -e "$BACKEND_DEST" ] || [ -L "$BACKEND_DEST" ]; then
        backend_destination_owned || return 1
        rm -f "$BACKEND_DEST"
    fi
    remove_backend_bytecode
    rm -f "$BACKEND_HASH_STATE"
}
run_moonraker_transition(){
    TRANSITION_FN="$1"
    VERIFY_FN="$2"
    if [ "$(moonraker_process_count)" -gt 0 ]; then
        MOONRAKER_WAS_RUNNING=1
        MOONRAKER_TRANSITION_STARTED=1
        stop_moonraker || return 1
    else
        MOONRAKER_TRANSITION_STARTED=1
    fi
    wait_moonraker_stopped || return 1
    "$TRANSITION_FN" || return 1
    start_moonraker || return 1
    wait_moonraker_http || return 1
    wait_klippy_ready || return 1
    "$VERIFY_FN"
}
restore_moonraker_after_rollback(){
    [ "$MOONRAKER_TRANSITION_STARTED" -eq 1 ] || return 0
    if [ "$(moonraker_process_count 2>/dev/null || echo 0)" -gt 0 ]; then
        stop_moonraker >/dev/null 2>&1 || true
        wait_moonraker_stopped "$MOONRAKER_STOP_TIMEOUT" >/dev/null 2>&1 || true
    fi
    [ "$MOONRAKER_WAS_RUNNING" -eq 1 ] || return 0
    start_moonraker >/dev/null 2>&1 || return 1
    wait_moonraker_http "$MOONRAKER_READY_TIMEOUT" >/dev/null 2>&1 || return 1
    wait_klippy_ready "$MOONRAKER_READY_TIMEOUT" >/dev/null 2>&1
}

if [ "${AD5X_INSTALLER_FUNCTIONS_ONLY:-0}" = 1 ]; then
    return 0 2>/dev/null || exit 0
fi

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

if [ "$MODE" != --apply-only ] && [ "$MODE" != --refresh-only ] && [ "$MODE" != --status ] && [ "$MODE" != --uninstall ] && [ ! -d "$PLUGIN_DIR/.git" ]; then
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    mkdir -p /opt/config/mod_data/plugins
    chroot "$ROOT" /usr/bin/git clone --branch "$REF" --single-branch "$REPO_URL" "$PLUGIN_DIR"
    exec "$PLUGIN_DIR/install.sh" --apply-only
fi

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
    if backend_source_valid; then echo '[OK] backend source'; else echo '[FAIL] backend source'; fi
    if backend_runtime_matches_source; then echo '[OK] backend runtime files'; else echo '[FAIL] backend runtime files'; fi
    if backend_include_ok; then echo '[OK] backend config include'; else echo '[FAIL] backend config include'; fi
    if zcal_hook_include_ok; then echo '[OK] Z Calibration Klipper hook include'; else echo '[FAIL] Z Calibration Klipper hook include'; fi
    INFO="$(moonraker_server_info 2>/dev/null || true)"
    if [ -n "$INFO" ]; then
        case "$(backend_component_state "$INFO" 2>/dev/null || true)" in
            ok) echo '[OK] Moonraker component presence' ;;
            failed) echo '[FAIL] Moonraker component presence (failed component)' ;;
            *) echo '[FAIL] Moonraker component presence' ;;
        esac
        if backend_snapshot_valid; then echo '[OK] backend snapshot'; else echo '[FAIL] backend snapshot'; fi
        klippy_ready_from_json "$INFO" && echo '[OK] Moonraker / Klippy ready' || echo '[FAIL] Moonraker reachable, Klippy not ready'
    else
        echo '[UNAVAILABLE] Moonraker component presence (runtime service unavailable)'
        echo '[UNAVAILABLE] backend snapshot (runtime service unavailable)'
        echo '[FAIL] Moonraker'
    fi
    ad5x_http_get 3 'http://127.0.0.1:8080/?action=snapshot' >/dev/null 2>&1 && echo '[OK] Camera 1' || echo '[FAIL] Camera 1'
    ad5x_http_get 3 'http://127.0.0.1:8081/?action=snapshot' >/dev/null 2>&1 && echo '[OK] Camera 2' || echo '[FAIL] Camera 2'
    ad5x_http_get 3 'http://127.0.0.1:7913/api/health' >/dev/null 2>&1 && echo '[OK] IFS' || echo '[FAIL] IFS'
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
    check_idle
    validate_backend_destination_ownership
    STAMP="$(date +%Y%m%d-%H%M%S)"; B="$BACKUPS/uninstall-$STAMP"; mkdir -p "$B"
    snapshot "$KLIPPER_INCLUDES" plugins.cfg
    snapshot "$MOONRAKER_INCLUDES" plugins.moonraker.conf
    snapshot "$USER_MOONRAKER" user.moonraker.conf
    snapshot "$POWER_ON" power_on.sh
    snapshot "$BACKEND_DEST" backend-runtime.py
    snapshot "$BACKEND_HASH_STATE" backend-runtime.sha256
    snapshot "$ZCAL_CORE_DEST" zcal-runtime.py
    snapshot "$ZCAL_CORE_HASH_STATE" zcal-runtime.sha256
    snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py
    snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256
    UNINSTALL_SUCCESS=0
    rollback_uninstall(){
        set +e
        if [ "$MOONRAKER_TRANSITION_STARTED" -eq 1 ] && [ "$(moonraker_process_count 2>/dev/null || echo 0)" -gt 0 ]; then
            stop_moonraker >/dev/null 2>&1 || true
            wait_moonraker_stopped >/dev/null 2>&1 || true
        fi
        restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg
        restore_snapshot "$MOONRAKER_INCLUDES" plugins.moonraker.conf
        restore_snapshot "$USER_MOONRAKER" user.moonraker.conf
        restore_snapshot "$POWER_ON" power_on.sh
        restore_snapshot "$BACKEND_DEST" backend-runtime.py
        restore_snapshot "$BACKEND_HASH_STATE" backend-runtime.sha256
        restore_snapshot "$ZCAL_CORE_DEST" zcal-runtime.py
        restore_snapshot "$ZCAL_CORE_HASH_STATE" zcal-runtime.sha256
        restore_snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py
        restore_snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256
        remove_backend_bytecode
        restore_moonraker_after_rollback || true
        echo "Uninstall rollback завершён. Backup: $B" >&2
    }
    finish_uninstall(){
        RC=$?
        trap - EXIT HUP INT TERM
        if [ "$UNINSTALL_SUCCESS" -ne 1 ]; then
            rollback_uninstall
            [ "$RC" -ne 0 ] || RC=1
        fi
        exit "$RC"
    }
    trap finish_uninstall EXIT HUP INT TERM

    remove_lines "$KLIPPER_INCLUDES" 'plugins/ad5x_custom/|ad5x_custom/generated/'
    restore_lines "$KLIPPER_INCLUDES" "$STATE/original-klipper-includes.lines"
    if [ -f "$STATE/original-power_on.sh" ]; then
        cp -p "$STATE/original-power_on.sh" "$POWER_ON"
    else
        strip_block "$POWER_ON" 'AD5X_CUSTOM_POWER_ON_BEGIN' 'AD5X_CUSTOM_POWER_ON_END'
    fi
    ROOT="$(find_root)" || fail 'chroot Z-Mod не найден'
    run_moonraker_transition backend_uninstall_transition verify_backend_absent || fail 'backend uninstall lifecycle failed'
    UNINSTALL_SUCCESS=1
    trap - EXIT HUP INT TERM
    echo 'Интеграция отключена. Backend и Z Calibration runtime удалены; исходный power_on.sh восстановлен; пользовательские камеры, IFS, таймлапсы, логи и backups сохранены.'
    exit 0
fi

check_idle
validate_backend_source
validate_backend_destination_ownership
STAMP="$(date +%Y%m%d-%H%M%S)"; B="$BACKUPS/$STAMP"; mkdir -p "$B/upstream"
SUCCESS=0

rollback_install(){
    set +e
    echo "ОШИБКА: установка не завершена, выполняется автоматический rollback." >&2
    if [ "$MOONRAKER_TRANSITION_STARTED" -eq 1 ] && [ "$(moonraker_process_count 2>/dev/null || echo 0)" -gt 0 ]; then
        stop_moonraker >/dev/null 2>&1 || true
        wait_moonraker_stopped >/dev/null 2>&1 || true
    fi
    restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg
    restore_snapshot "$MOONRAKER_INCLUDES" plugins.moonraker.conf
    restore_snapshot "$USER_MOONRAKER" user.moonraker.conf
    restore_snapshot "$POWER_ON" power_on.sh
    restore_snapshot /opt/config/mod_data/camera.conf camera.conf
    restore_snapshot "$GENERATED/notify.cfg" generated-notify.cfg
    restore_snapshot "$GENERATED/timelapse.cfg" generated-timelapse.cfg
    restore_snapshot "$BACKEND_DEST" backend-runtime.py
    restore_snapshot "$BACKEND_HASH_STATE" backend-runtime.sha256
    restore_snapshot "$ZCAL_CORE_DEST" zcal-runtime.py
    restore_snapshot "$ZCAL_CORE_HASH_STATE" zcal-runtime.sha256
    restore_snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py
    restore_snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256
    remove_backend_bytecode
    [ -f "$B/upstream/notify.cfg" ] && cp -p "$B/upstream/notify.cfg" /opt/config/mod_data/plugins/notify/ru/notify.cfg
    [ -f "$B/upstream/notify.moonraker.cfg" ] && cp -p "$B/upstream/notify.moonraker.cfg" /opt/config/mod_data/plugins/notify/ru/notify.moonraker.cfg
    [ -f "$B/upstream/timelapse.cfg" ] && cp -p "$B/upstream/timelapse.cfg" /opt/config/mod_data/plugins/timelapse/timelapse.cfg
    restore_moonraker_after_rollback || echo 'WARN: Moonraker не удалось автоматически вернуть в исходное running-state' >&2
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
snapshot "$BACKEND_DEST" backend-runtime.py
snapshot "$BACKEND_HASH_STATE" backend-runtime.sha256
snapshot "$ZCAL_CORE_DEST" zcal-runtime.py
snapshot "$ZCAL_CORE_HASH_STATE" zcal-runtime.sha256
snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py
snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256
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
append_line "$KLIPPER_INCLUDES" '[include plugins/ad5x_custom/z_calibration.cfg]'
append_line "$KLIPPER_INCLUDES" '[include ad5x_custom/generated/notify.cfg]'
append_line "$KLIPPER_INCLUDES" '[include ad5x_custom/generated/timelapse.cfg]'

install_power_on_hook
rm -f /etc/init.d/S99zzcamera2 /etc/init.d/S59ad5x-custom-refresh /etc/init.d/S66ad5x-ifs-spoolman /etc/init.d/S98ad5x-camera-select /etc/init.d/S99zzad5x-camera2 2>/dev/null || true

run_moonraker_transition backend_install_transition verify_backend_runtime || fail 'backend deployment lifecycle failed'

SUCCESS=1
trap - EXIT HUP INT TERM
echo "AD5X Custom применён. Backup: $B"
echo 'Plugins AD5X backend + Z Calibration core применены через managed copy и controlled Moonraker lifecycle.'
echo 'Z Calibration Klipper hook установлен с закрытым write-gate; effective hook загружен через controlled Klipper reload.'
