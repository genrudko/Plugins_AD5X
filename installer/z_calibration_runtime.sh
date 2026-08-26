#!/bin/sh
# Z Calibration managed runtime + owner RC productization helpers.
#
# install.sh owns the observed Moonraker stop/start lifecycle. This helper
# extends that transaction with the proven pure-Klipper saved+check policy,
# winning _USER_START_PRINT owner patch, owned saved-variable state, and a
# bounded Klipper reload/verification boundary for every lifecycle transition.
#
# Target runtime contract: Flashforge AD5X + Z-Mod chroot. Z-Mod 1.7 uses curl
# (inside chroot normally /usr/bin/curl; stock AD5X fallback lives under
# /usr/prog/curl-7.55.1-https/bin/curl). Do not introduce wget dependencies.

ZCAL_RC_PREFLIGHT_READY=0
ZCAL_RC_PREFLIGHT_JSON=""

ad5x_curl_bin(){
    if [ -n "${AD5X_CURL_BIN:-}" ]; then
        [ -x "$AD5X_CURL_BIN" ] || return 1
        printf '%s\n' "$AD5X_CURL_BIN"
    elif command -v curl >/dev/null 2>&1; then
        command -v curl
    elif [ -x /usr/bin/curl ]; then
        printf '%s\n' /usr/bin/curl
    elif [ -x /usr/prog/curl-7.55.1-https/bin/curl ]; then
        printf '%s\n' /usr/prog/curl-7.55.1-https/bin/curl
    else
        return 1
    fi
}

ad5x_http_get(){
    TIMEOUT="$1"; URL="$2"
    CURL_BIN="$(ad5x_curl_bin)" || return 1
    "$CURL_BIN" -f -sS -m "$TIMEOUT" "$URL"
}

ad5x_http_post(){
    TIMEOUT="$1"; URL="$2"
    CURL_BIN="$(ad5x_curl_bin)" || return 1
    "$CURL_BIN" -f -sS -m "$TIMEOUT" -X POST \
        -H 'Content-Type: application/json' "$URL"
}

