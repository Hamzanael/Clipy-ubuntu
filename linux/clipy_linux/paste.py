"""Send the paste keystroke to the focused window.

X11 uses `xdotool`. Wayland compositors do not let applications inject input,
so there we fall back to `wtype` (wlroots compositors) or `ydotool` (needs the
ydotoold daemon), if installed. Without any of them Clipy still puts the item
on the clipboard and the user presses Ctrl+V themselves.
"""

import os
import shutil
import subprocess

# Linux input event codes used by ydotool.
_YDOTOOL_CODES = {
    "ctrl": 29, "shift": 42, "alt": 56, "super": 125,
    "v": 47, "insert": 110,
}


def session_type():
    return os.environ.get("XDG_SESSION_TYPE", "x11" if os.environ.get("DISPLAY") else "").lower()


def parse_keys(keys):
    parts = [p.strip().lower() for p in keys.split("+") if p.strip()]
    return parts[:-1], parts[-1] if parts else "v"


def paste_command(keys="ctrl+v", session=None, which=shutil.which, window=None):
    """Return the argv that sends `keys` (e.g. "ctrl+shift+v"), or None.

    On X11, `window` is focused first so the paste reaches the app that was
    active before Clipy's panel took focus.
    """
    session = session or session_type()
    modifiers, key = parse_keys(keys)

    if session != "wayland" and which("xdotool"):
        xkey = {"insert": "Insert", "v": "v"}.get(key, key)
        focus = ["windowfocus", "--sync", str(window)] if window else []
        return ["xdotool"] + focus + ["key", "--clearmodifiers", "+".join(modifiers + [xkey])]

    if session == "wayland":
        if which("wtype"):
            argv = ["wtype"]
            for mod in modifiers:
                argv += ["-M", mod]
            argv += ["-k", "Insert" if key == "insert" else key]
            for mod in reversed(modifiers):
                argv += ["-m", mod]
            return argv
        if which("ydotool") and all(k in _YDOTOOL_CODES for k in modifiers + [key]):
            codes = [_YDOTOOL_CODES[k] for k in modifiers + [key]]
            return ["ydotool", "key"] + [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
        # XWayland apps still accept xdotool input.
        if which("xdotool"):
            return ["xdotool", "key", "--clearmodifiers", "+".join(modifiers + [key])]
    return None


def focused_window(which=shutil.which):
    """The X11 window that has keyboard focus, or None (always None on Wayland)."""
    if session_type() == "wayland" or not which("xdotool"):
        return None
    for command in ("getactivewindow", "getwindowfocus"):
        try:
            result = subprocess.run(["xdotool", command], capture_output=True, text=True, timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            return None
        window = result.stdout.strip()
        if result.returncode == 0 and window.isdigit() and window != "0":
            return int(window)
    return None


def send_paste(keys="ctrl+v", window=None):
    argv = paste_command(keys, window=window)
    if not argv:
        return False
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
