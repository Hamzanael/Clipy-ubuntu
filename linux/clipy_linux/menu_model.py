"""Toolkit-independent description of Clipy's menus.

This is a port of the layout rules in the macOS `MenuManager.swift`: the first
`inline_items` clips are placed directly in the menu, the rest are grouped into
numbered sub-folders of `items_per_folder` clips each, followed by snippet
folders and the app actions. The GTK layer only has to render the tree.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .storage import KIND_IMAGE

MAIN = "main"
HISTORY = "history"
SNIPPET = "snippet"
MENU_TYPES = (MAIN, HISTORY, SNIPPET)

# Actions an item can trigger.
PASTE_CLIP = "paste-clip"
PASTE_SNIPPET = "paste-snippet"
CLEAR_HISTORY = "clear-history"
EDIT_SNIPPETS = "edit-snippets"
PREFERENCES = "preferences"
QUIT = "quit"

SHORTEN_SYMBOL = "..."


@dataclass
class Label:
    title: str


@dataclass
class Separator:
    pass


@dataclass
class Item:
    title: str
    action: str
    payload: Optional[str] = None
    number: Optional[int] = None
    tooltip: Optional[str] = None
    image: Optional[bytes] = None
    icon: Optional[str] = None


@dataclass
class Submenu:
    title: str
    children: List[object] = field(default_factory=list)
    icon: Optional[str] = None


def trimmed_menu_title(text, max_length):
    """First non-blank line of `text`, shortened to `max_length` characters."""
    title = (text or "").strip()
    title = title.splitlines()[0] if title else ""
    limit = max(max_length, len(SHORTEN_SYMBOL))
    if len(title) <= limit:
        return title
    return title[: limit - len(SHORTEN_SYMBOL)] + SHORTEN_SYMBOL


def numbered_title(title, number, show_number):
    return f"{number}. {title}" if show_number else title


class MenuBuilder:
    def __init__(self, settings):
        self.settings = settings

    @property
    def first_index(self):
        return 0 if self.settings["start_numbering_at_zero"] else 1

    def build(self, menu_type, clips, folder_details):
        items = []
        if menu_type in (MAIN, HISTORY):
            items += self.history_items(clips)
        if menu_type in (MAIN, SNIPPET):
            items += self.snippet_items(folder_details, separate=menu_type == MAIN)
        if menu_type == MAIN:
            items.append(Separator())
            if self.settings["show_clear_history_item"]:
                items.append(Item("Clear History", CLEAR_HISTORY))
            items.append(Item("Edit Snippets…", EDIT_SNIPPETS))
            items.append(Item("Preferences…", PREFERENCES))
            items.append(Separator())
            items.append(Item("Quit Clipy", QUIT))
        return items

    # ----------------------------------------------------------------- history

    def history_items(self, clips):
        s = self.settings
        inline = max(0, s["inline_items"])
        per_folder = max(1, s["items_per_folder"])
        clips = clips[: max(0, s["max_history"])]
        first = self.first_index
        total = len(clips)

        items = [Label("History")]
        folder = None
        for i, clip in enumerate(clips):
            if i < inline:
                items.append(self.clip_item(clip, first + i))
                continue
            offset = (i - inline) % per_folder
            if offset == 0:
                start = i
                end = min(i + per_folder, total)
                folder = Submenu(f"{start + first} - {end - 1 + first}", icon=self._folder_icon())
                items.append(folder)
            folder.children.append(self.clip_item(clip, first + offset))
        return items

    def clip_item(self, clip, number):
        s = self.settings
        if clip.kind == KIND_IMAGE:
            title = "(Image)"
            tooltip = None
            image = clip.image if s["show_images"] else None
        else:
            title = trimmed_menu_title(clip.text, s["max_title_length"])
            tooltip = clip.text[: s["max_tooltip_length"]] if s["show_tooltips"] else None
            image = None
        return Item(
            numbered_title(title, number, s["mark_with_numbers"]),
            PASTE_CLIP,
            payload=clip.id,
            number=number,
            tooltip=tooltip,
            image=image,
        )

    # ---------------------------------------------------------------- snippets

    def snippet_items(self, folder_details, separate):
        if not folder_details:
            return []
        items = [Separator()] if separate else []
        items.append(Label("Snippet"))
        for folder, snippets in folder_details:
            if not folder.enabled:
                continue
            items.append(self.folder_submenu(folder, snippets))
        return items

    def folder_submenu(self, folder, snippets, with_label=False):
        s = self.settings
        submenu = Submenu(folder.title, icon=self._folder_icon())
        if with_label:
            submenu.children.append(Label(folder.title))
        number = self.first_index
        for snippet in snippets:
            if not snippet.enabled:
                continue
            submenu.children.append(Item(
                numbered_title(trimmed_menu_title(snippet.title, s["max_title_length"]), number, s["mark_with_numbers"]),
                PASTE_SNIPPET,
                payload=snippet.id,
                number=number,
                tooltip=snippet.content[: s["max_tooltip_length"]] if s["show_tooltips"] else None,
                icon="text-x-generic" if s["show_icons"] else None,
            ))
            number += 1
        return submenu

    def _folder_icon(self):
        return "folder" if self.settings["show_icons"] else None