zcal_core_init_paths(){
    ZCAL_CORE_SOURCE="${ZCAL_CORE_SOURCE:-$PLUGIN_DIR/moonraker/components/plugins_ad5x_zcalibration.py}"
    ZCAL_CORE_DEST="${AD5X_ZCAL_CORE_DEST:-$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_zcalibration.py}"
    ZCAL_CORE_HASH_STATE="${ZCAL_CORE_HASH_STATE:-$STATE/zcalibration-runtime.sha256}"
    ZCAL_MESH_ANCHOR_SOURCE="${AD5X_ZCAL_MESH_ANCHOR_SOURCE:-$PLUGIN_DIR/klipper/extras/ad5x_z_mesh_anchor.py}"
    ZCAL_MESH_ANCHOR_DEST="${AD5X_ZCAL_MESH_ANCHOR_DEST:-/opt/config/base/klipper/klippy/extras/ad5x_z_mesh_anchor.py}"
    ZCAL_KLIPPER_EXTRAS_DIR="${AD5X_ZCAL_KLIPPER_EXTRAS_DIR:-${ZCAL_MESH_ANCHOR_DEST%/*}}"
    ZCAL_MESH_ANCHOR_HASH_STATE="${AD5X_ZCAL_MESH_ANCHOR_HASH_STATE:-$STATE/zcal-mesh-anchor-runtime.sha256}"

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
    [ -s "$ZCAL_MESH_ANCHOR_SOURCE" ] || return 1
    [ -s "$ZCAL_RC_PRODUCTIZER" ] || return 1
    [ -s "$ZCAL_RC_POLICY_SOURCE" ] || return 1
    [ -d "$MOONRAKER_COMPONENTS_DIR" ] || return 1
    [ -d "$ZCAL_KLIPPER_EXTRAS_DIR" ] || return 1
    [ "$(grep -Fxc '[gcode_macro _AD5X_Z_SAVED_CHECK_POLICY]' "$ZCAL_RC_POLICY_SOURCE" 2>/dev/null || true)" -eq 1 ] || return 1
    [ "$(grep -Fxc '[gcode_macro _ADZ_PRIME_GATE]' "$ZCAL_RC_POLICY_SOURCE" 2>/dev/null || true)" -eq 1 ] || return 1
    [ "$(grep -Fxc '[gcode_macro _USER_START_PRINT]' "$PLUGIN_DIR/z_calibration.cfg" 2>/dev/null || true)" -eq 0 ] || return 1
    [ "$(grep -Fxc '[ad5x_z_mesh_anchor]' "$ZCAL_RC_POLICY_SOURCE" 2>/dev/null || true)" -eq 1 ] || return 1
    [ "$(grep -Fxc '[ad5x_z_mesh_anchor]' "$PLUGIN_DIR/z_calibration.cfg" 2>/dev/null || true)" -eq 0 ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B - "$ZCAL_CORE_SOURCE" "$ZCAL_MESH_ANCHOR_SOURCE" "$ZCAL_RC_PRODUCTIZER" <<'PY' >/dev/null 2>&1 || return 1
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

zcal_mesh_anchor_destination_owned(){
    zcal_core_init_paths
    [ -e "$ZCAL_MESH_ANCHOR_DEST" ] || [ -L "$ZCAL_MESH_ANCHOR_DEST" ] || return 0
    [ -f "$ZCAL_MESH_ANCHOR_DEST" ] || return 1
    [ ! -L "$ZCAL_MESH_ANCHOR_DEST" ] || return 1
    DEST_HASH="$(sha256_file "$ZCAL_MESH_ANCHOR_DEST" 2>/dev/null || true)"
    [ -n "$DEST_HASH" ] || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_MESH_ANCHOR_SOURCE" 2>/dev/null || true)"
    if [ -f "$ZCAL_MESH_ANCHOR_HASH_STATE" ] && [ "$(cat "$ZCAL_MESH_ANCHOR_HASH_STATE" 2>/dev/null || true)" = "$DEST_HASH" ]; then
        return 0
    fi
    [ -n "$SOURCE_HASH" ] && [ "$DEST_HASH" = "$SOURCE_HASH" ]
}

zcal_rc_query_preflight(){
    ad5x_http_get 5 \
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
    zcal_mesh_anchor_destination_owned || fail "неизвестный файл в Z Calibration mesh-anchor destination: $ZCAL_MESH_ANCHOR_DEST"
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

    # A manually deployed accepted RC may predate the canonical ownership
    # manifest. Adopt it only through the already-proven preflight/legacy
    # backup path, then immediately restore the recorded baseline.
    if [ ! -f "$ZCAL_RC_STATE_DIR/manifest.json" ]; then
        PLAN="$(zcal_rc_plan_file)"
        [ -f "$PLAN" ] || return 1
        "$PY" -B "$ZCAL_RC_PRODUCTIZER" apply \
            --plan "$PLAN" \
            --policy-source "$ZCAL_RC_POLICY_SOURCE" >/dev/null || return 1
    fi

    "$PY" -B "$ZCAL_RC_PRODUCTIZER" uninstall \
        --state-dir "$ZCAL_RC_STATE_DIR" \
        --variables-file "$ZCAL_RC_VARIABLES_FILE" \
        --keep-state
}

zcal_rc_query_live_policy(){
    ad5x_http_get 5 \
        "$MOONRAKER_HTTP_BASE/printer/objects/query?configfile&save_variables&gcode_macro%20_AD5X_Z_SAVED_CHECK_POLICY&gcode_macro%20_ADZ_SAVED_CHECK_POLICY&gcode_macro%20_ADZ_MEASUREMENT_POLICY&gcode_macro%20LOAD_CELL_TARE&ad5x_z_mesh_anchor" \
        2>/dev/null
}

zcal_rc_live_verify(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    PY="$(python_bin)" || return 1
    LIMIT="${AD5X_ZCAL_VERIFY_TIMEOUT:-30}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        LIVE="$(zcal_rc_query_live_policy 2>/dev/null || true)"
        if [ -n "$LIVE" ] && printf '%s' "$LIVE" | "$PY" -B "$ZCAL_RC_PRODUCTIZER" verify-live \
            --state-dir "$ZCAL_RC_STATE_DIR" >/dev/null 2>&1; then
            EXPECTED_ANCHOR_HASH="$(sha256_file "$ZCAL_MESH_ANCHOR_SOURCE" 2>/dev/null || true)"
            if [ -n "$EXPECTED_ANCHOR_HASH" ] && printf '%s' "$LIVE" | "$PY" -B -c '
import json, sys
expected = sys.argv[1]
data = json.load(sys.stdin)
loaded = data.get("result", {}).get("status", {}).get("ad5x_z_mesh_anchor", {}).get("loaded_source_sha256")
raise SystemExit(0 if isinstance(loaded, str) and loaded == expected else 1)
' "$EXPECTED_ANCHOR_HASH"; then
                return 0
            fi
        fi
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}

zcal_rc_live_verify_uninstalled(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    PY="$(python_bin)" || return 1
    LIMIT="${AD5X_ZCAL_VERIFY_TIMEOUT:-30}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        LIVE="$(zcal_rc_query_live_policy 2>/dev/null || true)"
        if [ -n "$LIVE" ] && printf '%s' "$LIVE" | "$PY" -B "$ZCAL_RC_PRODUCTIZER" verify-uninstalled \
            --state-dir "$ZCAL_RC_STATE_DIR" >/dev/null 2>&1; then
            return 0
        fi
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}

zcal_rc_finalize_uninstall(){
    zcal_core_init_paths
    zcal_rc_functions_only && return 0
    PY="$(python_bin)" || return 1
    "$PY" -B "$ZCAL_RC_PRODUCTIZER" finalize-uninstall \
        --state-dir "$ZCAL_RC_STATE_DIR"
}

zcal_rc_wait_klippy_connected(){
    LIMIT="${1:-$MOONRAKER_READY_TIMEOUT}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        INFO="$(moonraker_server_info 2>/dev/null || true)"
        COMPACT="$(printf '%s' "$INFO" | tr -d '[:space:]')"
        case "$COMPACT" in
            *'"klippy_connected":true'*) return 0 ;;
        esac
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}

zcal_rc_firmware_restart(){
    zcal_rc_functions_only && return 0
    zcal_rc_wait_klippy_connected || return 1
    ad5x_http_post 10 \
        "$MOONRAKER_HTTP_BASE/printer/firmware_restart" >/dev/null 2>&1 || return 1
    # Moonraker may briefly expose the pre-restart ready state after the POST
    # returns. Do not accept that stale sample as proof that the new Klipper
    # config loaded. Give Klippy time to enter its restart transition, then
    # require ready and confirm it once more after a short stability interval.
    sleep 2
    wait_klippy_ready || return 1
    sleep 1
    INFO="$(moonraker_server_info 2>/dev/null || true)"
    [ -n "$INFO" ] && klippy_ready_from_json "$INFO"
}

zcal_rc_klippy_host_restart(){
    zcal_rc_functions_only && return 0
    zcal_rc_wait_klippy_connected || return 1
    ZREMOTE="${AD5X_ZREMOTE_BIN:-/opt/config/mod/.shell/zremote.sh}"
    [ -x "$ZREMOTE" ] || return 1
    "$ZREMOTE" /bin/sh -c '
set -eu
PID_FILE=/run/klipper.pid
START=/usr/data/config/mod/.shell/klipper13.sh
[ -x "$START" ] || exit 71
[ -r "$PID_FILE" ] || exit 72
PID="$(cat "$PID_FILE" 2>/dev/null || true)"
[ -n "$PID" ] || exit 73
kill "$PID" 2>/dev/null || exit 74
COUNT=0
while kill -0 "$PID" 2>/dev/null; do
    COUNT=$((COUNT + 1))
    [ "$COUNT" -lt 15 ] || exit 75
    sleep 1
done
rm -f "$PID_FILE"
"$START"
' >/dev/null 2>&1 || return 1
    # A new OS process must reconnect to Moonraker.  Only that boundary clears
    # importlib/sys.modules and proves a changed Klipper extra is executable.
    wait_klippy_ready || return 1
    sleep 1
    INFO="$(moonraker_server_info 2>/dev/null || true)"
    [ -n "$INFO" ] && klippy_ready_from_json "$INFO"
}

# Override the generic transition only after this helper is sourced. A
# Moonraker restart alone does not reload Klipper config. Every productization
# mutation therefore crosses a bounded Klippy host-process restart boundary
# before the transition's live verifier may succeed.
run_moonraker_transition(){
    TRANSITION_FN="$1"
    VERIFY_FN="$2"
    if [ "$(moonraker_process_count)" -gt 0 ]; then
        MOONRAKER_WAS_RUNNING=1
        MOONRAKER_TRANSITION_STARTED=1
        stop_moonraker || return 1
    else
        MOONRAKER_TRANSITION_STARTED=1
    fi
    wait_moonraker_stopped || return 1
    "$TRANSITION_FN" || return 1
    start_moonraker || return 1
    wait_moonraker_http || return 1
    zcal_rc_klippy_host_restart || return 1
    "$VERIFY_FN"
}

# Rollback must restore not just bytes on disk but the effective Klipper
# config. Reload the restored state through the same observed boundary.
restore_moonraker_after_rollback(){
    [ "$MOONRAKER_TRANSITION_STARTED" -eq 1 ] || return 0
    if [ "$(moonraker_process_count 2>/dev/null || echo 0)" -gt 0 ]; then
        stop_moonraker >/dev/null 2>&1 || true
        wait_moonraker_stopped "$MOONRAKER_STOP_TIMEOUT" >/dev/null 2>&1 || true
    fi
    [ "$MOONRAKER_WAS_RUNNING" -eq 1 ] || return 0
    start_moonraker >/dev/null 2>&1 || return 1
    wait_moonraker_http "$MOONRAKER_READY_TIMEOUT" >/dev/null 2>&1 || return 1
    zcal_rc_klippy_host_restart >/dev/null 2>&1 || return 1
    wait_klippy_ready "$MOONRAKER_READY_TIMEOUT" >/dev/null 2>&1
}

# Uninstall only becomes successful after the original hook/settings are the
# effective runtime state and the RC policy macro is gone. Keep the manifest
# until that check passes so rollback still has exact provenance.
verify_backend_absent(){
    [ "$(backend_component_state 2>/dev/null || true)" = absent ] || return 1
    zcal_rc_live_verify_uninstalled || return 1
    zcal_rc_finalize_uninstall
}

zcal_mesh_anchor_deploy_managed_copy(){
    zcal_core_init_paths
    zcal_mesh_anchor_destination_owned || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_MESH_ANCHOR_SOURCE")"
    TMP="$ZCAL_KLIPPER_EXTRAS_DIR/.ad5x_z_mesh_anchor.py.tmp.$$"
    rm -f "$TMP"
    cp "$ZCAL_MESH_ANCHOR_SOURCE" "$TMP" || { rm -f "$TMP"; return 1; }
    chmod 0644 "$TMP" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$TMP")" = "$SOURCE_HASH" ] || { rm -f "$TMP"; return 1; }
    mv -f "$TMP" "$ZCAL_MESH_ANCHOR_DEST" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$ZCAL_MESH_ANCHOR_DEST")" = "$SOURCE_HASH" ] || return 1
    rm -f "$ZCAL_KLIPPER_EXTRAS_DIR/__pycache__/ad5x_z_mesh_anchor"*.pyc 2>/dev/null || true
    HASH_TMP="$ZCAL_MESH_ANCHOR_HASH_STATE.tmp.$$"
    printf '%s\n' "$SOURCE_HASH" >"$HASH_TMP"
    mv -f "$HASH_TMP" "$ZCAL_MESH_ANCHOR_HASH_STATE"
}

