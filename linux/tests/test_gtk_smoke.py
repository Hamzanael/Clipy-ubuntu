"""Build every window once under a real display (xvfb-run in CI).

Skipped when PyGObject/GTK or a display is unavailable.
"""

import os
import tempfile
import unittest

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    HAVE_DISPLAY = Gtk.init_check(None)[0]
except (ImportError, ValueError):
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, "needs PyGObject with GTK 3 and a display")
class GtkSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_env = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME")}
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "config")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.tmp.name, "data")

        from clipy_linux.app import ClipyApplication
        from clipy_linux.config import Settings
        from clipy_linux.storage import KIND_TEXT, Database

        self.app = ClipyApplication.__new__(ClipyApplication)
        Gtk.Application.__init__(self.app, application_id=None)
        self.app.settings = Settings()
        self.app.db = Database(":memory:")
        self.app.db.add_clip(KIND_TEXT, text="hello world")
        folder = self.app.db.add_folder("Folder")
        self.app.db.add_snippet(folder, "Snippet", "content")

    def tearDown(self):
        self.app.db.close()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_panel(self):
        from clipy_linux.panel import ClipboardPanel
        panel = ClipboardPanel(self.app)
        panel.refresh()
        self.assertEqual(len(panel.history_list.get_children()), 1)
        panel.stack.set_visible_child_name("snippet")
        self.assertIs(panel.current_list, panel.snippet_list)
        panel.search.set_text("nothing matches")
        panel.refresh()
        self.assertEqual(panel.history_list.get_children(), [])
        panel.destroy()

    def test_preferences(self):
        from clipy_linux.preferences import PreferencesWindow
        PreferencesWindow(self.app).destroy()

    def test_snippet_editor(self):
        from clipy_linux.snippet_editor import SnippetEditor
        editor = SnippetEditor(self.app)
        editor.on_add_snippet()
        self.assertEqual(len(self.app.db.snippets(self.app.db.folders()[0].id)), 2)
        editor.destroy()


if __name__ == "__main__":
    unittest.main()
