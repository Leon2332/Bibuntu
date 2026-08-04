#!/usr/bin/env bash
# Install Bibuntu for the host, and optionally for snap apps.
#
# Usage:
#   scripts/install.sh                 # build + user host install + apply
#   scripts/install.sh --system        # install under /usr/share/icons (sudo)
#   scripts/install.sh --with-snap     # also build/install/connect the content snap
#   scripts/install.sh --snap-only     # only the content snap (no host install)
#   scripts/install.sh --no-apply      # do not change gsettings
#   scripts/install.sh --no-build      # use existing build/Bibuntu
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

THEME_NAME="Bibuntu"
USER_ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/$THEME_NAME"
SYSTEM_ICONS="/usr/share/icons/$THEME_NAME"
SNAP_NAME="icon-theme-bibuntu"

do_build=1
do_host=1
do_system=0
do_snap=0
do_apply=1
snap_only=0

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --system) do_system=1 ;;
    --with-snap) do_snap=1 ;;
    --snap-only) snap_only=1; do_host=0; do_snap=1 ;;
    --no-apply) do_apply=0 ;;
    --no-build) do_build=0 ;;
    -h|--help) usage 0 ;;
    *)
      echo "unknown option: $1" >&2
      usage 1
      ;;
  esac
  shift
done

if [[ "$do_build" -eq 1 ]]; then
  echo "==> Building theme"
  python3 build_theme.py --no-install
fi

if [[ ! -d "$ROOT/build/$THEME_NAME" ]]; then
  echo "error: missing $ROOT/build/$THEME_NAME (run without --no-build)" >&2
  exit 1
fi

install_tree() {
  local dest="$1"
  local use_sudo="${2:-0}"
  echo "==> Installing host theme → $dest"
  if [[ "$use_sudo" -eq 1 ]]; then
    sudo rm -rf "$dest"
    sudo mkdir -p "$(dirname "$dest")"
    sudo cp -a "$ROOT/build/$THEME_NAME" "$dest"
  else
    rm -rf "$dest"
    mkdir -p "$(dirname "$dest")"
    cp -a "$ROOT/build/$THEME_NAME" "$dest"
  fi
}

if [[ "$do_host" -eq 1 ]]; then
  if [[ "$do_system" -eq 1 ]]; then
    install_tree "$SYSTEM_ICONS" 1
  else
    install_tree "$USER_ICONS" 0
  fi
fi

if [[ "$do_apply" -eq 1 && "$snap_only" -eq 0 ]]; then
  if command -v gsettings >/dev/null 2>&1; then
    echo "==> Applying cursor theme (GNOME/Ubuntu)"
    gsettings set org.gnome.desktop.interface cursor-theme "$THEME_NAME" || true
    gsettings set org.gnome.desktop.interface cursor-size 24 || true
  else
    echo "note: gsettings not found; set the cursor theme in your desktop settings"
  fi
fi

if [[ "$do_snap" -eq 1 ]]; then
  if ! command -v snap >/dev/null 2>&1; then
    echo "error: snap is not installed; cannot install content snap" >&2
    exit 1
  fi

  echo "==> Building content snap ($SNAP_NAME)"
  # Prefer snap pack (no snapcraft/LXD). Fall back to snapcraft if present.
  if [[ -x "$ROOT/scripts/pack-snap.sh" ]]; then
    "$ROOT/scripts/pack-snap.sh" --no-build
  elif command -v snapcraft >/dev/null 2>&1; then
    if ! snapcraft pack --destructive-mode; then
      echo "note: destructive-mode failed; trying managed/LXD build" >&2
      snapcraft pack
    fi
  else
    echo "error: need scripts/pack-snap.sh or snapcraft to build the content snap" >&2
    exit 1
  fi

  snap_file="$(ls -1t "${SNAP_NAME}"_*.snap 2>/dev/null | head -1 || true)"
  if [[ -z "$snap_file" ]]; then
    echo "error: no ${SNAP_NAME}_*.snap produced" >&2
    exit 1
  fi

  echo "==> Installing $snap_file"
  sudo snap install --dangerous "$snap_file"

  echo "==> Connecting snap apps to $SNAP_NAME"
  "$ROOT/scripts/connect-snap-apps.sh" "$SNAP_NAME"
fi

echo
echo "Host theme:  ${do_host}"
echo "  user path:   $USER_ICONS"
echo "  system path: $SYSTEM_ICONS"
echo "Snap theme:  ${do_snap} ($SNAP_NAME)"
echo
if [[ "$do_host" -eq 1 ]]; then
  echo "Native apps: Settings → Appearance → Cursor → $THEME_NAME"
fi
if [[ "$do_snap" -eq 0 ]]; then
  echo "Snap apps: install the content snap for sandboxed cursors:"
  echo "  make pack && sudo snap install --dangerous ${SNAP_NAME}_*.snap"
  echo "  scripts/connect-snap-apps.sh"
fi