zcal_mesh_anchor_runtime_matches_source(){
    zcal_core_init_paths
    [ -f "$ZCAL_MESH_ANCHOR_DEST" ] || return 1
    [ ! -L "$ZCAL_MESH_ANCHOR_DEST" ] || return 1
    [ -f "$ZCAL_MESH_ANCHOR_HASH_STATE" ] || return 1
    SOURCE_HASH="$(sha256_file "$ZCAL_MESH_ANCHOR_SOURCE" 2>/dev/null || true)"
    DEST_HASH="$(sha256_file "$ZCAL_MESH_ANCHOR_DEST" 2>/dev/null || true)"
    RECORDED_HASH="$(cat "$ZCAL_MESH_ANCHOR_HASH_STATE" 2>/dev/null || true)"
    [ -n "$SOURCE_HASH" ] && [ "$SOURCE_HASH" = "$DEST_HASH" ] && [ "$DEST_HASH" = "$RECORDED_HASH" ]
}

zcal_mesh_anchor_uninstall_managed_copy(){
    zcal_core_init_paths
    if [ -e "$ZCAL_MESH_ANCHOR_DEST" ] || [ -L "$ZCAL_MESH_ANCHOR_DEST" ]; then
        zcal_mesh_anchor_destination_owned || return 1
        rm -f "$ZCAL_MESH_ANCHOR_DEST"
    fi
    rm -f "$ZCAL_KLIPPER_EXTRAS_DIR/__pycache__/ad5x_z_mesh_anchor"*.pyc 2>/dev/null || true
    rm -f "$ZCAL_MESH_ANCHOR_HASH_STATE"
}

zcal_core_deploy_managed_copy(){
    zcal_core_init_paths
    zcal_core_source_valid || return 1
    zcal_core_destination_owned || return 1
    zcal_mesh_anchor_destination_owned || return 1
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
    zcal_mesh_anchor_deploy_managed_copy || return 1
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
    zcal_mesh_anchor_runtime_matches_source || return 1
    zcal_rc_live_verify
}

zcal_core_uninstall_managed_copy(){
    zcal_core_init_paths
    zcal_rc_uninstall || return 1
    zcal_mesh_anchor_uninstall_managed_copy || return 1
    if [ -e "$ZCAL_CORE_DEST" ] || [ -L "$ZCAL_CORE_DEST" ]; then
        zcal_core_destination_owned || return 1
        rm -f "$ZCAL_CORE_DEST"
    fi
    rm -f "$MOONRAKER_COMPONENTS_DIR/__pycache__/plugins_ad5x_zcalibration"*.pyc 2>/dev/null || true
    rm -f "$ZCAL_CORE_HASH_STATE"
}
