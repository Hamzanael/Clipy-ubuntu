import unittest

from clipy_linux import panel_model as pm
from clipy_linux.storage import KIND_IMAGE, KIND_TEXT, Clip, Folder, Snippet


def clip(text=None, kind=KIND_TEXT, updated=1000.0):
    return Clip("id", kind, text, b"png" if kind == KIND_IMAGE else None, updated, updated)


class PanelModelTests(unittest.TestCase):
    def test_relative_time(self):
        now = 1_000_000.0
        self.assertEqual(pm.relative_time(now - 5, now), "Just now")
        self.assertEqual(pm.relative_time(now - 125, now), "2 min ago")
        self.assertEqual(pm.relative_time(now - 3 * 3600, now), "3 h ago")
        self.assertEqual(pm.relative_time(now - 30 * 3600, now), "Yesterday")
        self.assertEqual(pm.relative_time(now - 3 * 86400, now), "3 days ago")
        self.assertEqual(pm.relative_time(now + 50, now), "Just now")

    def test_titles_and_subtitles(self):
        self.assertEqual(pm.clip_title(clip("  hello\n\n  world  ")), "hello world")
        self.assertEqual(pm.clip_title(clip("x" * 100), 10), "x" * 9 + "…")
        self.assertEqual(pm.clip_title(clip(kind=KIND_IMAGE)), "Image")
        self.assertEqual(pm.clip_subtitle(clip("abc", updated=0), now=10), "Just now · 3 characters")
        self.assertEqual(pm.clip_subtitle(clip("a\nb\nc", updated=0), now=10), "Just now · 3 lines")

    def test_filter_clips(self):
        clips = [clip("Hello World"), clip("goodbye"), clip(kind=KIND_IMAGE)]
        self.assertEqual(len(pm.filter_clips(clips, "")), 3)
        self.assertEqual([c.text for c in pm.filter_clips(clips, "world hello")], ["Hello World"])
        self.assertEqual(pm.filter_clips(clips, "IMAGE")[0].kind, KIND_IMAGE)
        self.assertEqual(pm.filter_clips(clips, "nothing"), [])

    def test_filter_snippets_skips_disabled(self):
        on, off = Folder("f1", "Work", 0, True), Folder("f2", "Hidden", 1, False)
        details = [
            (on, [Snippet("s1", "f1", "Signature", "Best, Sam", 0, True),
                  Snippet("s2", "f1", "Old", "unused", 1, False)]),
            (off, [Snippet("s3", "f2", "Secret", "Best", 0, True)]),
        ]
        self.assertEqual([s.id for _, s in pm.filter_snippets(details, "")], ["s1"])
        self.assertEqual([s.id for _, s in pm.filter_snippets(details, "work best")], ["s1"])
        self.assertEqual(pm.filter_snippets(details, "secret"), [])


if __name__ == "__main__":
    unittest.main()
