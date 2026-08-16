#!/bin/bash
set -euo pipefail

KS_SRC="${KS_SRC:-.ci/KlipperScreen}"
OUT="${OUT:-out/klipperscreen}"
APPROOT="$OUT/bundle-root/opt/ad5x-klipperscreen"
SITE="$APPROOT/lib/python3.12/site-packages"
APP="$APPROOT/app"
UPSTREAM_REF="${UPSTREAM_REF:?UPSTREAM_REF must be set}"

rm -rf "$OUT"
mkdir -p "$SITE" "$APP"

if [ ! -f "$KS_SRC/screen.py" ]; then
    echo "ERROR: pinned upstream KlipperScreen checkout not found at $KS_SRC" >&2
    exit 1
fi

# Copy the pinned upstream tree without VCS metadata. The app itself stays upstream;
# AD5X compatibility is applied only to this generated bundle.
rsync -a --delete --exclude='.git' "$KS_SRC/" "$APP/"

# The first hardware proof only needs dependencies imported unconditionally by the
# upstream shell. Install them into an architecture-neutral private site-packages.
python3 -m pip install \
    --disable-pip-version-check \
    --no-compile \
    --target "$SITE" \
    -r tools/ad5x-display-spike/klipperscreen/requirements-startup.txt \
    | tee "$OUT/pip-install.log"

# pip may select optional x86_64 accelerators for otherwise pure-Python packages
# (notably MarkupSafe/charset-normalizer). The AD5X layer must be architecture
# neutral, so remove every native extension and prove the pure fallbacks import.
find "$SITE" -type f -name '*.so' -print | sort > "$OUT/removed-host-extensions.txt"
while IFS= read -r so; do
    [ -n "$so" ] || continue
    rm -f "$so"
done < "$OUT/removed-host-extensions.txt"

if find "$SITE" -type f -name '*.so' -print -quit | grep -q .; then
    echo "ERROR: native extension leaked into Stage 4 app layer" >&2
    find "$SITE" -type f -name '*.so' -print >&2
    exit 1
fi

PYTHONPATH="$SITE" python3 - <<'PY' | tee "$OUT/host-python-imports.txt"
import jinja2
import requests
import websocket
import markupsafe
import charset_normalizer
import urllib3
import certifi
import idna
print(
    "HOST_PURE_PY_OK",
    "jinja2=" + jinja2.__version__,
    "requests=" + requests.__version__,
    "websocket=" + websocket.__version__,
    "markupsafe=" + markupsafe.__version__,
    "charset_normalizer=" + charset_normalizer.__version__,
    "urllib3=" + urllib3.__version__,
    "certifi=" + certifi.__version__,
    "idna=" + idna.__version__,
)
PY

# Stage 3 intentionally contains no librsvg. Preserve upstream visuals without
# adding a Rust/librsvg target stack: pre-render every shipped SVG to a 4x PNG.
# KlippyGtk already supports PNG; generated-bundle compatibility makes PNG the
# first choice and rewrites direct CSS/icon references. Upstream source is not
# modified in git.
: > "$OUT/svg-rendered.txt"
while IFS= read -r svg; do
    png="${svg%.svg}.png"
    if ! rsvg-convert --zoom=4 "$svg" --output "$png"; then
        echo "ERROR: failed to pre-render $svg" >&2
        exit 1
    fi
    printf '%s -> %s\n' "${svg#$APP/}" "${png#$APP/}" >> "$OUT/svg-rendered.txt"
done < <(find "$APP/styles" -type f -name '*.svg' -print | sort)

python3 - "$APP" <<'PY'
from pathlib import Path
import sys

app = Path(sys.argv[1])

# Normal icon loading: prefer our CI-rendered PNG, retain SVG as an upstream
# fallback for future runtimes that gain librsvg.
kg = app / "ks_includes" / "KlippyGtk.py"
s = kg.read_text()
old = 'for ext in ["svg", "png"]:'
new = 'for ext in ["png", "svg"]:'
if old not in s:
    raise SystemExit("KlippyGtk icon fallback pattern changed upstream")
kg.write_text(s.replace(old, new, 1))

# Gtk.Window icon is loaded directly rather than through KlippyGtk.
screen = app / "screen.py"
s = screen.read_text()
old = 'os.path.join(klipperscreendir, "styles", "icon.svg")'
new = 'os.path.join(klipperscreendir, "styles", "icon.png")'
if old not in s:
    raise SystemExit("screen.py icon path changed upstream")
screen.write_text(s.replace(old, new, 1))

# CSS background-image declarations do not have KlippyGtk's extension fallback.
for css in app.joinpath("styles").rglob("*.css"):
    text = css.read_text()
    if ".svg" in text:
        css.write_text(text.replace(".svg", ".png"))
PY

cp tools/ad5x-display-spike/klipperscreen/KlipperScreen.conf "$APPROOT/KlipperScreen.conf"
cp tools/ad5x-display-spike/klipperscreen/run-klipperscreen-test.sh "$APPROOT/run-klipperscreen-test.sh"
chmod +x "$APPROOT/run-klipperscreen-test.sh"

# Pin/provenance evidence travels with the artifact.
{
    echo "stage=4-klipperscreen-poc"
    echo "upstream_repo=KlipperScreen/KlipperScreen"
    echo "upstream_ref=$UPSTREAM_REF"
    echo "python_target=3.12.9"
    echo "stage3_runtime_root=/opt/ad5x-x11"
    echo "bundle_root=/opt/ad5x-klipperscreen"
    echo "native_extensions=forbidden"
    echo "svg_strategy=ci-prerendered-png-fallback"
} > "$APPROOT/BUILDINFO.txt"

python3 -m compileall -q "$APP"
find "$APP" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$SITE" -type d -name '__pycache__' -prune -exec rm -rf {} +

# Record actual resolved Python dependency versions for this artifact.
PYTHONPATH="$SITE" python3 - <<'PY' > "$OUT/dependency-versions.txt"
from importlib.metadata import distributions
for dist in sorted(distributions(path=["out/klipperscreen/bundle-root/opt/ad5x-klipperscreen/lib/python3.12/site-packages"]), key=lambda d: d.metadata["Name"].lower()):
    print(f'{dist.metadata["Name"]}=={dist.version}')
PY

# Path and payload invariants: Stage 4 is incremental and must not touch /usr,
# /lib, Z-Mod Python, or the already hardware-proven /opt/ad5x-x11 runtime.
find "$OUT/bundle-root" -mindepth 1 -maxdepth 1 -printf '%f\n' | grep -qx 'opt'
find "$OUT/bundle-root/opt" -mindepth 1 -maxdepth 1 -printf '%f\n' | grep -qx 'ad5x-klipperscreen'
test ! -e "$OUT/bundle-root/usr"
test ! -e "$OUT/bundle-root/lib"
test ! -e "$OUT/bundle-root/bin"
test ! -e "$OUT/bundle-root/opt/ad5x-x11"

tar \
    --sort=name \
    --mtime='UTC 2020-01-01' \
    --owner=0 --group=0 --numeric-owner \
    -C "$OUT/bundle-root" \
    -czf "$OUT/ad5x-klipperscreen-stage4.tar.gz" \
    opt
sha256sum "$OUT/ad5x-klipperscreen-stage4.tar.gz" | tee "$OUT/SHA256SUMS"
tar -tzf "$OUT/ad5x-klipperscreen-stage4.tar.gz" | sort > "$OUT/bundle-files.txt"

echo "STAGE4_APP_LAYER_OK"
