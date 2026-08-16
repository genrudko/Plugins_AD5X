import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


SNAPSHOT_METHOD = "server.plugins_ad5x.snapshot"
ACTION_METHOD = "server.plugins_ad5x.ifs.action"
SNAPSHOT_NOTIFICATION = "notify_plugins_ad5x_snapshot_changed"
SAFE_PRINT_STATES = {"standby", "complete", "cancelled", "error"}

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

ACTION_NAMES = {
    "select_slot": "выбор слота",
    "load_slot": "загрузка",
    "unload_slot": "выгрузка",
}


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "IFS")
        self._request_pending = False
        self._action_pending = False
        self._last_revision = None
        self._last_module = None
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

        manage = self._gtk.Button("settings", style="color2")
        manage.set_hexpand(False)
        manage.set_vexpand(False)
        manage.connect("clicked", self._on_manage_clicked)
        top.pack_end(manage, False, False, 0)

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
            margin=5,
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

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=3,
            homogeneous=True,
            hexpand=True,
            vexpand=False,
        )
        select = Gtk.Button(label="Выбрать")
        load = Gtk.Button(label="Загрузить")
        unload = Gtk.Button(label="Выгрузить")
        select.connect("clicked", self._on_action_clicked, "select_slot", slot)
        load.connect("clicked", self._on_action_clicked, "load_slot", slot)
        unload.connect("clicked", self._on_action_clicked, "unload_slot", slot)
        for button in (select, load, unload):
            button.set_sensitive(False)
            actions.pack_start(button, True, True, 0)

        box.pack_start(title, False, False, 0)
        box.pack_start(material, False, False, 0)
        box.pack_start(state, False, False, 0)
        box.pack_start(color, False, False, 0)
        box.pack_end(actions, False, False, 0)
        frame.add(box)
        return frame, {
            "title": title,
            "material": material,
            "state": state,
            "color": color,
            "select": select,
            "load": load,
            "unload": unload,
        }

    def activate(self):
        self._request_snapshot()

    def _on_refresh_clicked(self, _widget):
        self._request_snapshot(force=True)

    def _on_manage_clicked(self, _widget):
        self._screen.show_panel("ad5x_ifs_manage", "IFS — детали")

    def _on_action_clicked(self, _widget, action, slot):
        if self._action_pending:
            return
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self._screen.show_popup_message("IFS: Moonraker не подключён", level=2)
            return

        self._action_pending = True
        self._set_all_action_buttons(False)
        params = {"action": action, "slot": slot}
        if not ws.send_method(ACTION_METHOD, params, self._action_response):
            self._action_pending = False
            self._screen.show_popup_message("IFS: не удалось отправить команду", level=2)
            self._render_action_buttons()

    def _action_response(self, response, _method, _params):
        self._action_pending = False
        if not isinstance(response, dict):
            self._screen.show_popup_message("IFS: некорректный ответ backend", level=2)
            self._request_snapshot(force=True)
            return
        if "error" in response:
            error = response.get("error") or {}
            message = error.get("message", "ошибка backend") if isinstance(error, dict) else str(error)
            self._screen.show_popup_message(f"IFS: {message}", level=2)
            self._request_snapshot(force=True)
            return

        payload = response.get("result", response)
        if not isinstance(payload, dict):
            self._screen.show_popup_message("IFS: некорректный ответ операции", level=2)
            self._request_snapshot(force=True)
            return

        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            self._render_snapshot(snapshot)

        if not payload.get("ok", False):
            message = payload.get("error") or "операция отклонена"
            self._screen.show_popup_message(f"IFS: {message}", level=2)
            self._render_action_buttons()
            return

        action = ACTION_NAMES.get(payload.get("action"), payload.get("action") or "операция")
        slot = payload.get("slot")
        self._screen.show_popup_message(f"IFS: {action}, слот {slot} — выполнено", level=1)
        self._request_snapshot(force=True)

    def _request_snapshot(self, force=False):
        if self._request_pending and not force:
            return
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self.status.set_text("IFS: Moonraker не подключён")
            self._set_all_action_buttons(False)
            return
        self._request_pending = True
        if not ws.send_method(SNAPSHOT_METHOD, {}, self._snapshot_response):
            self._request_pending = False
            self.status.set_text("IFS: не удалось запросить состояние")
            self._set_all_action_buttons(False)

    def _snapshot_response(self, response, _method, _params):
        self._request_pending = False
        if not isinstance(response, dict) or "error" in response:
            logging.error("Plugins AD5X IFS snapshot failed: %s", response)
            self.status.set_text("IFS: ошибка backend")
            self._set_all_action_buttons(False)
            return
        payload = response.get("result", response)
        if not isinstance(payload, dict):
            self.status.set_text("IFS: некорректный ответ backend")
            self._set_all_action_buttons(False)
            return
        self._render_snapshot(payload)

    def _render_snapshot(self, snapshot):
        self._last_revision = snapshot.get("revision")
        module = (snapshot.get("modules") or {}).get("ifs")
        self._last_module = module if isinstance(module, dict) else None
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
        text = f"IFS: {state}" + (f"   •   активный слот {active}" if active else "")

        operation = module.get("operation") or {}
        if operation.get("state") == "running":
            action = ACTION_NAMES.get(operation.get("action"), operation.get("action") or "операция")
            text += f"   •   {action}…"
        elif operation.get("error"):
            text += "   •   последняя операция завершилась ошибкой"

        print_state = module.get("print_state") or "unknown"
        if print_state not in SAFE_PRINT_STATES:
            text += f"   •   операции заблокированы ({print_state})"
        self.status.set_text(text)

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
        self._render_action_buttons()

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

    def _render_action_buttons(self):
        module = self._last_module
        if not isinstance(module, dict) or not module.get("available", False):
            self._set_all_action_buttons(False)
            return

        operation = module.get("operation") or {}
        can_write = (
            not self._action_pending
            and module.get("state") == "ready"
            and module.get("print_state") in SAFE_PRINT_STATES
            and operation.get("state", "idle") == "idle"
        )
        active = int(module.get("active_slot") or 0)
        head_filament = module.get("filament_at_toolhead")
        slot_map = {
            item.get("slot"): item
            for item in (module.get("slots") or [])
            if isinstance(item, dict)
        }

        for slot, widgets in self._slot_widgets.items():
            data = slot_map.get(slot, {})
            present = bool(data.get("present", False))
            widgets["select"].set_sensitive(can_write and present and slot != active)
            widgets["load"].set_sensitive(
                can_write and present and not (slot == active and head_filament is True)
            )
            widgets["unload"].set_sensitive(
                can_write and slot == active and head_filament is True
            )

    def _set_all_action_buttons(self, sensitive):
        for widgets in self._slot_widgets.values():
            for name in ("select", "load", "unload"):
                widgets[name].set_sensitive(sensitive)

    def _clear_slots(self):
        self._last_module = None
        for slot in range(1, 5):
            widgets = self._slot_widgets[slot]
            widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")
            widgets["material"].set_text("—")
            widgets["state"].set_text("Нет данных")
            widgets["color"].set_text("")
        self.mapping.set_text("")
        self._set_all_action_buttons(False)

    def process_update(self, action, _data):
        if action == SNAPSHOT_NOTIFICATION:
            self._request_snapshot()
        elif action in ("notify_klippy_ready", "notify_klippy_disconnected"):
            self._request_snapshot(force=True)
