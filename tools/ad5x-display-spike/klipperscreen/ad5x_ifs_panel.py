import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


SNAPSHOT_METHOD = "server.plugins_ad5x.snapshot"
ACTION_METHOD = "server.plugins_ad5x.ifs.action"
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

ACTION_NAMES = {
    "select_slot": "выбор слота",
    "load_slot": "загрузка",
    "unload_slot": "выгрузка",
}

FINISH_NAMES = {
    "standard": "",
    "matte": "Matte",
    "silk": "Silk",
    "satin": "Satin",
    "metallic": "Metallic",
    "transparent": "Transparent",
    "translucent": "Translucent",
    "glitter": "Glitter",
    "glow": "Glow",
    "wood": "Wood",
    "carbon_fiber": "CF",
    "other": "Special",
}

COLOR_MODE_NAMES = {
    "solid": "1 цвет",
    "dual": "2 цвета",
    "tricolor": "3 цвета",
    "gradient": "Градиент",
    "rainbow": "Радуга",
    "special": "Special",
}


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "IFS")
        self._request_pending = False
        self._action_pending = False
        self._last_revision = None
        self._last_module = None
        self._slot_widgets = {}
        self._selected_slot = 0

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
            grid.attach(card, slot - 1, 0, 1, 1)
        root.pack_start(grid, True, True, 0)

        self.path = Gtk.Label(
            label="Тракт: —",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.path.set_ellipsize(Pango.EllipsizeMode.END)
        root.pack_start(self.path, False, False, 0)

        action_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=5,
            hexpand=True,
            vexpand=False,
        )
        self.selection = Gtk.Label(
            label="Выберите слот",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.selection.set_ellipsize(Pango.EllipsizeMode.END)
        action_bar.pack_start(self.selection, True, True, 0)

        self.action_edit = Gtk.Button(label="Катушка")

        self.action_edit.connect("clicked", self._on_edit_clicked)

        action_bar.pack_start(self.action_edit, False, False, 0)


        self.action_select = Gtk.Button(label="Выбрать")
        self.action_load = Gtk.Button(label="Загрузить")
        self.action_unload = Gtk.Button(label="Выгрузить")
        self.action_select.connect("clicked", self._on_context_action_clicked, "select_slot")
        self.action_load.connect("clicked", self._on_context_action_clicked, "load_slot")
        self.action_unload.connect("clicked", self._on_context_action_clicked, "unload_slot")
        for button in (self.action_select, self.action_load, self.action_unload):
            button.set_sensitive(False)
            action_bar.pack_start(button, False, False, 0)
        root.pack_end(action_bar, False, False, 0)

        self.content.add(root)
        self.content.show_all()
        self._request_snapshot()

    def _make_slot_card(self, slot):
        card = Gtk.Button(hexpand=True, vexpand=True)
        card.set_relief(Gtk.ReliefStyle.NONE)
        card.connect("clicked", self._on_slot_clicked, slot)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=3,
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
        material.set_ellipsize(Pango.EllipsizeMode.END)

        detail = Gtk.Label(
            label="",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        detail.set_ellipsize(Pango.EllipsizeMode.END)

        state = Gtk.Label(
            label="Нет данных",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )

        swatch = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=1,
            homogeneous=True,
            hexpand=True,
            vexpand=False,
        )
        swatch.set_size_request(-1, 24)

        box.pack_start(title, False, False, 0)
        box.pack_start(swatch, False, False, 0)
        box.pack_start(material, False, False, 0)
        box.pack_start(detail, False, False, 0)
        box.pack_end(state, False, False, 0)
        card.add(box)
        return card, {
            "card": card,
            "title": title,
            "material": material,
            "detail": detail,
            "state": state,
            "swatch": swatch,
            "data": {},
        }

    @staticmethod
    def _set_background(widget, color):
        provider = Gtk.CssProvider()
        provider.load_from_data(
            (
                "* { background-color: %s; min-height: 20px; "
                "border: 1px solid rgba(255,255,255,0.55); border-radius: 3px; }"
                % color
            ).encode("utf-8")
        )
        widget.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        widget._ad5x_css_provider = provider

    def _apply_card_style(self, slot):
        widgets = self._slot_widgets.get(slot)
        if not widgets:
            return
        data = widgets.get("data") or {}
        active = 0
        if isinstance(self._last_module, dict):
            active = int(self._last_module.get("active_slot") or 0)
        selected = slot == self._selected_slot
        stall = bool(data.get("stall", False))

        if stall:
            border = "#ffb020"
        elif slot == active:
            border = "#39d98a"
        elif selected:
            border = "#5da9ff"
        else:
            border = "rgba(255,255,255,0.20)"

        if selected:
            background = "rgba(255,255,255,0.10)"
        elif slot == active:
            background = "rgba(57,217,138,0.06)"
        else:
            background = "rgba(255,255,255,0.025)"

        provider = Gtk.CssProvider()
        provider.load_from_data(
            (
                "* { border: 2px solid %s; border-radius: 10px; "
                "background-color: %s; }" % (border, background)
            ).encode("utf-8")
        )
        widgets["card"].get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        widgets["card"]._ad5x_card_css_provider = provider

    def _render_swatch(self, container, appearance, present):
        for child in container.get_children():
            container.remove(child)
        if not present or not isinstance(appearance, dict):
            container.hide()
            return
        colors = appearance.get("colors")
        if not isinstance(colors, list) or not colors:
            container.hide()
            return
        for color in colors[:8]:
            if not isinstance(color, str) or not color.startswith("#"):
                continue
            segment = Gtk.EventBox(hexpand=True, vexpand=False)
            self._set_background(segment, color)
            container.pack_start(segment, True, True, 0)
        if container.get_children():
            container.show_all()
        else:
            container.hide()

    @staticmethod
    def _spool_title(data):
        spool = data.get("spool") if isinstance(data.get("spool"), dict) else {}
        name = spool.get("name") or ""
        brand = spool.get("brand") or ""
        material = spool.get("material") or data.get("material") or ""
        if name:
            return name
        if brand and material:
            return f"{brand} • {material}"
        return material or brand or "Материал не задан"

    @staticmethod
    def _spool_detail(data):
        spool = data.get("spool") if isinstance(data.get("spool"), dict) else {}
        appearance = (
            data.get("appearance") if isinstance(data.get("appearance"), dict) else {}
        )
        parts = []

        def add(value):
            if not value:
                return
            text = str(value)
            if text.casefold() not in {item.casefold() for item in parts}:
                parts.append(text)

        add(spool.get("series") or "")
        add(spool.get("variant") or "")
        add(FINISH_NAMES.get(appearance.get("finish"), appearance.get("finish") or ""))
        colors = appearance.get("colors") if isinstance(appearance.get("colors"), list) else []
        mode = appearance.get("color_mode")
        if colors:
            add(COLOR_MODE_NAMES.get(mode, f"{len(colors)} цвета"))
        return " • ".join(parts)

    def activate(self):
        self._request_snapshot()

    def _on_refresh_clicked(self, _widget):
        self._request_snapshot(force=True)

    def _on_manage_clicked(self, _widget):
        self._screen.show_panel("ad5x_ifs_manage", "IFS — детали")

    def _on_slot_clicked(self, _widget, slot):
        self._select_slot(slot)

    def _on_edit_clicked(self, _widget):
        slot = self._selected_slot or 1
        self._screen.show_panel(
            "ad5x_ifs_metadata",
            "IFS — катушка",
            panel_name=f"ad5x_ifs_metadata_slot_{slot}",
            slot=slot,
        )

    def _select_slot(self, slot):
        if slot not in self._slot_widgets:
            return
        self._selected_slot = slot
        self._render_selection()
        self._render_action_buttons()

    def _on_context_action_clicked(self, _widget, action):
        slot = self._selected_slot
        if not slot:
            return
        self._send_action(action, slot)

    def _send_action(self, action, slot):
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

        blocked = module.get("write_blocked_reason") or ""
        if blocked:
            text += f"   •   действия заблокированы ({blocked})"
        self.status.set_text(text)

        slots = module.get("slots") or []
        slot_map = {
            item.get("slot"): item
            for item in slots
            if isinstance(item, dict) and isinstance(item.get("slot"), int)
        }
        for slot in range(1, 5):
            self._render_slot(slot, slot_map.get(slot, {}), active)

        if self._selected_slot not in self._slot_widgets:
            self._selected_slot = 0
        if not self._selected_slot:
            if active in self._slot_widgets:
                self._selected_slot = active
            else:
                present = [slot for slot, data in slot_map.items() if data.get("present")]
                self._selected_slot = present[0] if present else 1
        self._render_selection()
        self._render_action_buttons()

    def _render_slot(self, slot, data, active):
        widgets = self._slot_widgets[slot]
        widgets["data"] = data if isinstance(data, dict) else {}
        if slot == active:
            widgets["title"].set_markup(
                f"<big><b>Слот {slot}</b></big>  <small>АКТИВНЫЙ</small>"
            )
        else:
            widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")

        present = bool(data.get("present", False))
        stall = bool(data.get("stall", False))
        metadata_status = data.get("metadata_status") or "none"

        if not present:
            widgets["material"].set_text("Пустой слот")
            if metadata_status == "stale":
                widgets["detail"].set_text("Было: " + self._spool_title(data))
            else:
                widgets["detail"].set_text("Катушка не назначена")
            widgets["state"].set_text("○ Пусто")
            self._render_swatch(widgets["swatch"], data.get("appearance"), False)
            self._apply_card_style(slot)
            return

        widgets["material"].set_text(self._spool_title(data))
        widgets["detail"].set_text(self._spool_detail(data))
        if stall:
            state = "⚠ ЗАМЯТИЕ"
        elif slot == active:
            state = "● В тракте"
        else:
            state = "● Загружен"
        widgets["state"].set_text(state)
        self._render_swatch(widgets["swatch"], data.get("appearance"), True)
        self._apply_card_style(slot)

    def _render_selection(self):
        active = 0
        if isinstance(self._last_module, dict):
            active = int(self._last_module.get("active_slot") or 0)
        for slot, widgets in self._slot_widgets.items():
            if slot == active:
                widgets["title"].set_markup(
                    f"<big><b>Слот {slot}</b></big>  <small>АКТИВНЫЙ</small>"
                )
            else:
                widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")
            self._apply_card_style(slot)

        self._render_path()
        if not self._selected_slot:
            self.selection.set_text("Выберите слот")
            return
        data = self._slot_widgets[self._selected_slot].get("data") or {}
        if data.get("present"):
            self.selection.set_text(
                f"Слот {self._selected_slot} • {self._spool_title(data)}"
            )
        else:
            self.selection.set_text(f"Слот {self._selected_slot} • пусто")

    def _render_path(self):
        module = self._last_module if isinstance(self._last_module, dict) else {}
        active = int(module.get("active_slot") or 0)
        head = module.get("filament_at_toolhead")
        if not active:
            self.path.set_text("Тракт: —")
            return
        if head is True:
            head_text = "● Головка"
        elif head is False:
            head_text = "○ Головка"
        else:
            head_text = "? Головка"
        self.path.set_text(f"Тракт: Слот {active}  →  IFS  →  {head_text}")

    def _render_action_buttons(self):
        if self._action_pending or not self._selected_slot:
            self._set_all_action_buttons(False)
            return
        widgets = self._slot_widgets.get(self._selected_slot) or {}
        data = widgets.get("data") if isinstance(widgets, dict) else {}
        permissions = data.get("permissions") if isinstance(data, dict) else {}
        if not isinstance(permissions, dict):
            permissions = {}
        self.action_select.set_sensitive(bool(permissions.get("select_slot", False)))
        self.action_load.set_sensitive(bool(permissions.get("load_slot", False)))
        self.action_unload.set_sensitive(bool(permissions.get("unload_slot", False)))

    def _set_all_action_buttons(self, sensitive):
        self.action_select.set_sensitive(sensitive)
        self.action_load.set_sensitive(sensitive)
        self.action_unload.set_sensitive(sensitive)

    def _clear_slots(self):
        self._last_module = None
        self._selected_slot = 0
        for slot in range(1, 5):
            widgets = self._slot_widgets[slot]
            widgets["data"] = {}
            widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")
            widgets["material"].set_text("—")
            widgets["detail"].set_text("")
            widgets["state"].set_text("Нет данных")
            self._render_swatch(widgets["swatch"], {}, False)
            self._apply_card_style(slot)
        self.path.set_text("Тракт: —")
        self.selection.set_text("Выберите слот")
        self._set_all_action_buttons(False)

    def process_update(self, action, _data):
        if action == SNAPSHOT_NOTIFICATION:
            self._request_snapshot()
        elif action in ("notify_klippy_ready", "notify_klippy_disconnected"):
            self._request_snapshot(force=True)
