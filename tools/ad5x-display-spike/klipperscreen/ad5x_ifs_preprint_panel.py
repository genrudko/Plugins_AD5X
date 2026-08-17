import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel


PREVIEW_METHOD = "server.plugins_ad5x.ifs.job.preview"
SNAPSHOT_NOTIFICATION = "notify_plugins_ad5x_snapshot_changed"

STATUS_NAMES = {
    "ready": "Готово к сопоставлению",
    "warning": "Есть предупреждения",
    "blocked": "Требуется исправление",
    "unavailable": "План недоступен",
}

WARNING_NAMES = {
    "material_failure": "Нет точного совпадения материала",
    "color_failure": "В G-code нет цвета или цвет не сопоставлен",
    "weak_color": "Z-Mod обнаружил слабое совпадение цвета",
    "duplicate_slot": "Несколько инструментов назначены на один слот",
    "unassigned_tool": "Есть инструмент без назначенного слота",
    "assigned_slot_missing": "Назначенный слот отсутствует в текущем IFS state",
    "assigned_slot_empty": "Назначенный слот физически пуст",
    "no_requirements": "Z-Mod не обнаружил требований к инструментам",
}

ROW_STATE_NAMES = {
    "ready": "✓",
    "unassigned": "—",
    "slot_missing": "!",
    "slot_empty": "○",
}


