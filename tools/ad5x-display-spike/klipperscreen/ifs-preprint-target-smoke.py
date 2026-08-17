#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.KlippyGtk import KlippyGtk
from panels.ad5x_ifs_preprint import Panel as IFSPreprintPanel


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
panel = IFSPreprintPanel(
    screen,
    "IFS — план печати",
    filename="3mf/model/demo/Metadata/plate_1.gcode",
)

ready_snapshot = {
    "modules": {
        "ifs": {
            "preprint_plan": {
                "available": True,
                "source": "zmod",
                "filename": "3mf/model/demo/Metadata/plate_1.gcode",
                "status": "ready",
                "rows": [
                    {
                        "tool": 0,
                        "requirement": {"material": "PLA", "color": "#F330F9"},
                        "assignment": {
                            "slot": 3,
                            "present": True,
                            "metadata_status": "assigned",
                            "spool": {
                                "source": "manual",
                                "brand": "ERYONE",
                                "series": "Silk",
                                "name": "Triple Color",
                                "material": "PLA",
                                "variant": "",
                                "spoolman_id": None,
                                "remaining_g": None,
                            },
                            "appearance": {
                                "color_mode": "tricolor",
                                "colors": ["#F330F9", "#27C4F4", "#FFD43B"],
                                "finish": "silk",
                            },
                        },
                        "state": "ready",
                    },
                    {
                        "tool": 1,
                        "requirement": {"material": "PETG", "color": "#161616"},
                        "assignment": {
                            "slot": 1,
                            "present": True,
                            "metadata_status": "assigned",
                            "spool": {
                                "source": "flashforge",
                                "brand": "",
                                "series": "",
                                "name": "",
                                "material": "PETG",
                                "variant": "",
                                "spoolman_id": None,
                                "remaining_g": None,
                            },
                            "appearance": {
                                "color_mode": "solid",
                                "colors": ["#161616"],
                                "finish": "standard",
                            },
                        },
                        "state": "ready",
                    },
                ],
                "warnings": [],
                "summary": {
                    "required_tools": 2,
                    "assigned_tools": 2,
                    "ready_tools": 2,
                },
                "auto_assign": {
                    "flags": 1,
                    "any_success": True,
                    "material_failure": False,
                    "color_failure": False,
                    "weak_color": False,
                    "duplicate_slot": False,
                },
                "messages": [],
                "error": "",
            }
        }
    }
}

panel._render_snapshot(ready_snapshot)
assert panel.filename_label.get_text() == "3mf/model/demo/Metadata/plate_1.gcode"
assert panel.summary.get_text() == "План: Готово к сопоставлению   •   готово 2/2"
assert panel.warning.get_text() == ""
assert len(panel._row_widgets) == 2
assert panel._row_widgets[0]["tool"].get_text() == "T0"
assert panel._row_widgets[0]["requirement"].get_text() == "PLA"
assert panel._row_widgets[0]["target"].get_text() == "Слот 3 • Triple Color"
assert panel._row_widgets[0]["state"].get_text() == "✓"
assert panel._row_widgets[1]["target"].get_text() == "Слот 1 • PETG"
assert not panel.start_button.get_sensitive()
assert panel.start_button.get_label() == "Запуск пока закрыт"
assert panel.source.get_text() == "Источник сопоставления: zmod"

blocked_snapshot = {
    "modules": {
        "ifs": {
            "preprint_plan": {
                "available": True,
                "source": "zmod",
                "filename": "bad.gcode",
                "status": "blocked",
                "rows": [
                    {
                        "tool": 2,
                        "requirement": {"material": "PLA", "color": "#FFFFFF"},
                        "assignment": None,
                        "state": "unassigned",
                    }
                ],
                "warnings": ["unassigned_tool", "weak_color"],
                "summary": {
                    "required_tools": 1,
                    "assigned_tools": 0,
                    "ready_tools": 0,
                },
                "auto_assign": {
                    "flags": 8,
                    "any_success": False,
                    "material_failure": False,
                    "color_failure": False,
                    "weak_color": True,
                    "duplicate_slot": False,
                },
                "messages": ["source warning"],
                "error": "",
            }
        }
    }
}

panel._render_snapshot(blocked_snapshot)
assert panel.summary.get_text() == "План: Требуется исправление   •   готово 0/1"
assert "Есть инструмент без назначенного слота" in panel.warning.get_text()
assert "слабое совпадение цвета" in panel.warning.get_text()
assert len(panel._row_widgets) == 1
assert panel._row_widgets[0]["target"].get_text() == "Слот не назначен"
assert panel._row_widgets[0]["state"].get_text() == "—"
assert not panel.start_button.get_sensitive()
assert panel.start_button.get_label() == "Исправьте сопоставление"

print("QEMU_AD5X_IFS_PREPRINT_PANEL_OK", len(panel._row_widgets))
print("QEMU_AD5X_IFS_PREPRINT_START_GATED_OK")
