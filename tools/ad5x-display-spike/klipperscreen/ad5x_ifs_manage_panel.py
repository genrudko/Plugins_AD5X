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

STORE_NAMES = {
    "ok": "Готов",
    "missing": "Пока пуст — будет создан при сохранении",
    "invalid": "Ошибка хранилища",
}


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "IFS — детали")
        self._request_pending = False
        self._last_revision = None

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
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
            label="IFS: загрузка…",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.summary.set_line_wrap(True)
        self.summary.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        top.pack_start(self.summary, True, True, 0)

        refresh = self._gtk.Button("refresh", style="color3")
        refresh.connect("clicked", self._on_refresh_clicked)
        top.pack_end(refresh, False, False, 0)
        root.pack_start(top, False, False, 0)

        details = Gtk.Grid(
            column_spacing=12,
            row_spacing=6,
            hexpand=True,
            vexpand=True,
        )
        self.values = {}
        rows = [
            ("head", "Филамент у головы"),
            ("print", "Состояние печати"),
            ("operation", "Операция IFS"),
            ("metadata", "Метаданные катушек"),
            ("mapping", "Карта инструментов"),
            ("silk", "Silk mask"),
            ("raw_channel", "F13 channel"),
            ("stall", "Stall mask"),
        ]
        for row, (key, label) in enumerate(rows):
            name = Gtk.Label(
                label=label,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
                xalign=0,
            )
            name.set_markup(f"<b>{label}</b>")
            value = Gtk.Label(
                label="—",
                hexpand=True,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
                xalign=0,
            )
            value.set_line_wrap(True)
            value.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            self.values[key] = value
            details.attach(name, 0, row, 1, 1)
            details.attach(value, 1, row, 1, 1)
        root.pack_start(details, True, True, 0)

        note = Gtk.Label(
            label=(
                "Катушки, материал, несколько цветов и тип поверхности сохраняются "
                "через Plugins AD5X и не меняют штатный Flashforge JSON. "
                "Cold-eject/recovery останутся отдельными flows после аппаратного доказательства."
            ),
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        note.set_line_wrap(True)
        note.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        root.pack_start(note, False, False, 0)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            homogeneous=True,
            hexpand=True,
            vexpand=False,
        )
        metadata = Gtk.Button(label="Катушки")
        metadata.connect("clicked", self._on_metadata_clicked)
        actions.pack_start(metadata, True, True, 0)

        spoolman = Gtk.Button(label="Spoolman")
        spoolman.set_sensitive(bool(getattr(self._printer, "spoolman", False)))
        spoolman.connect("clicked", self.menu_item_clicked, {"panel": "spoolman"})
        actions.pack_start(spoolman, True, True, 0)
        root.pack_end(actions, False, False, 0)

        self.content.add(root)
        self.content.show_all()
        self._request_snapshot()

    def activate(self):
        self._request_snapshot()

    def _on_refresh_clicked(self, _widget):
        self._request_snapshot(force=True)

    def _on_metadata_clicked(self, _widget):
        self._screen.show_panel("ad5x_ifs_metadata", "IFS — катушки")

    def _request_snapshot(self, force=False):
        if self._request_pending and not force:
            return
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self.summary.set_text("IFS: Moonraker не подключён")
            return
        self._request_pending = True
        if not ws.send_method(SNAPSHOT_METHOD, {}, self._snapshot_response):
            self._request_pending = False
            self.summary.set_text("IFS: не удалось запросить состояние")

    def _snapshot_response(self, response, _method, _params):
        self._request_pending = False
        if not isinstance(response, dict) or "error" in response:
            logging.error("Plugins AD5X IFS manage snapshot failed: %s", response)
            self.summary.set_text("IFS: ошибка backend")
            return
        payload = response.get("result", response)
        if not isinstance(payload, dict):
            self.summary.set_text("IFS: некорректный ответ backend")
            return
        self._render_snapshot(payload)

    def _render_snapshot(self, snapshot):
        self._last_revision = snapshot.get("revision")
        module = (snapshot.get("modules") or {}).get("ifs")
        if not isinstance(module, dict):
            self.summary.set_text("IFS: модуль пока не опубликован")
            return
        if not module.get("available", False):
            self.summary.set_text(f"IFS: недоступен ({module.get('reason', 'unknown')})")
            return

        state = STATE_NAMES.get(module.get("state"), module.get("state") or "Неизвестно")
        active = int(module.get("active_slot") or 0)
        self.summary.set_text(
            f"IFS: {state}" + (f"   •   активный слот {active}" if active else "")
        )

        head = module.get("filament_at_toolhead")
        self.values["head"].set_text(
            "Есть" if head is True else "Нет" if head is False else "Нет достоверных данных"
        )
        self.values["print"].set_text(str(module.get("print_state") or "unknown"))

        operation = module.get("operation") or {}
        if operation.get("state") == "running":
            op = f"{operation.get('action') or 'operation'} / slot {operation.get('slot') or '—'}"
        elif operation.get("error"):
            op = f"idle / последняя ошибка: {operation.get('error')}"
        else:
            op = "idle"
        self.values["operation"].set_text(op)

        store = module.get("metadata_store") or {}
        store_status = store.get("status") or "missing"
        store_text = STORE_NAMES.get(store_status, str(store_status))
        if store.get("error"):
            store_text += f" ({store.get('error')})"
        self.values["metadata"].set_text(store_text)

        mapping = module.get("tool_mapping")
        if isinstance(mapping, list) and mapping:
            self.values["mapping"].set_text(
                "   ".join(f"T{i}→{slot}" for i, slot in enumerate(mapping))
            )
        else:
            self.values["mapping"].set_text("—")

        diagnostics = module.get("diagnostics") or {}
        self.values["silk"].set_text(
            str(diagnostics.get("silk_mask", module.get("silk_mask", 0)))
        )
        runtime_active = diagnostics.get(
            "runtime_active_slot", module.get("runtime_active_slot", 0)
        )
        raw_channel = diagnostics.get("raw_channel", module.get("raw_channel", 0))
        self.values["raw_channel"].set_text(
            f"raw={raw_channel}, bridge_cur_port={runtime_active}"
        )
        self.values["stall"].set_text(
            str(diagnostics.get("stall_mask", module.get("stall_mask", 0)))
        )

    def process_update(self, action, _data):
        if action == SNAPSHOT_NOTIFICATION:
            self._request_snapshot()
        elif action in ("notify_klippy_ready", "notify_klippy_disconnected"):
            self._request_snapshot(force=True)
