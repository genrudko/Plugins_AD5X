#!/bin/sh
set -u
BASE="${AD5X_FLOOK_DIR:-/opt/config/mod_data/plugins/flook32}"
SRC="$BASE/flook32.py"
CFG="$BASE/flook32.cfg"
KLIPPER="${AD5X_KLIPPER_REPO_ROOT:-/usr/data/config/base/klipper}"
EXTRAS="${AD5X_KLIPPER_EXTRAS_DIR:-$KLIPPER/klippy/extras}"
LINK="${AD5X_FLOOK_KLIPPER_DEST:-$EXTRAS/flook32.py}"
EXCLUDE="$KLIPPER/.git/info/exclude"
PLUGINS_CFG="${AD5X_KLIPPER_INCLUDES:-/opt/config/mod_data/plugins.cfg}"
USER_CFG="${AD5X_USER_CFG:-/opt/config/mod_data/user.cfg}"
INCLUDE='[include plugins/flook32/flook32.cfg]'
PY="${AD5X_KLIPPER_PYTHON:-/usr/prog/Python-3.8.2/bin/python3}"
MODE="${1:-full}"
export LD_LIBRARY_PATH="/usr/prog/Python-3.8.2/lib:/usr/prog/openssl-1.0.2d/lib:/usr/prog/libffi-3.4.4/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo '=== FLOOK32 ENSURE ==='
[ -f "$SRC" ] || { echo "ERROR: missing $SRC"; exit 1; }
[ -f "$CFG" ] || { echo "ERROR: missing $CFG"; exit 1; }
[ -d "$EXTRAS" ] || { echo "ERROR: Klipper extras not found: $EXTRAS"; exit 1; }
chmod 644 "$SRC" "$CFG" 2>/dev/null || true
"$PY" -m py_compile "$SRC" || { echo 'ERROR: flook32.py is not valid for Klipper Python'; exit 1; }

if [ "$(readlink -f "$LINK" 2>/dev/null)" != "$SRC" ]; then
    rm -f "$LINK"
    ln -s "$SRC" "$LINK" || exit 1
    echo 'LINK: repaired'
else
    echo 'LINK: OK'
fi
if [ -d "$KLIPPER/.git/info" ]; then
    grep -qxF '/klippy/extras/flook32.py' "$EXCLUDE" 2>/dev/null || echo '/klippy/extras/flook32.py' >> "$EXCLUDE"
    echo 'GIT EXCLUDE: OK'
fi

# Keep an existing user.cfg include in place.  Do not rewrite user-owned
# configuration merely to move the include into plugins.cfg.
if [ -f "$USER_CFG" ] && grep -qxF "$INCLUDE" "$USER_CFG" 2>/dev/null; then
    # If an earlier installer also added the same exact line to plugins.cfg,
    # remove only that line to prevent Klipper from loading the section twice.
    if [ -f "$PLUGINS_CFG" ] && grep -qxF "$INCLUDE" "$PLUGINS_CFG" 2>/dev/null; then
        grep -Fvx "$INCLUDE" "$PLUGINS_CFG" > "$PLUGINS_CFG.tmp" 2>/dev/null || true
        mv "$PLUGINS_CFG.tmp" "$PLUGINS_CFG"
    fi
    echo 'CONFIG INCLUDE: user.cfg OK'
else
    [ -f "$PLUGINS_CFG" ] || : > "$PLUGINS_CFG"
    grep -qxF "$INCLUDE" "$PLUGINS_CFG" 2>/dev/null || echo "$INCLUDE" >> "$PLUGINS_CFG"
    echo 'CONFIG INCLUDE: plugins.cfg OK'
fi

if "$PY" - <<'PY' >/dev/null 2>&1
import websocket
assert websocket.__version__ == '1.8.0'
PY
then
    echo 'WEBSOCKET: 1.8.0 OK'
elif [ "$MODE" = '--boot' ]; then
    echo 'WARNING: websocket-client 1.8.0 missing; HTTP fallback remains available'
else
    echo 'WEBSOCKET: installing 1.8.0...'
    if "$PY" -m pip install --no-cache-dir --disable-pip-version-check 'websocket-client==1.8.0'; then
        echo 'WEBSOCKET: installed'
    else
        echo 'WARNING: websocket install failed; HTTP fallback remains available'
    fi
fi
echo 'FLOOK32 ENSURE: OK'
