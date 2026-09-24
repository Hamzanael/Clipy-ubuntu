"""Launch-at-login support through an XDG autostart entry."""

import os
import shlex
import shutil
from pathlib import Path

from . import APP_NAME

LAUNCHER = "clipy-ubuntu"


def autostart_path():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "clipy-ubuntu.desktop"


def launcher_command():
    found = shutil.which(LAUNCHER)
    if found:
        return found
    return str(Path(__file__).resolve().parent.parent / "bin" / LAUNCHER)


def desktop_entry(command):
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Clipboard history and snippets\n"
        f"Exec={shlex.quote(command)}\n"
        "Icon=clipy-ubuntu\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=3\n"
    )


def is_enabled():
    return autostart_path().exists()


def set_enabled(enabled):
    path = autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_entry(launcher_command()), encoding="utf-8")
    elif path.exists():
        path.unlink()
