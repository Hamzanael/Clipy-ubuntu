"""SQLite storage for clipboard history and snippets (no GTK dependency)."""

import hashlib
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

KIND_TEXT = "text"
KIND_IMAGE = "image"

SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    text TEXT,
    image BLOB,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    position INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS snippets (
    id TEXT PRIMARY KEY,
    folder_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    position INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass
class Clip:
    id: str
    kind: str
    text: str
    image: bytes
    created_at: float
    updated_at: float


@dataclass
class Folder:
    id: str
    title: str
    position: int
    enabled: bool


@dataclass
class Snippet:
    id: str
    folder_id: str
    title: str
    content: str
    position: int
    enabled: bool


def content_hash(kind, text=None, image=None):
    digest = hashlib.sha256(kind.encode())
    digest.update(b"\0")
    if kind == KIND_TEXT:
        digest.update((text or "").encode("utf-8"))
    else:
        digest.update(image or b"")
    return digest.hexdigest()


class Database:
    def __init__(self, path):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._listeners = []

    def connect(self, listener):
        """Register a callback invoked after any change."""
        self._listeners.append(listener)

    def _changed(self):
        self.conn.commit()
        for listener in list(self._listeners):
            listener()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------ history

    def add_clip(self, kind, text=None, image=None, *, overwrite_same=True,
                 copy_same=True, max_history=None, sort_by_created=False, now=None):
        """Save a clipboard entry following the macOS `ClipService.save` rules.

        Returns the stored clip id, or None when nothing was saved.
        """
        if kind == KIND_TEXT and not (text or "").strip():
            return None
        if kind == KIND_IMAGE and not image:
            return None
        now = time.time() if now is None else now
        digest = content_hash(kind, text, image)
        existing = self.conn.execute("SELECT id FROM history WHERE id = ?", (digest,)).fetchone()
        if existing and not copy_same:
            return None
        clip_id = digest if overwrite_same else uuid.uuid4().hex
        if existing and overwrite_same:
            self.conn.execute("UPDATE history SET updated_at = ? WHERE id = ?", (now, clip_id))
        else:
            self.conn.execute(
                "INSERT INTO history (id, kind, text, image, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (clip_id, kind, text, image, now, now),
            )
        if max_history is not None:
            self._trim(max_history, sort_by_created)
        self._changed()
        return clip_id

    def touch_clip(self, clip_id, now=None):
        now = time.time() if now is None else now
        self.conn.execute("UPDATE history SET updated_at = ? WHERE id = ?", (now, clip_id))
        self._changed()

    def clips(self, *, sort_by_created=False, limit=None):
        order = "created_at" if sort_by_created else "updated_at"
        sql = f"SELECT * FROM history ORDER BY {order} DESC, rowid DESC"
        params = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (max(0, int(limit)),)
        return [Clip(**dict(row)) for row in self.conn.execute(sql, params)]

    def clip(self, clip_id):
        row = self.conn.execute("SELECT * FROM history WHERE id = ?", (clip_id,)).fetchone()
        return Clip(**dict(row)) if row else None

    def delete_clip(self, clip_id):
        self.conn.execute("DELETE FROM history WHERE id = ?", (clip_id,))
        self._changed()

    def clear_history(self):
        self.conn.execute("DELETE FROM history")
        self._changed()
        self.conn.execute("VACUUM")

    def trim_history(self, max_history, sort_by_created=False):
        self._trim(max_history, sort_by_created)
        self._changed()

    def _trim(self, max_history, sort_by_created):
        order = "created_at" if sort_by_created else "updated_at"
        self.conn.execute(
            f"DELETE FROM history WHERE id NOT IN "
            f"(SELECT id FROM history ORDER BY {order} DESC, rowid DESC LIMIT ?)",
            (max(0, int(max_history)),),
        )

    # ----------------------------------------------------------------- snippets

    def folders(self):
        rows = self.conn.execute("SELECT * FROM folders ORDER BY position, rowid")
        return [Folder(r["id"], r["title"], r["position"], bool(r["enabled"])) for r in rows]

    def snippets(self, folder_id):
        rows = self.conn.execute(
            "SELECT * FROM snippets WHERE folder_id = ? ORDER BY position, rowid", (folder_id,)
        )
        return [
            Snippet(r["id"], r["folder_id"], r["title"], r["content"], r["position"], bool(r["enabled"]))
            for r in rows
        ]

    def snippet(self, snippet_id):
        r = self.conn.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,)).fetchone()
        if not r:
            return None
        return Snippet(r["id"], r["folder_id"], r["title"], r["content"], r["position"], bool(r["enabled"]))

    def folder_details(self):
        """Return [(Folder, [Snippet, ...]), ...] in display order."""
        return [(folder, self.snippets(folder.id)) for folder in self.folders()]

    def add_folder(self, title="untitled folder"):
        folder_id = uuid.uuid4().hex
        position = self.conn.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM folders").fetchone()[0]
        self.conn.execute(
            "INSERT INTO folders (id, title, position, enabled) VALUES (?, ?, ?, 1)",
            (folder_id, title, position),
        )
        self._changed()
        return folder_id

    def add_snippet(self, folder_id, title="untitled snippet", content=""):
        snippet_id = uuid.uuid4().hex
        position = self.conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) FROM snippets WHERE folder_id = ?", (folder_id,)
        ).fetchone()[0]
        self.conn.execute(
            "INSERT INTO snippets (id, folder_id, title, content, position, enabled) VALUES (?, ?, ?, ?, ?, 1)",
            (snippet_id, folder_id, title, content, position),
        )
        self._changed()
        return snippet_id

    def update_folder(self, folder_id, *, title=None, enabled=None):
        if title is not None:
            self.conn.execute("UPDATE folders SET title = ? WHERE id = ?", (title, folder_id))
        if enabled is not None:
            self.conn.execute("UPDATE folders SET enabled = ? WHERE id = ?", (int(enabled), folder_id))
        self._changed()

    def update_snippet(self, snippet_id, *, title=None, content=None, enabled=None):
        if title is not None:
            self.conn.execute("UPDATE snippets SET title = ? WHERE id = ?", (title, snippet_id))
        if content is not None:
            self.conn.execute("UPDATE snippets SET content = ? WHERE id = ?", (content, snippet_id))
        if enabled is not None:
            self.conn.execute("UPDATE snippets SET enabled = ? WHERE id = ?", (int(enabled), snippet_id))
        self._changed()

    def delete_folder(self, folder_id):
        self.conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        self._changed()

    def delete_snippet(self, snippet_id):
        self.conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        self._changed()

    def move_folder(self, folder_id, offset):
        ids = [f.id for f in self.folders()]
        self._reorder("folders", ids, folder_id, offset)

    def move_snippet(self, snippet_id, offset):
        snippet = self.snippet(snippet_id)
        if snippet:
            ids = [s.id for s in self.snippets(snippet.folder_id)]
            self._reorder("snippets", ids, snippet_id, offset)

    def _reorder(self, table, ids, item_id, offset):
        index = ids.index(item_id)
        target = min(max(index + offset, 0), len(ids) - 1)
        ids.insert(target, ids.pop(index))
        for position, value in enumerate(ids):
            self.conn.execute(f"UPDATE {table} SET position = ? WHERE id = ?", (position, value))
        self._changed()
