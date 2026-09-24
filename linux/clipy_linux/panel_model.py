"""Toolkit-independent helpers for the clipboard panel (search and row text)."""

import time

from .storage import KIND_IMAGE


def relative_time(timestamp, now=None):
    """Short human description of how long ago `timestamp` was."""
    now = time.time() if now is None else now
    seconds = max(0, int(now - timestamp))
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} h ago"
    days = hours // 24
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return time.strftime("%b %-d", time.localtime(timestamp))


def text_preview(text, max_length=80):
    """`text` collapsed to a single line and shortened to `max_length` characters."""
    text = " ".join((text or "").split())
    return text if len(text) <= max_length else text[: max_length - 1] + "…"


def clip_title(clip, max_length=80):
    return "Image" if clip.kind == KIND_IMAGE else text_preview(clip.text, max_length)


def clip_subtitle(clip, now=None):
    when = relative_time(clip.updated_at, now)
    if clip.kind == KIND_IMAGE:
        return when
    text = clip.text or ""
    lines = text.count("\n") + 1
    detail = f"{lines} lines" if lines > 1 else f"{len(text)} characters"
    return f"{when} · {detail}"


def matches(query, *texts):
    """Case-insensitive match where every word of `query` appears in one of `texts`."""
    words = query.lower().split()
    if not words:
        return True
    haystack = "\n".join(t for t in texts if t).lower()
    return all(word in haystack for word in words)


def filter_clips(clips, query):
    return [c for c in clips if matches(query, "image" if c.kind == KIND_IMAGE else c.text)]


def filter_snippets(folder_details, query):
    """Enabled snippets matching `query`, as [(folder, snippet)] in display order."""
    results = []
    for folder, snippets in folder_details:
        if not folder.enabled:
            continue
        for snippet in snippets:
            if snippet.enabled and matches(query, snippet.title, snippet.content, folder.title):
                results.append((folder, snippet))
    return results
