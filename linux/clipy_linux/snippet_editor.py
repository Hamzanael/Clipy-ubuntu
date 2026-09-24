"""Snippet editor window: a sidebar of folders and snippets next to an editor."""

from xml.etree.ElementTree import ParseError

from gi.repository import Gio, GLib, Gtk, Pango

from . import APP_NAME
from .panel_model import text_preview
from .snippets_xml import export_snippets, import_snippets


class SnippetEditor(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(title=f"{APP_NAME} Snippets", application=app)
        self.app = app
        self.db = app.db
        self._loading = False
        self.selected_id = None
        self.selected_is_folder = False
        self.set_default_size(860, 560)
        self.set_icon_name("clipy-ubuntu")

        self.set_titlebar(self._make_header())

        self.sidebar = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        self.sidebar.get_style_context().add_class("clipy-sidebar")
        self.sidebar.connect("row-selected", self.on_row_selected)
        sidebar_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sidebar_scroll.get_style_context().add_class("clipy-sidebar")
        sidebar_scroll.set_size_request(260, -1)
        sidebar_scroll.add(self.sidebar)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.pack1(sidebar_scroll, False, False)
        paned.pack2(self._make_detail(), True, False)
        self.add(paned)

        self.reload()
        self.show_all()
        self.update_detail()

    # ------------------------------------------------------------------ build

    def _make_header(self):
        header = Gtk.HeaderBar(show_close_button=True, title="Snippets")

        add_menu = Gio.Menu()
        add_menu.append("New Snippet", "win.add-snippet")
        add_menu.append("New Folder", "win.add-folder")
        add_button = Gtk.MenuButton(menu_model=add_menu, tooltip_text="Add")
        add_button.add(Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON))
        header.pack_start(add_button)

        more_menu = Gio.Menu()
        more_menu.append("Import Snippets…", "win.import")
        more_menu.append("Export Snippets…", "win.export")
        more_button = Gtk.MenuButton(menu_model=more_menu, tooltip_text="Import and export")
        more_button.add(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        header.pack_end(more_button)

        for name, callback in (
            ("add-snippet", self.on_add_snippet),
            ("add-folder", self.on_add_folder),
            ("import", self.on_import),
            ("export", self.on_export),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_args, cb=callback: cb())
            self.add_action(action)
        return header

    def _make_detail(self):
        detail = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.CENTER)
        empty.get_style_context().add_class("clipy-empty")
        icon = Gtk.Image.new_from_icon_name("accessories-text-editor-symbolic", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(64)
        icon.get_style_context().add_class("clipy-empty-icon")
        heading = Gtk.Label()
        heading.set_markup("<big><b>No Snippet Selected</b></big>")
        hint = Gtk.Label(label="Snippets are text you paste often: signatures, addresses, code.\n"
                               "Create one with the + button.", justify=Gtk.Justification.CENTER)
        new_button = Gtk.Button(label="New Snippet", halign=Gtk.Align.CENTER)
        new_button.get_style_context().add_class("suggested-action")
        new_button.connect("clicked", lambda *_: self.on_add_snippet())
        for widget in (icon, heading, hint, new_button):
            empty.pack_start(widget, False, False, 0)
        detail.add_named(empty, "empty")

        editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        editor.get_style_context().add_class("clipy-page")

        top = Gtk.Box(spacing=8)
        self.kind_icon = Gtk.Image()
        top.pack_start(self.kind_icon, False, False, 0)
        self.title_entry = Gtk.Entry(placeholder_text="Title", hexpand=True)
        self.title_entry.get_style_context().add_class("clipy-editor-title")
        self.title_entry.connect("changed", self.on_title_changed)
        top.pack_start(self.title_entry, True, True, 0)
        editor.pack_start(top, False, False, 0)

        toolbar = Gtk.Box(spacing=6)
        self.enabled_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.enabled_switch.connect("notify::active", self.on_enabled_changed)
        enabled_label = Gtk.Label(label="Show in menus")
        enabled_label.get_style_context().add_class("clipy-dim")
        toolbar.pack_start(self.enabled_switch, False, False, 0)
        toolbar.pack_start(enabled_label, False, False, 0)

        self.info_label = Gtk.Label(xalign=1)
        self.info_label.get_style_context().add_class("clipy-dim")
        toolbar.pack_start(self.info_label, True, True, 0)
        for icon_name, tooltip, callback in (
            # pack_end places these right to left.
            ("user-trash-symbolic", "Delete", lambda *_: self.on_delete()),
            ("go-down-symbolic", "Move down", lambda *_: self.on_move(1)),
            ("go-up-symbolic", "Move up", lambda *_: self.on_move(-1)),
        ):
            button = Gtk.Button.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
            button.set_tooltip_text(tooltip)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", callback)
            toolbar.pack_end(button, False, False, 0)
        editor.pack_start(toolbar, False, False, 0)

        self.content_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True,
                                         left_margin=14, right_margin=14, top_margin=12, bottom_margin=12)
        self.content_view.get_buffer().connect("changed", self.on_content_changed)
        self.content_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.content_scroll.get_style_context().add_class("clipy-editor-content")
        self.content_scroll.add(self.content_view)
        editor.pack_start(self.content_scroll, True, True, 0)

        self.folder_hint = Gtk.Label(xalign=0, wrap=True)
        self.folder_hint.get_style_context().add_class("clipy-dim")
        editor.pack_start(self.folder_hint, False, False, 0)

        detail.add_named(editor, "editor")
        self.detail = detail
        return detail

    def _sidebar_row(self, item_id, is_folder, title, subtitle, enabled):
        row = Gtk.ListBoxRow()
        row.item_id = item_id
        row.is_folder = is_folder
        box = Gtk.Box(spacing=8)
        if not is_folder:
            box.set_margin_start(18)
        icon = "folder-symbolic" if is_folder else "text-x-generic-symbolic"
        box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        escaped = GLib.markup_escape_text(title)
        label.set_markup(f"<b>{escaped}</b>" if is_folder else escaped)
        text.pack_start(label, False, False, 0)
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0, ellipsize=Pango.EllipsizeMode.END)
            sub.get_style_context().add_class("clipy-row-subtitle")
            text.pack_start(sub, False, False, 0)
        box.pack_start(text, True, True, 0)
        row.add(box)
        style = row.get_style_context()
        if is_folder:
            style.add_class("clipy-folder-row")
        if not enabled:
            style.add_class("clipy-disabled")
        return row

    # ------------------------------------------------------------------ model

    def reload(self, select_id=None):
        self._loading = True
        select_id = select_id or self.selected_id
        for child in self.sidebar.get_children():
            self.sidebar.remove(child)
        select_row = None
        for folder, snippets in self.db.folder_details():
            count = f"{len(snippets)} snippet" + ("" if len(snippets) == 1 else "s")
            row = self._sidebar_row(folder.id, True, folder.title or "Untitled folder", count, folder.enabled)
            self.sidebar.add(row)
            if folder.id == select_id:
                select_row = row
            for snippet in snippets:
                row = self._sidebar_row(snippet.id, False, snippet.title or "Untitled snippet",
                                        text_preview(snippet.content, 40), snippet.enabled and folder.enabled)
                self.sidebar.add(row)
                if snippet.id == select_id:
                    select_row = row
        self.sidebar.show_all()
        self._loading = False
        if select_row is not None:
            self.sidebar.select_row(select_row)
        else:
            self.sidebar.unselect_all()
            self.selected_id = None
        self.update_detail()

    def update_detail(self):
        self._loading = True
        if self.selected_id is None:
            self.detail.set_visible_child_name("empty")
        else:
            self.detail.set_visible_child_name("editor")
            if self.selected_is_folder:
                folder = next((f for f in self.db.folders() if f.id == self.selected_id), None)
                self.kind_icon.set_from_icon_name("folder-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
                self.title_entry.set_text(folder.title if folder else "")
                self.enabled_switch.set_active(bool(folder and folder.enabled))
                self.content_scroll.hide()
                count = len(self.db.snippets(self.selected_id))
                self.info_label.set_text(f"{count} snippet" + ("" if count == 1 else "s"))
                self.folder_hint.set_text("Folders group snippets in the menus. Turning a folder off hides all of its snippets.")
                self.folder_hint.show()
            else:
                snippet = self.db.snippet(self.selected_id)
                self.kind_icon.set_from_icon_name("text-x-generic-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
                self.title_entry.set_text(snippet.title if snippet else "")
                self.enabled_switch.set_active(bool(snippet and snippet.enabled))
                self.content_view.get_buffer().set_text(snippet.content if snippet else "")
                self.content_scroll.show()
                self.folder_hint.hide()
                self._update_info(snippet.content if snippet else "")
        self._loading = False

    def _update_info(self, content):
        lines = content.count("\n") + 1 if content else 0
        self.info_label.set_text(f"{len(content)} characters · {lines} line" + ("" if lines == 1 else "s"))

    def _refresh_selected_row(self):
        """Update the sidebar row text without rebuilding the list (keeps focus)."""
        row = self.sidebar.get_selected_row()
        if row is None:
            return
        index = row.get_index()
        if row.is_folder:
            folder = next((f for f in self.db.folders() if f.id == row.item_id), None)
            count = len(self.db.snippets(row.item_id))
            new = self._sidebar_row(row.item_id, True, folder.title or "Untitled folder",
                                    f"{count} snippet" + ("" if count == 1 else "s"), folder.enabled)
        else:
            snippet = self.db.snippet(row.item_id)
            folder = next((f for f in self.db.folders() if f.id == snippet.folder_id), None)
            new = self._sidebar_row(row.item_id, False, snippet.title or "Untitled snippet",
                                    text_preview(snippet.content, 40), snippet.enabled and folder.enabled)
        self._loading = True
        self.sidebar.remove(row)
        self.sidebar.insert(new, index)
        new.show_all()
        self.sidebar.select_row(new)
        self._loading = False

    # --------------------------------------------------------------- handlers

    def on_row_selected(self, _listbox, row):
        if self._loading:
            return
        self.selected_id = row.item_id if row else None
        self.selected_is_folder = bool(row and row.is_folder)
        self.update_detail()

    def on_title_changed(self, entry):
        if self._loading or self.selected_id is None:
            return
        if self.selected_is_folder:
            self.db.update_folder(self.selected_id, title=entry.get_text())
        else:
            self.db.update_snippet(self.selected_id, title=entry.get_text())
        self._refresh_selected_row()

    def on_content_changed(self, buffer):
        if self._loading or self.selected_id is None or self.selected_is_folder:
            return
        start, end = buffer.get_bounds()
        content = buffer.get_text(start, end, True)
        self.db.update_snippet(self.selected_id, content=content)
        self._update_info(content)
        self._refresh_selected_row()

    def on_enabled_changed(self, switch, _param):
        if self._loading or self.selected_id is None:
            return
        if self.selected_is_folder:
            self.db.update_folder(self.selected_id, enabled=switch.get_active())
            self.reload()
        else:
            self.db.update_snippet(self.selected_id, enabled=switch.get_active())
            self._refresh_selected_row()

    def _select(self, item_id, is_folder):
        self.selected_id = item_id
        self.selected_is_folder = is_folder
        self.reload(select_id=item_id)

    def on_add_folder(self):
        self._select(self.db.add_folder("New Folder"), True)
        self.title_entry.grab_focus()

    def on_add_snippet(self):
        if self.selected_id is None:
            folders = self.db.folders()
            folder_id = folders[0].id if folders else self.db.add_folder("Snippets")
        elif self.selected_is_folder:
            folder_id = self.selected_id
        else:
            folder_id = self.db.snippet(self.selected_id).folder_id
        self._select(self.db.add_snippet(folder_id, "New Snippet"), False)
        self.title_entry.grab_focus()

    def on_delete(self):
        if self.selected_id is None:
            return
        title = self.title_entry.get_text() or "this item"
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE, text=f"Delete “{title}”?",
        )
        dialog.format_secondary_text(
            "The folder and all of its snippets will be deleted." if self.selected_is_folder
            else "This can't be undone.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        delete = dialog.add_button("Delete", Gtk.ResponseType.OK)
        delete.get_style_context().add_class("destructive-action")
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if self.selected_is_folder:
            self.db.delete_folder(self.selected_id)
        else:
            self.db.delete_snippet(self.selected_id)
        self.selected_id = None
        self.reload()

    def on_move(self, offset):
        if self.selected_id is None:
            return
        if self.selected_is_folder:
            self.db.move_folder(self.selected_id, offset)
        else:
            self.db.move_snippet(self.selected_id, offset)
        self.reload()

    def _xml_filter(self):
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("Clipy snippets (XML)")
        xml_filter.add_pattern("*.xml")
        return xml_filter

    def on_import(self):
        dialog = Gtk.FileChooserNative.new("Import Snippets", self, Gtk.FileChooserAction.OPEN, "_Import", "_Cancel")
        dialog.add_filter(self._xml_filter())
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            try:
                with open(dialog.get_filename(), encoding="utf-8") as handle:
                    import_snippets(self.db, handle.read())
            except (OSError, ValueError, ParseError) as error:
                self._error("Could not import snippets", str(error))
            self.reload()
        dialog.destroy()

    def on_export(self):
        dialog = Gtk.FileChooserNative.new("Export Snippets", self, Gtk.FileChooserAction.SAVE, "_Export", "_Cancel")
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name("snippets.xml")
        dialog.add_filter(self._xml_filter())
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            try:
                with open(dialog.get_filename(), "w", encoding="utf-8") as handle:
                    handle.write(export_snippets(self.db))
            except OSError as error:
                self._error("Could not export snippets", str(error))
        dialog.destroy()

    def _error(self, title, detail):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()
