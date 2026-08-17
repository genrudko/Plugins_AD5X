#!/bin/sh
set -u

PLUGIN_DIR="/opt/config/mod_data/plugins/ad5x_custom"
STATE_DIR="/opt/config/mod_data/ad5x_custom"
LOG_DIR="$STATE_DIR/log"
LOG_FILE="$LOG_DIR/power-on.log"
LOCK_DIR="/tmp/ad5x-custom-power-on.lock"
CAMERA_RECOVERY_LOCK="/tmp/ad5x-custom-camera-recovery.lock"
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

    move_legacy_group "$LEGACY_DIR/zmod-shell" \
        /opt/config/mod/.shell/*.before-*
    move_legacy_group "$LEGACY_DIR/zmod-start" \
        /opt/config/mod/.shell/root/*.bak_*
    move_legacy_group "$LEGACY_DIR/zmod-translate" \
        /opt/config/mod/translate/ru/*.bak_*
    move_legacy_group "$LEGACY_DIR/timelapse" \
        /opt/config/mod_data/plugins/timelapse/*.bak_*

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
    # Z-Mod defines V4l2 as a compound command, for example:
    # chroot /usr/data/.mod/.zmod v4l2-ctl
    # It must therefore be expanded unquoted.
    $V4L2_COMMAND -d "$DEVICE" --list-formats-ext >/dev/null 2>&1
}

find_named_capture_device()
{
    CAMERA_NAME="$1"
    EXCLUDED_DEVICE="${2:-}"
    for SYSDEV in /sys/class/video4linux/video*; do
        [ -r "$SYSDEV/name" ] || continue
        CANDIDATE="${SYSDEV##*/}"
        [ -n "$EXCLUDED_DEVICE" ] && [ "$CANDIDATE" = "$EXCLUDED_DEVICE" ] && continue
        DEVICE_NAME="$(cat "$SYSDEV/name" 2>/dev/null || true)"
        case "$DEVICE_NAME" in
            *"$CAMERA_NAME"*)
                if v4l2_formats_available "/dev/$CANDIDATE"; then
                    echo "$CANDIDATE"
                    return 0
                fi
                ;;
        esac
    done
    return 1
}

configured_primary_camera_device()
{
    CAMERA_CONF="/opt/config/mod_data/camera.conf"
    [ -r "$CAMERA_CONF" ] || return 1
    sed -n 's/^VIDEO=//p' "$CAMERA_CONF" | tail -n 1
}

snapshot_ready()
{
    PORT="$1"
    wget -q -T 2 -O /dev/null "http://127.0.0.1:$PORT/?action=snapshot" 2>/dev/null
}

wait_snapshot()
{
    PORT="$1"
    LABEL="$2"
    LIMIT="$3"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        if snapshot_ready "$PORT"; then
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
        return 1
    fi

    CAMERA_CONF="/opt/config/mod_data/camera.conf"
    [ -f "$CAMERA_CONF" ] || : >"$CAMERA_CONF"
    if grep -q '^VIDEO=' "$CAMERA_CONF"; then
        sed -i "s/^VIDEO=.*/VIDEO=$FOUND_VIDEO/" "$CAMERA_CONF"
    else
        printf '\nVIDEO=%s\n' "$FOUND_VIDEO" >>"$CAMERA_CONF"
    fi
    log "Primary camera selected for stock startup: $PRIMARY_CAMERA_NAME -> /dev/$FOUND_VIDEO"
    return 0
}

