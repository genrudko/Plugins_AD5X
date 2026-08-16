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

# AD5X-specific UI remains a generated adapter outside the pinned upstream tree.
# It consumes only the Plugins_AD5X canonical backend contract over Moonraker.
install -m 0644 \
    tools/ad5x-display-spike/klipperscreen/ad5x_ifs_panel.py \
    "$APP/panels/ad5x_ifs.py"
install -m 0644 \
    tools/ad5x-display-spike/klipperscreen/ad5x_ifs_manage_panel.py \
    "$APP/panels/ad5x_ifs_manage.py"
install -m 0644 \
    tools/ad5x-display-spike/klipperscreen/ad5x_ifs_metadata_panel.py \
    "$APP/panels/ad5x_ifs_metadata.py"

# The first hardware proof only needs dependencies imported unconditionally by the
# upstream shell. Install them into an architecture-neutral private site-packages.
python3 -m pip install \
    --disable-pip-version-check \
    --no-compile \
    --target "$SITE" \
    -r tools/ad5x-display-spike/klipperscreen/requirements-startup.txt \
    | tee "$OUT/pip-install.log"

# pip may select optional x86_64 accelerators for otherwise pure-Python packages.
# Remove every native extension and prove the pure fallbacks import.
find "$SITE" -type f -name '*.so' -print | sort > "$OUT/removed-host-extensions.txt"
while IFS= read -r so; do
    [ -n "$so" ] || continue
    rm -f "$so"
done < "$OUT/removed-host-extensions.txt"

if find "$SITE" -type f -name '*.so' -print -quit | grep -q .; then
    echo "ERROR: native extension leaked into Stage 4 app layer" >&2
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
# adding a target Rust/librsvg stack: pre-render every shipped SVG to a 4x PNG.
: > "$OUT/svg-rendered.txt"
while IFS= read -r svg; do
    png="${svg%.svg}.png"
    rsvg-convert --zoom=4 "$svg" --output "$png"
    printf '%s -> %s\n' "${svg#$APP/}" "${png#$APP/}" >> "$OUT/svg-rendered.txt"
done < <(find "$APP/styles" -type f -name '*.svg' -print | sort)

python3 - "$APP" <<'PY'
from pathlib import Path
import sys

app = Path(sys.argv[1])

# Normal icon loading: prefer our CI-rendered PNG, retain SVG as a future fallback.
kg = app / "ks_includes" / "KlippyGtk.py"
s = kg.read_text()
old = 'for ext in ["svg", "png"]:'
new = 'for ext in ["png", "svg"]:'
if old not in s:
    raise SystemExit("KlippyGtk icon fallback pattern changed upstream")
kg.write_text(s.replace(old, new, 1))

screen = app / "screen.py"
s = screen.read_text()

# Gtk.Window icon is loaded directly rather than through KlippyGtk.
old = 'os.path.join(klipperscreendir, "styles", "icon.svg")'
new = 'os.path.join(klipperscreendir, "styles", "icon.png")'
if old not in s:
    raise SystemExit("screen.py icon path changed upstream")
s = s.replace(old, new, 1)

# AD5X has no xset in the proven private X11 runtime. The launcher directly owns
# the panel backlight and restores its state on exit, so generated compatibility
# must not make upstream X11 screensaver/DPMS helpers a hard startup dependency.
old = "import pathlib\nimport subprocess\n"
new = "import pathlib\nimport shutil\nimport subprocess\n"
if old not in s:
    raise SystemExit("screen.py import block changed upstream")
s = s.replace(old, new, 1)

old = '''    def set_dpms(self, use_dpms):
        if not use_dpms and not self.wayland:
'''
new = '''    def set_dpms(self, use_dpms):
        if not self.wayland and shutil.which("xset") is None:
            if self.check_dpms_timeout is not None:
                GLib.source_remove(self.check_dpms_timeout)
            self.check_dpms_timeout = None
            self.use_dpms = False
            self.blanking_time = 0
            self.screensaver.reset_timeout()
            logging.info("xset unavailable; AD5X launcher owns display blanking")
            return
        if not use_dpms and not self.wayland:
'''
if old not in s:
    raise SystemExit("screen.py set_dpms pattern changed upstream")
s = s.replace(old, new, 1)

old = '''        # disable screensaver we have our own
        if not self.wayland:
            cmd = ["xset", "-display", self.display_number, "s", "off"]
            subprocess.call(cmd)
            cmd = ["xset", "-display", self.display_number, "s", "noblank"]
            subprocess.call(cmd)
'''
new = '''        # disable the X11 screensaver when xset exists. AD5X uses the launcher
        # backlight owner instead and intentionally ships no xset.
        if not self.wayland and shutil.which("xset") is not None:
            cmd = ["xset", "-display", self.display_number, "s", "off"]
            subprocess.call(cmd)
            cmd = ["xset", "-display", self.display_number, "s", "noblank"]
            subprocess.call(cmd)
        elif not self.wayland:
            logging.debug("xset unavailable; skipping X11 screensaver commands")
'''
if old not in s:
    raise SystemExit("screen.py blanking pattern changed upstream")
