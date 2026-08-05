#!/bin/sh
set -u

PLUGIN_DIR="/opt/config/mod_data/plugins/ad5x_custom"
STATE_DIR="/opt/config/mod_data/ad5x_custom"
LOG_DIR="$STATE_DIR/log"
LOG_FILE="$LOG_DIR/power-on.log"
LOCK_DIR="/tmp/ad5x-custom-power-on.lock"
PRIMARY_CAMERA_NAME="HD Camera"
SECONDARY_CAMERA_NAME="CCX2F3298"
CAMERA2_CONTROL="$STATE_DIR/state/S99zzcamera2"

mkdir -p "$LOG_DIR"

log()
{
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG_FILE"
}

append_ignore()
{
    EXCLUDE_FILE="$1"
    ENTRY="$2"
    mkdir -p "${EXCLUDE_FILE%/*}"
    [ -f "$EXCLUDE_FILE" ] || : >"$EXCLUDE_FILE"
    grep -Fqx "$ENTRY" "$EXCLUDE_FILE" 2>/dev/null || echo "$ENTRY" >>"$EXCLUDE_FILE"
}

move_legacy_group()
{
    TARGET_DIR="$1"
    shift
    mkdir -p "$TARGET_DIR"
    for FILE in "$@"; do
        [ -e "$FILE" ] || continue
        NAME="${FILE##*/}"
        DEST="$TARGET_DIR/$NAME"
        if [ -e "$DEST" ]; then
            DEST="$TARGET_DIR/$(date '+%Y%m%d-%H%M%S')-$NAME"
        fi
        mv "$FILE" "$DEST"
        log "Moved legacy repository file: $FILE -> $DEST"
    done
}

normalize_git_hygiene()
{
    LEGACY_DIR="$STATE_DIR/legacy-repository-files"

    # Preserve old manual backup files outside Git working trees.
    move_legacy_group "$LEGACY_DIR/zmod-shell" \
        /opt/config/mod/.shell/*.before-*
    move_legacy_group "$LEGACY_DIR/zmod-start" \
        /opt/config/mod/.shell/root/*.bak_*
    move_legacy_group "$LEGACY_DIR/zmod-translate" \
        /opt/config/mod/translate/ru/*.bak_*
    move_legacy_group "$LEGACY_DIR/timelapse" \
        /opt/config/mod_data/plugins/timelapse/*.bak_*

    # Z-Mod itself creates these runtime configuration files in its repository
    # root. Keep them in place, but hide only these exact known generated paths
    # from Git status through the repository-local exclude file.
    ZMOD_EXCLUDE="/opt/config/mod/.git/info/exclude"
    append_ignore "$ZMOD_EXCLUDE" "# AD5X Custom: Z-Mod runtime generated files"
    for ENTRY in \
        /ad5x.cfg \
        /ad5x_config_native.cfg \
        /ad5x_config_off.cfg \
        /base.cfg \
        /base_display_off.cfg \
        /base_klipper13.cfg \
        /base_mod.cfg \
        /client.cfg \
        /display_off.cfg \
        /klipper13.cfg \
        /motion_sensor.cfg \
        /switch_sensor_display_off.cfg; do
        append_ignore "$ZMOD_EXCLUDE" "$ENTRY"
    done

    log "Repository hygiene normalized"
}

load_zmod_camera_tools()
{
    if [ -f /opt/config/mod/.shell/0.sh ]; then
        . /opt/config/mod/.shell/0.sh
    fi
    V4L2_COMMAND="${V4l2:-/usr/bin/v4l2-ctl}"
}

v4l2_formats_available()
{
    DEVICE="$1"
    # V4l2 is intentionally expanded unquoted: Z-Mod defines it as a command
    # such as "chroot /usr/data/.mod/.zmod v4l2-ctl".
    $V4L2_COMMAND -d "$DEVICE" --list-formats-ext >/dev/null 2>&1
}

find_named_capture_device()
{
    CAMERA_NAME="$1"
    for SYSDEV in /sys/class/video4linux/video*; do
        [ -r "$SYSDEV/name" ] || continue
        DEVICE_NAME="$(cat "$SYSDEV/name" 2>/dev/null || true)"
        case "$DEVICE_NAME" in
            *"$CAMERA_NAME"*)
                CANDIDATE="${SYSDEV##*/}"
                if v4l2_formats_available "/dev/$CANDIDATE"; then
                    echo "$CANDIDATE"
                    return 0
                fi
                ;;
        esac
    done
    return 1
}

wait_for_camera_devices()
{
    load_zmod_camera_tools
    COUNT=0
    while [ "$COUNT" -lt 60 ]; do
        PRIMARY="$(find_named_capture_device "$PRIMARY_CAMERA_NAME" 2>/dev/null || true)"
        SECONDARY="$(find_named_capture_device "$SECONDARY_CAMERA_NAME" 2>/dev/null || true)"
        if [ -n "$PRIMARY" ] && [ -n "$SECONDARY" ]; then
            log "Camera devices ready: $PRIMARY_CAMERA_NAME=/dev/$PRIMARY, $SECONDARY_CAMERA_NAME=/dev/$SECONDARY"
            return 0
        fi
        COUNT=$((COUNT + 1))
        sleep 1
    done
    log "ERROR: camera devices did not become ready: primary=${PRIMARY:-none}, secondary=${SECONDARY:-none}"
    return 1
}

