#!/bin/sh
# Canonical pure-Klipper RC Productization lifecycle for Z Calibration.
#
# This entrypoint deliberately performs no Git operation. It may be executed
# from an exact-commit staging directory while the live ad5x_custom worktree
# remains on an unrelated feature branch (for example IFS work). The shared
# productizer/runtime helper owns hook/policy/settings semantics; this script
# owns the bounded filesystem transaction + Klipper reload boundary.
#
# Target runtime is the Z-Mod chroot on Flashforge AD5X. HTTP access uses the
# curl contract from Z-Mod itself; wget is intentionally not a dependency.
set -eu

SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_DIR="${AD5X_ZCAL_SOURCE_DIR:-$(CDPATH= cd -- "$SELF_DIR/.." && pwd)}"
STATE_ROOT="${AD5X_STATE_DIR:-/opt/config/mod_data/ad5x_custom}"
GENERATED="$STATE_ROOT/generated"
STATE="$STATE_ROOT/state"
BACKUPS="$STATE_ROOT/backups"
LOG_DIR="$STATE_ROOT/log"
KLIPPER_INCLUDES="${AD5X_KLIPPER_INCLUDES:-/opt/config/mod_data/plugins.cfg}"
MOONRAKER_HTTP_BASE="${AD5X_MOONRAKER_HTTP_BASE:-http://127.0.0.1:7125}"
MOONRAKER_READY_TIMEOUT="${AD5X_MOONRAKER_READY_TIMEOUT:-90}"
MOONRAKER_STOP_TIMEOUT="${AD5X_MOONRAKER_STOP_TIMEOUT:-30}"
MOONRAKER_COMPONENTS_DIR="${AD5X_MOONRAKER_COMPONENTS_DIR:-/opt/config/base/moonraker/components}"
PLUGIN_DIR="$SOURCE_DIR"
MODE="${1:-}"
B=""
MOONRAKER_WAS_RUNNING=0
MOONRAKER_TRANSITION_STARTED=0
POLICY_INCLUDE='[include ad5x_custom/generated/zcal_owner_rc.cfg]'
ROLLBACK_STATE_DIR="$STATE/zcal-rc-rollback"
ROLLBACK_POINTER="$ROLLBACK_STATE_DIR/previous-successful-backup"

case "$MODE" in
    install|update|repair|rollback|uninstall|status) ;;
    *)
        echo "usage: $0 {install|update|repair|rollback|uninstall|status}" >&2
        exit 2
        ;;
esac

fail(){ echo "ОШИБКА: $*" >&2; exit 1; }
python_bin(){
    if [ -n "${AD5X_PYTHON_BIN:-}" ] && [ -x "$AD5X_PYTHON_BIN" ]; then
        echo "$AD5X_PYTHON_BIN"
    elif command -v python3 >/dev/null 2>&1; then
        command -v python3
    elif [ -x /root/moonraker-env/bin/python3 ]; then
        echo /root/moonraker-env/bin/python3
    else
        return 1
    fi
}
sha256_file(){ sha256sum "$1" | awk '{print $1}'; }
append_line(){
    F="$1"; L="$2"
    [ -f "$F" ] || : >"$F"
    grep -Fqx "$L" "$F" 2>/dev/null || printf '%s\n' "$L" >>"$F"
}
remove_exact_line(){
    F="$1"; L="$2"
    [ -f "$F" ] || return 0
    awk -v line="$L" '$0 != line { print }' "$F" >"$F.tmp"
    mv "$F.tmp" "$F"
}
moonraker_server_info(){ ad5x_http_get 3 "$MOONRAKER_HTTP_BASE/server/info" 2>/dev/null; }
klippy_ready_from_json(){
    COMPACT="$(printf '%s' "$1" | tr -d '[:space:]')"
    case "$COMPACT" in *'"klippy_connected":true'*) : ;; *) return 1 ;; esac
    case "$COMPACT" in *'"klippy_state":"ready"'*) return 0 ;; *) return 1 ;; esac
}
wait_klippy_ready(){
    LIMIT="${1:-$MOONRAKER_READY_TIMEOUT}"
    COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        INFO="$(moonraker_server_info 2>/dev/null || true)"
        [ -n "$INFO" ] && klippy_ready_from_json "$INFO" && return 0
        COUNT=$((COUNT + 1))
        sleep 1
    done
    return 1
}
recover_shutdown_klippy(){
    INFO="$(moonraker_server_info 2>/dev/null || true)"
    [ -n "$INFO" ] || fail 'не удалось прочитать Moonraker server/info перед idle preflight'
    COMPACT="$(printf '%s' "$INFO" | tr -d '[:space:]')"
    case "$COMPACT" in
        *'"klippy_connected":true'*'"klippy_state":"shutdown"'*)
            echo '[INFO] Klippy shutdown detected; restarting host process before idle preflight'
            zcal_rc_klippy_host_restart || fail 'не удалось восстановить Klippy из shutdown перед idle preflight'
            ;;
    esac
}

