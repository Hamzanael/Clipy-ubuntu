"""GTK application: tray icon, clipboard monitoring, popup menus and hotkeys."""

import importlib
import os
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, __version__, autostart, paste  # noqa: E402
from . import menu_model as mm  # noqa: E402
from .config import Settings, data_dir  # noqa: E402
from .storage import KIND_IMAGE, KIND_TEXT, Database  # noqa: E402

AppIndicator = None
for _name, _version in (("AyatanaAppIndicator3", "0.1"), ("AppIndicator3", "0.1")):
    try:
        gi.require_version(_name, _version)
        AppIndicator = importlib.import_module(f"gi.repository.{_name}")
        break
    except (ValueError, ImportError):
        continue

Keybinder = None
try:
    gi.require_version("Keybinder", "3.0")
    from gi.repository import Keybinder  # noqa: E402
except (ValueError, ImportError):
    Keybinder = None

ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "icons")

# Password managers mark secrets with these clipboard targets.
CONCEALED_TARGETS = {"x-kde-passwordManagerHint", "application/x-nspasteboard-concealed-type"}
PASTE_DELAY_MS = 150


class ClipyApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.settings = Settings()
        self.db = None
        self.builder = mm.MenuBuilder(self.settings)
        self.indicator = None
        self.status_icon = None
        self.tray_menu = None
        self.clipboard = None
        self.bound_shortcuts = []
        self.snippet_editor = None
        self.preferences = None
        self._menu_dirty = False
        self._popup_menu = None
        self._last_popup = 0.0

        self.add_main_option("menu", ord("m"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Pop up a menu: main, history or snippet", "TYPE")
        self.add_main_option("snippets", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Open the snippet editor", None)
        self.add_main_option("preferences", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Open the preferences window", None)
        self.add_main_option("clear-history", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Clear the clipboard history", None)
        self.add_main_option("quit", ord("q"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Quit the running instance", None)
        self.add_main_option("version", ord("v"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Show the version", None)

    # --------------------------------------------------------------- lifecycle

    def do_handle_local_options(self, options):
        if options.contains("version"):
            print(f"{APP_NAME} for Linux {__version__}")
            return 0
        return -1

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.db = Database(data_dir() / "clipy.db")
        self.db.connect(self.invalidate_menus)
        # The autostart file is the source of truth; it may have been removed by hand.
        self.settings["launch_at_login"] = autostart.is_enabled()
        self.settings.connect(self.on_setting_changed)
        self.hold()  # keep running without windows

        self.setup_tray()
        self.setup_clipboard()
        self.bind_shortcuts()
        self.db.trim_history(self.settings["max_history"], not self.settings["reorder_after_paste"])
        self.rebuild_tray_menu()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if options.get("quit"):
            self.quit()
        elif options.get("clear-history"):
            self.clear_history()
        elif options.get("snippets"):
            self.show_snippet_editor()
        elif options.get("preferences"):
            self.show_preferences()
        elif options.get("menu"):
            menu_type = options["menu"].lower()
            if menu_type not in mm.MENU_TYPES:
                command_line.printerr(f"Unknown menu type '{menu_type}'. Use: {', '.join(mm.MENU_TYPES)}\n")
                return 1
            # Let the invoking shortcut's key release reach the focused app first.
            GLib.timeout_add(50, lambda: self.popup(menu_type) and False)
        return 0

    def do_shutdown(self):
        if self.db is not None:
            if self.settings["clear_history_on_quit"]:
                self.db.clear_history()
            self.db.close()
        Gtk.Application.do_shutdown(self)

    # --------------------------------------------------------------------- tray

    def setup_tray(self):
        mode = self.settings["tray_icon"]
        if AppIndicator is not None:
            self.indicator = AppIndicator.Indicator.new(
                "clipy", self._tray_icon_name(), AppIndicator.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_icon_theme_path(ICON_DIR)
            self.indicator.set_title(APP_NAME)
            self.indicator.set_status(
                AppIndicator.IndicatorStatus.PASSIVE if mode == "hidden" else AppIndicator.IndicatorStatus.ACTIVE)
        else:
            self.status_icon = Gtk.StatusIcon()
            self.status_icon.set_from_file(os.path.join(ICON_DIR, self._tray_icon_name() + ".png"))
            self.status_icon.set_tooltip_text(APP_NAME)
            self.status_icon.set_visible(mode != "hidden")
            self.status_icon.connect("popup-menu", self._on_status_icon_menu)
            self.status_icon.connect("activate", lambda *_: self._on_status_icon_menu(None, 1, Gtk.get_current_event_time()))

    def _tray_icon_name(self):
        return "clipy-tray-dark" if self.settings["tray_icon"] == "dark" else "clipy-tray-light"

    def _on_status_icon_menu(self, _icon, button, time):
        self.rebuild_tray_menu()
        self.tray_menu.popup(None, None, Gtk.StatusIcon.position_menu, self.status_icon, button, time)

    def update_tray_icon(self):
        mode = self.settings["tray_icon"]
        if self.indicator is not None:
            self.indicator.set_icon_full(self._tray_icon_name(), APP_NAME)
            self.indicator.set_status(
                AppIndicator.IndicatorStatus.PASSIVE if mode == "hidden" else AppIndicator.IndicatorStatus.ACTIVE)
        elif self.status_icon is not None:
            self.status_icon.set_from_file(os.path.join(ICON_DIR, self._tray_icon_name() + ".png"))
            self.status_icon.set_visible(mode != "hidden")

    def invalidate_menus(self):
        # Coalesce bursts of database changes into a single rebuild.
        if not self._menu_dirty:
            self._menu_dirty = True
            GLib.idle_add(self.rebuild_tray_menu)

    def rebuild_tray_menu(self):
        self._menu_dirty = False
        self.tray_menu = self.build_gtk_menu(mm.MAIN)
        if self.indicator is not None:
            self.indicator.set_menu(self.tray_menu)
        return False

    # ------------------------------------------------------------------- menus

    def menu_model(self, menu_type):
        s = self.settings
        clips = self.db.clips(sort_by_created=not s["reorder_after_paste"], limit=s["max_history"])
        return self.builder.build(menu_type, clips, self.db.folder_details())

    def build_gtk_menu(self, menu_type, nodes=None):
        menu = Gtk.Menu()
        for node in self.menu_model(menu_type) if nodes is None else nodes:
            menu.append(self._gtk_item(node))
        menu.show_all()
        return menu

    def _gtk_item(self, node):
        if isinstance(node, mm.Separator):
            return Gtk.SeparatorMenuItem()
        if isinstance(node, mm.Label):
            item = Gtk.MenuItem(label=node.title)
            item.set_sensitive(False)
            return item
        if isinstance(node, mm.Submenu):
            item = self._menu_item(node.title, icon_name=node.icon)
            item.set_submenu(self.build_gtk_menu(None, node.children))
            return item

        item = self._menu_item(node.title, number=node.number, icon_name=node.icon, image=node.image)
        if node.tooltip:
            item.set_tooltip_text(node.tooltip)
        item.connect("activate", self.on_item_activated, node.action, node.payload)
        return item

    def _menu_item(self, title, number=None, icon_name=None, image=None):
        """A menu item whose leading list number (0-9) acts as its keyboard mnemonic."""
        label = Gtk.Label(xalign=0)
        escaped = title.replace("_", "__")
        prefix = f"{number}."
        if number is not None and 0 <= number <= 9 and self.settings["mark_with_numbers"] and title.startswith(prefix):
            label.set_text_with_mnemonic("_" + escaped)
        else:
            label.set_text_with_mnemonic(escaped)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        picture = self._thumbnail(image) if image else None
        if picture is None and icon_name:
            picture = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        if picture is not None:
            box.pack_start(picture, False, False, 0)
        box.pack_start(label, True, True, 0)

        item = Gtk.MenuItem()
        item.add(box)
        label.set_mnemonic_widget(item)
        return item

    def _thumbnail(self, data):
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pixbuf = loader.get_pixbuf()
        except GLib.Error:
            return None
        max_w, max_h = self.settings["thumbnail_width"], self.settings["thumbnail_height"]
        scale = min(max_w / pixbuf.get_width(), max_h / pixbuf.get_height(), 1.0)
        width, height = max(1, int(pixbuf.get_width() * scale)), max(1, int(pixbuf.get_height() * scale))
        return Gtk.Image.new_from_pixbuf(pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR))

    def popup(self, menu_type):
        # A shortcut bound both here and as a desktop shortcut would fire twice.
        now = time.monotonic()
        if now - self._last_popup < 0.3:
            return
        self._last_popup = now
        self._popup_menu = self.build_gtk_menu(menu_type)
        self._show_popup(self._popup_menu)

    def popup_snippet_folder(self, folder_id):
        for folder, snippets in self.db.folder_details():
            if folder.id == folder_id:
                submenu = self.builder.folder_submenu(folder, snippets, with_label=True)
                self._popup_menu = self.build_gtk_menu(None, submenu.children)
                self._show_popup(self._popup_menu)
                return

    def _show_popup(self, menu):
        event_time = Gtk.get_current_event_time() or Gdk.CURRENT_TIME
        # popup() without a trigger event is deprecated, but it is the only way
        # to show a menu at the pointer from a background process on X11.
        menu.popup(None, None, None, None, 0, event_time)
        first = next((c for c in menu.get_children() if c.get_sensitive() and not isinstance(c, Gtk.SeparatorMenuItem)), None)
        if first is not None:
            menu.select_item(first)

    # ----------------------------------------------------------------- actions

    def on_item_activated(self, _item, action, payload):
        if action == mm.PASTE_CLIP:
            self.paste_clip(payload)
        elif action == mm.PASTE_SNIPPET:
            snippet = self.db.snippet(payload)
            if snippet:
                self.paste_text(snippet.content)
        elif action == mm.CLEAR_HISTORY:
            self.clear_history()
        elif action == mm.EDIT_SNIPPETS:
            self.show_snippet_editor()
        elif action == mm.PREFERENCES:
            self.show_preferences()
        elif action == mm.QUIT:
            self.quit()

    def paste_clip(self, clip_id):
        clip = self.db.clip(clip_id)
        if clip is None:
            return
        if clip.kind == KIND_IMAGE:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(clip.image)
            loader.close()
            self.clipboard.set_image(loader.get_pixbuf())
            self.clipboard.store()
            self._send_paste()
        else:
            self.paste_text(clip.text)

    def paste_text(self, text):
        self.clipboard.set_text(text, -1)
        self.clipboard.store()
        self._send_paste()

    def _send_paste(self):
        if not self.settings["paste_automatically"]:
            return
        # Give the menu time to close and focus to return to the target window.
        GLib.timeout_add(PASTE_DELAY_MS, lambda: paste.send_paste(self.settings["paste_keys"]) and False)

    def clear_history(self):
        if self.settings["confirm_clear_history"]:
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text="Clear History",
            )
            dialog.format_secondary_text("Are you sure you want to clear your clipboard history?")
            dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Clear History", Gtk.ResponseType.OK)
            dont_ask = Gtk.CheckButton(label="Do not ask again")
            dialog.get_message_area().pack_start(dont_ask, False, False, 0)
            dialog.set_keep_above(True)
            dialog.show_all()
            dialog.present()
            response = dialog.run()
            suppress = dont_ask.get_active()
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return
            if suppress:
                self.settings["confirm_clear_history"] = False
        self.db.clear_history()

    def show_snippet_editor(self):
        from .snippet_editor import SnippetEditor
        if self.snippet_editor is None:
            self.snippet_editor = SnippetEditor(self)
            self.snippet_editor.connect("destroy", lambda *_: setattr(self, "snippet_editor", None))
        self.snippet_editor.present()

    def show_preferences(self):
        from .preferences import PreferencesWindow
        if self.preferences is None:
            self.preferences = PreferencesWindow(self)
            self.preferences.connect("destroy", lambda *_: setattr(self, "preferences", None))
        self.preferences.present()

    def on_setting_changed(self, key, _value):
        if key == "tray_icon":
            self.update_tray_icon()
        elif key.endswith("_shortcut"):
            self.bind_shortcuts()
        elif key == "launch_at_login":
            autostart.set_enabled(self.settings["launch_at_login"])
        elif key == "max_history":
            self.db.trim_history(self.settings["max_history"], not self.settings["reorder_after_paste"])
        self.invalidate_menus()

    # ---------------------------------------------------------------- clipboard

    def setup_clipboard(self):
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.clipboard.connect("owner-change", self.on_clipboard_changed)

    def on_clipboard_changed(self, clipboard, _event):
        clipboard.request_targets(self._on_targets)

    def _on_targets(self, clipboard, atoms, *_):
        targets = {atom.name() for atom in atoms or []}
        if not targets:
            return
        if self.settings["ignore_concealed_types"] and targets & CONCEALED_TARGETS:
            return
        if any(t in targets for t in ("UTF8_STRING", "STRING", "TEXT", "text/plain", "text/plain;charset=utf-8")):
            clipboard.request_text(self._on_text)
        elif self.settings["store_images"] and any(t.startswith("image/") for t in targets):
            clipboard.request_image(self._on_image)

    def _save(self, kind, text=None, image=None):
        s = self.settings
        self.db.add_clip(
            kind, text=text, image=image,
            overwrite_same=s["overwrite_same_history"],
            copy_same=s["copy_same_history"],
            max_history=s["max_history"],
            sort_by_created=not s["reorder_after_paste"],
        )

    def _on_text(self, _clipboard, text):
        if text:
            self._save(KIND_TEXT, text=text)

    def _on_image(self, _clipboard, pixbuf):
        if pixbuf is None:
            return
        ok, data = pixbuf.save_to_bufferv("png", [], [])
        if ok:
            self._save(KIND_IMAGE, image=bytes(data))

    # ---------------------------------------------------------------- shortcuts

    def bind_shortcuts(self):
        """Register global hotkeys through Keybinder (X11 only)."""
        if Keybinder is None or paste.session_type() == "wayland":
            return
        if not self.bound_shortcuts:
            Keybinder.init()
        for accel in self.bound_shortcuts:
            Keybinder.unbind(accel)
        self.bound_shortcuts = []
        for menu_type in mm.MENU_TYPES:
            accel = self.settings[f"{menu_type}_shortcut"]
            if accel and Keybinder.bind(accel, lambda _keystring, t: self.popup(t), menu_type):
                self.bound_shortcuts.append(accel)
            elif accel:
                print(f"clipy: could not bind shortcut {accel}", file=sys.stderr)


def main(argv=None):
    # Clipboard monitoring and menu popups need X11 (XWayland on Wayland sessions):
    # GTK3's native Wayland backend only sees the clipboard while focused.
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and "CLIPY_ALLOW_WAYLAND" not in os.environ:
        os.environ["GDK_BACKEND"] = "x11"
    app = ClipyApplication()
    return app.run(sys.argv if argv is None else argv)
