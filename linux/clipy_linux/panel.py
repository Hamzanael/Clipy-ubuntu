"""The clipboard panel: a searchable popup listing history and snippets."""

import gi
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from . import panel_model as pm
from .storage import KIND_IMAGE

try:
    gi.require_version("GdkX11", "3.0")
    from gi.repository import GdkX11
except (ValueError, ImportError):
    GdkX11 = None

# Includes the transparent margin the shadow is drawn in (see style.css).
PANEL_WIDTH = 484
PANEL_HEIGHT = 564
QUICK_KEYS = 9


class ClipboardPanel(Gtk.Window):
    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title="Clipy")
        self.app = app
        self._hiding = False
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_default_size(PANEL_WIDTH, PANEL_HEIGHT)
        self.set_icon_name("clipy-ubuntu")
        self.get_style_context().add_class("clipy-panel")

        # Rounded corners and a shadow need an RGBA visual and a compositor.
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)
        else:
            self.get_style_context().add_class("clipy-solid")

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        frame.get_style_context().add_class("clipy-panel-frame")
        self.add(frame)

        self.search = Gtk.SearchEntry(placeholder_text="Search clipboard and snippets")
        self.search.get_style_context().add_class("clipy-search")
        self.search.connect("search-changed", lambda *_: self.refresh())
        frame.pack_start(self.search, False, False, 0)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120)
        self.history_list = self._make_list(self.on_history_activated)
        self.snippet_list = self._make_list(self.on_snippet_activated)
        self.history_page = self._make_page(self.history_list, "edit-paste-symbolic",
                                            "Nothing copied yet", "Copied text and images appear here.")
        self.snippet_page = self._make_page(self.snippet_list, "accessories-text-editor-symbolic",
                                            "No snippets", "Add reusable text in the snippet editor.")
        self.stack.add_titled(self.history_page, "history", "Clipboard")
        self.stack.add_titled(self.snippet_page, "snippet", "Snippets")
        self.stack.connect("notify::visible-child", lambda *_: self._select_first())

        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER, homogeneous=True)
        switcher.get_style_context().add_class("clipy-tabs")
        frame.pack_start(switcher, False, False, 0)
        frame.pack_start(self.stack, True, True, 0)
        frame.pack_start(self._make_footer(), False, False, 0)

        # Children must be visible before a Gtk.Stack will switch to them.
        frame.show_all()

        self.connect("key-press-event", self.on_key_press)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("delete-event", lambda *_: self.dismiss() or True)

    # ------------------------------------------------------------------ build

    def _make_list(self, on_activate):
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE, activate_on_single_click=True)
        listbox.get_style_context().add_class("clipy-list")
        listbox.connect("row-activated", on_activate)
        listbox.set_can_focus(False)
        return listbox

    def _make_page(self, listbox, icon_name, title, subtitle):
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(listbox)
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        empty.get_style_context().add_class("clipy-empty")
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        icon.get_style_context().add_class("clipy-empty-icon")
        heading = Gtk.Label()
        heading.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        empty.pack_start(icon, False, False, 0)
        empty.pack_start(heading, False, False, 0)
        empty.pack_start(Gtk.Label(label=subtitle), False, False, 0)
        page = Gtk.Stack()
        page.add_named(scroll, "list")
        page.add_named(empty, "empty")
        page.listbox = listbox
        return page

    def _make_footer(self):
        footer = Gtk.Box(spacing=6)
        footer.get_style_context().add_class("clipy-footer")
        hint = Gtk.Label(label="↵ paste · Alt+1–9 quick paste · Tab switch · Shift+Del remove", xalign=0)
        hint.set_ellipsize(Pango.EllipsizeMode.END)
        footer.pack_start(hint, True, True, 0)
        for icon, tooltip, callback in (
            ("user-trash-symbolic", "Clear history", self.on_clear),
            ("document-edit-symbolic", "Edit snippets", lambda *_: self._run_after_hide(self.app.show_snippet_editor)),
            ("emblem-system-symbolic", "Preferences", lambda *_: self._run_after_hide(self.app.show_preferences)),
        ):
            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_tooltip_text(tooltip)
            button.set_can_focus(False)
            button.connect("clicked", callback)
            footer.pack_end(button, False, False, 0)
        return footer

    def _row(self, number, title, subtitle, thumbnail=None, icon_name=None, payload=None, on_remove=None):
        row = Gtk.ListBoxRow()
        row.payload = payload
        box = Gtk.Box(spacing=10)

        badge = Gtk.Label(label=str(number) if number <= QUICK_KEYS else "", valign=Gtk.Align.CENTER)
        badge.get_style_context().add_class("clipy-badge")
        if number > QUICK_KEYS:
            badge.set_opacity(0)
        box.pack_start(badge, False, False, 0)

        if thumbnail is not None:
            thumbnail.get_style_context().add_class("clipy-thumbnail")
            box.pack_start(thumbnail, False, False, 0)
        elif icon_name:
            box.pack_start(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        title_label = Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END, single_line_mode=True)
        title_label.get_style_context().add_class("clipy-row-title")
        subtitle_label = Gtk.Label(label=subtitle, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        subtitle_label.get_style_context().add_class("clipy-row-subtitle")
        text.pack_start(title_label, False, False, 0)
        text.pack_start(subtitle_label, False, False, 0)
        box.pack_start(text, True, True, 0)

        if on_remove is not None:
            remove = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
            remove.set_relief(Gtk.ReliefStyle.NONE)
            remove.set_valign(Gtk.Align.CENTER)
            remove.set_tooltip_text("Remove from history")
            remove.get_style_context().add_class("clipy-row-action")
            remove.set_can_focus(False)
            remove.connect("clicked", lambda *_: on_remove(payload))
            box.pack_end(remove, False, False, 0)

        row.add(box)
        return row

    def _thumbnail(self, data):
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pixbuf = loader.get_pixbuf()
        except GLib.Error:
            return None
        scale = min(64 / pixbuf.get_width(), 40 / pixbuf.get_height(), 1.0)
        width = max(1, int(pixbuf.get_width() * scale))
        height = max(1, int(pixbuf.get_height() * scale))
        return Gtk.Image.new_from_pixbuf(pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR))

    # ---------------------------------------------------------------- content

    def refresh(self):
        query = self.search.get_text()
        settings = self.app.settings
        clips = self.app.db.clips(sort_by_created=not settings["reorder_after_paste"], limit=settings["max_history"])
        self._fill(self.history_page, [
            self._row(
                number, pm.clip_title(clip), pm.clip_subtitle(clip),
                thumbnail=self._thumbnail(clip.image) if clip.kind == KIND_IMAGE and settings["show_images"] else None,
                icon_name="image-x-generic-symbolic" if clip.kind == KIND_IMAGE else None,
                payload=clip.id, on_remove=self.on_remove_clip,
            )
            for number, clip in enumerate(pm.filter_clips(clips, query), start=1)
        ])
        self._fill(self.snippet_page, [
            self._row(
                number, snippet.title or "Untitled snippet",
                f"{folder.title} · {pm.text_preview(snippet.content, 60)}",
                icon_name="text-x-generic-symbolic", payload=snippet.id,
            )
            for number, (folder, snippet) in enumerate(pm.filter_snippets(self.app.db.folder_details(), query), start=1)
        ])
        self._select_first()

    def _fill(self, page, rows):
        listbox = page.listbox
        for child in listbox.get_children():
            listbox.remove(child)
        for row in rows:
            listbox.add(row)
        listbox.show_all()
        page.set_visible_child_name("list" if rows else "empty")

    @property
    def current_list(self):
        if self.stack.get_visible_child_name() == "snippet":
            return self.snippet_list
        return self.history_list

    def _select_first(self):
        listbox = self.current_list
        first = listbox.get_row_at_index(0)
        if first is not None:
            listbox.select_row(first)

    def _move_selection(self, offset):
        listbox = self.current_list
        row = listbox.get_selected_row()
        index = row.get_index() + offset if row else 0
        count = len(listbox.get_children())
        if count == 0:
            return
        target = listbox.get_row_at_index(max(0, min(index, count - 1)))
        listbox.select_row(target)
        self._scroll_to(listbox, target)

    def _scroll_to(self, listbox, row):
        adjustment = listbox.get_parent().get_vadjustment() if isinstance(listbox.get_parent(), Gtk.Viewport) else None
        if adjustment is None:
            return
        allocation = row.get_allocation()
        if allocation.y < adjustment.get_value():
            adjustment.set_value(allocation.y)
        elif allocation.y + allocation.height > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(allocation.y + allocation.height - adjustment.get_page_size())

    # ------------------------------------------------------------- show/hide

    def show_at_pointer(self, page="history", event_time=0):
        self.search.set_text("")
        self.stack.set_visible_child_name("snippet" if page == "snippet" else "history")
        self.refresh()
        self._position_near_pointer()
        self.show()
        self._hiding = False
        if not event_time and GdkX11 is not None and isinstance(self.get_window(), GdkX11.X11Window):
            # Launched from a desktop shortcut command: use the X server time so
            # the window manager's focus-stealing prevention lets us take focus.
            event_time = GdkX11.x11_get_server_time(self.get_window())
        self.present_with_time(event_time or Gdk.CURRENT_TIME)
        self.search.grab_focus()

    def _position_near_pointer(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        _screen, x, y = seat.get_pointer().get_position()
        monitor = display.get_monitor_at_point(x, y)
        area = monitor.get_workarea()
        width, height = PANEL_WIDTH, PANEL_HEIGHT
        left = min(max(area.x, x - width // 2), area.x + area.width - width)
        top = min(max(area.y, y - 24), area.y + area.height - height)
        self.move(left, top)

    def dismiss(self):
        self._hiding = True
        self.hide()

    def _run_after_hide(self, callback):
        self.dismiss()
        GLib.idle_add(lambda: callback() and False)

    # ---------------------------------------------------------------- events

    def on_focus_out(self, *_):
        # Closing on focus loss matches a popup menu; wait a moment so dialogs
        # opened from the panel don't race with it.
        if not self._hiding:
            GLib.timeout_add(80, lambda: (not self.is_active() and self.dismiss()) and False)
        return False

    def on_key_press(self, _widget, event):
        key = event.keyval
        state = event.state & Gtk.accelerator_get_default_mod_mask()
        if key == Gdk.KEY_Escape:
            if self.search.get_text():
                self.search.set_text("")
            else:
                self.dismiss()
            return True
        if key in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._move_selection(1)
            return True
        if key in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._move_selection(-1)
            return True
        if key in (Gdk.KEY_Page_Down, Gdk.KEY_Page_Up):
            self._move_selection(8 if key == Gdk.KEY_Page_Down else -8)
            return True
        if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            other = "snippet" if self.stack.get_visible_child_name() == "history" else "history"
            self.stack.set_visible_child_name(other)
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            row = self.current_list.get_selected_row()
            if row is not None:
                row.activate()
            return True
        if key == Gdk.KEY_Delete and state & Gdk.ModifierType.SHIFT_MASK:
            row = self.current_list.get_selected_row()
            if row is not None and self.current_list is self.history_list:
                self.on_remove_clip(row.payload)
            return True
        if state & Gdk.ModifierType.MOD1_MASK and Gdk.KEY_1 <= key <= Gdk.KEY_9:
            row = self.current_list.get_row_at_index(key - Gdk.KEY_1)
            if row is not None:
                row.activate()
            return True
        return False

    def on_history_activated(self, _listbox, row):
        self._run_after_hide(lambda: self.app.paste_clip(row.payload))

    def on_snippet_activated(self, _listbox, row):
        self._run_after_hide(lambda: self.app.paste_snippet(row.payload))

    def on_remove_clip(self, clip_id):
        index = self.history_list.get_selected_row().get_index() if self.history_list.get_selected_row() else 0
        self.app.db.delete_clip(clip_id)
        self.refresh()
        row = self.history_list.get_row_at_index(min(index, len(self.history_list.get_children()) - 1))
        if row is not None:
            self.history_list.select_row(row)

    def on_clear(self, *_):
        self._run_after_hide(self.app.clear_history)