check_idle(){
    STATE_JSON="$(ad5x_http_get 3 "$MOONRAKER_HTTP_BASE/printer/objects/query?print_stats" 2>/dev/null)" \
        || fail 'не удалось подтвердить idle state: Moonraker print_stats недоступен'
    PY="$(python_bin)" || fail 'Python недоступен'
    PRINT_STATE="$(printf '%s' "$STATE_JSON" | "$PY" -B -c '
import json, sys
try:
    data=json.load(sys.stdin)
    state=data["result"]["status"]["print_stats"]["state"]
except (json.JSONDecodeError, KeyError, TypeError):
    raise SystemExit(1)
if not isinstance(state, str) or not state:
    raise SystemExit(1)
sys.stdout.write(state)
')" || fail 'невалидный Moonraker print_stats response'
    case "$PRINT_STATE" in
        standby|complete|error|cancelled) return 0 ;;
        printing|paused) fail 'принтер сейчас печатает или стоит на паузе' ;;
        *) fail "неизвестное print_stats.state=$PRINT_STATE" ;;
    esac
}

mkdir -p "$GENERATED" "$STATE" "$BACKUPS" "$LOG_DIR"
[ -s "$SOURCE_DIR/installer/z_calibration_runtime.sh" ] || fail 'runtime helper отсутствует в source staging'
[ -s "$SOURCE_DIR/installer/z_calibration_productization.py" ] || fail 'productizer отсутствует в source staging'
[ -s "$SOURCE_DIR/z_calibration_rc_policy.cfg" ] || fail 'canonical RC policy отсутствует в source staging'
. "$SOURCE_DIR/installer/z_calibration_runtime.sh"
zcal_core_init_paths
[ -s "$ZCAL_MESH_ANCHOR_SOURCE" ] || fail 'Z Calibration mesh-anchor source отсутствует в source staging'
[ -d "$ZCAL_KLIPPER_EXTRAS_DIR" ] || fail 'Klipper extras directory недоступен'
zcal_mesh_anchor_destination_owned || fail "неизвестный файл в Z Calibration mesh-anchor destination: $ZCAL_MESH_ANCHOR_DEST"

include_count(){ grep -Fxc "$POLICY_INCLUDE" "$KLIPPER_INCLUDES" 2>/dev/null || true; }
plan_baseline_source(){
    PY="$(python_bin)" || return 1
    "$PY" -B - "$(zcal_rc_plan_file)" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    print(json.load(f).get("baseline_source", ""))
PY
}
prepare_include_provenance(){
    COUNT="$(include_count)"
    [ "$COUNT" -le 1 ] || fail 'duplicate generated RC policy include'
    if [ -f "$ZCAL_RC_STATE_DIR/manifest.json" ]; then
        [ -f "$ZCAL_RC_STATE_DIR/include-state" ] \
            || fail 'Z Calibration ownership manifest exists without include provenance'
        return 0
    fi
    BASELINE="$(plan_baseline_source)" || fail 'не удалось прочитать productization plan'
    case "$BASELINE" in
        legacy_backup) ORIGINAL=0 ;;
        current) ORIGINAL="$COUNT" ;;
        *) fail "неожиданный baseline_source=$BASELINE" ;;
    esac
    printf 'original_present=%s\n' "$ORIGINAL" >"$B/include-state.pending"
}
commit_include_provenance(){
    [ -f "$ZCAL_RC_STATE_DIR/include-state" ] && return 0
    [ -f "$B/include-state.pending" ] || return 1
    cp -p "$B/include-state.pending" "$ZCAL_RC_STATE_DIR/include-state"
}
restore_owned_include_state(){
    [ -f "$ZCAL_RC_STATE_DIR/include-state" ] || return 1
    case "$(cat "$ZCAL_RC_STATE_DIR/include-state")" in
        original_present=0) remove_exact_line "$KLIPPER_INCLUDES" "$POLICY_INCLUDE" ;;
        original_present=1) append_line "$KLIPPER_INCLUDES" "$POLICY_INCLUDE" ;;
        *) return 1 ;;
    esac
}

