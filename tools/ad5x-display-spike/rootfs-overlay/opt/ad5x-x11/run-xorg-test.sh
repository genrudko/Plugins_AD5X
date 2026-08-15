#!/bin/sh
set -eu

BUNDLE=/opt/ad5x-x11
export PATH="$BUNDLE/bin${PATH:+:$PATH}"
export LD_LIBRARY_PATH="$BUNDLE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

for required in Xorg xinput xkbcomp xsetroot xev; do
    if [ ! -x "$BUNDLE/bin/$required" ]; then
        echo "ERROR: missing $BUNDLE/bin/$required" >&2
        exit 1
    fi
done

if [ ! -d "$BUNDLE/share/X11/xkb" ]; then
    echo "ERROR: missing $BUNDLE/share/X11/xkb" >&2
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

mkdir -p /tmp/.X11-unix /tmp/ad5x-xkb
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

# A visible render sanity check before opening xev.
DISPLAY=:0 "$BUNDLE/bin/xsetroot" -solid '#203050'

echo
echo "Xorg is running on /dev/fb0. xev will open a test window."
echo "Touch the LCD and watch this terminal for Button/Motion events."
echo "Press Ctrl-C in this terminal to stop the test and Xorg."
echo

DISPLAY=:0 "$BUNDLE/bin/xev" -geometry 640x360+80+60
