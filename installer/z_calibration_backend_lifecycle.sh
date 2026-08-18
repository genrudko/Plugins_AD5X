#!/bin/sh
# Standalone Moonraker observer lifecycle for Z Calibration.
#
# This lifecycle intentionally does NOT deploy or modify plugins_ad5x.py.
# It installs a separate plugins_ad5x_zcal component beside any existing
# shared/IFS backend and verifies that the shared backend survives each
# individual ZCal transaction unchanged. It never owns/pins the shared backend.
# Target runtime: Flashforge AD5X Z-Mod chroot.
set -eu

SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SOURCE_DIR="${AD5X_ZCAL_SOURCE_DIR:-$(CDPATH= cd -- "$SELF_DIR/.." && pwd)}"
STATE_ROOT="${AD5X_STATE_DIR:-/opt/config/mod_data/ad5x_custom}"
STATE_DIR="$STATE_ROOT/state/zcal-backend"
BACKUPS="$STATE_ROOT/backups"
GENERATED="$STATE_ROOT/generated"
MOONRAKER_COMPONENTS_DIR="${AD5X_MOONRAKER_COMPONENTS_DIR:-/opt/config/base/moonraker/components}"
MOONRAKER_INCLUDES="${AD5X_MOONRAKER_INCLUDES:-/opt/config/mod_data/plugins.moonraker.conf}"
MOONRAKER_HTTP_BASE="${AD5X_MOONRAKER_HTTP_BASE:-http://127.0.0.1:7125}"
MOONRAKER_READY_TIMEOUT="${AD5X_MOONRAKER_READY_TIMEOUT:-90}"
MOONRAKER_STOP_TIMEOUT="${AD5X_MOONRAKER_STOP_TIMEOUT:-30}"
MODE="${1:-}"

OBSERVER_SOURCE="$SOURCE_DIR/moonraker/components/plugins_ad5x_zcal.py"
CORE_SOURCE="$SOURCE_DIR/moonraker/components/plugins_ad5x_zcalibration.py"
CONFIG_SOURCE="$SOURCE_DIR/plugins_ad5x_zcal.moonraker.conf"
OBSERVER_DEST="$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_zcal.py"
CORE_DEST="$MOONRAKER_COMPONENTS_DIR/plugins_ad5x_zcalibration.py"
CONFIG_DEST="$GENERATED/zcal_backend.moonraker.conf"
INCLUDE_LINE='[include ad5x_custom/generated/zcal_backend.moonraker.conf]'
MANIFEST="$STATE_DIR/manifest.json"

case "$MODE" in
    install|update|repair|uninstall|status) ;;
    *) echo "usage: $0 {install|update|repair|uninstall|status}" >&2; exit 2 ;;
esac