plan_allows_parked_policy_refresh(){
    PY="$(python_bin)" || return 1
    "$PY" -B - "$(zcal_rc_plan_file)" "$ZCAL_RC_STATE_DIR/manifest.json" "$ZCAL_RC_POLICY_DEST" <<'PY'
import json, os, sys
plan=json.load(open(sys.argv[1], encoding="utf-8"))
manifest=json.load(open(sys.argv[2], encoding="utf-8"))
if plan.get("baseline_source") != "manifest": raise SystemExit(1)
if plan.get("effective_commands") not in ([], ["CC_APPLY_PROFILE"]): raise SystemExit(1)
if os.path.abspath(str(manifest.get("policy_dest", ""))) != os.path.abspath(sys.argv[3]): raise SystemExit(1)
PY
}
policy_macro_loaded(){
    LIVE="$(zcal_rc_query_preflight 2>/dev/null)" || return 2
    PY="$(python_bin)" || return 2
    printf '%s' "$LIVE" | "$PY" -B -c 'import json,sys; d=json.load(sys.stdin); s=d["result"]["status"]["configfile"]["settings"]; keys={str(k).strip().lower() for k in s}; raise SystemExit(0 if keys & {"gcode_macro _adz_saved_check_policy", "gcode_macro _ad5x_z_saved_check_policy"} else 1)' || return $?
}
manifest_policy_hash(){
    PY="$(python_bin)" || return 1
    "$PY" -B - "$ZCAL_RC_STATE_DIR/manifest.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1], encoding="utf-8")).get("policy_sha256")
if not isinstance(v,str) or len(v)!=64: raise SystemExit(1)
print(v)
PY
}
prepare_parked_policy_refresh(){
    [ "$MODE" = update ] || return 0
    [ "$(cat "$B/effective-state" 2>/dev/null || true)" = 'active=0' ] || return 0
    [ "$(include_count)" -eq 0 ] || return 0
    [ -f "$ZCAL_RC_STATE_DIR/manifest.json" ] || return 0
    [ -e "$ZCAL_RC_POLICY_DEST" ] || return 0
    [ -f "$ZCAL_RC_POLICY_DEST" ] && [ ! -L "$ZCAL_RC_POLICY_DEST" ] || fail 'parked RC policy destination is not a regular owned file'
    plan_allows_parked_policy_refresh || fail 'parked RC policy refresh ownership cannot be proven'
    if policy_macro_loaded; then RC=0; else RC=$?; fi
    case "$RC" in 0) fail 'parked RC policy macro is still loaded' ;; 1) : ;; *) fail 'could not prove parked RC policy macro is inactive' ;; esac
    CUR="$(sha256_file "$ZCAL_RC_POLICY_DEST")"
    OLD="$(manifest_policy_hash)" || fail 'owned manifest policy hash is invalid'
    NEW="$(sha256_file "$ZCAL_RC_POLICY_SOURCE")"
    [ "$CUR" = "$OLD" ] || [ "$CUR" = "$NEW" ] || {
        echo "[INFO] parked inactive RC policy drift detected: $CUR"
        echo '[INFO] preserving it in the transaction snapshot and refreshing the owned generated policy.'
        rm -f "$ZCAL_RC_POLICY_DEST" || fail 'failed to stage parked RC policy refresh'
    }
}

