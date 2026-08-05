#!/bin/sh
set -u
STATE_DIR="/opt/config/mod_data/ad5x_custom"
CONFIG_FILE="$STATE_DIR/config.sh"
LOG_DIR="$STATE_DIR/log"
mkdir -p "$LOG_DIR"
PRIMARY_CAMERA_NAME="HD Camera"
CAMERA2_SCRIPT="$STATE_DIR/state/S99zzcamera2"
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"

camera_select() {
    LOG="$LOG_DIR/camera-select.log"
    [ -f /opt/config/mod/.shell/0.sh ] && . /opt/config/mod/.shell/0.sh
    V4L2_BIN="${V4l2:-/usr/bin/v4l2-ctl}"
    FOUND=""
    for SYSDEV in /sys/class/video4linux/video*; do
        [ -r "$SYSDEV/name" ] || continue
        NAME="$(cat "$SYSDEV/name" 2>/dev/null || true)"
        case "$NAME" in
            *"$PRIMARY_CAMERA_NAME"*)
                CANDIDATE="${SYSDEV##*/}"
                if "$V4L2_BIN" -d "/dev/$CANDIDATE" --list-formats-ext >/dev/null 2>&1; then
                    FOUND="$CANDIDATE"; break
                fi
                ;;
        esac
    done
    [ -n "$FOUND" ] || { echo "$(date) primary camera not found: $PRIMARY_CAMERA_NAME" >>"$LOG"; return 0; }
    CONF=/opt/config/mod_data/camera.conf
    [ -f "$CONF" ] || : >"$CONF"
    if grep -q '^VIDEO=' "$CONF"; then sed -i "s/^VIDEO=.*/VIDEO=$FOUND/" "$CONF"; else printf '\nVIDEO=%s\n' "$FOUND" >>"$CONF"; fi
    echo "$(date) primary camera: $PRIMARY_CAMERA_NAME -> /dev/$FOUND" >>"$LOG"
}

camera2_start() {
    LOG="$LOG_DIR/camera2.log"
    if [ "${1:-start}" = stop ]; then [ -x "$CAMERA2_SCRIPT" ] && "$CAMERA2_SCRIPT" stop >>"$LOG" 2>&1 || true; return 0; fi
    wget -qO- 'http://127.0.0.1:8081/?action=snapshot' >/dev/null 2>&1 && return 0
    [ -x "$CAMERA2_SCRIPT" ] || { echo "$(date) missing $CAMERA2_SCRIPT" >>"$LOG"; return 0; }
    i=0
    while [ "$i" -lt 30 ]; do wget -qO- 'http://127.0.0.1:8080/?action=snapshot' >/dev/null 2>&1 && break; i=$((i+1)); sleep 1; done
    "$CAMERA2_SCRIPT" start >>"$LOG" 2>&1 &
    echo "$(date) camera 2 start requested" >>"$LOG"
}

ifs_start() {
    LOG="$LOG_DIR/ifs.log"
    if [ "${1:-start}" = stop ]; then [ -x /opt/config/mod_data/ifs_spoolman/stop.sh ] && /opt/config/mod_data/ifs_spoolman/stop.sh >>"$LOG" 2>&1 || true; return 0; fi
    START=/opt/config/mod_data/ifs_spoolman/start.sh
    [ -x "$START" ] || { echo "$(date) missing IFS start.sh" >>"$LOG"; return 0; }
    i=0
    while [ "$i" -lt 60 ]; do wget -qO- http://127.0.0.1:7125/server/info >/dev/null 2>&1 && break; i=$((i+1)); sleep 1; done
    "$START" >>"$LOG" 2>&1 || true
}

case "${0##*/}" in
    S98ad5x-camera-select) camera_select ;;
    S99zzad5x-camera2) camera2_start "${1:-start}" ;;
    S66ad5x-ifs-spoolman) ifs_start "${1:-start}" ;;
    *)
        case "${1:-}" in
            camera-select) camera_select ;;
            camera2) camera2_start "${2:-start}" ;;
            ifs) ifs_start "${2:-start}" ;;
            *) echo "Usage: $0 {camera-select|camera2|ifs}" >&2; exit 2 ;;
        esac
        ;;
esac
