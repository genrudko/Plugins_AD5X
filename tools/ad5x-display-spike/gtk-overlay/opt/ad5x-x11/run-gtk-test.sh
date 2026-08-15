#!/bin/sh
set -eu

BUNDLE=/opt/ad5x-x11
PYTHON=/bin/python3
export PATH="$BUNDLE/bin${PATH:+:$PATH}"
export LD_LIBRARY_PATH="$BUNDLE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$BUNDLE/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export GI_TYPELIB_PATH="$BUNDLE/lib/girepository-1.0"
export XDG_DATA_DIRS="$BUNDLE/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
export FONTCONFIG_PATH="$BUNDLE/etc/fonts"
export FONTCONFIG_FILE="$BUNDLE/etc/fonts/fonts.conf"
export GDK_BACKEND=x11

for required in Xorg xinput xkbcomp xsetroot; do
    if [ ! -x "$BUNDLE/bin/$required" ]; then
        echo "ERROR: missing $BUNDLE/bin/$required" >&2
        exit 1
    fi
done

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: missing Z-Mod chroot Python at $PYTHON" >&2
    exit 1
fi
if [ ! -f "$BUNDLE/gtk-smoke.py" ]; then
    echo "ERROR: missing $BUNDLE/gtk-smoke.py" >&2
    exit 1
fi
if [ ! -d "$BUNDLE/share/X11/xkb" ]; then
    echo "ERROR: missing $BUNDLE/share/X11/xkb" >&2
    exit 1
fi
if [ ! -d "$BUNDLE/lib/girepository-1.0" ]; then
    echo "ERROR: missing GObject typelibs" >&2
    exit 1
fi
if [ ! -d "$BUNDLE/lib/python3.12/site-packages/gi" ]; then
    echo "ERROR: missing PyGObject site-packages" >&2
    exit 1
fi

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

CONF=/tmp/ad5x-xorg.conf
LOG=/tmp/ad5x-Xorg.0.log
sed "s#@TOUCH_EVENT@#$TOUCH_EVENT#g" "$BUNDLE/xorg.conf.in" > "$CONF"

mkdir -p /tmp/.X11-unix /tmp/ad5x-xkb /tmp/ad5x-fontconfig-cache
rm -f /tmp/.X0-lock /tmp/.X11-unix/X0

BACKLIGHT=/sys/class/backlight/backlight_gpio0
BACKLIGHT_BRIGHTNESS=""
BACKLIGHT_POWER=""
XORG_PID=""

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
}
trap cleanup EXIT INT TERM

if [ -n "$BACKLIGHT_BRIGHTNESS" ] && [ -n "$BACKLIGHT_POWER" ]; then
    echo "$(cat "$BACKLIGHT/max_brightness")" > "$BACKLIGHT/brightness"
    echo 0 > "$BACKLIGHT/bl_power"
    echo "LCD backlight enabled via $BACKLIGHT"
else
    echo "WARNING: $BACKLIGHT is unavailable; LCD may remain blank" >&2
fi

"$BUNDLE/bin/Xorg" :0 vt1 \
    -config "$CONF" \
    -modulepath "$BUNDLE/lib/xorg/modules" \
    -xkbdir "$BUNDLE/share/X11/xkb" \
    -logfile "$LOG" \
    -nolisten tcp \
    -noreset \
    -s 0 &
XORG_PID=$!

READY=0
i=0
while [ "$i" -lt 10 ]; do
    if DISPLAY=:0 "$BUNDLE/bin/xinput" --list >/tmp/ad5x-xinput.txt 2>&1; then
        READY=1
        break
    fi
    if ! kill -0 "$XORG_PID" 2>/dev/null; then
        echo "ERROR: Xorg exited during startup" >&2
        tail -n 80 "$LOG" 2>/dev/null || true
        exit 1
    fi
    i=$((i + 1))
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "ERROR: Xorg did not become ready" >&2
    tail -n 80 "$LOG" 2>/dev/null || true
    exit 1
fi

echo "=== xinput ==="
cat /tmp/ad5x-xinput.txt
DISPLAY=:0 "$BUNDLE/bin/xsetroot" -solid '#101820'

echo
echo "Xorg is ready. Starting GTK3/PyGObject smoke with Z-Mod Python:"
"$PYTHON" --version
echo "Touch the GTK window and watch for GTK_TOUCH_OK."
echo "Press Ctrl-C to stop; the launcher will restore the LCD backlight state."
echo

DISPLAY=:0 "$PYTHON" "$BUNDLE/gtk-smoke.py"