rollback_target(){
    [ -f "$ROLLBACK_POINTER" ] || fail 'previous successful Z Calibration version is not recorded'
    TARGET="$(cat "$ROLLBACK_POINTER")"
    case "$TARGET" in
        "$BACKUPS"/zcal-productization-update-*|"$BACKUPS"/zcal-productization-rollback-*) ;;
        *) fail 'rollback pointer is outside managed version backups' ;;
    esac
    [ -d "$TARGET/zcal-rc-transaction" ] || fail 'rollback transaction snapshot is missing'
    [ -f "$TARGET/zcal-rc-plan.json" ] || fail 'rollback plan is missing'
    [ -f "$TARGET/plugins.cfg" ] || [ -f "$TARGET/.absent-plugins.cfg" ] || fail 'rollback plugins.cfg snapshot is missing'
    [ -f "$TARGET/zcal-mesh-anchor.py" ] || [ -f "$TARGET/.absent-zcal-mesh-anchor.py" ] || fail 'rollback mesh-anchor runtime snapshot is missing'
    [ -f "$TARGET/zcal-mesh-anchor.sha256" ] || [ -f "$TARGET/.absent-zcal-mesh-anchor.sha256" ] || fail 'rollback mesh-anchor hash snapshot is missing'
    [ -f "$TARGET/effective-state" ] || fail 'rollback effective-state marker is missing'
    case "$(cat "$TARGET/effective-state")" in active=0|active=1) ;; *) fail 'invalid rollback effective-state marker' ;; esac
    printf '%s\n' "$TARGET"
}
record_rollback_target(){
    TARGET="$1"
    mkdir -p "$ROLLBACK_STATE_DIR"
    TMP="$ROLLBACK_POINTER.tmp.$$"
    printf '%s\n' "$TARGET" >"$TMP"
    mv -f "$TMP" "$ROLLBACK_POINTER"
}
restore_version_snapshot(){
    TARGET="$1"
    CURRENT_B="$B"
    B="$TARGET"
    restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg || { B="$CURRENT_B"; return 1; }
    restore_snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py || { B="$CURRENT_B"; return 1; }
    restore_snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256 || { B="$CURRENT_B"; return 1; }
    rm -f "$ZCAL_KLIPPER_EXTRAS_DIR/__pycache__/ad5x_z_mesh_anchor"*.pyc 2>/dev/null || true
    B="$CURRENT_B"
}

managed_active_preflight(){
    [ "$(include_count)" -eq 1 ] || return 1
    [ -f "$ZCAL_RC_STATE_DIR/manifest.json" ] || return 1
    [ -n "$ZCAL_RC_PREFLIGHT_JSON" ] || return 1
    PY="$(python_bin)" || return 1
    printf '%s' "$ZCAL_RC_PREFLIGHT_JSON" | "$PY" -B -c '
import json, sys
try:
    p=json.load(sys.stdin)
except (json.JSONDecodeError, TypeError):
    raise SystemExit(1)
if p.get("baseline_source") != "manifest":
    raise SystemExit(1)
cmds=p.get("effective_commands")
allowed=(
    ["_ADZ_SAVED_CHECK_POLICY"],
    ["CC_APPLY_PROFILE", "_ADZ_SAVED_CHECK_POLICY"],
    ["_AD5X_Z_SAVED_CHECK_POLICY"],
    ["CC_APPLY_PROFILE", "_AD5X_Z_SAVED_CHECK_POLICY"],
)
raise SystemExit(0 if cmds in allowed else 1)
'
}

verify_restored_managed_active(){
    wait_klippy_ready || return 1
    ZCAL_RC_PREFLIGHT_READY=0
    ZCAL_RC_PREFLIGHT_JSON=""
    zcal_rc_preflight || return 1
    managed_active_preflight
}

