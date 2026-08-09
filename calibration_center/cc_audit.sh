#!/bin/sh
# CALIBRATION-CENTER-001: on-demand event audit. No daemon/polling.
set -eu

STATE_ROOT="/opt/config/mod_data/calibration_center"
if [ -d /usr/data/config/mod_data ] && [ ! -d /opt/config/mod_data ]; then
    STATE_ROOT="/usr/data/config/mod_data/calibration_center"
fi
LOG_FILE="${STATE_ROOT}/audit.log"

mkdir -p "${STATE_ROOT}"

# Do not let arbitrary control characters enter the audit file.
EVENT="${1:-unknown}"
shift || true
DETAILS="$*"
EVENT=$(printf '%s' "$EVENT" | tr '\r\n\t' '   ')
DETAILS=$(printf '%s' "$DETAILS" | tr '\r\n\t' '   ')
TS=$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || date)

printf '%s\t%s\t%s\n' "$TS" "$EVENT" "$DETAILS" >>"${LOG_FILE}"

# Keep the file bounded without assuming GNU tools. Rotation is intentionally
# coarse and only runs when a Calibration Center event is written.
SIZE=$(wc -c <"${LOG_FILE}" 2>/dev/null || echo 0)
case "$SIZE" in
    ''|*[!0-9]*) SIZE=0 ;;
esac
if [ "$SIZE" -gt 262144 ]; then
    if [ -f "${LOG_FILE}.1" ]; then
        rm -f "${LOG_FILE}.1"
    fi
    mv "${LOG_FILE}" "${LOG_FILE}.1"
    : >"${LOG_FILE}"
fi

exit 0
