import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


SNAPSHOT_METHOD = "server.plugins_ad5x.snapshot"
SNAPSHOT_NOTIFICATION = "notify_plugins_ad5x_snapshot_changed"

STATE_NAMES = {
    "ready": "Готов",
    "polling": "Опрос",
    "clamped": "Зажим",
    "loading": "Загрузка",
    "releasing": "Освобождение",
    "unloading": "Выгрузка",
    "driver_error": "Ошибка драйвера",
    "unavailable": "Недоступен",
    "unknown": "Неизвестно",
}


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "IFS")
        self._request_pending = False
        self._last_revision = None
        self._slot_widgets = {}

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            hexpand=True,
            vexpand=True,
        )

        top = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            hexpand=True,
            vexpand=False,
        )
        self.status = Gtk.Label(
            label="IFS: загрузка…",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.status.set_line_wrap(True)
        self.status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        top.pack_start(self.status, True, True, 0)

        refresh = self._gtk.Button("refresh", style="color3")
        refresh.set_hexpand(False)
        refresh.set_vexpand(False)
        refresh.connect("clicked", self._on_refresh_clicked)
        top.pack_end(refresh, False, False, 0)
        root.pack_start(top, False, False, 0)

        grid = Gtk.Grid(
            column_homogeneous=True,
            row_homogeneous=True,
            column_spacing=6,
            row_spacing=6,
            hexpand=True,
            vexpand=True,
        )
        for slot in range(1, 5):
            card, widgets = self._make_slot_card(slot)
            self._slot_widgets[slot] = widgets
            col = (slot - 1) % 2
            row = (slot - 1) // 2
            grid.attach(card, col, row, 1, 1)
        root.pack_start(grid, True, True, 0)

        self.mapping = Gtk.Label(
            label="",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.mapping.set_line_wrap(True)
        self.mapping.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        root.pack_end(self.mapping, False, False, 0)

        self.content.add(root)
        self.content.show_all()
        self._request_snapshot()

    def _make_slot_card(self, slot):
        frame = Gtk.Frame(hexpand=True, vexpand=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            margin=7,
            hexpand=True,
            vexpand=True,
        )
        title = Gtk.Label(
            label=f"Слот {slot}",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        title.set_markup(f"<big><b>Слот {slot}</b></big>")
        material = Gtk.Label(
            label="—",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        state = Gtk.Label(
            label="Нет данных",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        color = Gtk.Label(
            label="",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        box.pack_start(title, False, False, 0)
        box.pack_start(material, False, False, 0)
        box.pack_start(state, False, False, 0)
        box.pack_start(color, False, False, 0)
        frame.add(box)
        return frame, {
            "title": title,
            "material": material,
            "state": state,
            "color": color,
        }

    def activate(self):
        self._request_snapshot()

    def _on_refresh_clicked(self, _widget):
        self._request_snapshot(force=True)

    def _request_snapshot(self, force=False):
        if self._request_pending and not force:
            return
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self.status.set_text("IFS: Moonraker не подключён")
            return
        self._request_pending = True
        if not ws.send_method(SNAPSHOT_METHOD, {}, self._snapshot_response):
            self._request_pending = False
            self.status.set_text("IFS: не удалось запросить состояние")

    def _snapshot_response(self, response, _method, _params):
        self._request_pending = False
        if not isinstance(response, dict) or "error" in response:
            logging.error("Plugins AD5X IFS snapshot failed: %s", response)
            self.status.set_text("IFS: ошибка backend")
            return
        payload = response.get("result", response)
        if not isinstance(payload, dict):
            self.status.set_text("IFS: некорректный ответ backend")
            return
        self._render_snapshot(payload)

    def _render_snapshot(self, snapshot):
        self._last_revision = snapshot.get("revision")
        module = (snapshot.get("modules") or {}).get("ifs")
        if not isinstance(module, dict):
            self.status.set_text("IFS: модуль пока не опубликован")
            self._clear_slots()
            return

        if not module.get("available", False):
            reason = module.get("reason") or "unavailable"
            self.status.set_text(f"IFS: недоступен ({reason})")
            self._clear_slots()
            return

        state = STATE_NAMES.get(module.get("state"), module.get("state") or "Неизвестно")
        active = int(module.get("active_slot") or 0)
        self.status.set_text(
            f"IFS: {state}" + (f"   •   активный слот {active}" if active else "")
        )

        slots = module.get("slots") or []
        slot_map = {
            item.get("slot"): item
            for item in slots
            if isinstance(item, dict) and isinstance(item.get("slot"), int)
        }
        for slot in range(1, 5):
            self._render_slot(slot, slot_map.get(slot, {}), active)

        tool_mapping = module.get("tool_mapping")
        if isinstance(tool_mapping, list) and tool_mapping:
            pairs = [f"T{tool}→{slot}" for tool, slot in enumerate(tool_mapping)]
            self.mapping.set_text("Карта инструментов: " + "   ".join(pairs))
        else:
            self.mapping.set_text("")

    def _render_slot(self, slot, data, active):
        widgets = self._slot_widgets[slot]
        title = f"Слот {slot}" + ("  ★" if slot == active else "")
        widgets["title"].set_markup(f"<big><b>{title}</b></big>")

        material = data.get("material") or "Материал не задан"
        widgets["material"].set_text(str(material))

        present = bool(data.get("present", False))
        stall = bool(data.get("stall", False))
        if stall:
            state = "⚠ Филамент остановлен"
        elif present:
            state = "● Филамент установлен"
        else:
            state = "○ Пусто"
        widgets["state"].set_text(state)

        color = data.get("color")
        widgets["color"].set_text(f"Цвет: {color}" if color else "")

    def _clear_slots(self):
        for slot in range(1, 5):
            widgets = self._slot_widgets[slot]
            widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")
            widgets["material"].set_text("—")
            widgets["state"].set_text("Нет данных")
            widgets["color"].set_text("")
        self.mapping.set_text("")

    def process_update(self, action, _data):
        if action == SNAPSHOT_NOTIFICATION:
            self._request_snapshot()
        elif action in ("notify_klippy_ready", "notify_klippy_disconnected"):
            self._request_snapshot(force=True)
