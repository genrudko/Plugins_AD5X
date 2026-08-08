#!/bin/sh
# CALIBRATION-CENTER-001 standalone installer for AD5X + Z-Mod.
# POSIX/BusyBox-safe: no GNU-only command options are required.
set -eu

REPO_URL="https://github.com/genrudko/Plugins_AD5X.git"
PLUGIN_DIR="/opt/config/mod_data/plugins/calibration_center"
STATE_DIR="/opt/config/mod_data/calibration_center"
BACKUP_DIR="$STATE_DIR/backups"
KLIPPER_PLUGINS="/opt/config/mod_data/plugins.cfg"
USER_CFG="/opt/config/mod_data/user.cfg"
USER_MOONRAKER="/opt/config/mod_data/user.moonraker.conf"
REF="${CALIBRATION_CENTER_REF:-main}"
MODE="${1:---install}"
INCLUDE_LINE="[include plugins/calibration_center/calibration_center/calibration_center.cfg]"
HOOK_BEGIN="# CALIBRATION_CENTER_START_HOOK_BEGIN"
HOOK_END="# CALIBRATION_CENTER_START_HOOK_END"
UPDATE_BEGIN="# CALIBRATION_CENTER_UPDATE_MANAGER_BEGIN"
UPDATE_END="# CALIBRATION_CENTER_UPDATE_MANAGER_END"

fail() { echo "ОШИБКА: $*" >&2; exit 1; }
info() { echo "Calibration Center: $*"; }

find_root() {
    for P in /proc/[0-9]*; do
        [ -r "$P/cmdline" ] || continue
        CMD="$(tr '\0' ' ' <"$P/cmdline" 2>/dev/null || true)"
        case "$CMD" in
            *moonraker.py*) [ -d "$P/root" ] && { echo "$P/root"; return 0; } ;;
        esac
    done
    [ -d /usr/data/.mod/.zmod ] && { echo /usr/data/.mod/.zmod; return 0; }
    return 1
}

check_idle() {
    DATA="$(wget -qO- 'http://127.0.0.1:7125/printer/objects/query?print_stats' 2>/dev/null || true)"
    [ -n "$DATA" ] || fail "Moonraker недоступен; безопасное состояние принтера не подтверждено"
    printf '%s' "$DATA" | grep -q '"state"' || fail "Moonraker не вернул print_stats.state; установка остановлена fail-closed"
    case "$DATA" in
        *'"state":"printing"'*|*'"state": "printing"'*|*'"state":"paused"'*|*'"state": "paused"'*)
            fail "принтер печатает или стоит на паузе"
            ;;
    esac
}

strip_block() {
    F="$1"; BEGIN_MARK="$2"; END_MARK="$3"
    [ -f "$F" ] || return 0
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
        index($0,b){skip=1;next}
        index($0,e){skip=0;next}
        !skip{print}
    ' "$F" >"$F.tmp"
    mv "$F.tmp" "$F"
}

append_line() {
    F="$1"; L="$2"
    [ -f "$F" ] || : >"$F"
    grep -Fqx "$L" "$F" 2>/dev/null || printf '%s\n' "$L" >>"$F"
}

remove_exact_line() {
    F="$1"; L="$2"
    [ -f "$F" ] || return 0
    awk -v line="$L" '$0 != line { print }' "$F" >"$F.tmp"
    mv "$F.tmp" "$F"
}

snapshot_file() {
    SRC="$1"; NAME="$2"; DEST="$3"
    if [ -e "$SRC" ]; then
        cp -p "$SRC" "$DEST/$NAME"
    else
        : >"$DEST/.absent-$NAME"
    fi
}

restore_file() {
    DST="$1"; NAME="$2"; SRC="$3"
    if [ -f "$SRC/.absent-$NAME" ]; then
        rm -f "$DST"
    elif [ -f "$SRC/$NAME" ]; then
        cp -p "$SRC/$NAME" "$DST"
    fi
}

repo_clean() {
    ROOT="$1"; PATH_="$2"; NAME="$3"
    if ! chroot "$ROOT" /usr/bin/git -C "$PATH_" rev-parse --git-dir >/dev/null 2>&1; then
        printf '%-14s N/A\n' "$NAME"
        return 0
    fi
    STATUS="$(chroot "$ROOT" /usr/bin/git -C "$PATH_" status --porcelain 2>/dev/null || true)"
    if [ -n "$STATUS" ]; then
        printf '%-14s DIRTY\n' "$NAME"
        return 1
    fi
    printf '%-14s CLEAN\n' "$NAME"
    return 0
}

