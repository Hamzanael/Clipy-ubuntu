import os
import tempfile
import unittest
from pathlib import Path

from clipy_linux import autostart, paste
from clipy_linux import menu_model as mm
from clipy_linux.config import DEFAULTS, Settings
from clipy_linux.snippets_xml import export_snippets, import_snippets
from clipy_linux.storage import KIND_IMAGE, KIND_TEXT, Database


class TempSettingsMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.tmp.name) / "settings.json")
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class SettingsTests(TempSettingsMixin, unittest.TestCase):
    def test_defaults_and_persistence(self):
        self.assertEqual(self.settings["max_history"], 30)
        changes = []
        self.settings.connect(lambda k, v: changes.append((k, v)))
        self.settings["max_history"] = 50
        self.settings["max_history"] = 50  # no-op
        self.assertEqual(changes, [("max_history", 50)])
        self.assertEqual(Settings(self.settings.path)["max_history"], 50)

    def test_ignores_unknown_and_mistyped_values(self):
        self.settings.path.write_text('{"max_history": "lots", "bogus": 1, "inline_items": 3}')
        loaded = Settings(self.settings.path)
        self.assertEqual(loaded["max_history"], DEFAULTS["max_history"])
        self.assertEqual(loaded["inline_items"], 3)
        with self.assertRaises(KeyError):
            loaded["bogus"] = 1


class HistoryTests(TempSettingsMixin, unittest.TestCase):
    def test_blank_text_is_ignored(self):
        self.assertIsNone(self.db.add_clip(KIND_TEXT, text="  \n\t"))
        self.assertEqual(self.db.clips(), [])

    def test_overwrite_same_moves_to_top(self):
        a = self.db.add_clip(KIND_TEXT, text="a", now=1)
        self.db.add_clip(KIND_TEXT, text="b", now=2)
        self.assertEqual(self.db.add_clip(KIND_TEXT, text="a", now=3), a)
        self.assertEqual([c.text for c in self.db.clips()], ["a", "b"])
        self.assertEqual([c.text for c in self.db.clips(sort_by_created=True)], ["b", "a"])

    def test_duplicates_when_not_overwriting(self):
        self.db.add_clip(KIND_TEXT, text="a", overwrite_same=False, now=1)
        self.db.add_clip(KIND_TEXT, text="a", overwrite_same=False, now=2)
        self.assertEqual(len(self.db.clips()), 2)

    def test_copy_same_disabled_skips_existing(self):
        self.db.add_clip(KIND_TEXT, text="a", now=1)
        self.db.add_clip(KIND_TEXT, text="b", now=2)
        self.assertIsNone(self.db.add_clip(KIND_TEXT, text="a", copy_same=False, now=3))
        self.assertEqual([c.text for c in self.db.clips()], ["b", "a"])

    def test_trim_to_max_history(self):
        for i in range(5):
            self.db.add_clip(KIND_TEXT, text=str(i), max_history=3, now=i)
        self.assertEqual([c.text for c in self.db.clips()], ["4", "3", "2"])

    def test_images_and_delete(self):
        clip_id = self.db.add_clip(KIND_IMAGE, image=b"\x89PNG")
        self.assertEqual(self.db.clip(clip_id).image, b"\x89PNG")
        self.db.delete_clip(clip_id)
        self.assertIsNone(self.db.clip(clip_id))

    def test_change_listener(self):
        calls = []
        self.db.connect(lambda: calls.append(1))
        self.db.add_clip(KIND_TEXT, text="x")
        self.db.clear_history()
        self.assertEqual(len(calls), 2)


class SnippetTests(TempSettingsMixin, unittest.TestCase):
    def test_crud_and_ordering(self):
        f1 = self.db.add_folder("One")
        f2 = self.db.add_folder("Two")
        s1 = self.db.add_snippet(f1, "a", "A")
        s2 = self.db.add_snippet(f1, "b", "B")
        self.db.move_snippet(s2, -1)
        self.assertEqual([s.id for s in self.db.snippets(f1)], [s2, s1])
        self.db.move_folder(f2, -5)
        self.assertEqual([f.id for f in self.db.folders()], [f2, f1])
        self.db.update_snippet(s1, title="aa", content="AA", enabled=False)
        self.assertEqual((self.db.snippet(s1).title, self.db.snippet(s1).enabled), ("aa", False))
        self.db.delete_folder(f1)
        self.assertIsNone(self.db.snippet(s1))

    def test_xml_round_trip_matches_macos_format(self):
        folder = self.db.add_folder("Greetings")
        self.db.add_snippet(folder, "Hello", "Hello <world> & you\nline 2")
        xml = export_snippets(self.db)
        self.assertIn("<folders>", xml)
        self.assertIn("<snippets>", xml)

        other = Database(":memory:")
        self.assertEqual(import_snippets(other, xml), 1)
        (imported_folder, snippets), = other.folder_details()
        self.assertEqual(imported_folder.title, "Greetings")
        self.assertEqual(snippets[0].content, "Hello <world> & you\nline 2")
        other.close()

    def test_import_macos_export(self):
        xml = (
            '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
            "<folders><folder><title>Mac</title><snippets>"
            "<snippet><title>t1</title><content>c1</content></snippet>"
            "<snippet><title/><content/></snippet>"
            "</snippets></folder></folders>"
        )
        import_snippets(self.db, xml)
        (folder, snippets), = self.db.folder_details()
        self.assertEqual(folder.title, "Mac")
        self.assertEqual([(s.title, s.content) for s in snippets], [("t1", "c1"), ("untitled snippet", "")])


