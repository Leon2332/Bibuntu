![Bibuntu](docs/Bibuntu.jpeg)

# Bibuntu

A cursor theme for Ubuntu — based on Bibata.

Portable **XCursor** theme (Wayland + X11). Hotspots and aliases match **Bibata Modern**.

Based on [Bibata Cursor](https://github.com/ful1e5/Bibata_Cursor) by [Abdulkaiz Khatri](https://github.com/ful1e5).

## Why two installs?

Strict snap apps cannot read host icon directories (`~/.local/share/icons`,
`/usr/share/icons`). A normal host install covers Settings and native apps; a
local **content snap** is needed so snap applications can
use the same cursors.

## Quick start (host)

```bash
python3 build_theme.py --apply
```

Requires: Python 3, Pillow, PyGObject + librsvg (`gi.repository.Rsvg`), cairo.

Installs to:

```text
~/.local/share/icons/Bibuntu
```

Or use the installer script / Makefile:

```bash
./scripts/install.sh          # build, user install, apply gsettings
make install                  # same
make install-system           # /usr/share/icons/Bibuntu (sudo)
```

Build without installing:

```bash
python3 build_theme.py --no-install
# → build/Bibuntu
```

### Apply (GNOME / Ubuntu)

```bash
gsettings set org.gnome.desktop.interface cursor-theme 'Bibuntu'
gsettings set org.gnome.desktop.interface cursor-size 24
```

Or **Settings → Appearance → Cursor**.

### Host CLI options

```bash
python3 build_theme.py --apply           # user install + gsettings
python3 build_theme.py --system --apply  # /usr/share/icons (needs root)
python3 build_theme.py --prefix /usr     # packaging DESTDIR-style prefixes OK via DESTDIR/usr
python3 build_theme.py --no-install      # build tree only
```

## Snap applications

Strict snaps only see cursor themes shared over the **`icon-themes`** content
interface. This repo packs that as a local snap named **`icon-theme-bibuntu`**.

### Install

No snapcraft required (`snap pack`):

```bash
make install-snap
# packs via scripts/pack-snap.sh, installs with --dangerous, connects plugs
```

Equivalent steps:

```bash
make pack                                          # → icon-theme-bibuntu_0.1.0_all.snap
sudo snap install --dangerous icon-theme-bibuntu_*.snap
./scripts/connect-snap-apps.sh
```

Restart open snap apps (or log out/in) after connecting.

One-shot host + snap:

```bash
./scripts/install.sh --with-snap
```

### Connect only

```bash
./scripts/connect-snap-apps.sh
# or for a single app:
sudo snap connect brave:icon-themes icon-theme-bibuntu:icon-themes
```

Multiple theme snaps can stay connected at once (e.g. `gtk-common-themes` + Bibuntu).

After you install **new** snap apps later, re-run `./scripts/connect-snap-apps.sh`
so they pick up Bibuntu (local installs do not auto-connect).

### Checks

```bash
make test          # host + pack (no root)
make test-sudo     # also install + connect (password prompt)
```

## Uninstall

Host (user):

```bash
rm -rf ~/.local/share/icons/Bibuntu
gsettings set org.gnome.desktop.interface cursor-theme 'Yaru'
# or whatever you used before
```

Host (system):

```bash
sudo rm -rf /usr/share/icons/Bibuntu
```

Snap:

```bash
sudo snap remove icon-theme-bibuntu
```

## Packaging layout

| Path | Role |
| --- | --- |
| `build_theme.py` | Build XCursor theme from `src/svg` |
| `scripts/install.sh` | Host install (+ optional snap) |
| `scripts/pack-snap.sh` | Pack local content snap (`snap pack`) |
| `scripts/connect-snap-apps.sh` | Wire all snaps to `icon-theme-bibuntu` |
| `scripts/test-local.sh` | Local verification |
| `snap/snapcraft.yaml` | Content snap definition (optional snapcraft builds) |
| `Makefile` | `build`, `install`, `pack`, `connect`, … |

## Credits

- (original) **Bibata Cursor** — [ful1e5/Bibata_Cursor](https://github.com/ful1e5/Bibata_Cursor) (GPL-3.0)
- **Bibuntu** — Ubuntu-oriented variant and animation work
