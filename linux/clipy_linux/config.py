"""Settings and XDG paths.

The setting names and defaults mirror the macOS app's `AppStorageValues.swift`
so both versions behave the same out of the box.
"""

import json
import os
from pathlib import Path

DEFAULTS = {
    # General
    "max_history": 30,
    "paste_automatically": True,
    "reorder_after_paste": True,
    "overwrite_same_history": True,
    "copy_same_history": True,
    "clear_history_on_quit": False,
    "ignore_concealed_types": True,
    "store_images": True,
    "launch_at_login": False,
    # Menu
    "inline_items": 0,
    "items_per_folder": 10,
    "max_title_length": 20,
    "start_numbering_at_zero": False,
    "mark_with_numbers": True,
    "show_tooltips": True,
    "max_tooltip_length": 200,
    "show_images": True,
    "thumbnail_width": 100,
    "thumbnail_height": 32,
    "show_icons": True,
    "show_clear_history_item": True,
    "confirm_clear_history": True,
    # "panel" (searchable clipboard window) or "menu" (classic Clipy menu)
    "popup_style": "panel",
    # "light" (white icon for dark panels), "dark" or "hidden"
    "tray_icon": "light",
    # Shortcuts (Gtk accelerator syntax). Only registered directly on X11;
    # on Wayland bind `clipy-ubuntu --menu main` etc. as desktop shortcuts.
    "main_shortcut": "<Primary><Alt>v",
    "history_shortcut": "<Primary><Alt>h",
    "snippet_shortcut": "<Primary><Alt>b",
    # Keys sent to the focused window to paste. Terminals usually need
    # "ctrl+shift+v"; "shift+Insert" works almost everywhere on X11.
    "paste_keys": "ctrl+v",
}


def _xdg_dir(env_name, fallback):
    value = os.environ.get(env_name)
    base = Path(value) if value else Path.home() / fallback
    return base / "clipy"


def config_dir():
    return _xdg_dir("XDG_CONFIG_HOME", ".config")


def data_dir():
    return _xdg_dir("XDG_DATA_HOME", ".local/share")


class Settings:
    """A small JSON-backed settings store with change callbacks."""

    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "settings.json"
        self._values = dict(DEFAULTS)
        self._listeners = []
        self.load()

    def load(self):
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                    self._values[key] = value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._values, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def __getitem__(self, key):
        return self._values[key]

    def __setitem__(self, key, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        if self._values.get(key) == value:
            return
        self._values[key] = value
        self.save()
        for listener in list(self._listeners):
            listener(key, value)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def connect(self, listener):
        self._listeners.append(listener)
