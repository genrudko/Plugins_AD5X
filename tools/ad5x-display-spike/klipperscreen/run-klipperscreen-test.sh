#!/bin/sh
set -eu

RUNTIME=/opt/ad5x-x11
APPROOT=/opt/ad5x-klipperscreen
APP="$APPROOT/app"
PYTHON=/bin/python3
CONFIG="$APPROOT/KlipperScreen.conf"
LOG=/tmp/KlipperScreen.log
HELIX_INIT=/etc/init.d/S80helixscreen

export PATH="$RUNTIME/bin${PATH:+:$PATH}"
export LD_LIBRARY_PATH="$APPROOT/lib:$RUNTIME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$APPROOT/lib/python3.12/lib-dynload:$APPROOT/lib/python3.12/site-packages:$RUNTIME/lib/python3.12/site-packages:$APP${PYTHONPATH:+:$PYTHONPATH}"
export GI_TYPELIB_PATH="$RUNTIME/lib/girepository-1.0"
export XDG_DATA_DIRS="$RUNTIME/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
export FONTCONFIG_PATH="$RUNTIME/etc/fonts"
export FONTCONFIG_FILE="$RUNTIME/etc/fonts/fonts.conf"
export GDK_BACKEND=x11
export AD5X_KLIPPERSCREEN_PNG_ONLY=1
export HOME=/tmp/ad5x-klipperscreen-home
export XDG_RUNTIME_DIR=/tmp/ad5x-klipperscreen-runtime

mkdir -p "$HOME" "$XDG_RUNTIME_DIR" /tmp/.X11-unix /tmp/ad5x-xkb /tmp/ad5x-fontconfig-cache
chmod 700 "$XDG_RUNTIME_DIR"

for required in Xorg xinput xkbcomp xsetroot; do
    if [ ! -x "$RUNTIME/bin/$required" ]; then
        echo "ERROR: missing proven Stage 3 runtime executable $RUNTIME/bin/$required" >&2
        exit 1
    fi
done

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: missing Z-Mod Python at $PYTHON" >&2
    exit 1
fi
if [ ! -f "$APP/screen.py" ]; then
    echo "ERROR: missing upstream KlipperScreen at $APP/screen.py" >&2
    exit 1
fi
if [ ! -f "$CONFIG" ]; then
    echo "ERROR: missing Stage 4 config at $CONFIG" >&2
    exit 1
fi
if [ ! -d "$APPROOT/lib/python3.12/lib-dynload" ]; then
    echo "ERROR: missing Stage 4 Python network delta" >&2
    exit 1
fi

"$PYTHON" -c 'import cairo,gi,hashlib,jinja2,requests,ssl,websocket,zlib; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk; print("KS_IMPORTS_OK", Gtk.get_major_version(), Gtk.get_minor_version(), jinja2.__version__, requests.__version__, websocket.__version__, cairo.version, zlib.ZLIB_VERSION, ssl.OPENSSL_VERSION, hashlib.sha256(b"ad5x").hexdigest()[:12])'

TOUCH_EVENT=""
for namefile in /sys/class/input/event*/device/name; do
    [ -r "$namefile" ] || continue
    name="$(cat "$namefile")"
    case "$name" in
        *TSC2007*|*Touchscreen*)
            event="$(basename "$(dirname "$(dirname "$namefile")")")"
            TOUCH_EVENT="/dev/input/$event"
            echo "Touch candidate: $name -> $TOUCH_EVENT"
            case "$name" in
                *TSC2007*) break ;;
            esac
            ;;
    esac
done

if [ -z "$TOUCH_EVENT" ] || [ ! -c "$TOUCH_EVENT" ]; then
    echo "ERROR: TSC2007 touchscreen evdev node was not found" >&2
    exit 1
fi

CONF=/tmp/ad5x-klipperscreen-xorg.conf
XORG_LOG=/tmp/ad5x-klipperscreen-Xorg.0.log
sed "s#@TOUCH_EVENT@#$TOUCH_EVENT#g" "$RUNTIME/xorg.conf.in" > "$CONF"
rm -f /tmp/.X0-lock /tmp/.X11-unix/X0 "$LOG"

BACKLIGHT=/sys/class/backlight/backlight_gpio0
BACKLIGHT_BRIGHTNESS=""
BACKLIGHT_POWER=""
XORG_PID=""
HELIX_WAS_RUNNING=0

helix_running() {
    for proc in /proc/[0-9]*; do
        [ -r "$proc/cmdline" ] || continue
        cmd="$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
        cmd_lower="$(printf '%s' "$cmd" | tr '[:upper:]' '[:lower:]')"
        case "$cmd_lower" in
            *helix*screen*) return 0 ;;
        esac
    done
    return 1
}

