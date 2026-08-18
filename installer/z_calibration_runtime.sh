#!/bin/sh
# Z Calibration managed runtime + owner RC productization helpers.
#
# install.sh owns the observed Moonraker stop/start lifecycle. This helper
# extends that transaction with the proven pure-Klipper saved+check policy,
# winning _USER_START_PRINT owner patch, and owned saved-variable state.

ZCAL_RC_PREFLIGHT_READY=0
ZCAL_RC_PREFLIGHT_JSON=""

zcal_core_init_paths(){
    ZCAL_CORE_SOURCE="${ZCAL_CORE_SOURCE:-$PLUGIN_DIR/moonraker/components/plugins_ad5x_zcalibration.py}"
    ZCAL_CORE_DEST="${AD5X_ZCAL_CORE_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_zcalibration.py}"
    ZCAL_CORE_HASH_STATE="${ZCAL_CORE_HASH_STATE:-$STATE/zcalibration-runtime.sha256}"

    ZCAL_RC_PRODUCTIZER="${AD5X_ZCAL_PRODUCTIZER:-$PLUGIN_DIR/installer/z_calibration_productization.py}"
    ZCAL_RC_POLICY_SOURCE="${AD5X_ZCAL_POLICY_SOURCE:-$PLUGIN_DIR/z_calibration_rc_policy.cfg}"
    ZCAL_RC_POLICY_DEST="${AD5X_ZCAL_POLICY_DEST:-$GENERATED/zcal_owner_rc.cfg}"
    ZCAL_RC_STATE_DIR="${AD5X_ZCAL_PRODUCT_STATE:-$STATE/zcal-rc-productization}"
    ZCAL_RC_PRINTER_CONFIG="${AD5X_ZCAL_PRINTER_CONFIG:-/opt/config/printer.cfg}"
    if [ -n "${AD5X_ZCAL_VARIABLES_FILE:-}" ]; then
        ZCAL_RC_VARIABLES_FILE="$AD5X_ZCAL_VARIABLES_FILE"
    elif [ -f /opt/config/mod_data/variables.cfg ]; then
        ZCAL_RC_VARIABLES_FILE=/opt/config/mod_data/variables.cfg
    else
        ZCAL_RC_VARIABLES_FILE=/usr/data/config/mod_data/variables.cfg
    fi
}

zcal_rc_functions_only(){
    [ "${AD5X_INSTALLER_FUNCTIONS_ONLY:-0}" = 1 ]
}

