from pathlib import Path
import re

panel = Path('tools/ad5x-display-spike/klipperscreen/ad5x_ifs_panel.py')
s = panel.read_text()

# Four physical IFS lanes should read as one horizontal MMU bank.
s, n = re.subn(
    r'''        for slot in range\(1, 5\):\n            card, widgets = self\._make_slot_card\(slot\)\n            self\._slot_widgets\[slot\] = widgets\n            col = \(slot - 1\) % 2\n            row = \(slot - 1\) // 2\n            grid\.attach\(card, col, row, 1, 1\)\n        root\.pack_start\(grid, True, True, 0\)\n''',
    '''        for slot in range(1, 5):\n            card, widgets = self._make_slot_card(slot)\n            self._slot_widgets[slot] = widgets\n            grid.attach(card, slot - 1, 0, 1, 1)\n        root.pack_start(grid, True, True, 0)\n\n        self.path = Gtk.Label(\n            label="Тракт: —",\n            hexpand=True,\n            halign=Gtk.Align.START,\n            valign=Gtk.Align.CENTER,\n            xalign=0,\n        )\n        self.path.set_ellipsize(Pango.EllipsizeMode.END)\n        root.pack_start(self.path, False, False, 0)\n''',
    s,
    count=1,
)
assert n == 1, 'grid layout block not found'

s = s.replace('action_bar.pack_end(button, False, False, 0)',
              'action_bar.pack_start(button, False, False, 0)', 1)
s = s.replace('spacing=2,\n            margin=5,', 'spacing=3,\n            margin=7,', 1)
s = s.replace('swatch.set_size_request(-1, 16)', 'swatch.set_size_request(-1, 24)', 1)

old = '''        box.pack_start(title, False, False, 0)\n        box.pack_start(material, False, False, 0)\n        box.pack_start(detail, False, False, 0)\n        box.pack_start(state, False, False, 0)\n        box.pack_end(swatch, False, False, 0)\n'''
new = '''        box.pack_start(title, False, False, 0)\n        box.pack_start(swatch, False, False, 0)\n        box.pack_start(material, False, False, 0)\n        box.pack_start(detail, False, False, 0)\n        box.pack_end(state, False, False, 0)\n'''
assert old in s, 'card child order block not found'
s = s.replace(old, new, 1)

pattern = re.compile(
    r'''    @staticmethod\n    def _set_background\(widget, color\):\n.*?\n    def _render_swatch\(self, container, appearance, present\):\n''',
    re.S,
)
replacement = '''    @staticmethod\n    def _set_background(widget, color):\n        provider = Gtk.CssProvider()\n        provider.load_from_data(\n            (\n                "* { background-color: %s; min-height: 20px; "\n                "border: 1px solid rgba(255,255,255,0.55); border-radius: 3px; }"\n                % color\n            ).encode("utf-8")\n        )\n        widget.get_style_context().add_provider(\n            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION\n        )\n        widget._ad5x_css_provider = provider\n\n    def _apply_card_style(self, slot):\n        widgets = self._slot_widgets.get(slot)\n        if not widgets:\n            return\n        data = widgets.get("data") or {}\n        active = 0\n        if isinstance(self._last_module, dict):\n            active = int(self._last_module.get("active_slot") or 0)\n        selected = slot == self._selected_slot\n        stall = bool(data.get("stall", False))\n\n        if stall:\n            border = "#ffb020"\n        elif slot == active:\n            border = "#39d98a"\n        elif selected:\n            border = "#5da9ff"\n        else:\n            border = "rgba(255,255,255,0.20)"\n\n        if selected:\n            background = "rgba(255,255,255,0.10)"\n        elif slot == active:\n            background = "rgba(57,217,138,0.06)"\n        else:\n            background = "rgba(255,255,255,0.025)"\n\n        provider = Gtk.CssProvider()\n        provider.load_from_data(\n            (\n                "* { border: 2px solid %s; border-radius: 10px; "\n                "background-color: %s; }" % (border, background)\n            ).encode("utf-8")\n        )\n        widgets["card"].get_style_context().add_provider(\n            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION\n        )\n        widgets["card"]._ad5x_card_css_provider = provider\n\n    def _render_swatch(self, container, appearance, present):\n'''
s, n = pattern.subn(replacement, s, count=1)
assert n == 1, '_set_background block not found'

old = '''        widgets = self._slot_widgets[slot]\n        widgets["data"] = data if isinstance(data, dict) else {}\n        selected = slot == self._selected_slot\n        title = f"Слот {slot}"\n        if slot == active:\n            title += "  ★"\n        if selected:\n            title += "  ▸"\n        widgets["title"].set_markup(f"<big><b>{title}</b></big>")\n'''
new = '''        widgets = self._slot_widgets[slot]\n        widgets["data"] = data if isinstance(data, dict) else {}\n        if slot == active:\n            widgets["title"].set_markup(\n                f"<big><b>Слот {slot}</b></big>  <small>АКТИВНЫЙ</small>"\n            )\n        else:\n            widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")\n'''
assert old in s, 'slot title block not found'
s = s.replace(old, new, 1)

