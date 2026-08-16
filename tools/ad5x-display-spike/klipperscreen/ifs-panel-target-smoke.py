#!/usr/bin/env python3

import copy

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.KlippyGtk import KlippyGtk
from panels.ad5x_ifs import Panel as IFSPanel
from panels.ad5x_ifs_manage import Panel as IFSManagePanel


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
        self.opened_panels = []
        self.popups = []

    def show_panel(self, panel, title=None, **_kwargs):
        self.opened_panels.append((panel, title))

    def show_popup_message(self, message, level=1):
        self.popups.append((message, level))


Gtk.init([])
screen = Screen()
panel = IFSPanel(screen, "IFS")

sample = {
    "revision": 17,
    "modules": {
        "ifs": {
            "available": True,
            "state": "ready",
            "state_code": 5,
            "active_slot": 1,
            "runtime_active_slot": 0,
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
            "print_state": "standby",
            "filament_at_toolhead": True,
            "operation": {
                "state": "idle",
                "action": "",
                "slot": 0,
                "error": "",
            },
            "operations": {
                "select_slot": True,
                "load_slot": True,
                "unload_slot": True,
                "manage": True,
            },
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

# Known-active toolhead filament: only the active slot may unload; another
# present slot may be selected/loaded; an empty slot is inert.
assert not panel._slot_widgets[1]["select"].get_sensitive()
assert not panel._slot_widgets[1]["load"].get_sensitive()
assert panel._slot_widgets[1]["unload"].get_sensitive()
assert panel._slot_widgets[2]["select"].get_sensitive()
assert panel._slot_widgets[2]["load"].get_sensitive()
assert not panel._slot_widgets[2]["unload"].get_sensitive()
for name in ("select", "load", "unload"):
    assert not panel._slot_widgets[4][name].get_sensitive()

# Helix-derived AD5X safety invariant: PAUSED is not a safe filament-op state.
paused = copy.deepcopy(sample)
paused["revision"] = 18
paused["modules"]["ifs"]["print_state"] = "paused"
panel._render_snapshot(paused)
assert "операции заблокированы (paused)" in panel.status.get_text()
for widgets in panel._slot_widgets.values():
    for name in ("select", "load", "unload"):
        assert not widgets[name].get_sensitive()

# Restore idle sample and prove the Manage navigation target exists.
panel._render_snapshot(sample)
panel._on_manage_clicked(None)
assert screen.opened_panels[-1] == ("ad5x_ifs_manage", "IFS — детали")

manage = IFSManagePanel(screen, "IFS — детали")
manage._render_snapshot(sample)
assert manage.summary.get_text() == "IFS: Готов   •   активный слот 1"
assert manage.values["head"].get_text() == "Есть"
assert manage.values["print"].get_text() == "standby"
assert manage.values["operation"].get_text() == "idle"
assert manage.values["mapping"].get_text() == "T0→1   T1→1   T2→1   T3→4"
assert manage.values["raw_channel"].get_text() == "raw=0, bridge_cur_port=0"
assert manage.values["silk"].get_text() == "7"
assert manage.values["stall"].get_text() == "0"

print("QEMU_AD5X_IFS_PANEL_CONSTRUCT_OK", panel._last_revision)
print("QEMU_AD5X_IFS_ACTION_GATES_OK")
print("QEMU_AD5X_IFS_MANAGE_PANEL_OK", manage._last_revision)
