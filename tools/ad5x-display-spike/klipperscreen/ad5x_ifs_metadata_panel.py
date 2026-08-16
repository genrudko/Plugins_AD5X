import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


SNAPSHOT_METHOD = "server.plugins_ad5x.snapshot"
METADATA_METHOD = "server.plugins_ad5x.ifs.metadata"
SNAPSHOT_NOTIFICATION = "notify_plugins_ad5x_snapshot_changed"

COLOR_MODES = [
    ("solid", "Один цвет"),
    ("dual", "Два цвета"),
    ("tricolor", "Три цвета"),
    ("gradient", "Градиент"),
    ("rainbow", "Радуга"),
    ("special", "Особый"),
]

FINISHES = [
    ("standard", "Обычный"),
    ("matte", "Matte"),
    ("silk", "Silk"),
    ("satin", "Satin"),
    ("metallic", "Metallic"),
    ("transparent", "Прозрачный"),
    ("translucent", "Полупрозрачный"),
    ("glitter", "Glitter"),
    ("glow", "Glow"),
    ("wood", "Wood"),
    ("carbon_fiber", "Carbon Fiber"),
    ("other", "Другой"),
]

SOURCE_NAMES = {
    "manual": "Plugins AD5X",
    "flashforge": "Flashforge/Z-Mod",
    "spoolman": "Spoolman",
    "slicer": "Слайсер",
    "rfid": "RFID",
    "unknown": "Неизвестно",
}


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "IFS — катушки")
        self._request_pending = False
        self._save_pending = False
        self._last_module = None
        self._selected_slot = 1
        self._slot_data = {}
        self._loading_form = False

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
        self.summary = Gtk.Label(
            label="Катушки IFS: загрузка…",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.summary.set_ellipsize(Pango.EllipsizeMode.END)
        top.pack_start(self.summary, True, True, 0)
        refresh = self._gtk.Button("refresh", style="color3")
        refresh.connect("clicked", self._on_refresh_clicked)
        top.pack_end(refresh, False, False, 0)
        root.pack_start(top, False, False, 0)

        selector = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            homogeneous=True,
            hexpand=True,
            vexpand=False,
        )
        self.slot_buttons = {}
        for slot in range(1, 5):
            button = Gtk.Button(label=f"Слот {slot}")
            button.connect("clicked", self._on_slot_clicked, slot)
            selector.pack_start(button, True, True, 0)
            self.slot_buttons[slot] = button
        root.pack_start(selector, False, False, 0)

        self.source = Gtk.Label(
            label="Источник: —",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.source.set_ellipsize(Pango.EllipsizeMode.END)
        root.pack_start(self.source, False, False, 0)

        scroll = self._gtk.ScrolledWindow()
        form = Gtk.Grid(
            column_spacing=8,
            row_spacing=5,
            hexpand=True,
            vexpand=True,
            margin=2,
        )
        self.entries = {}
        fields = [
            ("brand", "Производитель"),
            ("name", "Название"),
            ("material", "Материал"),
            ("series", "Серия"),
            ("variant", "Вариант"),
        ]
        for row, (key, label) in enumerate(fields):
            name = Gtk.Label(
                label=label,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
                xalign=0,
            )
            entry = Gtk.Entry(hexpand=True)
            entry.connect("touch-event", self._screen.show_keyboard)
            entry.connect("button-press-event", self._screen.show_keyboard)
            self.entries[key] = entry
            form.attach(name, 0, row, 1, 1)
            form.attach(entry, 1, row, 3, 1)

        mode_label = Gtk.Label(
            label="Цвет",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.color_mode = Gtk.ComboBoxText(hexpand=True)
        for value, label in COLOR_MODES:
            self.color_mode.append(value, label)
        self.color_mode.set_active_id("solid")
        form.attach(mode_label, 0, len(fields), 1, 1)
        form.attach(self.color_mode, 1, len(fields), 1, 1)

        finish_label = Gtk.Label(
            label="Поверхность",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.finish = Gtk.ComboBoxText(hexpand=True)
        for value, label in FINISHES:
            self.finish.append(value, label)
        self.finish.set_active_id("standard")
        form.attach(finish_label, 2, len(fields), 1, 1)
        form.attach(self.finish, 3, len(fields), 1, 1)

        self.color_checks = []
        self.color_buttons = []
        color_row = len(fields) + 1
        for index in range(4):
            check = Gtk.CheckButton(label=f"{index + 1}")
            color = Gtk.ColorButton(use_alpha=False)
            color.set_hexpand(True)
            check.connect("toggled", self._on_color_toggled, color)
            color.set_sensitive(False)
            form.attach(check, index, color_row, 1, 1)
            form.attach(color, index, color_row + 1, 1, 1)
            self.color_checks.append(check)
            self.color_buttons.append(color)

        scroll.add(form)
        root.pack_start(scroll, True, True, 0)

        bottom = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            homogeneous=True,
            hexpand=True,
            vexpand=False,
        )
        self.clear_button = Gtk.Button(label="Сбросить свои данные")
        self.clear_button.connect("clicked", self._on_clear_clicked)
        bottom.pack_start(self.clear_button, True, True, 0)
        self.save_button = Gtk.Button(label="Сохранить")
        self.save_button.connect("clicked", self._on_save_clicked)
        bottom.pack_start(self.save_button, True, True, 0)
        root.pack_end(bottom, False, False, 0)

        self.content.add(root)
        self.content.show_all()
        self._request_snapshot()

    def activate(self):
        self._request_snapshot()

    def deactivate(self):
        if hasattr(self._screen, "remove_keyboard"):
            self._screen.remove_keyboard()

    def _on_refresh_clicked(self, _widget):
        self._request_snapshot(force=True)

    @staticmethod
    def _on_color_toggled(check, color):
        color.set_sensitive(check.get_active())

    def _on_slot_clicked(self, _widget, slot):
        if self._save_pending:
            return
        self._selected_slot = slot
        self._load_selected_slot()

    def _request_snapshot(self, force=False):
        if self._request_pending and not force:
            return
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self.summary.set_text("Катушки IFS: Moonraker не подключён")
            self._set_write_sensitive(False)
            return
        self._request_pending = True
        if not ws.send_method(SNAPSHOT_METHOD, {}, self._snapshot_response):
            self._request_pending = False
            self.summary.set_text("Катушки IFS: не удалось запросить состояние")
            self._set_write_sensitive(False)

    def _snapshot_response(self, response, _method, _params):
        self._request_pending = False
        if not isinstance(response, dict) or "error" in response:
            logging.error("Plugins AD5X IFS metadata snapshot failed: %s", response)
            self.summary.set_text("Катушки IFS: ошибка backend")
            self._set_write_sensitive(False)
            return
        payload = response.get("result", response)
        if not isinstance(payload, dict):
            self.summary.set_text("Катушки IFS: некорректный ответ backend")
            self._set_write_sensitive(False)
            return
        self._render_snapshot(payload)

    def _render_snapshot(self, snapshot):
        module = (snapshot.get("modules") or {}).get("ifs")
        self._last_module = module if isinstance(module, dict) else None
        if not isinstance(module, dict):
            self.summary.set_text("Катушки IFS: модуль пока не опубликован")
            self._slot_data = {}
            self._set_write_sensitive(False)
            return

        slots = module.get("slots") or []
        self._slot_data = {
            item.get("slot"): item
            for item in slots
            if isinstance(item, dict) and isinstance(item.get("slot"), int)
        }
        if self._selected_slot not in self._slot_data:
            active = int(module.get("active_slot") or 0)
            self._selected_slot = active if active in self._slot_data else 1

        store = module.get("metadata_store") or {}
        status = store.get("status") or "missing"
        if status == "invalid":
            self.summary.set_text(
                f"Катушки IFS: хранилище повреждено ({store.get('error') or 'unknown'})"
            )
            self._set_write_sensitive(False)
        else:
            self.summary.set_text("Катушки IFS: ручные данные сохраняются отдельно от Flashforge")
            self._set_write_sensitive(not self._save_pending)
        self._load_selected_slot()

    def _load_selected_slot(self):
        data = self._slot_data.get(self._selected_slot, {})
        spool = data.get("spool") if isinstance(data.get("spool"), dict) else {}
        appearance = (
            data.get("appearance") if isinstance(data.get("appearance"), dict) else {}
        )
        self._loading_form = True
        try:
            for key, entry in self.entries.items():
                entry.set_text(str(spool.get(key) or ""))
            mode = appearance.get("color_mode") or "solid"
            if not self.color_mode.set_active_id(mode):
                self.color_mode.set_active_id("solid")
            finish = appearance.get("finish") or "standard"
            if not self.finish.set_active_id(finish):
                self.finish.set_active_id("standard")

            colors = appearance.get("colors")
            if not isinstance(colors, list):
                colors = []
            for index, (check, button) in enumerate(
                zip(self.color_checks, self.color_buttons)
            ):
                enabled = index < len(colors)
                check.set_active(enabled)
                button.set_sensitive(enabled)
                rgba = Gdk.RGBA()
                value = colors[index] if enabled else "#FFFFFF"
                if not rgba.parse(value):
                    rgba.parse("#FFFFFF")
                button.set_rgba(rgba)
        finally:
            self._loading_form = False

        source = spool.get("source") or "unknown"
        source_name = SOURCE_NAMES.get(source, str(source))
        presence = "филамент есть" if data.get("present") else "физически пусто"
        metadata_status = data.get("metadata_status") or "none"
        self.source.set_text(
            f"Слот {self._selected_slot}: {source_name} • {presence} • {metadata_status}"
        )
        for slot, button in self.slot_buttons.items():
            marker = "▸ " if slot == self._selected_slot else ""
            active = " ★" if data and slot == int((self._last_module or {}).get("active_slot") or 0) else ""
            button.set_label(f"{marker}Слот {slot}{active}")

        can_write = self._store_writable() and not self._save_pending
        self._set_write_sensitive(can_write)
        self.clear_button.set_sensitive(can_write and source == "manual")

    def _store_writable(self):
        if not isinstance(self._last_module, dict):
            return False
        store = self._last_module.get("metadata_store") or {}
        return (store.get("status") or "missing") != "invalid"

    def _set_write_sensitive(self, sensitive):
        self.save_button.set_sensitive(sensitive)
        self.clear_button.set_sensitive(sensitive)
        for entry in self.entries.values():
            entry.set_sensitive(sensitive)
        self.color_mode.set_sensitive(sensitive)
        self.finish.set_sensitive(sensitive)
        for check, button in zip(self.color_checks, self.color_buttons):
            check.set_sensitive(sensitive)
            button.set_sensitive(sensitive and check.get_active())

    @staticmethod
    def _rgba_hex(button):
        rgba = button.get_rgba()
        values = [
            max(0, min(255, int(round(component * 255))))
            for component in (rgba.red, rgba.green, rgba.blue)
        ]
        return "#{:02X}{:02X}{:02X}".format(*values)

    def _collect_metadata(self):
        spool = {key: entry.get_text().strip() for key, entry in self.entries.items()}
        colors = [
            self._rgba_hex(button)
            for check, button in zip(self.color_checks, self.color_buttons)
            if check.get_active()
        ]
        appearance = {
            "color_mode": self.color_mode.get_active_id() or "solid",
            "colors": colors,
            "finish": self.finish.get_active_id() or "standard",
        }
        return spool, appearance

    def _on_save_clicked(self, _widget):
        if self._save_pending or not self._store_writable():
            return
        spool, appearance = self._collect_metadata()
        self._send_metadata(
            {
                "slot": self._selected_slot,
                "spool": spool,
                "appearance": appearance,
            }
        )

    def _on_clear_clicked(self, _widget):
        if self._save_pending or not self._store_writable():
            return
        self._send_metadata({"slot": self._selected_slot, "clear": True})

    def _send_metadata(self, params):
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self._screen.show_popup_message("IFS: Moonraker не подключён", level=2)
            return
        if hasattr(self._screen, "remove_keyboard"):
            self._screen.remove_keyboard()
        self._save_pending = True
        self._set_write_sensitive(False)
        if not ws.send_method(METADATA_METHOD, params, self._metadata_response):
            self._save_pending = False
            self._screen.show_popup_message("IFS: не удалось сохранить данные катушки", level=2)
            self._load_selected_slot()

    def _metadata_response(self, response, _method, _params):
        self._save_pending = False
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
            self._screen.show_popup_message("IFS: некорректный ответ сохранения", level=2)
            self._request_snapshot(force=True)
            return
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            self._render_snapshot(snapshot)
        if not payload.get("ok", False):
            self._screen.show_popup_message(
                f"IFS: {payload.get('error') or 'данные не сохранены'}", level=2
            )
            return
        result = payload.get("result") or "updated"
        if result == "cleared":
            message = "IFS: свои данные сброшены, снова используется Flashforge/Z-Mod"
        else:
            message = f"IFS: данные слота {payload.get('slot')} сохранены"
        self._screen.show_popup_message(message, level=1)

    def process_update(self, action, _data):
        if action == SNAPSHOT_NOTIFICATION:
            self._request_snapshot()
        elif action in ("notify_klippy_ready", "notify_klippy_disconnected"):
            self._request_snapshot(force=True)