class Panel(ScreenPanel):
    def __init__(self, screen, title, filename=""):
        super().__init__(screen, title or "IFS — план печати")
        self.filename = filename if isinstance(filename, str) else ""
        self._request_pending = False
        self._last_plan = None
        self._row_widgets = []

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
        self.filename_label = Gtk.Label(
            label=self.filename or "Файл не выбран",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
            ellipsize=Pango.EllipsizeMode.MIDDLE,
        )
        top.pack_start(self.filename_label, True, True, 0)
        refresh = self._gtk.Button("refresh", style="color3")
        refresh.connect("clicked", self._on_refresh_clicked)
        top.pack_end(refresh, False, False, 0)
        root.pack_start(top, False, False, 0)

        self.summary = Gtk.Label(
            label="План: загрузка…" if self.filename else "План: выберите G-code",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        self.summary.set_ellipsize(Pango.EllipsizeMode.END)
        root.pack_start(self.summary, False, False, 0)

        self.warning = Gtk.Label(
            label="",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            lines=2,
        )
        root.pack_start(self.warning, False, False, 0)

        scroll = self._gtk.ScrolledWindow()
        self.rows = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            hexpand=True,
            vexpand=True,
        )
        scroll.add(self.rows)
        root.pack_start(scroll, True, True, 0)

        bottom = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            hexpand=True,
            vexpand=False,
        )
        self.source = Gtk.Label(
            label="Источник: Z-Mod",
            hexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            xalign=0,
        )
        bottom.pack_start(self.source, True, True, 0)
        self.start_button = Gtk.Button(label="Запуск пока закрыт")
        self.start_button.set_sensitive(False)
        bottom.pack_end(self.start_button, False, False, 0)
        root.pack_end(bottom, False, False, 0)

        self.content.add(root)
        self.content.show_all()
        if self.filename:
            self._request_preview()

    def activate(self):
        if self.filename:
            self._request_preview()

    def _on_refresh_clicked(self, _widget):
        if self.filename:
            self._request_preview(force=True)

    def _request_preview(self, force=False):
        if self._request_pending and not force:
            return
        ws = getattr(self._screen, "_ws", None)
        if ws is None or not ws.connected:
            self.summary.set_text("План: Moonraker не подключён")
            return
        self._request_pending = True
        params = {"filename": self.filename}
        if not ws.send_method(PREVIEW_METHOD, params, self._preview_response):
            self._request_pending = False
            self.summary.set_text("План: не удалось отправить запрос")

    def _preview_response(self, response, _method, _params):
        self._request_pending = False
        if not isinstance(response, dict) or "error" in response:
            logging.error("Plugins AD5X IFS job preview failed: %s", response)
            self.summary.set_text("План: ошибка backend")
            return
        payload = response.get("result", response)
        if not isinstance(payload, dict):
            self.summary.set_text("План: некорректный ответ backend")
            return
        if not payload.get("ok", False):
            self.summary.set_text("План: " + str(payload.get("error") or "недоступен"))
            return
        snapshot = payload.get("snapshot")
        if isinstance(snapshot, dict):
            self._render_snapshot(snapshot)

    @staticmethod
    def _spool_title(assignment):
        if not isinstance(assignment, dict):
            return ""
        spool = assignment.get("spool")
        spool = spool if isinstance(spool, dict) else {}
        name = spool.get("name") or ""
        brand = spool.get("brand") or ""
        material = spool.get("material") or ""
        if name:
            return str(name)
        if brand and material:
            return f"{brand} • {material}"
        return str(material or brand or "Без данных")

    @staticmethod
    def _set_swatch(widget, color):
        context = widget.get_style_context()
        old = getattr(widget, "_ad5x_css_provider", None)
        if old is not None:
            context.remove_provider(old)
        provider = Gtk.CssProvider()
        if isinstance(color, str) and color.startswith("#"):
            fill = color
        else:
            fill = "rgba(255,255,255,0.05)"
        provider.load_from_data(
            (
                "* { background-color: %s; min-width: 30px; min-height: 22px; "
                "border: 1px solid rgba(255,255,255,0.65); border-radius: 4px; }"
                % fill
            ).encode("utf-8")
        )
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        widget._ad5x_css_provider = provider

    def _clear_rows(self):
        for child in self.rows.get_children():
            self.rows.remove(child)
        self._row_widgets = []

    def _make_row(self, row):
        tool = int(row.get("tool") or 0)
        requirement = row.get("requirement")
        requirement = requirement if isinstance(requirement, dict) else {}
        assignment = row.get("assignment")
        state = row.get("state") or "unassigned"

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=7,
            hexpand=True,
            vexpand=False,
        )
        box.get_style_context().add_class("frame-item")

        tool_label = Gtk.Label(
            label=f"T{tool}",
            width_chars=3,
            halign=Gtk.Align.START,
            xalign=0,
        )
        tool_label.set_markup(f"<big><b>T{tool}</b></big>")
        box.pack_start(tool_label, False, False, 0)

        swatch = Gtk.EventBox(hexpand=False, vexpand=False)
        self._set_swatch(swatch, requirement.get("color"))
        box.pack_start(swatch, False, False, 0)

        material = requirement.get("material") or "?"
        req = Gtk.Label(
            label=str(material),
            width_chars=8,
            halign=Gtk.Align.START,
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
        )
        box.pack_start(req, False, False, 0)

        arrow = Gtk.Label(label="→")
        box.pack_start(arrow, False, False, 0)

        if isinstance(assignment, dict):
            slot = assignment.get("slot")
            target_text = f"Слот {slot} • {self._spool_title(assignment)}"
        else:
            target_text = "Слот не назначен"
        target = Gtk.Label(
            label=target_text,
            hexpand=True,
            halign=Gtk.Align.START,
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
        )
        box.pack_start(target, True, True, 0)

        state_label = Gtk.Label(
            label=ROW_STATE_NAMES.get(state, "!"),
            width_chars=2,
            halign=Gtk.Align.END,
            xalign=1,
        )
        box.pack_end(state_label, False, False, 0)

        self._row_widgets.append(
            {
                "tool": tool_label,
                "swatch": swatch,
                "requirement": req,
                "target": target,
                "state": state_label,
                "data": row,
            }
        )
        return box

    def _render_snapshot(self, snapshot):
        module = (snapshot.get("modules") or {}).get("ifs")
        if not isinstance(module, dict):
            self._last_plan = None
            self.summary.set_text("План: IFS Manager не опубликован")
            self.warning.set_text("")
            self._clear_rows()
            return

        plan = module.get("preprint_plan")
        if not isinstance(plan, dict):
            self._last_plan = None
            self.summary.set_text("План: backend ещё не публикует preprint_plan")
            self.warning.set_text("")
            self._clear_rows()
            return

        self._last_plan = plan
        filename = plan.get("filename") or self.filename
        if filename:
            self.filename = str(filename)
            self.filename_label.set_text(self.filename)

        status = plan.get("status") or "unavailable"
        summary = plan.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        required = int(summary.get("required_tools") or 0)
        ready = int(summary.get("ready_tools") or 0)
        self.summary.set_text(
            f"План: {STATUS_NAMES.get(status, status)}   •   готово {ready}/{required}"
        )

        warnings = plan.get("warnings")
        warnings = warnings if isinstance(warnings, list) else []
        warning_text = [WARNING_NAMES.get(code, str(code)) for code in warnings]
        self.warning.set_text(" • ".join(warning_text))

        self._clear_rows()
        for row in plan.get("rows") or []:
            if isinstance(row, dict):
                self.rows.pack_start(self._make_row(row), False, False, 0)
        self.rows.show_all()

        source = plan.get("source") or "zmod"
        self.source.set_text(f"Источник сопоставления: {source}")
        self.start_button.set_sensitive(False)
        if status == "blocked":
            self.start_button.set_label("Исправьте сопоставление")
        else:
            self.start_button.set_label("Запуск пока закрыт")

    def process_update(self, action, _data):
        if action == SNAPSHOT_NOTIFICATION and self.filename:
            self._request_preview()
        elif action in ("notify_klippy_ready", "notify_klippy_disconnected") and self.filename:
            self._request_preview(force=True)