zcal_core_source_valid(){
    zcal_core_init_paths
    [ -s "$ZCAL_CORE_SOURCE" ] || return 1
    [ -s "$ZCAL_RC_PRODUCTIZER" ] || return 1
    [ -s "$ZCAL_RC_POLICY_SOURCE" ] || return 1
    [ -d "$MOONRAKER_COMPONENTS_DIR" ] || return 1
    [ "$(grep -Fxc '[gcode_macro _AD5X_Z_SAVED_CHECK_POLICY]' "$ZCAL_RC_POLICY_SOURCE" 2>/dev/null || true)" -eq 1 ] || return 1
    [ "$(grep -Fxc '[gcode_macro _USER_START_PRINT]' "$PLUGIN_DIR/z_calibration.cfg" 2>/dev/null || true)" -eq 0 ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B - "$ZCAL_CORE_SOURCE" "$ZCAL_RC_PRODUCTIZER" <<'PY' >/dev/null 2>&1 || return 1
import ast
import pathlib
import sys
for raw in sys.argv[1:]:
    path = pathlib.Path(raw)
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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

zcal_rc_query_preflight(){
    wget -q -T 5 -O - \
        "$MOONRAKER_HTTP_BASE/printer/objects/query?configfile&save_variables" 2>/dev/null
}

zcal_rc_preflight(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    [ "$ZCAL_RC_PREFLIGHT_READY" -eq 1 ] && return 0

    LIVE="$(zcal_rc_query_preflight)" || return 1
    [ -n "$LIVE" ] || return 1
    PY="$(python_bin)" || return 1
    ZCAL_RC_PREFLIGHT_JSON="$(
        printf '%s' "$LIVE" | "$PY" -B "$ZCAL_RC_PRODUCTIZER" preflight \
            --printer-config "$ZCAL_RC_PRINTER_CONFIG" \
            --policy-source "$ZCAL_RC_POLICY_SOURCE" \
            --policy-dest "$ZCAL_RC_POLICY_DEST" \
            --variables-file "$ZCAL_RC_VARIABLES_FILE" \
            --state-dir "$ZCAL_RC_STATE_DIR" \
            --backups-root "$BACKUPS"
    )" || return 1
    [ -n "$ZCAL_RC_PREFLIGHT_JSON" ] || return 1
    ZCAL_RC_PREFLIGHT_READY=1
}

validate_zcal_core_destination_ownership(){
    zcal_core_destination_owned || fail "неизвестный файл в Z Calibration runtime destination: $ZCAL_CORE_DEST"
    zcal_rc_preflight || fail 'Z Calibration RC productization preflight failed closed'
}

zcal_rc_plan_file(){
    printf '%s/zcal-rc-plan.json\n' "$B"
}

zcal_rc_txn_dir(){
    printf '%s/zcal-rc-transaction\n' "$B"
}

zcal_rc_transaction_snapshot(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    [ "$ZCAL_RC_PREFLIGHT_READY" -eq 1 ] || return 1
    PLAN="$(zcal_rc_plan_file)"
    TXN="$(zcal_rc_txn_dir)"
    if [ ! -f "$PLAN" ]; then
        printf '%s\n' "$ZCAL_RC_PREFLIGHT_JSON" >"$PLAN" || return 1
    fi
    [ -d "$TXN" ] && return 0
    PY="$(python_bin)" || return 1
    "$PY" -B "$ZCAL_RC_PRODUCTIZER" txn-snapshot --plan "$PLAN" --backup "$TXN"
}

zcal_rc_transaction_restore(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    PLAN="$(zcal_rc_plan_file)"
    TXN="$(zcal_rc_txn_dir)"
    [ -f "$PLAN" ] || return 0
    [ -d "$TXN" ] || return 0
    PY="$(python_bin)" || return 1
    "$PY" -B "$ZCAL_RC_PRODUCTIZER" txn-restore --plan "$PLAN" --backup "$TXN"
}

snapshot(){
    FILE="$1"; KEY="$2"
    if [ -e "$FILE" ] || [ -L "$FILE" ]; then
        cp -p "$FILE" "$B/$KEY"
    else
        : >"$B/.absent-$KEY"
    fi
    if [ "$KEY" = plugins.cfg ]; then
        zcal_rc_transaction_snapshot || fail 'не удалось создать Z Calibration transaction snapshot'
    fi
}

restore_snapshot(){
    FILE="$1"; KEY="$2"
    if [ -f "$B/.absent-$KEY" ]; then
        rm -f "$FILE"
    elif [ -e "$B/$KEY" ] || [ -L "$B/$KEY" ]; then
        cp -p "$B/$KEY" "$FILE"
    fi
    if [ "$KEY" = plugins.cfg ]; then
        zcal_rc_transaction_restore || return 1
    fi
}

zcal_rc_policy_include(){
    printf '%s\n' '[include ad5x_custom/generated/zcal_owner_rc.cfg]'
}

zcal_hook_include_ok(){
    [ "$(grep -Fxc '[include plugins/ad5x_custom/z_calibration.cfg]' "$KLIPPER_INCLUDES" 2>/dev/null || true)" -eq 1 ] || return 1
    INC="$(zcal_rc_policy_include)"
    [ "$(grep -Fxc "$INC" "$KLIPPER_INCLUDES" 2>/dev/null || true)" -eq 1 ] || return 1
    [ -s "$ZCAL_RC_POLICY_DEST" ] || return 1
}

zcal_rc_apply(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    PLAN="$(zcal_rc_plan_file)"
    [ -f "$PLAN" ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B "$ZCAL_RC_PRODUCTIZER" apply \
        --plan "$PLAN" \
        --policy-source "$ZCAL_RC_POLICY_SOURCE" >/dev/null || return 1
    INC="$(zcal_rc_policy_include)"
    append_line "$KLIPPER_INCLUDES" "$INC"
    [ "$(grep -Fxc "$INC" "$KLIPPER_INCLUDES" 2>/dev/null || true)" -eq 1 ]
}

zcal_rc_uninstall(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    PY="$(python_bin)" || return 1
    "$PY" -B "$ZCAL_RC_PRODUCTIZER" uninstall \
        --state-dir "$ZCAL_RC_STATE_DIR" \
        --variables-file "$ZCAL_RC_VARIABLES_FILE"
}

zcal_rc_live_verify(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    LIVE="$(
        wget -q -T 5 -O - \
            "$MOONRAKER_HTTP_BASE/printer/objects/query?configfile&save_variables&gcode_macro%20_AD5X_Z_SAVED_CHECK_POLICY" \
            2>/dev/null
    )" || return 1
    [ -n "$LIVE" ] || return 1
    PY="$(python_bin)" || return 1
    printf '%s' "$LIVE" | "$PY" -B "$ZCAL_RC_PRODUCTIZER" verify-live \
        --state-dir "$ZCAL_RC_STATE_DIR" >/dev/null
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
    zcal_rc_apply
}

zcal_core_runtime_matches_source(){
    zcal_core_init_paths
    [ -f "$ZCAL_CORE_DEST" ] || return 1
    [ ! -L "$ZCAL_CORE_DEST" ] || return 1
    [ -f "$ZCAL_CORE_HASH_STATE" ] || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_CORE_SOURCE" 2>/dev/null || true)"
    DEST_HASH="$(sha256_file "$ZCAL_CORE_DEST" 2>/dev/null || true)"
    RECORDED_HASH="$(cat "$ZCAL_CORE_HASH_STATE" 2>/dev/null || true)"
    [ -n "$SOURCE_HASH" ] && [ "$SOURCE_HASH" = "$DEST_HASH" ] && [ "$DEST_HASH" = "$RECORDED_HASH" ] || return 1
    zcal_rc_live_verify
}

zcal_core_uninstall_managed_copy(){
    zcal_core_init_paths
    zcal_rc_uninstall || return 1
    if [ -e "$ZCAL_CORE_DEST" ] || [ -L "$ZCAL_CORE_DEST" ]; then
        zcal_core_destination_owned || return 1
        rm -f "$ZCAL_CORE_DEST"
    fi
    rm -f "$MOONRAKER_COMPONENTS_DIR/__pycache__/plugins_ad5x_zcalibration"*.pyc 2>/dev/null || true
    rm -f "$ZCAL_CORE_HASH_STATE"
}