operation_prepare(){
    recover_shutdown_klippy
    check_idle
    zcal_rc_preflight || fail 'RC productization preflight failed closed'
    STAMP="$(date +%Y%m%d-%H%M%S)"
    B="$BACKUPS/zcal-productization-$MODE-$STAMP-$$"
    mkdir -p "$B"
    snapshot "$KLIPPER_INCLUDES" plugins.cfg
    snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py
    snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256
    if zcal_rc_live_verify >/dev/null 2>&1 || managed_active_preflight; then
        printf 'active=1\n' >"$B/effective-state"
    else
        printf 'active=0\n' >"$B/effective-state"
    fi
    prepare_include_provenance
}
rollback_operation(){
    set +e
    echo 'ОШИБКА: RC Productization не завершён, восстанавливается transaction snapshot.' >&2
    restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg >/dev/null 2>&1 || true
    restore_snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py >/dev/null 2>&1 || true
    restore_snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256 >/dev/null 2>&1 || true
    rm -f "$ZCAL_KLIPPER_EXTRAS_DIR/__pycache__/ad5x_z_mesh_anchor"*.pyc 2>/dev/null || true
    if ! zcal_rc_klippy_host_restart >/dev/null 2>&1; then
        echo 'CRITICAL: файлы rollback восстановлены, но effective Klipper state не удалось перезагрузить автоматически.' >&2
    fi
    echo "Rollback backup: $B" >&2
}

if [ "$MODE" = status ]; then
    if [ ! -f "$ZCAL_RC_STATE_DIR/manifest.json" ]; then
        echo '[INACTIVE] Z Calibration RC Productization ownership manifest отсутствует'
        exit 1
    fi
    [ "$(include_count)" -eq 1 ] || fail 'generated RC policy include отсутствует/дублирован'
    zcal_mesh_anchor_runtime_matches_source || fail 'mesh-anchor runtime не соответствует source staging'
    zcal_rc_live_verify || fail 'effective RC state не соответствует ownership manifest'
    echo '[OK] Z Calibration RC Productization active and verified'
    if [ -f "$ROLLBACK_POINTER" ]; then
        TARGET="$(rollback_target)"
        echo "[OK] previous successful version available for rollback: $TARGET"
    else
        echo '[INFO] no previous successful update recorded for rollback'
    fi
    exit 0
fi

ROLLBACK_TARGET=""
if [ "$MODE" = rollback ]; then
    ROLLBACK_TARGET="$(rollback_target)"
fi

operation_prepare
SUCCESS=0
finish(){
    RC=$?
    trap - EXIT HUP INT TERM
    if [ "$SUCCESS" -ne 1 ]; then
        rollback_operation
        [ "$RC" -ne 0 ] || RC=1
    fi
    exit "$RC"
}
trap finish EXIT HUP INT TERM

case "$MODE" in
    install|update|repair)
        prepare_parked_policy_refresh
        zcal_mesh_anchor_deploy_managed_copy || fail 'mesh-anchor runtime deploy failed'
        zcal_rc_apply || fail 'apply/update/repair mutation failed'
        commit_include_provenance || fail 'include provenance commit failed'
        [ "$(include_count)" -eq 1 ] || fail 'generated RC policy include invariant failed'
        zcal_rc_klippy_host_restart || fail 'Klipper reload after RC apply failed'
        zcal_rc_live_verify || fail 'effective RC state verification failed'
        if [ "$MODE" = update ]; then
            record_rollback_target "$B" || fail 'failed to record previous successful version'
        fi
        ;;
    rollback)
        restore_version_snapshot "$ROLLBACK_TARGET" || fail 'previous successful version restore failed'
        zcal_rc_klippy_host_restart || fail 'Klipper reload after version rollback failed'
        case "$(cat "$ROLLBACK_TARGET/effective-state")" in
            active=1) verify_restored_managed_active || fail 'rolled-back active state compatibility verification failed' ;;
            active=0) wait_klippy_ready || fail 'rolled-back inactive/parked state did not become Klipper-ready' ;;
        esac
        record_rollback_target "$B" || fail 'failed to preserve rollback undo point'
        ;;
    uninstall)
        zcal_rc_uninstall || fail 'uninstall mutation failed'
        commit_include_provenance || fail 'include provenance adoption failed'
        restore_owned_include_state || fail 'generated include baseline restore failed'
        zcal_rc_klippy_host_restart || fail 'Klipper reload after RC uninstall failed'
        zcal_rc_live_verify_uninstalled || fail 'effective uninstall baseline verification failed'
        zcal_rc_finalize_uninstall || fail 'ownership finalize failed'
        rm -rf "$ROLLBACK_STATE_DIR" || fail 'rollback state cleanup failed'
        ;;
esac

SUCCESS=1
trap - EXIT HUP INT TERM
echo "[OK] Z Calibration RC Productization $MODE complete. Backup: $B"