old = '''        if not present:\n            widgets["material"].set_text("Пустой слот")\n            if metadata_status == "stale":\n                widgets["detail"].set_text("Сохранено: " + self._spool_title(data))\n            else:\n                widgets["detail"].set_text("Катушка не назначена")\n            widgets["state"].set_text("○ Пусто")\n            self._render_swatch(widgets["swatch"], data.get("appearance"), False)\n            return\n'''
new = '''        if not present:\n            widgets["material"].set_text("Пустой слот")\n            if metadata_status == "stale":\n                widgets["detail"].set_text("Было: " + self._spool_title(data))\n            else:\n                widgets["detail"].set_text("Катушка не назначена")\n            widgets["state"].set_text("○ Пусто")\n            self._render_swatch(widgets["swatch"], data.get("appearance"), False)\n            self._apply_card_style(slot)\n            return\n'''
assert old in s, 'empty slot block not found'
s = s.replace(old, new, 1)

old = '''        if stall:\n            state = "⚠ Филамент остановлен"\n        elif slot == active:\n            state = "● Активный филамент"\n        else:\n            state = "● Филамент установлен"\n        widgets["state"].set_text(state)\n        self._render_swatch(widgets["swatch"], data.get("appearance"), True)\n'''
new = '''        if stall:\n            state = "⚠ ЗАМЯТИЕ"\n        elif slot == active:\n            state = "● В тракте"\n        else:\n            state = "● Загружен"\n        widgets["state"].set_text(state)\n        self._render_swatch(widgets["swatch"], data.get("appearance"), True)\n        self._apply_card_style(slot)\n'''
assert old in s, 'present slot state block not found'
s = s.replace(old, new, 1)

pattern = re.compile(
    r'''    def _render_selection\(self\):\n.*?\n    def _render_action_buttons\(self\):\n''',
    re.S,
)
replacement = '''    def _render_selection(self):\n        active = 0\n        if isinstance(self._last_module, dict):\n            active = int(self._last_module.get("active_slot") or 0)\n        for slot, widgets in self._slot_widgets.items():\n            if slot == active:\n                widgets["title"].set_markup(\n                    f"<big><b>Слот {slot}</b></big>  <small>АКТИВНЫЙ</small>"\n                )\n            else:\n                widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")\n            self._apply_card_style(slot)\n\n        self._render_path()\n        if not self._selected_slot:\n            self.selection.set_text("Выберите слот")\n            return\n        data = self._slot_widgets[self._selected_slot].get("data") or {}\n        if data.get("present"):\n            self.selection.set_text(\n                f"Слот {self._selected_slot} • {self._spool_title(data)}"\n            )\n        else:\n            self.selection.set_text(f"Слот {self._selected_slot} • пусто")\n\n    def _render_path(self):\n        module = self._last_module if isinstance(self._last_module, dict) else {}\n        active = int(module.get("active_slot") or 0)\n        head = module.get("filament_at_toolhead")\n        if not active:\n            self.path.set_text("Тракт: —")\n            return\n        if head is True:\n            head_text = "● Головка"\n        elif head is False:\n            head_text = "○ Головка"\n        else:\n            head_text = "? Головка"\n        self.path.set_text(f"Тракт: Слот {active}  →  IFS  →  {head_text}")\n\n    def _render_action_buttons(self):\n'''
s, n = pattern.subn(replacement, s, count=1)
assert n == 1, 'selection/action boundary not found'

old = '''            widgets["state"].set_text("Нет данных")\n            self._render_swatch(widgets["swatch"], {}, False)\n        self.selection.set_text("Выберите слот")\n'''
new = '''            widgets["state"].set_text("Нет данных")\n            self._render_swatch(widgets["swatch"], {}, False)\n            self._apply_card_style(slot)\n        self.path.set_text("Тракт: —")\n        self.selection.set_text("Выберите слот")\n'''
assert old in s, 'clear slots block not found'
s = s.replace(old, new, 1)

panel.write_text(s)

smoke = Path('tools/ad5x-display-spike/klipperscreen/ifs-panel-target-smoke.py')
q = smoke.read_text()
q = q.replace(
    'assert "Активный филамент" in panel._slot_widgets[1]["state"].get_text()',
    'assert "В тракте" in panel._slot_widgets[1]["state"].get_text()',
)
q = q.replace(
    'assert "Сохранено: Previous TPU" == panel._slot_widgets[4]["detail"].get_text()',
    'assert "Было: Previous TPU" == panel._slot_widgets[4]["detail"].get_text()',
)
needle = 'assert not panel._slot_widgets[4]["swatch"].get_visible()\n'
assert needle in q, 'smoke swatch assertion not found'
q = q.replace(
    needle,
    needle + 'assert panel.path.get_text() == "Тракт: Слот 1  →  IFS  →  ● Головка"\n',
    1,
)
smoke.write_text(q)
