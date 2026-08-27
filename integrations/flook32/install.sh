#!/bin/sh
set -eu

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TARGET="${AD5X_FLOOK_DIR:-/opt/config/mod_data/plugins/flook32}"
POWER_ON="${AD5X_POWER_ON:-/opt/config/mod_data/power_on.sh}"
BACKUPS="${AD5X_FLOOK_BACKUPS:-$TARGET/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUPS/$STAMP"
SUCCESS=0

SRC_PY="$HERE/klipper/flook32.py"
SRC_CFG="$HERE/klipper/flook32.cfg"
SRC_ENSURE="$HERE/scripts/ensure.sh"

[ -f "$SRC_PY" ] || { echo "ERROR: missing $SRC_PY" >&2; exit 1; }
[ -f "$SRC_CFG" ] || { echo "ERROR: missing $SRC_CFG" >&2; exit 1; }
[ -f "$SRC_ENSURE" ] || { echo "ERROR: missing $SRC_ENSURE" >&2; exit 1; }

mkdir -p "$TARGET" "$BACKUP"

snapshot()
{
    FILE="$1"; KEY="$2"
    if [ -L "$FILE" ]; then
        readlink "$FILE" > "$BACKUP/.symlink-$KEY"
    elif [ -e "$FILE" ]; then
        cp -p "$FILE" "$BACKUP/$KEY"
    else
        : > "$BACKUP/.absent-$KEY"
    fi
}

restore()
{
    FILE="$1"; KEY="$2"
    rm -f "$FILE"
    if [ -f "$BACKUP/.symlink-$KEY" ]; then
        ln -s "$(cat "$BACKUP/.symlink-$KEY")" "$FILE"
    elif [ -f "$BACKUP/$KEY" ]; then
        cp -p "$BACKUP/$KEY" "$FILE"
    fi
}

snapshot "$TARGET/flook32.py" flook32.py
snapshot "$TARGET/flook32.cfg" flook32.cfg
snapshot "$TARGET/ensure.sh" ensure.sh
snapshot "$POWER_ON" power_on.sh

rollback()
{
    set +e
    restore "$TARGET/flook32.py" flook32.py
    restore "$TARGET/flook32.cfg" flook32.cfg
    restore "$TARGET/ensure.sh" ensure.sh
    restore "$POWER_ON" power_on.sh
    echo "ERROR: FLOOK32 install rolled back. Backup: $BACKUP" >&2
}

finish()
{
    RC=$?
    trap - EXIT HUP INT TERM
    if [ "$SUCCESS" -ne 1 ]; then
        rollback
        [ "$RC" -ne 0 ] || RC=1
    fi
    exit "$RC"
}
trap finish EXIT HUP INT TERM

cp -p "$SRC_PY" "$TARGET/flook32.py"
cp -p "$SRC_CFG" "$TARGET/flook32.cfg"
cp -p "$SRC_ENSURE" "$TARGET/ensure.sh"
chmod 0644 "$TARGET/flook32.py" "$TARGET/flook32.cfg"
chmod 0755 "$TARGET/ensure.sh"

[ -f "$POWER_ON" ] || printf '#!/bin/sh\n# Enter Poweron code here\n' > "$POWER_ON"
BEGIN_COUNT="$(grep -Fxc '# >>> FLOOK32_BOOT_ENSURE >>>' "$POWER_ON" 2>/dev/null || true)"
END_COUNT="$(grep -Fxc '# <<< FLOOK32_BOOT_ENSURE <<<' "$POWER_ON" 2>/dev/null || true)"
[ "$BEGIN_COUNT" = "$END_COUNT" ] || { echo 'ERROR: malformed FLOOK32 power_on marker block' >&2; exit 1; }
[ "$BEGIN_COUNT" -le 1 ] || { echo 'ERROR: duplicate FLOOK32 power_on marker blocks' >&2; exit 1; }
awk '
  /# >>> FLOOK32_BOOT_ENSURE >>>/ {skip=1; next}
  /# <<< FLOOK32_BOOT_ENSURE <<</ {skip=0; next}
  !skip {print}
' "$POWER_ON" > "$POWER_ON.tmp"
cat >> "$POWER_ON.tmp" <<'HOOK'

# >>> FLOOK32_BOOT_ENSURE >>>
if [ -x /opt/config/mod_data/plugins/flook32/ensure.sh ]; then
    /opt/config/mod_data/plugins/flook32/ensure.sh --boot \
        >> /opt/config/mod_data/plugins/flook32/boot.log 2>&1
fi
# <<< FLOOK32_BOOT_ENSURE <<<
HOOK
mv "$POWER_ON.tmp" "$POWER_ON"
chmod 0755 "$POWER_ON"
sh -n "$POWER_ON"

"$TARGET/ensure.sh"

SUCCESS=1
trap - EXIT HUP INT TERM
echo "FLOOK32 AD5X integration installed. Backup: $BACKUP"
echo 'Full Klipper process restart/reboot is required before the new Python module is loaded.'