check_upstream_clean() {
    ROOT="$(find_root || true)"
    [ -n "$ROOT" ] || fail "не удалось определить runtime root Z-Mod"
    BAD=0
    repo_clean "$ROOT" /opt/config/mod Z-Mod || BAD=1
    repo_clean "$ROOT" /opt/config/base/klipper Klipper || BAD=1
    repo_clean "$ROOT" /opt/config/base/moonraker Moonraker || BAD=1
    [ "$BAD" -eq 0 ] || fail "upstream уже DIRTY; установка остановлена, чтобы не смешивать изменения"
}

compatibility_check() {
    BASE="/opt/config/mod"
    [ -d "$BASE" ] || fail "Z-Mod не найден: $BASE"
    # Calibration Center intentionally depends on the current, documented AD5X
    # extension and probe safety primitives. Fail closed if they disappear.
    grep -R -q '^\[gcode_macro _USER_START_PRINT\]' "$BASE" 2>/dev/null || fail "Z-Mod: отсутствует _USER_START_PRINT"
    grep -R -q '^\[gcode_macro _ORIG_CLEAR_NOZZLE\]' "$BASE" 2>/dev/null || fail "Z-Mod: отсутствует _ORIG_CLEAR_NOZZLE"
    grep -R -q '^\[gcode_macro _G28\]' "$BASE" 2>/dev/null || grep -R -q '^\[gcode_macro _HOME\]' "$BASE" 2>/dev/null || fail "Z-Mod: не найден безопасный homing path"
    grep -R -q '_SET_GCODE_OFFSET_FAST' "$BASE" 2>/dev/null || fail "Z-Mod: отсутствует _SET_GCODE_OFFSET_FAST"
    grep -R -q 'LOAD_CELL_TARE' "$BASE" 2>/dev/null || fail "Z-Mod: отсутствует LOAD_CELL_TARE"
    grep -R -q 'variable_ad5x' "$BASE" 2>/dev/null || fail "Z-Mod: AD5X client contract не найден"
}

check_user_hook_conflict() {
    [ -f "$USER_CFG" ] || return 0
    TMP="$STATE_DIR/user.no-cc.$$"
    awk -v b="$HOOK_BEGIN" -v e="$HOOK_END" '
        index($0,b){skip=1;next}
        index($0,e){skip=0;next}
        !skip{print}
    ' "$USER_CFG" >"$TMP"
    if grep -q '^\[gcode_macro _USER_START_PRINT\]' "$TMP"; then
        rm -f "$TMP"
        fail "mod_data/user.cfg уже содержит пользовательский _USER_START_PRINT. Автоматически объединять его небезопасно; hook не изменён."
    fi
    rm -f "$TMP"
}

write_hook() {
    mkdir -p "$(dirname "$USER_CFG")"
    [ -f "$USER_CFG" ] || : >"$USER_CFG"
    strip_block "$USER_CFG" "$HOOK_BEGIN" "$HOOK_END"
    cat >>"$USER_CFG" <<EOF
$HOOK_BEGIN
[gcode_macro _USER_START_PRINT]
gcode:
    CC_APPLY_PROFILE
$HOOK_END
EOF
}

write_update_manager() {
    mkdir -p "$(dirname "$USER_MOONRAKER")"
    [ -f "$USER_MOONRAKER" ] || : >"$USER_MOONRAKER"
    strip_block "$USER_MOONRAKER" "$UPDATE_BEGIN" "$UPDATE_END"
    cat >>"$USER_MOONRAKER" <<EOF
$UPDATE_BEGIN
[update_manager calibration_center]
type: git_repo
path: $PLUGIN_DIR
origin: $REPO_URL
primary_branch: $REF
managed_services: klipper moonraker
$UPDATE_END
EOF
}

ensure_checkout() {
    ROOT="$(find_root || true)"
    [ -n "$ROOT" ] || fail "не удалось определить runtime root"
    GIT="chroot $ROOT /usr/bin/git"

    if [ -d "$PLUGIN_DIR/.git" ]; then
        DIRTY="$($GIT -C "$PLUGIN_DIR" status --porcelain 2>/dev/null || true)"
        [ -z "$DIRTY" ] || fail "checkout Calibration Center DIRTY; автоматическое обновление запрещено"
        $GIT -C "$PLUGIN_DIR" fetch origin "$REF"
        $GIT -C "$PLUGIN_DIR" checkout "$REF" 2>/dev/null || $GIT -C "$PLUGIN_DIR" checkout -B "$REF" "origin/$REF"
        $GIT -C "$PLUGIN_DIR" reset --hard "origin/$REF"
    else
        [ ! -e "$PLUGIN_DIR" ] || fail "$PLUGIN_DIR существует, но не является git checkout"
        mkdir -p "$(dirname "$PLUGIN_DIR")"
        $GIT clone --branch "$REF" --single-branch "$REPO_URL" "$PLUGIN_DIR"
    fi

    [ -f "$PLUGIN_DIR/calibration_center/calibration_center.cfg" ] || fail "checkout не содержит Calibration Center"
    chmod +x "$PLUGIN_DIR/calibration_center/install.sh" "$PLUGIN_DIR/calibration_center/cc_audit.sh"
}

