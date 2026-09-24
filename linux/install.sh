#!/bin/sh
# Install Clipy for the current user.
#
#   ./install.sh              install into ~/.local
#   ./install.sh --deps       also install the required Ubuntu packages (uses sudo)
#   ./install.sh --uninstall  remove it again
#   ./install.sh --check      report what is installed and missing (exit 0 when ready)
set -eu

SRC=$(dirname "$(readlink -f "$0")")
PREFIX=${PREFIX:-$HOME/.local}
APP_DIR=$PREFIX/share/clipy-ubuntu
BIN_DIR=$PREFIX/bin
DESKTOP_DIR=$PREFIX/share/applications
ICON_DIR=$PREFIX/share/icons/hicolor/256x256/apps
PACKAGES="python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gir1.2-keybinder-3.0 xdotool"

if [ "${1:-}" = "--check" ]; then
    status=0
    report() { printf '%-22s %s\n' "$1" "$2"; }
    missing=""
    for pkg in $PACKAGES; do
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing="$missing $pkg"
    done
    if [ -n "$missing" ]; then
        report "packages:" "MISSING$missing"
        status=1
    else
        report "packages:" "ok"
    fi
    if /usr/bin/python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
        report "python3 + GTK 3:" "ok"
    else
        report "python3 + GTK 3:" "MISSING (install python3-gi gir1.2-gtk-3.0)"
        status=1
    fi
    if [ -x "$BIN_DIR/clipy-ubuntu" ]; then
        report "installed:" "ok ($("$BIN_DIR/clipy-ubuntu" --version 2>/dev/null || echo "version unknown"))"
    else
        report "installed:" "no (run ./install.sh)"
        status=1
    fi
    case ":$PATH:" in
        *":$BIN_DIR:"*) report "on PATH:" "ok" ;;
        *) report "on PATH:" "no ($BIN_DIR is not on PATH; use the full path or log in again)" ;;
    esac
    if pgrep -f '^[^ ]*python3[.0-9]* -m clipy_linux' >/dev/null 2>&1; then
        report "running:" "yes"
    else
        report "running:" "no"
    fi
    report "session:" "${XDG_SESSION_TYPE:-unknown}"
    if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
        if gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null | grep -q clipy-; then
            report "wayland shortcuts:" "ok"
        else
            report "wayland shortcuts:" "not set (run clipy-ubuntu-shortcuts)"
        fi
    fi
    exit $status
fi

if [ "${1:-}" = "--uninstall" ]; then
    "$BIN_DIR/clipy-ubuntu" --quit 2>/dev/null || true
    "$BIN_DIR/clipy-ubuntu-shortcuts" --remove 2>/dev/null || true
    rm -rf "${APP_DIR:?}"
    rm -f "$BIN_DIR/clipy-ubuntu" "$BIN_DIR/clipy-ubuntu-shortcuts" \
          "$DESKTOP_DIR/clipy-ubuntu.desktop" "$ICON_DIR/clipy-ubuntu.png" \
          "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/clipy-ubuntu.desktop"
    echo "Clipy removed. Your history and snippets are kept in ${XDG_DATA_HOME:-$HOME/.local/share}/clipy."
    exit 0
fi

if [ "${1:-}" = "--deps" ]; then
    # shellcheck disable=SC2086 # word splitting is intended
    sudo apt-get install -y $PACKAGES
fi

if ! /usr/bin/python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "PyGObject/GTK 3 is missing. Install it with:" >&2
    echo "  sudo apt install $PACKAGES" >&2
    echo "or run: $0 --deps" >&2
    exit 1
fi

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"
rm -rf "${APP_DIR:?}/clipy_linux" "${APP_DIR:?}/bin" "${APP_DIR:?}/data"
cp -R "$SRC/clipy_linux" "$SRC/bin" "$SRC/data" "$APP_DIR/"
find "$APP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +
chmod +x "$APP_DIR/bin/"*
ln -sf "$APP_DIR/bin/clipy-ubuntu" "$BIN_DIR/clipy-ubuntu"
ln -sf "$APP_DIR/bin/clipy-ubuntu-shortcuts" "$BIN_DIR/clipy-ubuntu-shortcuts"
cp "$SRC/data/icons/clipy.png" "$ICON_DIR/clipy-ubuntu.png"
sed "s|^Exec=clipy-ubuntu|Exec=$BIN_DIR/clipy-ubuntu|" "$SRC/data/clipy-ubuntu.desktop" > "$DESKTOP_DIR/clipy-ubuntu.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi

echo "Clipy installed. Start it from the app grid or run: clipy-ubuntu"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: $BIN_DIR is not on your PATH; log out and back in, or add it." ;;
esac
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    echo "You are on Wayland: run 'clipy-ubuntu-shortcuts' to set up the global shortcuts."
fi