def flatten_titles(nodes):
    out = []
    for node in nodes:
        if isinstance(node, mm.Submenu):
            out.append((node.title, flatten_titles(node.children)))
        elif isinstance(node, (mm.Item, mm.Label)):
            out.append(node.title)
        else:
            out.append("---")
    return out


class MenuTests(TempSettingsMixin, unittest.TestCase):
    def build(self, menu_type=mm.HISTORY, count=0):
        for i in range(count):
            self.db.add_clip(KIND_TEXT, text=f"clip{i}", now=i)
        builder = mm.MenuBuilder(self.settings)
        return builder.build(menu_type, self.db.clips(), self.db.folder_details())

    def test_trimmed_title(self):
        self.assertEqual(mm.trimmed_menu_title("  hello\nworld", 20), "hello")
        self.assertEqual(mm.trimmed_menu_title("abcdefghij", 6), "abc...")
        self.assertEqual(mm.trimmed_menu_title("abcdef", 1), "...")

    def test_history_grouped_in_folders(self):
        self.settings["items_per_folder"] = 2
        titles = flatten_titles(self.build(count=5))
        self.assertEqual(titles, [
            "History",
            ("1 - 2", ["1. clip4", "2. clip3"]),
            ("3 - 4", ["1. clip2", "2. clip1"]),
            ("5 - 5", ["1. clip0"]),
        ])

    def test_inline_items_and_zero_start(self):
        self.settings["inline_items"] = 2
        self.settings["items_per_folder"] = 10
        self.settings["start_numbering_at_zero"] = True
        titles = flatten_titles(self.build(count=4))
        self.assertEqual(titles, ["History", "0. clip3", "1. clip2", ("2 - 3", ["0. clip1", "1. clip0"])])

    def test_without_numbers(self):
        self.settings["inline_items"] = 1
        self.settings["mark_with_numbers"] = False
        self.assertEqual(flatten_titles(self.build(count=1)), ["History", "clip0"])

    def test_main_menu_with_snippets(self):
        folder = self.db.add_folder("F")
        self.db.add_snippet(folder, "s1", "x")
        disabled = self.db.add_snippet(folder, "s2", "y")
        self.db.update_snippet(disabled, enabled=False)
        hidden = self.db.add_folder("Hidden")
        self.db.update_folder(hidden, enabled=False)
        self.settings["show_clear_history_item"] = False
        titles = flatten_titles(self.build(mm.MAIN))
        self.assertEqual(titles, [
            "History", "---", "Snippet", ("F", ["1. s1"]), "---",
            "Edit Snippets…", "Preferences…", "---", "Quit Clipy",
        ])
        snippet_menu = flatten_titles(self.build(mm.SNIPPET))
        self.assertEqual(snippet_menu, ["Snippet", ("F", ["1. s1"])])

    def test_image_items_and_tooltips(self):
        self.db.add_clip(KIND_IMAGE, image=b"img", now=1)
        self.db.add_clip(KIND_TEXT, text="x" * 500, now=2)
        self.settings["inline_items"] = 5
        self.settings["max_tooltip_length"] = 10
        _, text_item, image_item = self.build()
        self.assertEqual(text_item.tooltip, "x" * 10)
        self.assertEqual(image_item.image, b"img")
        self.assertEqual(image_item.action, mm.PASTE_CLIP)


class PasteTests(unittest.TestCase):
    def test_x11_uses_xdotool(self):
        argv = paste.paste_command("ctrl+shift+v", session="x11", which=lambda name: name == "xdotool")
        self.assertEqual(argv, ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"])

    def test_wayland_prefers_wtype_then_ydotool(self):
        argv = paste.paste_command("ctrl+v", session="wayland", which=lambda name: True)
        self.assertEqual(argv, ["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"])
        argv = paste.paste_command("ctrl+v", session="wayland", which=lambda name: name == "ydotool")
        self.assertEqual(argv, ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])

    def test_x11_refocuses_target_window(self):
        argv = paste.paste_command("ctrl+v", session="x11", which=lambda name: True, window=42)
        self.assertEqual(argv, ["xdotool", "windowfocus", "--sync", "42", "key", "--clearmodifiers", "ctrl+v"])

    def test_no_tool(self):
        self.assertIsNone(paste.paste_command("ctrl+v", session="x11", which=lambda name: False))


class AutostartTests(unittest.TestCase):
    def test_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = tmp
            try:
                autostart.set_enabled(True)
                self.assertTrue(autostart.is_enabled())
                self.assertIn("Exec=", autostart.autostart_path().read_text())
                autostart.set_enabled(False)
                self.assertFalse(autostart.is_enabled())
            finally:
                if old is None:
                    del os.environ["XDG_CONFIG_HOME"]
                else:
                    os.environ["XDG_CONFIG_HOME"] = old


if __name__ == "__main__":
    unittest.main()
