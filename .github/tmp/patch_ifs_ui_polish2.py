from pathlib import Path

p = Path('tools/ad5x-display-spike/klipperscreen/ad5x_ifs_panel.py')
s = p.read_text()

old = '''        provider = Gtk.CssProvider()\n        provider.load_from_data(\n            (\n                "* { border: 2px solid %s; border-radius: 10px; "\n                "background-color: %s; }" % (border, background)\n            ).encode("utf-8")\n        )\n        widgets["card"].get_style_context().add_provider(\n            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION\n        )\n        widgets["card"]._ad5x_card_css_provider = provider\n'''
new = '''        context = widgets["card"].get_style_context()\n        old_provider = getattr(widgets["card"], "_ad5x_card_css_provider", None)\n        if old_provider is not None:\n            context.remove_provider(old_provider)\n        provider = Gtk.CssProvider()\n        provider.load_from_data(\n            (\n                "* { border: 2px solid %s; border-radius: 10px; "\n                "background-color: %s; }" % (border, background)\n            ).encode("utf-8")\n        )\n        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)\n        widgets["card"]._ad5x_card_css_provider = provider\n'''
assert old in s
s = s.replace(old, new, 1)

old = '''        if slot == active:\n            widgets["title"].set_markup(\n                f"<big><b>Слот {slot}</b></big>  <small>АКТИВНЫЙ</small>"\n            )\n        else:\n            widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")\n'''
new = '''        widgets["title"].set_markup(f"<big><b>Слот {slot}</b></big>")\n'''
assert s.count(old) == 2
s = s.replace(old, new, 2)

p.write_text(s)
