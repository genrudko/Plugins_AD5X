#!/usr/bin/env python3
"""Patch the pinned upstream KlipperScreen gcode chooser for AD5X IFS preview.

The normal upstream Print action is intentionally preserved.  This patch adds a
separate IFS-plan action which opens the Plugins AD5X frontend-neutral pre-print
preview.  It does not start a print and does not write Z-Mod mapping state.
"""

from pathlib import Path
import sys


if len(sys.argv) != 2:
    raise SystemExit("usage: apply-ad5x-ifs-gcodes-patch.py <KlipperScreen app root>")

app = Path(sys.argv[1])
gcodes = app / "panels" / "gcodes.py"
text = gcodes.read_text(encoding="utf-8")

old_buttons = '''        buttons = [
            {"name": _("Delete"), "response": Gtk.ResponseType.REJECT, "style": "dialog-error"},
            {"name": action, "response": Gtk.ResponseType.OK, "style": "dialog-primary"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-secondary"},
        ]
'''
new_buttons = '''        buttons = [
            {"name": _("Delete"), "response": Gtk.ResponseType.REJECT, "style": "dialog-error"},
            {"name": action, "response": Gtk.ResponseType.OK, "style": "dialog-primary"},
            {"name": "IFS план", "response": Gtk.ResponseType.APPLY, "style": "dialog-primary"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-secondary"},
        ]
'''
if old_buttons not in text:
    raise SystemExit("KlipperScreen gcodes.py confirmation button contract changed upstream")
text = text.replace(old_buttons, new_buttons, 1)

old_response = '''        elif response_id == Gtk.ResponseType.OK:
            logging.info(f"Starting print: {filename}")
            self._screen._ws.api.print_start(filename)
        elif response_id == Gtk.ResponseType.REJECT:
            self.confirm_delete_file(None, f"gcodes/{filename}")
'''
new_response = '''        elif response_id == Gtk.ResponseType.OK:
            logging.info(f"Starting print: {filename}")
            self._screen._ws.api.print_start(filename)
        elif response_id == Gtk.ResponseType.APPLY:
            logging.info(f"Opening AD5X IFS pre-print plan: {filename}")
            self._screen.show_panel(
                "ad5x_ifs_preprint",
                "IFS — план печати",
                panel_name="ad5x_ifs_preprint_job",
                filename=filename,
            )
        elif response_id == Gtk.ResponseType.REJECT:
            self.confirm_delete_file(None, f"gcodes/{filename}")
'''
if old_response not in text:
    raise SystemExit("KlipperScreen gcodes.py print response contract changed upstream")
text = text.replace(old_response, new_response, 1)

gcodes.write_text(text, encoding="utf-8")

if text.count('"ad5x_ifs_preprint"') != 1:
    raise SystemExit("AD5X IFS pre-print integration was not applied exactly once")
if 'Gtk.ResponseType.APPLY' not in text:
    raise SystemExit("AD5X IFS pre-print response route missing")

print("AD5X_IFS_GCODES_PREPRINT_ROUTE_OK")