payload_safety_check() {
    CFG_DIR="$PLUGIN_DIR/calibration_center"
    AUDIT="$CFG_DIR/cc_audit.sh"
    # Match executable command lines in every split Klipper cfg, not docs or
    # this installer's own guard text.
    if grep -E '^[[:space:]]*(UPDATE_MCU|Z_OFFSET_APPLY_PROBE|Z_OFFSET_APPLY_ENDSTOP|SAVE_CONFIG)([[:space:]]|$)' "$CFG_DIR"/*.cfg >/dev/null 2>&1; then
        fail "Calibration Center cfg содержит запрещённую operational primitive"
    fi
    if grep -E '/sys/.*/(unbind|bind)|usb.*reset' "$AUDIT" >/dev/null 2>&1; then
        fail "audit helper содержит запрещённую USB primitive"
    fi
}

install_now() {
    check_idle
    check_upstream_clean
    compatibility_check
    mkdir -p "$STATE_DIR" "$BACKUP_DIR"
    check_user_hook_conflict

    TS="$(date '+%Y%m%d-%H%M%S' 2>/dev/null || echo now)"
    B="$BACKUP_DIR/$TS"
    mkdir -p "$B"
    snapshot_file "$KLIPPER_PLUGINS" plugins.cfg "$B"
    snapshot_file "$USER_CFG" user.cfg "$B"
    snapshot_file "$USER_MOONRAKER" user.moonraker.conf "$B"
    printf '%s\n' "$B" >"$STATE_DIR/last-install-backup"

    SUCCESS=0
    trap 'if [ "$SUCCESS" -ne 1 ]; then restore_file "$KLIPPER_PLUGINS" plugins.cfg "$B"; restore_file "$USER_CFG" user.cfg "$B"; restore_file "$USER_MOONRAKER" user.moonraker.conf "$B"; fi' EXIT HUP INT TERM

    ensure_checkout
    payload_safety_check
    append_line "$KLIPPER_PLUGINS" "$INCLUDE_LINE"
    write_hook
    write_update_manager

    sync
    check_upstream_clean
    SUCCESS=1
    trap - EXIT HUP INT TERM
    info "установлен. Требуется обычный FIRMWARE_RESTART/перезапуск Klipper для загрузки нового cfg; MCU не прошивается."
}

uninstall_now() {
    check_idle
    mkdir -p "$STATE_DIR"
    remove_exact_line "$KLIPPER_PLUGINS" "$INCLUDE_LINE"
    strip_block "$USER_CFG" "$HOOK_BEGIN" "$HOOK_END"
    strip_block "$USER_MOONRAKER" "$UPDATE_BEGIN" "$UPDATE_END"
    # Preserve profile/audit state for reinstall/forensics. The plugin checkout
    # can be removed because no config references remain.
    rm -rf "$PLUGIN_DIR"
    sync
    info "удалён; профильный state сохранён в $STATE_DIR. Штатный Z-Mod path не изменён."
}

status_now() {
    info "status"
    echo "ref=$REF"
    echo "plugin_dir=$PLUGIN_DIR"
    [ -d "$PLUGIN_DIR/.git" ] && echo "checkout=present" || echo "checkout=absent"
    grep -Fqx "$INCLUDE_LINE" "$KLIPPER_PLUGINS" 2>/dev/null && echo "klipper_include=present" || echo "klipper_include=absent"
    grep -Fq "$HOOK_BEGIN" "$USER_CFG" 2>/dev/null && echo "start_hook=present" || echo "start_hook=absent"
    grep -Fq "$UPDATE_BEGIN" "$USER_MOONRAKER" 2>/dev/null && echo "update_manager=present" || echo "update_manager=absent"
    if ROOT="$(find_root || true)"; [ -n "$ROOT" ]; then
        repo_clean "$ROOT" /opt/config/mod Z-Mod || true
        repo_clean "$ROOT" /opt/config/base/klipper Klipper || true
        repo_clean "$ROOT" /opt/config/base/moonraker Moonraker || true
        repo_clean "$ROOT" "$PLUGIN_DIR" CalibCenter || true
    fi
}

case "$MODE" in
    --install|--apply-only) install_now ;;
    --uninstall) uninstall_now ;;
    --status) status_now ;;
    *) fail "usage: $0 [--install|--apply-only|--uninstall|--status]" ;;
esac
