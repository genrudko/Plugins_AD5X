#!/usr/bin/env python3

import copy

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.KlippyGtk import KlippyGtk
from panels.ad5x_ifs import Panel as IFSPanel
from panels.ad5x_ifs_manage import Panel as IFSManagePanel
from panels.ad5x_ifs_metadata import Panel as IFSMetadataPanel


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
        self.keyboard_requests = 0

    def show_panel(self, panel, title=None, **_kwargs):
        self.opened_panels.append((panel, title))

    def show_popup_message(self, message, level=1):
        self.popups.append((message, level))

    def show_keyboard(self, *_args, **_kwargs):
        self.keyboard_requests += 1
        return False

    def remove_keyboard(self, *_args, **_kwargs):
        return None


def slot(
    number,
    *,
    present,
    material,
    color,
    active=False,
    source="flashforge",
    name="",
    brand="",
    series="",
    variant="",
    color_mode="solid",
    colors=None,
    finish="standard",
    metadata_status="assigned",
    select=False,
    load=False,
    unload=False,
):
    return {
        "slot": number,
        "present": present,
        "stall": False,
        "material": material,
        "color": color,
        "spool": {
            "source": source,
            "brand": brand,
            "series": series,
            "name": name,
            "material": material,
            "variant": variant,
            "spoolman_id": None,
            "remaining_g": None,
        },
        "appearance": {
            "color_mode": color_mode,
            "colors": list(colors or ([color] if color else [])),
            "finish": finish,
        },
        "metadata_status": metadata_status,
        "active": active,
        "permissions": {
            "select_slot": select,
            "load_slot": load,
            "unload_slot": unload,
            "blocked_reason": "",
        },
    }


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
                slot(
                    1,
                    present=True,
                    material="PETG",
                    color="#161616",
                    active=True,
                    unload=True,
                ),
                slot(
                    2,
                    present=True,
                    material="PLA",
                    color="#E53935",
                    source="manual",
                    brand="Kingroon",
                    series="Silk",
                    name="Red Blue Dual",
                    color_mode="dual",
                    colors=["#E53935", "#1E88E5"],
                    finish="silk",
                    select=True,
                    load=True,
                ),
                slot(
                    3,
                    present=True,
                    material="PLA",
                    color="#F330F9",
                    source="manual",
                    brand="ERYONE",
                    series="Silk",
                    name="Triple Color",
                    color_mode="tricolor",
                    colors=["#F330F9", "#27C4F4", "#FFD43B"],
                    finish="silk",
                    select=True,
                    load=True,
                ),
                slot(
                    4,
                    present=False,
                    material="TPU",
                    color="#161616",
                    source="manual",
                    name="Previous TPU",
                    metadata_status="stale",
                    select=False,
                    load=False,
                    unload=False,
                ),
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
            "write_blocked_reason": "",
            "metadata_store": {
                "status": "ok",
                "schema_version": "1.0",
                "error": "",
            },
            "capabilities": {
                "schema_version": "1.0",
                "slot_count": 4,
                "integrations": {
                    "flashforge": True,
                    "manual_store": True,
                    "spoolman": False,
                    "slicer": False,
                    "rfid": False,
                },
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
assert panel._selected_slot == 1
assert panel._slot_widgets[1]["material"].get_text() == "PETG"
assert "В тракте" in panel._slot_widgets[1]["state"].get_text()
assert panel._slot_widgets[2]["material"].get_text() == "Red Blue Dual"
assert panel._slot_widgets[2]["detail"].get_text() == "Silk • 2 цвета"
assert panel._slot_widgets[3]["material"].get_text() == "Triple Color"
assert "3 цвета" in panel._slot_widgets[3]["detail"].get_text()
assert len(panel._slot_widgets[3]["swatch"].get_children()) == 3
assert "Пустой слот" == panel._slot_widgets[4]["material"].get_text()
assert "Было: Previous TPU" == panel._slot_widgets[4]["detail"].get_text()
assert not panel._slot_widgets[4]["swatch"].get_visible()
assert panel.path.get_text() == "Тракт: Слот 1  →  IFS  →  ● Головка"

# Contextual actions are backend-owned. The initially selected active slot may
# only unload, exactly as slot.permissions says.
assert not panel.action_select.get_sensitive()
assert not panel.action_load.get_sensitive()
assert panel.action_unload.get_sensitive()

# Selecting another card changes only session/UI selection. Permissions still
# come from the selected slot contract; the frontend does not recalculate them.
panel._select_slot(2)
assert panel._selected_slot == 2
assert panel.selection.get_text() == "Слот 2 • Red Blue Dual"
assert panel.action_select.get_sensitive()
assert panel.action_load.get_sensitive()
assert not panel.action_unload.get_sensitive()

# Prove there are no per-card action buttons and no HEX label in the main UI.
for widgets in panel._slot_widgets.values():
    assert "select" not in widgets
    assert "load" not in widgets
    assert "unload" not in widgets
    assert "color" not in widgets

# PAUSED safety is represented by backend permissions + write_blocked_reason.
# The frontend only renders that decision.
paused = copy.deepcopy(sample)
paused["revision"] = 18
paused_module = paused["modules"]["ifs"]
paused_module["print_state"] = "paused"
paused_module["write_blocked_reason"] = "unsafe_print_state"
for item in paused_module["slots"]:
    item["permissions"] = {
        "select_slot": False,
        "load_slot": False,
        "unload_slot": False,
        "blocked_reason": "unsafe_print_state",
    }
panel._render_snapshot(paused)
assert "действия заблокированы (unsafe_print_state)" in panel.status.get_text()
assert not panel.action_select.get_sensitive()
assert not panel.action_load.get_sensitive()
assert not panel.action_unload.get_sensitive()

# Restore idle sample and prove the Advanced/Details navigation target exists.
panel._render_snapshot(sample)
panel._select_slot(3)
panel._on_edit_clicked(None)
assert screen.opened_panels[-1] == ("ad5x_ifs_metadata", "IFS — катушка")
panel._on_manage_clicked(None)
assert screen.opened_panels[-1] == ("ad5x_ifs_manage", "IFS — детали")

manage = IFSManagePanel(screen, "IFS — детали")
manage._render_snapshot(sample)
assert manage.summary.get_text() == "IFS: Готов   •   активный слот 1"
assert manage.values["head"].get_text() == "Есть"
assert manage.values["print"].get_text() == "standby"
assert manage.values["operation"].get_text() == "idle"
assert manage.values["metadata"].get_text() == "Готов"
assert manage.values["mapping"].get_text() == "T0→1   T1→1   T2→1   T3→4"
assert manage.values["raw_channel"].get_text() == "raw=0, bridge_cur_port=0"
assert manage.values["silk"].get_text() == "7"
assert manage.values["stall"].get_text() == "0"
manage._on_metadata_clicked(None)
assert screen.opened_panels[-1] == ("ad5x_ifs_metadata", "IFS — катушки")

metadata = IFSMetadataPanel(screen, "IFS — катушки", slot=3)
metadata._render_snapshot(sample)
assert metadata._selected_slot == 3
assert "Plugins AD5X" in metadata.source.get_text()
metadata._on_slot_clicked(None, 1)
assert "Flashforge/Z-Mod" in metadata.source.get_text()
assert metadata.entries["material"].get_text() == "PETG"
assert metadata.save_button.get_sensitive()
assert not metadata.clear_button.get_sensitive()

metadata._on_slot_clicked(None, 3)
assert metadata._selected_slot == 3
assert "Plugins AD5X" in metadata.source.get_text()
assert metadata.entries["brand"].get_text() == "ERYONE"
assert metadata.entries["name"].get_text() == "Triple Color"
assert metadata.color_mode.get_active_id() == "tricolor"
assert metadata.finish.get_active_id() == "silk"
assert sum(check.get_active() for check in metadata.color_checks) == 3
assert metadata.clear_button.get_sensitive()

print("QEMU_AD5X_IFS_PANEL_CONSTRUCT_OK", panel._last_revision)
print("QEMU_AD5X_IFS_MANAGER_CONTRACT_UI_OK", panel._selected_slot)
print("QEMU_AD5X_IFS_ACTION_GATES_OK")
print("QEMU_AD5X_IFS_MANAGE_PANEL_OK", manage._last_revision)
print("QEMU_AD5X_IFS_METADATA_PANEL_OK", metadata._selected_slot)