wait_and_select_primary_camera()
{
    LIMIT="${1:-30}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        if select_primary_camera; then
            return 0
        fi
        COUNT=$((COUNT + 1))
        sleep 1
    done
    log "WARN: primary camera selection timed out; stock S99camera remains authoritative"
    return 1
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
        log "Starting Camera 2 after stock Camera 1, attempt $ATTEMPT"
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

camera_recover()
{
    if ! mkdir "$CAMERA_RECOVERY_LOCK" 2>/dev/null; then
        log "Camera 2 recovery is already running"
        return 0
    fi
    trap 'rmdir "$CAMERA_RECOVERY_LOCK" 2>/dev/null || true' EXIT INT TERM

    COUNT=0
    PRIMARY_WAIT_LOGGED=0
    while [ "$COUNT" -lt 60 ]; do
        if snapshot_ready 8081; then
            log "Camera 2 recovery completed: port 8081 is available"
            return 0
        fi

        # Camera 1 is owned exclusively by the stock Z-Mod S99camera service.
        # Never restart or stop it here: stock stop() uses a global killall.
        if ! snapshot_ready 8080; then
            if [ "$PRIMARY_WAIT_LOGGED" -eq 0 ]; then
                log "Waiting for stock Camera 1 on port 8080 before starting Camera 2"
                PRIMARY_WAIT_LOGGED=1
            fi
            COUNT=$((COUNT + 1))
            sleep 10
            continue
        fi

        load_zmod_camera_tools
        PRIMARY_DEVICE="$(configured_primary_camera_device 2>/dev/null || true)"

        # A single UVC camera may expose multiple /dev/videoN nodes. If the
        # configured stock primary has the identity that used to belong to
        # Camera 2, treat the machine as single-camera before scanning sibling
        # nodes. Excluding only /dev/video0 would still allow the same physical
        # camera to be rediscovered through /dev/video1.
        if [ -n "$PRIMARY_DEVICE" ] && [ -r "/sys/class/video4linux/$PRIMARY_DEVICE/name" ]; then
            PRIMARY_NAME="$(cat "/sys/class/video4linux/$PRIMARY_DEVICE/name" 2>/dev/null || true)"
            case "$PRIMARY_NAME" in
                *"$SECONDARY_CAMERA_NAME"*)
                    log "Single-camera mode detected: $SECONDARY_CAMERA_NAME is already stock Camera 1 on /dev/$PRIMARY_DEVICE; Camera 2 recovery disabled"
                    return 0
                    ;;
            esac
        fi

        SECONDARY="$(find_named_capture_device "$SECONDARY_CAMERA_NAME" "$PRIMARY_DEVICE" 2>/dev/null || true)"

        if [ -n "$SECONDARY" ]; then
            log "Camera 2 device ready after stock Camera 1: /dev/$SECONDARY"
            start_secondary_camera || true

            if snapshot_ready 8081; then
                log "Camera 2 recovery completed successfully"
                return 0
            fi
        fi

        COUNT=$((COUNT + 1))
        sleep 10
    done

    log "ERROR: Camera 2 did not recover within 10 minutes; Camera 1 was left untouched"
    return 1
}

launch_camera_recovery()
{
    if snapshot_ready 8081; then
        return 0
    fi

    log "Scheduling late Camera 2 recovery after stock Camera 1 startup"
    nohup "$PLUGIN_DIR/runtime.sh" camera-recover \
        </dev/null >>"$LOG_FILE" 2>&1 &
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
        if wget -q -T 5 -O /dev/null http://127.0.0.1:7125/server/info 2>/dev/null; then
            log "Generated configs changed; requesting firmware restart"
            wget -q -T 5 -O /dev/null --post-data='' \
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
    RC=0
    refresh_overlays || RC=$?
    [ "$RC" -eq 10 ] && CHANGED=1

    # IFS must not be delayed by camera discovery.
    start_ifs

    # Only select the device for the later stock S99camera startup.
    # Do not call S99camera restart from this early power-on hook.
    wait_and_select_primary_camera 30 || true

    # The worker waits for stock port 8080, then starts only Camera 2.
    launch_camera_recovery

    if [ "$CHANGED" -eq 1 ]; then
        sleep 3
        request_klipper_restart
    fi

    log "Power-on integration completed; Camera 1 remains owned by stock S99camera"
}

case "${1:-}" in
    power-on) power_on ;;
    hygiene) normalize_git_hygiene ;;
    camera-select) select_primary_camera ;;
    cameras|camera-recover) camera_recover ;;
    ifs) start_ifs ;;
    *)
        echo "Usage: $0 {power-on|hygiene|camera-select|cameras|camera-recover|ifs}" >&2
        exit 2
        ;;
esac
