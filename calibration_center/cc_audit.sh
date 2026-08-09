#!/bin/sh
# CALIBRATION-CENTER-001: on-demand event audit and bounded test-file generation.
# No daemon/polling.
set -eu

is_number_in_range() {
    VALUE="$1"; LOW="$2"; HIGH="$3"
    awk -v v="$VALUE" -v lo="$LOW" -v hi="$HIGH" 'BEGIN {
        if (v ~ /^[-+]?[0-9]+([.][0-9]+)?$/ && (v + 0) >= lo && (v + 0) <= hi) exit 0
        exit 1
    }'
}

generate_first_layer() {
    [ "$#" -eq 5 ] || {
        echo "Calibration Center: generate-first-layer expects GCODE_DIR MATERIAL NOZZLE_TEMP BED_TEMP NOZZLE" >&2
        exit 2
    }

    GCODE_DIR="$1"
    MATERIAL="$2"
    NOZZLE_TEMP="$3"
    BED_TEMP="$4"
    NOZZLE="$5"

    [ -d "$GCODE_DIR" ] || {
        echo "Calibration Center: virtual_sdcard path not found: $GCODE_DIR" >&2
        exit 2
    }

    case "$MATERIAL" in
        PLA|PETG|ABS|ASA|TPU|CUSTOM) ;;
        *) echo "Calibration Center: unsupported material preset: $MATERIAL" >&2; exit 2 ;;
    esac

    is_number_in_range "$NOZZLE_TEMP" 170 280 || {
        echo "Calibration Center: nozzle temperature outside 170..280 C" >&2
        exit 2
    }
    is_number_in_range "$BED_TEMP" 0 110 || {
        echo "Calibration Center: bed temperature outside 0..110 C" >&2
        exit 2
    }
    is_number_in_range "$NOZZLE" 0.20 1.20 || {
        echo "Calibration Center: nozzle diameter outside 0.20..1.20 mm" >&2
        exit 2
    }

    OUT="$GCODE_DIR/Calibration_Center_First_Layer.gcode"
    TMP="$OUT.tmp.$$"
    umask 022

    # The patch is centered on the 220x220 AD5X bed. Line width/layer height and
    # extrusion are derived from the selected nozzle. The file deliberately uses
    # START_PRINT/END_PRINT so Z-Mod and the Calibration Center start hook see the
    # same print-time coordinate/offset stack as a normal sliced job.
    awk -v mat="$MATERIAL" -v nt="$NOZZLE_TEMP" -v bt="$BED_TEMP" -v nozzle="$NOZZLE" '
        BEGIN {
            filament_area = 3.141592653589793 * 1.75 * 1.75 / 4.0
            layer = nozzle * 0.50
            if (layer < 0.15) layer = 0.15
            if (layer > 0.40) layer = 0.40
            width = nozzle * 1.12
            pitch = width
            e_per_mm = width * layer / filament_area

            x0 = 80.0
            x1 = 140.0
            y0 = 100.0
            patch_h = 20.0
            lines = int(patch_h / pitch) + 1
            print_feed = 1200
            travel_feed = 6000
            line_e = (x1 - x0) * e_per_mm

            print "; Calibration Center built-in first-layer verification"
            printf "; material=%s nozzle=%.3f nozzle_temp=%.1f bed_temp=%.1f\n", mat, nozzle, nt, bt
            printf "; layer_height=%.3f line_width=%.3f\n", layer, width
            printf "START_PRINT EXTRUDER_TEMP=%.1f BED_TEMP=%.1f\n", nt, bt
            printf "CC_FIRST_LAYER_TEST_BEGIN MATERIAL=%s NOZZLE_TEMP=%.1f BED_TEMP=%.1f NOZZLE=%.3f\n", mat, nt, bt, nozzle
            print "SET_PRINT_STATS_INFO TOTAL_LAYER=1 CURRENT_LAYER=1"
            print "M106 S0"
            print "G90"
            print "M83"
            print "G92 E0"
            print "G1 Z5 F3000"
            printf "G1 X%.3f Y%.3f F%d\n", x0, y0, travel_feed
            printf "G1 Z%.3f F600\n", layer

            for (i = 0; i < lines; i++) {
                y = y0 + i * pitch
                if (i % 2 == 0)
                    printf "G1 X%.3f Y%.3f E%.5f F%d\n", x1, y, line_e, print_feed
                else
                    printf "G1 X%.3f Y%.3f E%.5f F%d\n", x0, y, line_e, print_feed

                if (i < lines - 1) {
                    next_y = y0 + (i + 1) * pitch
                    printf "G1 Y%.3f F1800\n", next_y
                }
            }

            print "G1 E-0.6 F900"
            print "G1 Z5 F1200"
            print "M400"
            print "CC_FIRST_LAYER_TEST_FILE_END"
            print "END_PRINT"
        }
    ' >"$TMP" || {
        rm -f "$TMP"
        exit 2
    }

    mv "$TMP" "$OUT"
    exit 0
}

if [ "${1:-}" = "generate-first-layer" ]; then
    shift
    generate_first_layer "$@"
fi

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
