# AGENTS.md

This file is for AI coding agents (Claude Code, Codex, Cursor, Copilot, Gemini
CLI, …) working in this repository. It covers:

1. [Installing Clipy on a user's Ubuntu machine](#1-installing-clipy-on-ubuntu)
2. [Working on the code](#2-working-on-the-code)

The repository has two independent apps:

| Path | What | Language / toolkit | Builds on |
|------|------|--------------------|-----------|
| `linux/` | Clipy for Ubuntu / Linux | Python 3 + GTK 3 (PyGObject) | Linux |
| `Clipy/`, `ClipyTests/`, `Clipy.xcodeproj` | Original Clipy for macOS | Swift + AppKit | macOS with Xcode only |

---

## 1. Installing Clipy on Ubuntu

Use this when a user asks you to "install Clipy", "set up the clipboard manager"
or similar on **Linux**. On macOS, send them to <https://clipy-app.com> instead.
This repository doesn't build the macOS app for end users.

### Rules

- **Ask before running `sudo`.** Installing the dependencies needs root. If
  `sudo -n true` fails (a password is needed), don't try to supply a password.
  Show the user the `apt` command from step 2 and wait for them to run it.
- **Install for the current user only.** `install.sh` writes only to `~/.local`
  (and to `~/.config/autostart` if the user wants launch at login). Never
  install system-wide or with `sudo ./install.sh`.
- **Don't change the user's keyboard shortcuts without asking.** Step 5 adds
  GNOME custom shortcuts. Say which keys it binds (Ctrl+Alt+V/H/B) before
  running it.
- Clipy is a desktop app. It needs a graphical session: `DISPLAY` or
  `WAYLAND_DISPLAY` must be set. Over plain SSH you can install it, but you
  can't start it. Tell the user to start it from their desktop.

### Step 1: Check the system

```sh
. /etc/os-release && echo "$ID $VERSION_ID"   # expect: ubuntu 22.04 / 24.04 (other Debian-based distros usually work)
echo "session=$XDG_SESSION_TYPE display=${DISPLAY:-} wayland=${WAYLAND_DISPLAY:-}"
```

Other distributions: the app works anywhere GTK 3 and PyGObject are available,
but `install.sh --deps` uses `apt`. On Fedora or Arch, install the equivalent
packages yourself (see the table under Troubleshooting), then continue with
step 3.

### Step 2: Get the code and install the dependencies

```sh
git clone https://github.com/Hamzanael/Clipy-ubuntu.git ~/Clipy-ubuntu   # skip if you are already in a checkout
cd ~/Clipy-ubuntu/linux
./install.sh --check          # shows what is missing; exit code 0 means ready
```

If `--check` reports missing packages:

```sh
sudo apt-get update
sudo apt-get install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gir1.2-keybinder-3.0 xdotool
```

`./install.sh --deps` runs the same `apt-get install` and then installs Clipy.

### Step 3: Install

```sh
./install.sh
```

Expected output ends with `Clipy installed.`. It exits non-zero (status 1)
with an explanation if PyGObject/GTK is missing. The installer is idempotent,
so running it again upgrades in place. It installs:

- `~/.local/share/clipy-ubuntu/` for the app files
- `~/.local/bin/clipy-ubuntu` and `~/.local/bin/clipy-ubuntu-shortcuts`
- `~/.local/share/applications/clipy-ubuntu.desktop` (app grid entry) and the icon

### Step 4: Start it

```sh
setsid -f ~/.local/bin/clipy-ubuntu >/dev/null 2>&1
```

Use the full path. `~/.local/bin` is only on `PATH` after the user logs in
again. Only one instance ever runs: running the command again talks to the
running instance, which is safe.

To make it start at login (ask the user first):

```sh
mkdir -p ~/.config/autostart
cp ~/.local/share/applications/clipy-ubuntu.desktop ~/.config/autostart/
```

The Preferences window's "Launch at login" switch controls the same file.

### Step 5: Keyboard shortcuts (Wayland only)

On Wayland, which is Ubuntu's default session, apps can't register global
shortcuts, so they must be added as GNOME custom shortcuts. On X11, Clipy
registers them itself, so skip this step.

```sh
[ "$XDG_SESSION_TYPE" = wayland ] && ~/.local/bin/clipy-ubuntu-shortcuts
```

This binds the shortcuts set in Clipy's Preferences, by default Ctrl+Alt+V
(clipboard), Ctrl+Alt+H (history) and Ctrl+Alt+B (snippets). It keeps the user's existing custom shortcuts, and running it again
is safe. `clipy-ubuntu-shortcuts --remove` undoes it.

### Step 6: Verify

```sh
./install.sh --check
```

Healthy output on a Wayland desktop:

```
packages:              ok
python3 + GTK 3:       ok
installed:             ok (Clipy for Linux 0.1.0)
on PATH:               ok
running:               yes
session:               wayland
wayland shortcuts:     ok
```

`on PATH: no` is fine until the user logs in again. `running: no` means step 4
has not run, or the app exited. Run `~/.local/bin/clipy-ubuntu` in the
foreground to see its error.

Tell the user to copy some text, press **Ctrl+Alt+V**, and check that it
appears in the panel.

### Controlling a running instance

These are useful when helping a user, and all of them are safe:

```sh
~/.local/bin/clipy-ubuntu --menu main       # open the clipboard panel (also: history, snippet)
~/.local/bin/clipy-ubuntu --preferences
~/.local/bin/clipy-ubuntu --snippets        # snippet editor
~/.local/bin/clipy-ubuntu --clear-history   # asks for confirmation unless the user turned that off
~/.local/bin/clipy-ubuntu --quit
~/.local/bin/clipy-ubuntu --version
```

User data lives in `~/.config/clipy/settings.json` (settings, JSON) and
`~/.local/share/clipy/clipy.db` (history and snippets, SQLite). Don't edit
these while Clipy is running. Quit it first.

### Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `PyGObject/GTK 3 is missing` | Install the packages from step 2. Clipy runs with the **system** Python (`/usr/bin/python3`). A pip, conda or pyenv Python won't do. |
| No tray icon on GNOME | The "Ubuntu AppIndicators" extension is disabled. Run `gnome-extensions enable ubuntu-appindicators@ubuntu.com`. On non-Ubuntu GNOME, install "AppIndicator and KStatusNotifierItem Support". Clipy still works without the icon through the shortcuts. |
| A Shift shortcut such as Ctrl+Shift+V does nothing on X11 | Clipy's key-grabbing library (Keybinder) can't detect Shift with a character key, so Clipy skips it and logs `can't be registered by Clipy`. Keep it in Preferences and run `~/.local/bin/clipy-ubuntu-shortcuts` (ask the user first) to add it as a GNOME shortcut. |
| Shortcuts do nothing on Wayland | Run step 5, then check that `gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings` lists `clipy-main`. |
| Item is copied but not pasted | Auto-paste needs `xdotool` (X11). On Wayland it needs `ydotool` with `ydotoold` running, or `wtype` on wlroots compositors. Without them, the user presses Ctrl+V. In terminals, set Preferences → Paste keystroke to `ctrl+shift+v`. |
| History stays empty on Wayland | Clipy reads the clipboard through XWayland. Make sure `CLIPY_ALLOW_WAYLAND` is **not** set in the environment. |
| Non-Ubuntu package names | Fedora: `python3-gobject gtk3 libayatana-appindicator-gtk3 keybinder3 xdotool`. Arch: `python-gobject gtk3 libayatana-appindicator libkeybinder3 xdotool`. |

### Uninstall

```sh
cd ~/Clipy-ubuntu/linux && ./install.sh --uninstall
```

This removes the app, launchers, autostart entry and Clipy's GNOME shortcuts.
It keeps the history and snippets in `~/.local/share/clipy`. Delete that
folder only if the user asks.

---

## 2. Working on the code

### Linux app (`linux/`)

```
linux/
  clipy_linux/
    app.py             Gtk.Application: tray, clipboard monitoring, hotkeys, paste
    panel.py           searchable clipboard panel (the default popup)
    preferences.py     preferences window
    snippet_editor.py  snippet editor window
    storage.py         SQLite history and snippets              (no GTK)
    menu_model.py      classic menu layout, port of MenuManager.swift  (no GTK)
    panel_model.py     panel search and row text                (no GTK)
    snippets_xml.py    macOS-compatible snippet XML             (no GTK)
    paste.py           paste keystroke via xdotool/wtype/ydotool (no GTK)
    config.py          settings; defaults mirror the macOS app  (no GTK)
  data/                style.css, icons, .desktop file
  tests/               test_core.py and test_panel_model.py (no display needed),
                       test_gtk_smoke.py (needs a display, e.g. xvfb-run)
  install.sh, bin/     installer and launchers (POSIX sh)
```

Run the checks before you commit. CI (`.github/workflows/linux.yml`) runs the
same ones on Ubuntu 24.04:

```sh
cd linux
python3 -m unittest discover -s tests -t .                  # pure tests; GTK tests are skipped without a display
xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -t .   # everything, including GTK window smoke tests
python3 -m pyflakes clipy_linux tests
shellcheck install.sh bin/clipy-ubuntu bin/clipy-ubuntu-shortcuts
```

Conventions:

- Keep GTK out of `storage`, `menu_model`, `panel_model`, `snippets_xml`,
  `paste` and `config` so they stay testable without a display. Put new logic
  there and add a test.
- GTK 3 only. The tray (AyatanaAppIndicator) needs GTK 3, and GTK 3 and GTK 4
  can't be mixed in one process.
- Styling belongs in `data/style.css`. Use theme colours (`@theme_fg_color`,
  `@theme_base_color`, …) rather than hard-coded ones, so light and dark
  themes both work.
- Settings keys and defaults in `config.py` mirror the macOS app's
  `AppStorageValues.swift`. Snippet XML must stay compatible with the macOS
  export (`<folders><folder><title/><snippets><snippet><title/><content/>`).
- Scripts are POSIX `sh` and must pass `shellcheck`.

### macOS app

The macOS app builds only on macOS with Xcode (see README.md, "Building from
source"). From Linux, don't edit the Swift sources or the Xcode project unless
you were asked to, because you can't build or test those changes. The `CI`
workflow builds and tests it on a macOS runner.