fail(){ echo "ОШИБКА: $*" >&2; exit 1; }
sha256_file(){ sha256sum "$1" | awk '{print $1}'; }
python_bin(){
    if [ -n "${AD5X_PYTHON_BIN:-}" ] && [ -x "$AD5X_PYTHON_BIN" ]; then
        printf '%s\n' "$AD5X_PYTHON_BIN"
    elif command -v python3 >/dev/null 2>&1; then
        command -v python3
    elif [ -x /root/moonraker-env/bin/python3 ]; then
        printf '%s\n' /root/moonraker-env/bin/python3
    else
        return 1
    fi
}
curl_bin(){
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
http_code(){
    METHOD="$1"; URL="$2"; OUT="$3"
    CURL="$(curl_bin)" || return 1
    if [ "$METHOD" = POST ]; then
        "$CURL" -sS -m 5 -X POST -H 'Content-Type: application/json' \
            -o "$OUT" -w '%{http_code}' "$URL" 2>/dev/null || true
    else
        "$CURL" -sS -m 5 -o "$OUT" -w '%{http_code}' "$URL" 2>/dev/null || true
    fi
}
include_count(){ grep -Fxc "$INCLUDE_LINE" "$MOONRAKER_INCLUDES" 2>/dev/null || true; }
append_include(){
    [ -f "$MOONRAKER_INCLUDES" ] || : >"$MOONRAKER_INCLUDES"
    grep -Fqx "$INCLUDE_LINE" "$MOONRAKER_INCLUDES" 2>/dev/null || \
        printf '%s\n' "$INCLUDE_LINE" >>"$MOONRAKER_INCLUDES"
}
remove_include(){
    [ -f "$MOONRAKER_INCLUDES" ] || return 0
    awk -v line="$INCLUDE_LINE" '$0 != line { print }' "$MOONRAKER_INCLUDES" \
        >"$MOONRAKER_INCLUDES.tmp"
    mv "$MOONRAKER_INCLUDES.tmp" "$MOONRAKER_INCLUDES"
}
check_idle(){
    TMP="/tmp/zcal-backend-print-state.$$"
    CODE="$(http_code GET "$MOONRAKER_HTTP_BASE/printer/objects/query?print_stats" "$TMP")"
    [ "$CODE" = 200 ] || { rm -f "$TMP"; fail 'Moonraker print_stats недоступен'; }
    PY="$(python_bin)" || { rm -f "$TMP"; fail 'Python недоступен'; }
    PRINT_STATE="$("$PY" -B - "$TMP" <<'PY'
import json, sys
try:
    d=json.load(open(sys.argv[1], encoding="utf-8"))
    state=d["result"]["status"]["print_stats"]["state"]
except Exception:
    raise SystemExit(1)
if not isinstance(state, str) or not state:
    raise SystemExit(1)
print(state)
PY
)" || { rm -f "$TMP"; fail 'невалидный print_stats response'; }
    rm -f "$TMP"
    case "$PRINT_STATE" in
        standby|complete|error|cancelled) ;;
        printing|paused) fail 'принтер сейчас печатает или стоит на паузе' ;;
        *) fail "неизвестный print_stats.state=$PRINT_STATE" ;;
    esac
}
source_valid(){
    [ -s "$OBSERVER_SOURCE" ] || return 1
    [ -s "$CORE_SOURCE" ] || return 1
    [ -s "$CONFIG_SOURCE" ] || return 1
    [ "$(grep -Fxc '[plugins_ad5x_zcal]' "$CONFIG_SOURCE" 2>/dev/null || true)" -eq 1 ] || return 1
    [ "$(grep -Ec '^\[[^]]+\]$' "$CONFIG_SOURCE" 2>/dev/null || true)" -eq 1 ] || return 1
    [ -d "$MOONRAKER_COMPONENTS_DIR" ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B - "$OBSERVER_SOURCE" "$CORE_SOURCE" <<'PY' >/dev/null 2>&1
import ast, pathlib, sys
for raw in sys.argv[1:]:
    p=pathlib.Path(raw)
    ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
PY
}
file_matches_source_or_absent(){
    DEST="$1"; SOURCE="$2"
    [ ! -e "$DEST" ] && [ ! -L "$DEST" ] && return 0
    [ -f "$DEST" ] || return 1
    [ ! -L "$DEST" ] || return 1
    [ "$(sha256_file "$DEST")" = "$(sha256_file "$SOURCE")" ]
}
shared_signature(){
    OUT="$1"
    CODE="$(http_code GET "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/snapshot" "$OUT")"
    PY="$(python_bin)" || return 1
    "$PY" -B - "$CODE" "$OUT" <<'PY'
import json, sys
code=sys.argv[1]
path=sys.argv[2]
if code != "200":
    print("http=" + code)
    raise SystemExit(0)
try:
    d=json.load(open(path, encoding="utf-8")).get("result", {})
except Exception:
    print("http=200;invalid_json=1")
    raise SystemExit(0)
mods=d.get("modules") or {}
print("http=200;backend_version=%s;ifs=%s" % (d.get("backend_version"), int("ifs" in mods)))
PY
}
moonraker_process_count(){
    COUNT=0
    for P in /proc/[0-9]*; do
        [ -r "$P/cmdline" ] || continue
        CMD="$(tr '\0' ' ' <"$P/cmdline" 2>/dev/null || true)"
        case "$CMD" in *moonraker.py*) COUNT=$((COUNT + 1)) ;; esac
    done
    printf '%s\n' "$COUNT"
}
wait_moonraker_stopped(){
    LIMIT="${1:-$MOONRAKER_STOP_TIMEOUT}"; COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        [ "$(moonraker_process_count)" -eq 0 ] && return 0
        COUNT=$((COUNT + 1)); sleep 1
    done
    return 1
}
wait_moonraker_ready(){
    LIMIT="$MOONRAKER_READY_TIMEOUT"; COUNT=0
    while [ "$COUNT" -lt "$LIMIT" ]; do
        OUT="/tmp/zcal-backend-server-info.$$"
        CODE="$(http_code GET "$MOONRAKER_HTTP_BASE/server/info" "$OUT")"
        if [ "$CODE" = 200 ]; then
            PY="$(python_bin)" || { rm -f "$OUT"; return 1; }
            if "$PY" -B - "$OUT" <<'PY' >/dev/null 2>&1
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8")).get("result", {})
raise SystemExit(0 if d.get("klippy_connected") is True and d.get("klippy_state") == "ready" else 1)
PY
            then rm -f "$OUT"; return 0; fi
        fi
        rm -f "$OUT"
        COUNT=$((COUNT + 1)); sleep 1
    done
    return 1
}
stop_moonraker(){ /etc/init.d/S65moonraker stop >/dev/null 2>&1; }
start_moonraker(){ /etc/init.d/S65moonraker start >/dev/null 2>&1; }
remove_bytecode(){
    rm -f "$MOONRAKER_COMPONENTS_DIR/__pycache__/plugins_ad5x_zcal"*.pyc 2>/dev/null || true
    rm -f "$MOONRAKER_COMPONENTS_DIR/__pycache__/plugins_ad5x_zcalibration"*.pyc 2>/dev/null || true
}
copy_atomic(){
    SOURCE="$1"; DEST="$2"; MODE_="$3"
    TMP="$DEST.tmp.$$"
    rm -f "$TMP"
    cp "$SOURCE" "$TMP" || { rm -f "$TMP"; return 1; }
    chmod "$MODE_" "$TMP" || { rm -f "$TMP"; return 1; }
    [ "$(sha256_file "$TMP")" = "$(sha256_file "$SOURCE")" ] || { rm -f "$TMP"; return 1; }
    mv -f "$TMP" "$DEST"
}
snapshot_file(){
    FILE="$1"; KEY="$2"; DIR="$3"
    if [ -e "$FILE" ] || [ -L "$FILE" ]; then
        [ -f "$FILE" ] && [ ! -L "$FILE" ] || return 1
        cp -p "$FILE" "$DIR/$KEY"
    else
        : >"$DIR/.absent-$KEY"
    fi
}
restore_file(){
    FILE="$1"; KEY="$2"; DIR="$3"
    if [ -f "$DIR/.absent-$KEY" ]; then
        rm -f "$FILE"
    elif [ -f "$DIR/$KEY" ]; then
        cp -p "$DIR/$KEY" "$FILE"
    else
        return 1
    fi
}
manifest_value(){
    KEY="$1"
    PY="$(python_bin)" || return 1
    "$PY" -B - "$MANIFEST" "$KEY" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
v=d.get(sys.argv[2])
if isinstance(v, bool): print("1" if v else "0")
elif v is None: print("")
else: print(v)
PY
}
owned_runtime_ok(){
    [ -f "$MANIFEST" ] || return 1
    [ -f "$OBSERVER_DEST" ] && [ ! -L "$OBSERVER_DEST" ] || return 1
    [ -f "$CORE_DEST" ] && [ ! -L "$CORE_DEST" ] || return 1
    [ -f "$CONFIG_DEST" ] && [ ! -L "$CONFIG_DEST" ] || return 1
    [ "$(sha256_file "$OBSERVER_DEST")" = "$(manifest_value observer_installed_sha256)" ] || return 1
    [ "$(sha256_file "$CORE_DEST")" = "$(manifest_value core_installed_sha256)" ] || return 1
    [ "$(sha256_file "$CONFIG_DEST")" = "$(manifest_value config_installed_sha256)" ] || return 1
    [ "$(include_count)" -eq 1 ] || return 1
}
verify_z_backend(){
    SNAP="/tmp/zcal-backend-snapshot.$$"
    REC="/tmp/zcal-backend-reconcile.$$"
    DIA="/tmp/zcal-backend-diagnostics.$$"
    [ "$(http_code GET "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/z_calibration/snapshot" "$SNAP")" = 200 ] || return 1
    [ "$(http_code POST "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/z_calibration/reconcile" "$REC")" = 200 ] || return 1
    [ "$(http_code GET "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/z_calibration/diagnostics" "$DIA")" = 200 ] || return 1
    PY="$(python_bin)" || return 1
    "$PY" -B - "$SNAP" <<'PY' >/dev/null
import json, sys
r=json.load(open(sys.argv[1], encoding="utf-8")).get("result", {})
m=r.get("module") or {}
s=m.get("state") or {}
c=s.get("calibration") or {}
if c.get("state") != "observer": raise SystemExit(1)
if c.get("motion_owner") != "zmod": raise SystemExit(1)
if c.get("motion_actions_enabled") is not False: raise SystemExit(1)
if c.get("offset_write_enabled") is not False: raise SystemExit(1)
PY
    RC=$?
    rm -f "$SNAP" "$REC" "$DIA"
    return "$RC"
}
write_manifest(){
    DIR="$1"; SHARED="$2"; ENDPOINT_HTTP="$3"
    PY="$(python_bin)" || return 1
    "$PY" -B - "$DIR/manifest.json" "$SHARED" "$ENDPOINT_HTTP" \
        "$(sha256_file "$OBSERVER_SOURCE")" "$(sha256_file "$CORE_SOURCE")" \
        "$(sha256_file "$CONFIG_SOURCE")" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1])
