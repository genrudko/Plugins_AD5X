#!/bin/sh
# Z Calibration managed Moonraker runtime artifact helpers.
#
# This file is sourced by install.sh only after its generic paths/helpers have
# been defined.  It deliberately contains no service control and no printer
# mutation; install.sh owns observed-stop/start/rollback orchestration.

zcal_core_init_paths(){
    ZCAL_CORE_SOURCE="${ZCAL_CORE_SOURCE:-$PLUGIN_DIR/moonraker/components/plugins_ad5x_zcalibration.py}"
    ZCAL_CORE_DEST="${AD5X_ZCAL_CORE_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_zcalibration.py}"
    ZCAL_CORE_HASH_STATE="${ZCAL_CORE_HASH_STATE:-$STATE/zcalibration-runtime.sha256}"
}

zcal_core_source_valid(){
    zcal_core_init_paths
    [ -s "$ZCAL_CORE_SOURCE" ] || return 1
    [ -d "$MOONRAKER_COMPONENTS_DIR" ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B - "$ZCAL_CORE_SOURCE" <<'PY' >/dev/null 2>&1 || return 1
import ast
import pathlib
import sys
ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"), filename=sys.argv[1])
PY
}

zcal_core_destination_owned(){
    zcal_core_init_paths
    [ -e "$ZCAL_CORE_DEST" ] || [ -L "$ZCAL_CORE_DEST" ] || return 0
    [ -f "$ZCAL_CORE_DEST" ] || return 1
    [ ! -L "$ZCAL_CORE_DEST" ] || return 1
    DEST_HASH="$(sha256_file "$ZCAL_CORE_DEST" 2>/dev/null || true)"
    [ -n "$DEST_HASH" ] || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_CORE_SOURCE" 2>/dev/null || true)"
    if [ -f "$ZCAL_CORE_HASH_STATE" ] && [ "$(cat "$ZCAL_CORE_HASH_STATE" 2>/dev/null || true)" = "$DEST_HASH" ]; then
        return 0
    fi
    [ -n "$SOURCE_HASH" ] && [ "$DEST_HASH" = "$SOURCE_HASH" ]
}

validate_zcal_core_destination_ownership(){
    zcal_core_destination_owned || fail "неизвестный файл в Z Calibration runtime destination: $ZCAL_CORE_DEST"
}

zcal_core_deploy_managed_copy(){
    zcal_core_init_paths
    zcal_core_source_valid || return 1
    zcal_core_destination_owned || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_CORE_SOURCE")"
    TMP="$MOONRAKER_COMPONENTS_DIR/.plugins_ad5x_zcalibration.py.tmp.$$"
    rm -f "$TMP"
    cp "$ZCAL_CORE_SOURCE" "$TMP" || { rm -f "$TMP"; return 1; }
    chmod 0644 "$TMP" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$TMP")" = "$SOURCE_HASH" ] || { rm -f "$TMP"; return 1; }
    mv -f "$TMP" "$ZCAL_CORE_DEST" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$ZCAL_CORE_DEST")" = "$SOURCE_HASH" ] || return 1
    HASH_TMP="$ZCAL_CORE_HASH_STATE.tmp.$$"
    printf '%s\n' "$SOURCE_HASH" >"$HASH_TMP"
    mv -f "$HASH_TMP" "$ZCAL_CORE_HASH_STATE"
}

zcal_core_runtime_matches_source(){
    zcal_core_init_paths
    [ -f "$ZCAL_CORE_DEST" ] || return 1
    [ ! -L "$ZCAL_CORE_DEST" ] || return 1
    [ -f "$ZCAL_CORE_HASH_STATE" ] || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_CORE_SOURCE" 2>/dev/null || true)"
    DEST_HASH="$(sha256_file "$ZCAL_CORE_DEST" 2>/dev/null || true)"
    RECORDED_HASH="$(cat "$ZCAL_CORE_HASH_STATE" 2>/dev/null || true)"
    [ -n "$SOURCE_HASH" ] && [ "$SOURCE_HASH" = "$DEST_HASH" ] && [ "$DEST_HASH" = "$RECORDED_HASH" ]
}

zcal_core_uninstall_managed_copy(){
    zcal_core_init_paths
    if [ -e "$ZCAL_CORE_DEST" ] || [ -L "$ZCAL_CORE_DEST" ]; then
        zcal_core_destination_owned || return 1
        rm -f "$ZCAL_CORE_DEST"
    fi
    rm -f "$MOONRAKER_COMPONENTS_DIR/__pycache__/plugins_ad5x_zcalibration"*.pyc 2>/dev/null || true
    rm -f "$ZCAL_CORE_HASH_STATE"
}
