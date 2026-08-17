#!/usr/bin/env python3

import builtins
import os

builtins._ = lambda value: value
os.environ["AD5X_KLIPPERSCREEN_PNG_ONLY"] = "1"

from panels import spoolman


class FakeGtk:
    def __init__(self):
        self.img_scale = 1.0
        self.calls = []

    def PixbufFromIcon(self, name, width, height):
        self.calls.append((name, width, height))
        return ("STATIC_PIXBUF", name, width, height)


class FakePanel:
    def __init__(self):
        self.active_spool_id = None
        self.bts = 1
        self.timeFormat = "%Y-%m-%d %H:%M"
        self._gtk = FakeGtk()

    @staticmethod
    def _set_cell_background(_cell, _spool):
        return True


class FakeCell:
    def __init__(self):
        self.values = {}

    def set_property(self, name, value):
        self.values[name] = value


class FakeModel:
    def __init__(self, spool):
        self.spool = spool

    def get_value(self, _it, column):
        assert column == 0
        return self.spool


class FakeSpool:
    id = 7
    name = "Vendor A&B - PLA"
    comment = "Lot A&B"
    last_used = None

    @property
    def icon(self):
        raise AssertionError("dynamic SVG spool.icon must not be touched in PNG-only mode")


panel = FakePanel()
spool = FakeSpool()
cell = FakeCell()
model = FakeModel(spool)

spoolman.Panel._set_cell_icon(panel, None, cell, model, object(), None)
assert cell.values["pixbuf"][0] == "STATIC_PIXBUF"
assert panel._gtk.calls and panel._gtk.calls[0][0] == "spool"
print("QEMU_AD5X_SPOOLMAN_PNG_FALLBACK_OK")

markup = spoolman.Panel._get_filament_formated(panel, spool)
assert "Vendor A&amp;B - PLA" in markup, markup
assert "Lot A&amp;B" in markup, markup
assert "Vendor A&B" not in markup, markup
assert "Lot A&B" not in markup, markup
print("QEMU_AD5X_SPOOLMAN_MARKUP_ESCAPE_OK")
