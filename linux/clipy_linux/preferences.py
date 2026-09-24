"""Preferences window, laid out like a libadwaita preferences dialog."""

from gi.repository import Gtk, Pango

from . import APP_NAME, paste


class PreferencesWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title=f"{APP_NAME} Preferences", application=app)
        self.settings = app.settings
        self.set_default_size(620, 640)
        self.set_icon_name("clipy-ubuntu")

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        stack.add_titled(self.general_page(), "general", "General")
        stack.add_titled(self.menu_page(), "menu", "Menu")
        stack.add_titled(self.shortcuts_page(), "shortcuts", "Shortcuts")

        header = Gtk.HeaderBar(show_close_button=True)
        header.set_custom_title(Gtk.StackSwitcher(stack=stack))
        self.set_titlebar(header)
        self.add(stack)
        self.show_all()

    # ------------------------------------------------------------------ pages

    def general_page(self):
        page = self._page()

        group = self._group(page, "Appearance")
        self._combo(group, "popup_style", "Popup style",
                    [("panel", "Clipboard panel"), ("menu", "Classic menu")],
                    "The panel has search and previews. The classic menu matches Clipy on macOS")
        self._combo(group, "tray_icon", "Status icon",
                    [("light", "Light"), ("dark", "Dark"), ("hidden", "Hidden")],
                    "Use Light on dark panels, like Ubuntu's top bar")
        self._switch(group, "launch_at_login", "Launch at login")

        group = self._group(page, "History")
        self._spin(group, "max_history", "Items to keep", 1, 9999)
        self._switch(group, "store_images", "Save images")
        self._switch(group, "reorder_after_paste", "Move pasted items to the top")
        self._switch(group, "overwrite_same_history", "Merge identical items",
                     "Copying something already in the history moves it instead of adding a copy")
        self._switch(group, "copy_same_history", "Record items copied again")
        self._switch(group, "clear_history_on_quit", "Clear history on quit")

        group = self._group(page, "Pasting")
        self._switch(group, "paste_automatically", "Paste automatically",
                     "Send the paste keystroke after choosing an item")
        self._entry(group, "paste_keys", "Paste keystroke", "ctrl+v",
                    "Terminals need ctrl+shift+v; shift+insert works almost everywhere")
        if paste.paste_command(self.settings["paste_keys"]) is None:
            self._note(page, "Automatic paste needs xdotool (X11) or ydotool/wtype (Wayland). "
                             "Until one is installed, Clipy copies the item and you press Ctrl+V.")

        group = self._group(page, "Privacy")
        self._switch(group, "ignore_concealed_types", "Ignore passwords",
                     "Skip secrets copied from password managers such as KeePassXC")
        return self._scrolled(page)

    def menu_page(self):
        page = self._page()
        group = self._group(page, "Layout", "These settings apply to the classic menu and the tray menu")
        self._spin(group, "inline_items", "Items shown inline", 0, 999)
        self._spin(group, "items_per_folder", "Items per folder", 1, 999)
        self._spin(group, "max_title_length", "Title length", 3, 999, "Characters shown for each item")
        self._switch(group, "mark_with_numbers", "Number items")
        self._switch(group, "start_numbering_at_zero", "Start numbering at 0")
        self._switch(group, "show_icons", "Show icons")

        group = self._group(page, "Previews")
        self._switch(group, "show_tooltips", "Show tooltips")
        self._spin(group, "max_tooltip_length", "Tooltip length", 1, 99999)
        self._switch(group, "show_images", "Show image thumbnails")
        self._spin(group, "thumbnail_width", "Thumbnail width", 16, 512)
        self._spin(group, "thumbnail_height", "Thumbnail height", 16, 512)

        group = self._group(page, "Clear History")
        self._switch(group, "show_clear_history_item", "Show “Clear History” item")
        self._switch(group, "confirm_clear_history", "Ask before clearing")
        return self._scrolled(page)

    def shortcuts_page(self):
        page = self._page()
        group = self._group(page, "Global Shortcuts", "Use GTK syntax, for example <Primary><Alt>v. Leave a field empty to turn that shortcut off")
        self._entry(group, "main_shortcut", "Open clipboard", "<Primary><Alt>v")
        self._entry(group, "history_shortcut", "Open history", "<Primary><Alt>h")
        self._entry(group, "snippet_shortcut", "Open snippets", "<Primary><Alt>b")
        if paste.session_type() == "wayland":
            self._note(page, "Wayland does not let apps register global shortcuts. Run "
                             "clipy-ubuntu-shortcuts once, or add custom shortcuts in Settings → Keyboard "
                             "that run “clipy-ubuntu --menu main”, “--menu history” or “--menu snippet”.")

        group = self._group(page, "In the Clipboard Panel")
        for keys, action in (
            ("↑ ↓", "Select an item"),
            ("Enter", "Paste the selected item"),
            ("Alt+1 … Alt+9", "Paste item 1–9"),
            ("Tab", "Switch between Clipboard and Snippets"),
            ("Shift+Delete", "Remove the selected item"),
            ("Esc", "Clear the search, or close"),
        ):
            label = Gtk.Label(label=keys)
            label.get_style_context().add_class("clipy-shortcut-label")
            self._row(group, action, label)
        return self._scrolled(page)

    # ------------------------------------------------------------ containers

    def _page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.get_style_context().add_class("clipy-page")
        return page

    def _scrolled(self, page):
        clamp = Gtk.Box(halign=Gtk.Align.CENTER)
        page.set_size_request(540, -1)
        clamp.pack_start(page, False, False, 0)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(clamp)
        return scroll

    def _group(self, page, title, description=None):
        heading = Gtk.Label(label=title, xalign=0)
        heading.get_style_context().add_class("clipy-group-title")
        page.pack_start(heading, False, False, 0)
        if description:
            self._note(page, description, css="clipy-group-description")
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.get_style_context().add_class("clipy-boxed-list")
        listbox.connect("row-activated", lambda _l, row: getattr(row, "on_activate", lambda: None)())
        page.pack_start(listbox, False, False, 0)
        return listbox

    def _note(self, page, text, css="clipy-dim"):
        label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=70)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.get_style_context().add_class(css)
        if css == "clipy-dim":
            label.set_margin_top(8)
            label.set_margin_start(4)
        page.pack_start(label, False, False, 0)

    def _row(self, group, title, widget, subtitle=None):
        row = Gtk.ListBoxRow(activatable=False)
        box = Gtk.Box(spacing=12)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        text.pack_start(Gtk.Label(label=title, xalign=0, wrap=True), False, False, 0)
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0, wrap=True, max_width_chars=50)
            sub.get_style_context().add_class("clipy-dim")
            text.pack_start(sub, False, False, 0)
        box.pack_start(text, True, True, 0)
        widget.set_valign(Gtk.Align.CENTER)
        box.pack_end(widget, False, False, 0)
        row.add(box)
        group.add(row)
        return row

    # --------------------------------------------------------------- controls

    def _set(self, key, value):
        self.settings[key] = value

    def _switch(self, group, key, title, subtitle=None):
        switch = Gtk.Switch(active=self.settings[key])
        switch.connect("notify::active", lambda s, _p: self._set(key, s.get_active()))
        row = self._row(group, title, switch, subtitle)
        # Clicking anywhere on the row flips the switch, as in GNOME Settings.
        row.set_activatable(True)
        row.on_activate = lambda: switch.set_active(not switch.get_active())

    def _spin(self, group, key, title, low, high, subtitle=None):
        spin = Gtk.SpinButton.new_with_range(low, high, 1)
        spin.set_value(self.settings[key])
        spin.connect("value-changed", lambda s: self._set(key, s.get_value_as_int()))
        self._row(group, title, spin, subtitle)

    def _entry(self, group, key, title, placeholder, subtitle=None):
        entry = Gtk.Entry(text=self.settings[key], placeholder_text=placeholder, width_chars=18)
        # Apply on Enter or when leaving the field, not on every keystroke.
        entry.connect("activate", lambda e: self._set(key, e.get_text().strip()))
        entry.connect("focus-out-event", lambda e, _ev: self._set(key, e.get_text().strip()) or False)
        self._row(group, title, entry, subtitle)

    def _combo(self, group, key, title, options, subtitle=None):
        combo = Gtk.ComboBoxText()
        for value, label in options:
            combo.append(value, label)
        combo.set_active_id(self.settings[key])
        combo.connect("changed", lambda c: self._set(key, c.get_active_id()))
        self._row(group, title, combo, subtitle)