if [ -r "$BACKLIGHT/brightness" ] && [ -w "$BACKLIGHT/brightness" ] && \
   [ -r "$BACKLIGHT/max_brightness" ] && \
   [ -r "$BACKLIGHT/bl_power" ] && [ -w "$BACKLIGHT/bl_power" ]; then
    BACKLIGHT_BRIGHTNESS="$(cat "$BACKLIGHT/brightness")"
    BACKLIGHT_POWER="$(cat "$BACKLIGHT/bl_power")"
fi

cleanup() {
    if [ -n "$XORG_PID" ]; then
        kill "$XORG_PID" 2>/dev/null || true
        wait "$XORG_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKLIGHT_BRIGHTNESS" ] && [ -n "$BACKLIGHT_POWER" ]; then
        echo "$BACKLIGHT_BRIGHTNESS" > "$BACKLIGHT/brightness" 2>/dev/null || true
        echo "$BACKLIGHT_POWER" > "$BACKLIGHT/bl_power" 2>/dev/null || true
    fi
    if [ "$HELIX_WAS_RUNNING" -eq 1 ]; then
        if [ -x "$HELIX_INIT" ]; then
            "$HELIX_INIT" start >/tmp/ad5x-klipperscreen-helix-start.log 2>&1 || \
                echo "WARNING: failed to restore HelixScreen; see /tmp/ad5x-klipperscreen-helix-start.log" >&2
        else
            echo "WARNING: HelixScreen was running but $HELIX_INIT is unavailable during cleanup" >&2
        fi
    fi
}
trap cleanup EXIT INT TERM HUP

# HelixScreen and KlipperScreen must never compete for the AD5X LCD/input stack.
# Hardware acceptance proved that this launcher, not the operator, must own the
# transition and restore the previous UI on exit.
if helix_running; then
    [ -x "$HELIX_INIT" ] || {
        echo "ERROR: HelixScreen is running but $HELIX_INIT is unavailable" >&2
        exit 1
    }
    HELIX_WAS_RUNNING=1
    echo "HelixScreen is running; stopping it before starting AD5X Xorg/KlipperScreen"
    "$HELIX_INIT" stop >/tmp/ad5x-klipperscreen-helix-stop.log 2>&1 || true
    i=0
    while helix_running && [ "$i" -lt 10 ]; do
        i=$((i + 1))
        sleep 1
    done
    if helix_running; then
        echo "ERROR: HelixScreen did not stop; refusing competing display startup" >&2
        exit 1
    fi
    echo "HELIX_STOPPED_FOR_KLIPPERSCREEN"
fi

if [ -n "$BACKLIGHT_BRIGHTNESS" ] && [ -n "$BACKLIGHT_POWER" ]; then
    echo "$(cat "$BACKLIGHT/max_brightness")" > "$BACKLIGHT/brightness"
    echo 0 > "$BACKLIGHT/bl_power"
    echo "LCD backlight enabled via $BACKLIGHT"
else
    echo "WARNING: $BACKLIGHT is unavailable; LCD may remain blank" >&2
fi

"$RUNTIME/bin/Xorg" :0 vt1 \
    -config "$CONF" \
    -modulepath "$RUNTIME/lib/xorg/modules" \
    -xkbdir "$RUNTIME/share/X11/xkb" \
    -logfile "$XORG_LOG" \
    -nolisten tcp \
    -noreset \
    -s 0 &
XORG_PID=$!

READY=0
i=0
while [ "$i" -lt 10 ]; do
    if DISPLAY=:0 "$RUNTIME/bin/xinput" --list >/tmp/ad5x-klipperscreen-xinput.txt 2>&1; then
        READY=1
        break
    fi
    if ! kill -0 "$XORG_PID" 2>/dev/null; then
        echo "ERROR: Xorg exited during KlipperScreen startup" >&2
        tail -n 80 "$XORG_LOG" 2>/dev/null || true
        exit 1
    fi
    i=$((i + 1))
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "ERROR: Xorg did not become ready" >&2
    tail -n 80 "$XORG_LOG" 2>/dev/null || true
    exit 1
fi

echo "=== xinput ==="
cat /tmp/ad5x-klipperscreen-xinput.txt
DISPLAY=:0 "$RUNTIME/bin/xsetroot" -solid '#101820'

echo
echo "Xorg is ready. Starting upstream KlipperScreen with Z-Mod Python:"
"$PYTHON" --version
echo "Config: $CONFIG"
echo "Log: $LOG"
echo "Press Ctrl-C to stop; the launcher will restore the previous display state."
echo

cd "$APP"
set +e
DISPLAY=:0 "$PYTHON" "$APP/screen.py" -c "$CONFIG" -l "$LOG"
KS_RC=$?
set -e

if [ "$KS_RC" -ne 0 ]; then
    echo "ERROR: KlipperScreen exited with status $KS_RC" >&2
    echo "=== KlipperScreen log tail ===" >&2
    tail -n 120 "$LOG" 2>/dev/null || true
    exit "$KS_RC"
fi

echo "KLIPPERSCREEN_EXIT_OK"