wait_snapshot()
{
    PORT="$1"
    LABEL="$2"
    LIMIT="$3"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        if wget -q -T 2 -O /dev/null "http://127.0.0.1:$PORT/?action=snapshot" 2>/dev/null; then
            log "$LABEL is ready on port $PORT"
            return 0
        fi
        COUNT=$((COUNT + 1))
        sleep 1
    done
    log "ERROR: $LABEL did not become ready on port $PORT"
    return 1
}

select_primary_camera()
{
    load_zmod_camera_tools
    FOUND_VIDEO="$(find_named_capture_device "$PRIMARY_CAMERA_NAME" 2>/dev/null || true)"

    if [ -z "$FOUND_VIDEO" ]; then
        log "ERROR: primary camera not found by name: $PRIMARY_CAMERA_NAME"
        return 1
    fi

    CAMERA_CONF="/opt/config/mod_data/camera.conf"
    [ -f "$CAMERA_CONF" ] || : >"$CAMERA_CONF"
    if grep -q '^VIDEO=' "$CAMERA_CONF"; then
        sed -i "s/^VIDEO=.*/VIDEO=$FOUND_VIDEO/" "$CAMERA_CONF"
    else
        printf '\nVIDEO=%s\n' "$FOUND_VIDEO" >>"$CAMERA_CONF"
    fi
    log "Primary camera selected: $PRIMARY_CAMERA_NAME -> /dev/$FOUND_VIDEO"
    return 0
}

start_primary_camera()
{
    if ! select_primary_camera; then
        return 1
    fi
    if [ ! -x /opt/config/mod/.shell/root/S99camera ]; then
        log "ERROR: Z-Mod camera controller not found"
        return 1
    fi

    # Z-Mod's restart stops every mjpg_streamer/ustreamer process. Therefore
    # the primary camera must always be restarted before Camera 2.
    log "Restarting primary camera"
    /opt/config/mod/.shell/root/S99camera restart >>"$LOG_FILE" 2>&1 || true
    wait_snapshot 8080 "Camera 1" 30
}

start_secondary_camera()
{
    if [ ! -x "$CAMERA2_CONTROL" ]; then
        log "ERROR: camera 2 controller missing: $CAMERA2_CONTROL"
        return 1
    fi

    ATTEMPT=1
    while [ "$ATTEMPT" -le 3 ]; do
        rm -f /opt/config/mod_data/camera2.pid 2>/dev/null || true
        log "Starting Camera 2, attempt $ATTEMPT"
        "$CAMERA2_CONTROL" restart >>"$LOG_FILE" 2>&1 || \
            "$CAMERA2_CONTROL" start >>"$LOG_FILE" 2>&1 || true

        if wait_snapshot 8081 "Camera 2" 25; then
            return 0
        fi

        "$CAMERA2_CONTROL" stop >>"$LOG_FILE" 2>&1 || true
        ATTEMPT=$((ATTEMPT + 1))
        sleep 2
    done

    log "ERROR: Camera 2 failed after 3 attempts"
    return 1
}

start_cameras()
{
    if ! wait_for_camera_devices; then
        return 1
    fi

    start_primary_camera || true
    sleep 3
    start_secondary_camera || true
}

start_ifs()
{
    IFS_BOOT="/opt/config/mod_data/ifs_spoolman/start.sh"
    if [ -x "$IFS_BOOT" ]; then
        log "Starting IFS Spoolman Manager"
        "$IFS_BOOT" >>"$STATE_DIR/log/ifs.log" 2>&1 &
    else
        log "ERROR: IFS start.sh missing"
    fi
}

refresh_overlays()
{
    rm -f "$STATE_DIR/refresh.changed"
    if "$PLUGIN_DIR/install.sh" --refresh-only >>"$LOG_FILE" 2>&1; then
        [ -f "$STATE_DIR/refresh.changed" ] && return 10
        return 0
    fi
    log "ERROR: overlay refresh failed"
    return 1
}

request_klipper_restart()
{
    i=0
    while [ "$i" -lt 30 ]; do
        if wget -qO- http://127.0.0.1:7125/server/info >/dev/null 2>&1; then
            log "Generated configs changed; requesting firmware restart"
            wget -qO- --post-data='' \
                http://127.0.0.1:7125/printer/firmware_restart \
                >>"$LOG_FILE" 2>&1 || true
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    log "WARN: Moonraker unavailable; firmware restart was not requested"
}

power_on()
{
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        log "Power-on integration is already running"
        return 0
    fi
    trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

    normalize_git_hygiene

    CHANGED=0
    refresh_overlays || RC=$?
    RC="${RC:-0}"
    [ "$RC" -eq 10 ] && CHANGED=1

    start_cameras
    start_ifs

    if [ "$CHANGED" -eq 1 ]; then
        sleep 3
        request_klipper_restart
    fi

    log "Power-on integration completed"
}

case "${1:-}" in
    power-on) power_on ;;
    hygiene) normalize_git_hygiene ;;
    camera-select) select_primary_camera ;;
    cameras) start_cameras ;;
    ifs) start_ifs ;;
    *)
        echo "Usage: $0 {power-on|hygiene|camera-select|cameras|ifs}" >&2
        exit 2
        ;;
esac