d={
    "schema": 1,
    "shared_signature_at_adoption": sys.argv[2],
    "z_endpoint_original_http": sys.argv[3],
    "observer_installed_sha256": sys.argv[4],
    "core_installed_sha256": sys.argv[5],
    "config_installed_sha256": sys.argv[6],
}
p.write_text(json.dumps(d, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
}
update_manifest_hashes(){
    PY="$(python_bin)" || return 1
    "$PY" -B - "$MANIFEST" "$(sha256_file "$OBSERVER_SOURCE")" \
        "$(sha256_file "$CORE_SOURCE")" "$(sha256_file "$CONFIG_SOURCE")" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text(encoding="utf-8"))
d["observer_installed_sha256"]=sys.argv[2]
d["core_installed_sha256"]=sys.argv[3]
d["config_installed_sha256"]=sys.argv[4]
p.write_text(json.dumps(d, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
}

mkdir -p "$BACKUPS" "$GENERATED" "$STATE_ROOT/state"
source_valid || fail 'standalone ZCal backend source validation failed'

if [ "$MODE" = status ]; then
    owned_runtime_ok || fail 'standalone ZCal backend ownership/runtime mismatch'
    wait_moonraker_ready || fail 'Moonraker/Klippy not ready'
    verify_z_backend || fail 'standalone ZCal backend endpoint verification failed'
    echo '[OK] standalone Z Calibration observer active'
    exit 0
fi

check_idle
STAMP="$(date +%Y%m%d-%H%M%S)"
B="$BACKUPS/zcal-backend-$MODE-$STAMP-$$"
mkdir -p "$B"
snapshot_file "$OBSERVER_DEST" observer.py "$B" || fail 'observer destination snapshot failed'
snapshot_file "$CORE_DEST" core.py "$B" || fail 'core destination snapshot failed'
snapshot_file "$CONFIG_DEST" config.conf "$B" || fail 'config destination snapshot failed'
snapshot_file "$MOONRAKER_INCLUDES" includes.conf "$B" || fail 'Moonraker include snapshot failed'

SHARED_BEFORE="$(shared_signature "$B/shared-before.json")"
Z_ORIGINAL_HTTP="$(http_code GET "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/z_calibration/snapshot" "$B/z-before.json")"

if [ -f "$MANIFEST" ]; then
    owned_runtime_ok || fail 'existing standalone ZCal ownership is inconsistent'
else
    file_matches_source_or_absent "$OBSERVER_DEST" "$OBSERVER_SOURCE" || fail 'foreign standalone observer destination exists'
    file_matches_source_or_absent "$CORE_DEST" "$CORE_SOURCE" || fail 'foreign ZCal core destination exists'
    file_matches_source_or_absent "$CONFIG_DEST" "$CONFIG_SOURCE" || fail 'foreign ZCal config destination exists'
    COUNT="$(include_count)"
    [ "$COUNT" -le 1 ] || fail 'duplicate standalone ZCal Moonraker include'
    if [ "$COUNT" -eq 1 ]; then
        [ -f "$CONFIG_DEST" ] && [ "$(sha256_file "$CONFIG_DEST")" = "$(sha256_file "$CONFIG_SOURCE")" ] \
            || fail 'pre-existing ZCal include does not point to canonical config'
    fi
fi

SUCCESS=0
rollback(){
    RC=$?
    trap - EXIT HUP INT TERM
    if [ "$SUCCESS" -ne 1 ]; then
        set +e
        echo 'ОШИБКА: standalone ZCal backend transition failed; restoring snapshot.' >&2
        stop_moonraker >/dev/null 2>&1 || true
        wait_moonraker_stopped >/dev/null 2>&1 || true
        restore_file "$OBSERVER_DEST" observer.py "$B" >/dev/null 2>&1 || true
        restore_file "$CORE_DEST" core.py "$B" >/dev/null 2>&1 || true
        restore_file "$CONFIG_DEST" config.conf "$B" >/dev/null 2>&1 || true
        restore_file "$MOONRAKER_INCLUDES" includes.conf "$B" >/dev/null 2>&1 || true
        remove_bytecode
        start_moonraker >/dev/null 2>&1 || true
        wait_moonraker_ready >/dev/null 2>&1 || true
        echo "Rollback backup: $B" >&2
        [ "$RC" -ne 0 ] || RC=1
    fi
    exit "$RC"
}
trap rollback EXIT HUP INT TERM

case "$MODE" in
    install|update|repair)
        if [ ! -f "$MANIFEST" ]; then
            PENDING="$B/state-pending"
            mkdir -p "$PENDING/original"
            snapshot_file "$OBSERVER_DEST" observer.py "$PENDING/original" || fail 'original observer snapshot failed'
            snapshot_file "$CORE_DEST" core.py "$PENDING/original" || fail 'original core snapshot failed'
            snapshot_file "$CONFIG_DEST" config.conf "$PENDING/original" || fail 'original config snapshot failed'
            printf '%s\n' "$(include_count)" >"$PENDING/original/include-count"
            write_manifest "$PENDING" "$SHARED_BEFORE" "$Z_ORIGINAL_HTTP" || fail 'pending manifest write failed'
        fi

        stop_moonraker || fail 'Moonraker stop failed'
        wait_moonraker_stopped || fail 'Moonraker stop timeout'
        copy_atomic "$OBSERVER_SOURCE" "$OBSERVER_DEST" 0644 || fail 'observer deploy failed'
        copy_atomic "$CORE_SOURCE" "$CORE_DEST" 0644 || fail 'core deploy failed'
        copy_atomic "$CONFIG_SOURCE" "$CONFIG_DEST" 0644 || fail 'config deploy failed'
        append_include
        [ "$(include_count)" -eq 1 ] || fail 'standalone ZCal include invariant failed'
        remove_bytecode
        start_moonraker || fail 'Moonraker start failed'
        wait_moonraker_ready || fail 'Moonraker/Klippy ready timeout'
        verify_z_backend || fail 'standalone ZCal live verification failed'
        SHARED_AFTER="$(shared_signature "$B/shared-after.json")"
        [ "$SHARED_AFTER" = "$SHARED_BEFORE" ] || fail 'shared/IFS backend changed during ZCal deployment'

        if [ ! -f "$MANIFEST" ]; then
            rm -rf "$STATE_DIR"
            mv "$PENDING" "$STATE_DIR"
        else
            update_manifest_hashes || fail 'manifest hash update failed'
        fi
        ;;
    uninstall)
        [ -f "$MANIFEST" ] || fail 'standalone ZCal ownership manifest missing'
        owned_runtime_ok || fail 'standalone ZCal ownership/runtime mismatch'
        ORIGINAL="$STATE_DIR/original"
        [ -d "$ORIGINAL" ] || fail 'standalone ZCal original snapshot missing'
        ORIGINAL_INCLUDE_COUNT="$(cat "$ORIGINAL/include-count" 2>/dev/null || true)"
        case "$ORIGINAL_INCLUDE_COUNT" in 0|1) ;; *) fail 'invalid original include provenance' ;; esac

        stop_moonraker || fail 'Moonraker stop failed'
        wait_moonraker_stopped || fail 'Moonraker stop timeout'
        restore_file "$OBSERVER_DEST" observer.py "$ORIGINAL" || fail 'observer restore failed'
        restore_file "$CORE_DEST" core.py "$ORIGINAL" || fail 'core restore failed'
        restore_file "$CONFIG_DEST" config.conf "$ORIGINAL" || fail 'config restore failed'
        if [ "$ORIGINAL_INCLUDE_COUNT" -eq 0 ]; then remove_include; else append_include; fi
        remove_bytecode
        start_moonraker || fail 'Moonraker start failed'
        wait_moonraker_ready || fail 'Moonraker/Klippy ready timeout'
        SHARED_AFTER="$(shared_signature "$B/shared-after.json")"
        [ "$SHARED_AFTER" = "$SHARED_BEFORE" ] || fail 'shared backend changed during uninstall'
        Z_AFTER_HTTP="$(http_code GET "$MOONRAKER_HTTP_BASE/server/plugins_ad5x/z_calibration/snapshot" "$B/z-after.json")"
        [ "$Z_AFTER_HTTP" = "$(manifest_value z_endpoint_original_http)" ] || fail 'ZCal endpoint did not return to original availability'
        mv "$STATE_DIR" "$B/ownership-state-restored"
        ;;
esac

SUCCESS=1
trap - EXIT HUP INT TERM
echo "[OK] standalone Z Calibration backend $MODE complete. Backup: $B"