s = s.replace(old, new, 1)
screen.write_text(s)

# Spoolman dynamically recolors its SVG in memory, which the no-librsvg Stage 3
# runtime cannot decode. The generated AD5X bundle defaults to the normal static
# pre-rendered PNG icon; a future librsvg runtime may opt out of PNG-only mode.
base = app / "panels" / "base_panel.py"
s = base.read_text()
old = '''        icon_size = self._gtk.img_scale * self.bts * 0.9
        if not os.path.isfile(icon_path):
'''
new = '''        icon_size = self._gtk.img_scale * self.bts * 0.9
        if os.environ.get("AD5X_KLIPPERSCREEN_PNG_ONLY", "1") == "1":
            return self._gtk.PixbufFromIcon("spool", icon_size, icon_size)
        if not os.path.isfile(icon_path):
'''
if old not in s:
    raise SystemExit("base_panel.py spool icon pattern changed upstream")
base.write_text(s.replace(old, new, 1))

# CSS background-image declarations do not have KlippyGtk's extension fallback.
for css in app.joinpath("styles").rglob("*.css"):
    text = css.read_text()
    if ".svg" in text:
        css.write_text(text.replace(".svg", ".png"))
PY

cp tools/ad5x-display-spike/klipperscreen/KlipperScreen.conf "$APPROOT/KlipperScreen.conf"
cp tools/ad5x-display-spike/klipperscreen/run-klipperscreen-test.sh "$APPROOT/run-klipperscreen-test.sh"
chmod +x "$APPROOT/run-klipperscreen-test.sh"

{
    echo "stage=4-klipperscreen-poc"
    echo "upstream_repo=KlipperScreen/KlipperScreen"
    echo "upstream_ref=$UPSTREAM_REF"
    echo "python_target=3.12.9"
    echo "stage3_runtime_root=/opt/ad5x-x11"
    echo "bundle_root=/opt/ad5x-klipperscreen"
    echo "svg_strategy=ci-prerendered-png-fallback"
    echo "display_blanking_owner=ad5x-launcher-backlight"
    echo "xset_required=false"
    echo "spoolman_dynamic_svg_gradient=deferred"
    echo "ifs_panel=plugins-ad5x-manager-contract"
    echo "ifs_manage_panel=plugins-ad5x-diagnostics"
    echo "ifs_metadata_panel=plugins-ad5x-manual-store-editor"
} > "$APPROOT/BUILDINFO.txt"

python3 -m compileall -q "$APP"
find "$APP" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$SITE" -type d -name '__pycache__' -prune -exec rm -rf {} +

PYTHONPATH="$SITE" python3 - <<'PY' > "$OUT/dependency-versions.txt"
from importlib.metadata import distributions
site = "out/klipperscreen/bundle-root/opt/ad5x-klipperscreen/lib/python3.12/site-packages"
for dist in sorted(distributions(path=[site]), key=lambda d: d.metadata["Name"].lower()):
    print(f'{dist.metadata["Name"]}=={dist.version}')
PY

find "$OUT/bundle-root" -mindepth 1 -maxdepth 1 -printf '%f\n' | grep -qx 'opt'
find "$OUT/bundle-root/opt" -mindepth 1 -maxdepth 1 -printf '%f\n' | grep -qx 'ad5x-klipperscreen'
test -s "$APP/panels/ad5x_ifs.py"
test -s "$APP/panels/ad5x_ifs_manage.py"
test -s "$APP/panels/ad5x_ifs_metadata.py"
grep -Fqx 'panel: ad5x_ifs' "$APPROOT/KlipperScreen.conf"
test ! -e "$OUT/bundle-root/usr"
test ! -e "$OUT/bundle-root/lib"
test ! -e "$OUT/bundle-root/bin"
test ! -e "$OUT/bundle-root/opt/ad5x-x11"

tar --sort=name --mtime='UTC 2020-01-01' \
    --owner=0 --group=0 --numeric-owner \
    -C "$OUT/bundle-root" \
    -czf "$OUT/ad5x-klipperscreen-stage4.tar.gz" opt
sha256sum "$OUT/ad5x-klipperscreen-stage4.tar.gz" | tee "$OUT/SHA256SUMS"
tar -tzf "$OUT/ad5x-klipperscreen-stage4.tar.gz" | sort > "$OUT/bundle-files.txt"

echo "STAGE4_APP_LAYER_OK"
