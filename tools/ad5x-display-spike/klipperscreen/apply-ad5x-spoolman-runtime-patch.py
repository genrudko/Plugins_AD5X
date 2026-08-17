#!/usr/bin/env python3

from pathlib import Path
import sys


PATCH_MARKER = "_ad5x_static_spool_icon"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one upstream pattern, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-ad5x-spoolman-runtime-patch.py <KlipperScreen app root>")

    app = Path(sys.argv[1])
    target = app / "panels" / "spoolman.py"
    if not target.is_file():
        raise SystemExit(f"spoolman.py not found: {target}")

    text = target.read_text(encoding="utf-8")
    if PATCH_MARKER in text and "spool_name = GLib.markup_escape_text" in text:
        print("AD5X_SPOOLMAN_RUNTIME_PATCH_ALREADY_OK")
        return 0

    old_icon = '''    def _set_cell_icon(self, column, cell, model, it, data):
        spool = model.get_value(it, 0)
        if not spool:
            return
        self._set_cell_background(cell, spool)
        cell.set_property("pixbuf", spool.icon)
'''
    new_icon = '''    def _set_cell_icon(self, column, cell, model, it, data):
        spool = model.get_value(it, 0)
        if not spool:
            return
        self._set_cell_background(cell, spool)
        if os.environ.get("AD5X_KLIPPERSCREEN_PNG_ONLY", "1") == "1":
            icon = getattr(self, "_ad5x_static_spool_icon", None)
            if icon is None:
                icon_size = int(self._gtk.img_scale * self.bts * 2)
                icon = self._gtk.PixbufFromIcon("spool", icon_size, icon_size)
                self._ad5x_static_spool_icon = icon
            cell.set_property("pixbuf", icon)
            return
        cell.set_property("pixbuf", spool.icon)
'''
    text = replace_once(text, old_icon, new_icon, "Spoolman PNG fallback")

    old_markup = '''    def _get_filament_formated(self, spool: SpoolmanSpool):
        if spool.id == self.active_spool_id:
            result = f"<big><b>{spool.name}</b></big>\\n"
        else:
            result = f"<big>{spool.name}</big>\\n"

        if hasattr(spool, "comment"):
            result += f"{_('Comment')}:<b> {spool.comment}</b>\\n"
'''
    new_markup = '''    def _get_filament_formated(self, spool: SpoolmanSpool):
        spool_name = GLib.markup_escape_text(str(spool.name or ""))
        if spool.id == self.active_spool_id:
            result = f"<big><b>{spool_name}</b></big>\\n"
        else:
            result = f"<big>{spool_name}</big>\\n"

        if hasattr(spool, "comment"):
            comment = GLib.markup_escape_text(str(spool.comment or ""))
            result += f"{_('Comment')}:<b> {comment}</b>\\n"
'''
    text = replace_once(text, old_markup, new_markup, "Spoolman markup escaping")

    target.write_text(text, encoding="utf-8")
    print("AD5X_SPOOLMAN_RUNTIME_PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
