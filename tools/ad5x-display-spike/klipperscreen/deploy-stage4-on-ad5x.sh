#!/bin/sh
set -eu

ARCHIVE="${1:-}"
EXPECTED_SHA256="${2:-}"
ROOT="${AD5X_ZMOD_ROOT:-/usr/data/.mod/.zmod}"
DEST="$ROOT/opt/ad5x-klipperscreen"
BACKUP=""
COMMITTED=0

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -n "$ARCHIVE" ] || fail "usage: $0 <ad5x-klipperscreen-stage4.tar.gz> [sha256]"
[ -f "$ARCHIVE" ] || fail "archive not found: $ARCHIVE"
[ -d "$ROOT/opt" ] || fail "Z-Mod root is not mounted as expected: $ROOT"
command -v gzip >/dev/null 2>&1 || fail "gzip is unavailable"
command -v tar >/dev/null 2>&1 || fail "tar is unavailable"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is unavailable"

ACTUAL_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
echo "archive_sha256=$ACTUAL_SHA256"
if [ -n "$EXPECTED_SHA256" ] && [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    fail "archive SHA256 mismatch: expected $EXPECTED_SHA256"
fi

rollback() {
    [ "$COMMITTED" -eq 0 ] || return 0
    rm -rf "$DEST"
    if [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
        mv "$BACKUP" "$DEST" || true
        echo "Previous KlipperScreen bundle restored: $DEST" >&2
    fi
}
trap rollback EXIT INT TERM HUP

if [ -d "$DEST" ]; then
    STAMP="$(date +%Y%m%d-%H%M%S)"
    BACKUP="$ROOT/opt/ad5x-klipperscreen.pre-deploy-$STAMP"
    mv "$DEST" "$BACKUP"
    echo "Previous bundle saved: $BACKUP"
fi

# FlashForge AD5X BusyBox tar has no -z. Keep decompression explicit so the
# deployment path is identical on stock/Z-Mod hardware and in acceptance docs.
gzip -dc "$ARCHIVE" | tar -xf - -C "$ROOT"

[ -x "$DEST/run-klipperscreen-test.sh" ] || fail "launcher missing after extraction"
[ -s "$DEST/app/panels/ad5x_ifs.py" ] || fail "IFS panel missing after extraction"
[ -s "$DEST/app/panels/ad5x_ifs_preprint.py" ] || fail "IFS pre-print panel missing after extraction"
grep -Fq '"IFS план"' "$DEST/app/panels/gcodes.py" || fail "IFS plan route missing after extraction"
grep -Fq 'AD5X_KLIPPERSCREEN_PNG_ONLY' "$DEST/app/panels/spoolman.py" || fail "Spoolman PNG fallback missing after extraction"
grep -Fq 'markup_escape_text' "$DEST/app/panels/spoolman.py" || fail "Spoolman markup escaping missing after extraction"

COMMITTED=1
trap - EXIT INT TERM HUP

echo "AD5X_STAGE4_DEPLOY_OK"
echo "bundle=$DEST"
[ -n "$BACKUP" ] && echo "backup=$BACKUP"
