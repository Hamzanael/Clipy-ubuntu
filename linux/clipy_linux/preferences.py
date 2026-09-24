"""Preferences window."""

from gi.repository import Gtk

from . import APP_NAME, paste


class PreferencesWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title=f"{APP_NAME} – Preferences", application=app)
        self.settings = app.settings
        self.set_default_size(520, -1)
        self.set_resizable(False)
        self.set_icon_name("clipy-ubuntu")

        notebook = Gtk.Notebook()
        notebook.set_border_width(8)
        notebook.append_page(self.general_page(), Gtk.Label(label="General"))
        notebook.append_page(self.menu_page(), Gtk.Label(label="Menu"))
        notebook.append_page(self.shortcuts_page(), Gtk.Label(label="Shortcuts"))
        self.add(notebook)
        self.show_all()

    # ------------------------------------------------------------------ pages

    def general_page(self):
        grid = self._grid()
        self._check(grid, "launch_at_login", "Launch Clipy at login")
        self._spin(grid, "max_history", "Maximum clipboard history", 1, 9999)
        self._check(grid, "paste_automatically", "Paste automatically after selecting an item")
        self._entry(grid, "paste_keys", "Paste keystroke",
                    "Keys sent to paste, e.g. ctrl+v, ctrl+shift+v or shift+insert")
        self._check(grid, "reorder_after_paste", "Move pasted items to the top of the history")
        self._check(grid, "overwrite_same_history", "Overwrite identical history items")
        self._check(grid, "copy_same_history", "Save identical items again when copied")
        self._check(grid, "store_images", "Save images")
        self._check(grid, "ignore_concealed_types", "Ignore passwords copied from password managers")
        self._check(grid, "clear_history_on_quit", "Clear history on quit")
        self._combo(grid, "tray_icon", "Status icon",
                    [("light", "Light (for dark panels)"), ("dark", "Dark (for light panels)"), ("hidden", "Hidden")])
        if paste.paste_command(self.settings["paste_keys"]) is None:
            hint = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
            hint.set_markup("<small>Automatic pasting needs <b>xdotool</b> (X11) or <b>ydotool</b>/<b>wtype</b> "
                            "(Wayland). Until one is installed, press Ctrl+V after choosing an item.</small>")
            self._row(grid, hint)
        return grid

    def menu_page(self):
        grid = self._grid()
        self._spin(grid, "inline_items", "Number of items placed inline", 0, 999)
        self._spin(grid, "items_per_folder", "Number of items placed inside a folder", 1, 999)
        self._spin(grid, "max_title_length", "Number of characters in the menu", 3, 999)
        self._check(grid, "mark_with_numbers", "Mark menu items with numbers")
        self._check(grid, "start_numbering_at_zero", "Start numbering at 0")
        self._check(grid, "show_icons", "Show icons in the menu")
        self._check(grid, "show_tooltips", "Show tooltips on menu items")
        self._spin(grid, "max_tooltip_length", "Maximum length of tooltips", 1, 99999)
        self._check(grid, "show_images", "Show image thumbnails in the menu")
        self._spin(grid, "thumbnail_width", "Thumbnail width", 16, 512)
        self._spin(grid, "thumbnail_height", "Thumbnail height", 16, 512)
        self._check(grid, "show_clear_history_item", "Add “Clear History” menu item")
        self._check(grid, "confirm_clear_history", "Ask before clearing the history")
        return grid

    def shortcuts_page(self):
        grid = self._grid()
        tip = "GTK accelerator, e.g. <Primary><Alt>v. Leave empty to disable."
        self._entry(grid, "main_shortcut", "Main menu", tip)
        self._entry(grid, "history_shortcut", "History menu", tip)
        self._entry(grid, "snippet_shortcut", "Snippet menu", tip)
        note = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)
        if paste.session_type() == "wayland":
            note.set_markup(
                "<small>Wayland does not allow apps to register global shortcuts. Add them in "
                "<b>Settings → Keyboard → Custom Shortcuts</b> with the commands "
                "<tt>clipy-ubuntu --menu main</tt>, <tt>--menu history</tt> or <tt>--menu snippet</tt>, "
                "or run <tt>clipy-ubuntu-shortcuts</tt>.</small>")
        else:
            note.set_markup("<small>Shortcuts apply immediately. They can also be set up as desktop "
                            "shortcuts running <tt>clipy-ubuntu --menu main</tt>.</small>")
        self._row(grid, note)
        return grid

    # ---------------------------------------------------------------- helpers

    def _grid(self):
        grid = Gtk.Grid(column_spacing=12, row_spacing=8, border_width=12)
        grid._next_row = 0
        return grid

    def _row(self, grid, widget, label=None):
        row = grid._next_row
        if label is None:
            grid.attach(widget, 0, row, 2, 1)
        else:
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, row, 1, 1)
        grid._next_row += 1

    def _check(self, grid, key, label):
        button = Gtk.CheckButton(label=label)
        button.set_active(self.settings[key])
        button.connect("toggled", lambda b: self.settings.__setitem__(key, b.get_active()))
        self._row(grid, button)

    def _spin(self, grid, key, label, low, high):
        spin = Gtk.SpinButton.new_with_range(low, high, 1)
        spin.set_value(self.settings[key])
        spin.connect("value-changed", lambda s: self.settings.__setitem__(key, s.get_value_as_int()))
        self._row(grid, spin, label)

    def _entry(self, grid, key, label, tooltip):
        entry = Gtk.Entry(text=self.settings[key])
        entry.set_tooltip_text(tooltip)
        # Apply on Enter or when leaving the field, not on every keystroke.
        entry.connect("activate", lambda e: self.settings.__setitem__(key, e.get_text().strip()))
        entry.connect("focus-out-event", lambda e, _ev: self.settings.__setitem__(key, e.get_text().strip()) or False)
        self._row(grid, entry, label)

    def _combo(self, grid, key, label, options):
        combo = Gtk.ComboBoxText()
        for value, title in options:
            combo.append(value, title)
        combo.set_active_id(self.settings[key])
        combo.connect("changed", lambda c: self.settings.__setitem__(key, c.get_active_id()))
        self._row(grid, combo, label)
