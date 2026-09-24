"""Snippet editor window."""

from xml.etree.ElementTree import ParseError

from gi.repository import Gtk, Pango

from . import APP_NAME
from .snippets_xml import export_snippets, import_snippets

COL_ID, COL_IS_FOLDER, COL_TITLE, COL_ENABLED = range(4)


class SnippetEditor(Gtk.Window):
    def __init__(self, app):
        super().__init__(title=f"{APP_NAME} – Snippets", application=app)
        self.app = app
        self.db = app.db
        self._loading = False
        self.set_default_size(760, 480)
        self.set_icon_name("clipy-ubuntu")

        self.store = Gtk.TreeStore(str, bool, str, bool)
        self.tree = Gtk.TreeView(model=self.store, headers_visible=False, reorderable=False)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.on_enabled_toggled)
        self.tree.append_column(Gtk.TreeViewColumn("Enabled", toggle, active=COL_ENABLED))
        text = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        column = Gtk.TreeViewColumn("Title", text, text=COL_TITLE)
        column.set_expand(True)
        self.tree.append_column(column)
        self.tree.get_selection().connect("changed", self.on_selection_changed)

        tree_scroll = Gtk.ScrolledWindow(hexpand=False, vexpand=True)
        tree_scroll.set_size_request(240, -1)
        tree_scroll.add(self.tree)

        toolbar = Gtk.Box(spacing=4)
        for icon, tooltip, handler in (
            ("folder-new-symbolic", "Add folder", self.on_add_folder),
            ("document-new-symbolic", "Add snippet", self.on_add_snippet),
            ("list-remove-symbolic", "Delete", self.on_delete),
            ("go-up-symbolic", "Move up", lambda *_: self.on_move(-1)),
            ("go-down-symbolic", "Move down", lambda *_: self.on_move(1)),
            ("document-open-symbolic", "Import snippets (XML)", self.on_import),
            ("document-save-as-symbolic", "Export snippets (XML)", self.on_export),
        ):
            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.SMALL_TOOLBAR)
            button.set_tooltip_text(tooltip)
            button.connect("clicked", handler)
            toolbar.pack_start(button, False, False, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.pack_start(tree_scroll, True, True, 0)
        left.pack_start(toolbar, False, False, 0)

        self.title_entry = Gtk.Entry(placeholder_text="Title")
        self.title_entry.connect("changed", self.on_title_changed)
        self.content_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True)
        self.content_view.get_buffer().connect("changed", self.on_content_changed)
        self.content_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.content_scroll.add(self.content_view)
        self.placeholder = Gtk.Label(label="Select or add a snippet.")

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.pack_start(self.title_entry, False, False, 0)
        right.pack_start(self.content_scroll, True, True, 0)
        right.pack_start(self.placeholder, True, True, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.pack1(left, False, False)
        paned.pack2(right, True, False)
        paned.set_border_width(8)
        self.add(paned)

        self.reload()
        self.show_all()
        self.update_detail()

    # ------------------------------------------------------------------ model

    def reload(self, select_id=None):
        self._loading = True
        expanded = set()
        self.tree.map_expanded_rows(lambda _t, path, _d: expanded.add(self.store[path][COL_ID]), None)
        select_id = select_id or self.selected_id()
        self.store.clear()
        select_iter = None
        for folder, snippets in self.db.folder_details():
            parent = self.store.append(None, [folder.id, True, folder.title, folder.enabled])
            if folder.id == select_id:
                select_iter = parent
            for snippet in snippets:
                child = self.store.append(parent, [snippet.id, False, snippet.title, snippet.enabled])
                if snippet.id == select_id:
                    select_iter = child
            if folder.id in expanded or select_iter is not None and self.store.is_ancestor(parent, select_iter):
                self.tree.expand_row(self.store.get_path(parent), False)
        self._loading = False
        if select_iter is not None:
            self.tree.get_selection().select_iter(select_iter)
        self.update_detail()

    def selected(self):
        model, it = self.tree.get_selection().get_selected()
        if it is None:
            return None
        return model[it][COL_ID], model[it][COL_IS_FOLDER], it

    def selected_id(self):
        selected = self.selected()
        return selected[0] if selected else None

    def update_detail(self):
        selected = self.selected()
        self._loading = True
        if selected is None:
            self.title_entry.hide()
            self.content_scroll.hide()
            self.placeholder.show()
        else:
            item_id, is_folder, it = selected
            self.placeholder.hide()
            self.title_entry.show()
            self.title_entry.set_text(self.store[it][COL_TITLE])
            if is_folder:
                self.content_scroll.hide()
            else:
                self.content_scroll.show()
                snippet = self.db.snippet(item_id)
                self.content_view.get_buffer().set_text(snippet.content if snippet else "")
        self._loading = False

    # --------------------------------------------------------------- handlers

    def on_selection_changed(self, _selection):
        if not self._loading:
            self.update_detail()

    def on_title_changed(self, entry):
        selected = self.selected()
        if self._loading or selected is None:
            return
        item_id, is_folder, it = selected
        title = entry.get_text()
        self.store[it][COL_TITLE] = title
        if is_folder:
            self.db.update_folder(item_id, title=title)
        else:
            self.db.update_snippet(item_id, title=title)

    def on_content_changed(self, buffer):
        selected = self.selected()
        if self._loading or selected is None or selected[1]:
            return
        start, end = buffer.get_bounds()
        self.db.update_snippet(selected[0], content=buffer.get_text(start, end, True))

    def on_enabled_toggled(self, _renderer, path):
        row = self.store[path]
        row[COL_ENABLED] = not row[COL_ENABLED]
        if row[COL_IS_FOLDER]:
            self.db.update_folder(row[COL_ID], enabled=row[COL_ENABLED])
        else:
            self.db.update_snippet(row[COL_ID], enabled=row[COL_ENABLED])

    def on_add_folder(self, *_):
        folder_id = self.db.add_folder()
        self.reload(select_id=folder_id)
        self.title_entry.grab_focus()

    def on_add_snippet(self, *_):
        selected = self.selected()
        if selected is None:
            folders = self.db.folders()
            folder_id = folders[0].id if folders else self.db.add_folder()
        elif selected[1]:
            folder_id = selected[0]
        else:
            folder_id = self.db.snippet(selected[0]).folder_id
        snippet_id = self.db.add_snippet(folder_id)
        self.reload(select_id=snippet_id)
        self.title_entry.grab_focus()

    def on_delete(self, *_):
        selected = self.selected()
        if selected is None:
            return
        item_id, is_folder, it = selected
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Delete “{self.store[it][COL_TITLE]}”?",
        )
        if is_folder:
            dialog.format_secondary_text("The folder and all of its snippets will be deleted.")
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if is_folder:
            self.db.delete_folder(item_id)
        else:
            self.db.delete_snippet(item_id)
        self.tree.get_selection().unselect_all()
        self.reload()

    def on_move(self, offset):
        selected = self.selected()
        if selected is None:
            return
        item_id, is_folder, _ = selected
        if is_folder:
            self.db.move_folder(item_id, offset)
        else:
            self.db.move_snippet(item_id, offset)
        self.reload(select_id=item_id)

    def _xml_filter(self):
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("XML files")
        xml_filter.add_pattern("*.xml")
        return xml_filter

    def on_import(self, *_):
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

    def on_export(self, *_):
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
