#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.KlippyGtk import KlippyGtk
from panels.ad5x_ifs import Panel


class MainConfig:
    def get(self, _name, fallback=None):
        return fallback

    def getboolean(self, _name, fallback=False):
        return fallback


class Config:
    def __init__(self):
        self.main = MainConfig()

    def get_main_config(self):
        return self.main


class TimeoutOwner:
    @staticmethod
    def reset_timeout(*_args):
        return None


class OfflineWebsocket:
    connected = False


class Screen:
    width = 800
    height = 480
    vertical_mode = False
    theme = "material-dark"
    files = None
    printer = None

    def __init__(self):
        self._config = Config()
        self.screensaver = TimeoutOwner()
        self.lock_screen = TimeoutOwner()
        self._ws = OfflineWebsocket()
        self.gtk = KlippyGtk(self)


Gtk.init([])
screen = Screen()
panel = Panel(screen, "IFS")

sample = {
    "revision": 17,
    "modules": {
        "ifs": {
            "available": True,
            "state": "ready",
            "state_code": 5,
            "active_slot": 1,
            "runtime_active_slot": 1,
            "slots": [
                {
                    "slot": 1,
                    "present": True,
                    "stall": False,
                    "material": "PETG",
                    "color": "#161616",
                },
                {
                    "slot": 2,
                    "present": True,
                    "stall": False,
                    "material": "PLA",
                    "color": "#161616",
                },
                {
                    "slot": 3,
                    "present": True,
                    "stall": False,
                    "material": "PLA",
                    "color": "#F330F9",
                },
                {
                    "slot": 4,
                    "present": False,
                    "stall": False,
                    "material": "TPU",
                    "color": "#161616",
                },
            ],
            "silk_mask": 7,
            "raw_channel": 0,
            "insert_slot": 0,
            "need_insert": False,
            "stall": False,
            "stall_mask": 0,
            "tool_mapping": [1, 1, 1, 4],
        }
    },
}

panel._render_snapshot(sample)
assert panel.status.get_text() == "IFS: Готов   •   активный слот 1"
assert panel._slot_widgets[1]["material"].get_text() == "PETG"
assert "Филамент установлен" in panel._slot_widgets[3]["state"].get_text()
assert "Пусто" in panel._slot_widgets[4]["state"].get_text()
assert panel._slot_widgets[3]["color"].get_text() == "Цвет: #F330F9"
assert panel.mapping.get_text() == "Карта инструментов: T0→1   T1→1   T2→1   T3→4"

print("QEMU_AD5X_IFS_PANEL_CONSTRUCT_OK", panel._last_revision)
