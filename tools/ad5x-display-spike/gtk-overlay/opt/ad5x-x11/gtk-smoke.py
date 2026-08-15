#!/bin/python3
import signal
import sys

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango


def log(message):
    print(message, flush=True)


surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
ctx = cairo.Context(surface)
ctx.set_source_rgb(0.10, 0.30, 0.55)
ctx.paint()
log(f"PYCAIRO_OK version={cairo.version} cairo={cairo.cairo_version_string()}")
log(
    "GI_OK "
    f"gtk={Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()} "
    f"pango={Pango.version_string()}"
)

window = Gtk.Window(title="AD5X GTK3 smoke")
window.set_decorated(False)
window.set_default_size(800, 480)
window.set_resizable(False)
window.connect("destroy", Gtk.main_quit)

root = Gtk.EventBox()
root.set_name("ad5x-smoke-root")
root.set_events(
    Gdk.EventMask.BUTTON_PRESS_MASK
    | Gdk.EventMask.BUTTON_RELEASE_MASK
    | Gdk.EventMask.POINTER_MOTION_MASK
)

box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
box.set_halign(Gtk.Align.CENTER)
box.set_valign(Gtk.Align.CENTER)

headline = Gtk.Label(label="AD5X GTK3 / PyGObject")
headline.set_name("ad5x-smoke-headline")
status = Gtk.Label(label="X11 + GTK3 + gi + pycairo OK\nTouch the screen")
status.set_name("ad5x-smoke-status")
status.set_justify(Gtk.Justification.CENTER)

box.pack_start(headline, False, False, 0)
box.pack_start(status, False, False, 0)
root.add(box)
window.add(root)

css = Gtk.CssProvider()
css.load_from_data(
    b"""
    #ad5x-smoke-root {
        background-color: #17324d;
        color: #ffffff;
    }
    #ad5x-smoke-headline {
        color: #ffffff;
        font-family: DejaVu Sans;
        font-size: 34px;
        font-weight: bold;
    }
    #ad5x-smoke-status {
        color: #d8f3ff;
        font-family: DejaVu Sans;
        font-size: 22px;
    }
    """
)
screen = Gdk.Screen.get_default()
if screen is None:
    raise RuntimeError("Gdk.Screen.get_default() returned None")
Gtk.StyleContext.add_provider_for_screen(
    screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
)


def on_press(_widget, event):
    log(f"GTK_TOUCH_OK press x={event.x:.1f} y={event.y:.1f}")
    return True


def on_release(_widget, event):
    log(f"GTK_TOUCH_OK release x={event.x:.1f} y={event.y:.1f}")
    return True


root.connect("button-press-event", on_press)
root.connect("button-release-event", on_release)


def request_exit(_signum, _frame):
    GLib.idle_add(Gtk.main_quit)


signal.signal(signal.SIGINT, request_exit)
signal.signal(signal.SIGTERM, request_exit)

window.show_all()
window.move(0, 0)
log("GTK_WINDOW_READY size=800x480")
Gtk.main()
log("GTK_SMOKE_EXIT")
sys.exit(0)
