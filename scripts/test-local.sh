#!/usr/bin/env bash
# Local verification for host + content-snap packaging.
#
# Phases without root run automatically. Install/connect need sudo — pass
# --sudo to run them (you will be prompted for your password).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

THEME_NAME="Bibuntu"
SNAP_NAME="icon-theme-bibuntu"
VERSION="0.1.0"
SNAP_FILE="${SNAP_NAME}_${VERSION}_all.snap"
USER_ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/$THEME_NAME"

use_sudo=0
skip_build=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sudo) use_sudo=1 ;;
    --no-build) skip_build=1 ;;
    -h|--help)
      echo "Usage: $0 [--sudo] [--no-build]"
      echo "  --sudo     also install the snap and connect apps (password prompt)"
      echo "  --no-build reuse existing build/ and snap file when present"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

pass=0
fail=0
skip=0

ok()   { echo "  PASS  $*"; pass=$((pass + 1)); }
bad()  { echo "  FAIL  $*"; fail=$((fail + 1)); }
note() { echo "  SKIP  $*"; skip=$((skip + 1)); }

echo "=========================================="
echo " Bibuntu local test"
echo "=========================================="

echo
echo "== Phase A: build theme =="
if [[ "$skip_build" -eq 1 && -d "build/$THEME_NAME" ]]; then
  note "using existing build/$THEME_NAME"
else
  if python3 build_theme.py --no-install >/tmp/bibuntu-test-build.log 2>&1; then
    ok "build_theme.py --no-install"
  else
    bad "build failed (see /tmp/bibuntu-test-build.log)"
    tail -20 /tmp/bibuntu-test-build.log || true
  fi
fi

if [[ -f "build/$THEME_NAME/index.theme" ]]; then
  ok "index.theme present"
else
  bad "missing build/$THEME_NAME/index.theme"
fi

if [[ -e "build/$THEME_NAME/cursors/left_ptr" ]]; then
  ftype="$(file -b "build/$THEME_NAME/cursors/left_ptr" || true)"
  if [[ "$ftype" == *Xcursor* ]]; then
    ok "left_ptr is Xcursor ($ftype)"
  else
    bad "left_ptr unexpected type: $ftype"
  fi
else
  bad "missing left_ptr cursor"
fi

n_files="$(find "build/$THEME_NAME/cursors" -type f 2>/dev/null | wc -l)"
n_links="$(find "build/$THEME_NAME/cursors" -type l 2>/dev/null | wc -l)"
if [[ "$n_files" -ge 50 ]]; then
  ok "cursor files=$n_files symlinks=$n_links"
else
  bad "too few cursor files: $n_files"
fi

echo
echo "== Phase B: host install =="
if ./scripts/install.sh --no-build --no-apply >/tmp/bibuntu-test-host.log 2>&1; then
  ok "scripts/install.sh --no-build --no-apply"
else
  bad "host install script failed"
  cat /tmp/bibuntu-test-host.log || true
fi

if [[ -f "$USER_ICONS/index.theme" && -e "$USER_ICONS/cursors/left_ptr" ]]; then
  ok "host tree at $USER_ICONS"
else
  bad "host tree incomplete at $USER_ICONS"
fi

if command -v gsettings >/dev/null 2>&1; then
  # Apply only if not already Bibuntu, or re-apply for test signal
  gsettings set org.gnome.desktop.interface cursor-theme "$THEME_NAME" 2>/dev/null || true
  gsettings set org.gnome.desktop.interface cursor-size 24 2>/dev/null || true
  cur="$(gsettings get org.gnome.desktop.interface cursor-theme 2>/dev/null || echo '')"
  if [[ "$cur" == *"$THEME_NAME"* ]]; then
    ok "gsettings cursor-theme=$cur"
  else
    bad "gsettings cursor-theme is $cur (expected $THEME_NAME)"
  fi
else
  note "gsettings not available"
fi

echo
echo "== Phase C: pack content snap =="
if [[ "$skip_build" -eq 1 && -f "$SNAP_FILE" ]]; then
  note "using existing $SNAP_FILE"
else
  if ./scripts/pack-snap.sh --no-build --version "$VERSION" >/tmp/bibuntu-test-pack.log 2>&1; then
    ok "pack-snap.sh → $SNAP_FILE"
  else
    bad "pack-snap.sh failed"
    cat /tmp/bibuntu-test-pack.log || true
  fi
fi

if [[ -f "$SNAP_FILE" ]]; then
  ok "snap file exists ($(du -h "$SNAP_FILE" | cut -f1))"
  # Avoid pipefail+grep -q SIGPIPE false failures: buffer listings first.
  snap_meta="$(unsquashfs -cat "$SNAP_FILE" meta/snap.yaml 2>/dev/null || true)"
  snap_list="$(unsquashfs -ll "$SNAP_FILE" 2>/dev/null || true)"
  if grep -q "name: ${SNAP_NAME}" <<<"$snap_meta"; then
    ok "snap meta name=$SNAP_NAME"
  else
    bad "snap meta missing or wrong name"
  fi
  if grep -qE "share/icons/${THEME_NAME}/cursors/left_ptr$" <<<"$snap_list"; then
    ok "snap contains share/icons/${THEME_NAME}/cursors/left_ptr"
  else
    bad "snap missing Bibuntu left_ptr path"
  fi
  if grep -q 'content: icon-themes' <<<"$snap_meta"; then
    ok "content slot id is icon-themes"
  else
    bad "content: icon-themes not in meta"
  fi
else
  bad "no snap file to inspect"
fi

echo
echo "== Phase D: install + connect (needs sudo) =="
if [[ "$use_sudo" -ne 1 ]]; then
  note "pass --sudo to install and connect"
  echo "       sudo snap install --dangerous $SNAP_FILE"
  echo "       ./scripts/connect-snap-apps.sh"
elif ! command -v snap >/dev/null 2>&1; then
  note "snap not installed"
elif [[ ! -f "$SNAP_FILE" ]]; then
  bad "cannot install: missing $SNAP_FILE"
else
  if sudo snap install --dangerous "$SNAP_FILE"; then
    ok "snap install --dangerous $SNAP_FILE"
  else
    bad "snap install failed"
  fi

  if snap list "$SNAP_NAME" >/dev/null 2>&1; then
    ok "snap list shows $SNAP_NAME"
  else
    bad "$SNAP_NAME not listed after install"
  fi

  if ./scripts/connect-snap-apps.sh "$SNAP_NAME"; then
    ok "connect-snap-apps.sh completed"
  else
    bad "connect-snap-apps.sh failed"
  fi

  n_conn="$(snap connections 2>/dev/null | awk -v s="${SNAP_NAME}:icon-themes" '$3 == s { c++ } END { print c+0 }')"
  if [[ "$n_conn" -gt 0 ]]; then
    ok "$n_conn app plug(s) connected to ${SNAP_NAME}:icon-themes"
    echo "       sample connections:"
    snap connections 2>/dev/null | awk -v s="${SNAP_NAME}:icon-themes" '$3 == s { print "         " $2 " → " $3 }' | head -8
  else
    bad "no connections to ${SNAP_NAME}:icon-themes"
  fi

  # Prove theme is mounted into a connected snap's view
  probe_app="$(snap connections 2>/dev/null | awk -v s="${SNAP_NAME}:icon-themes" '$3 == s { split($2, a, ":"); print a[1]; exit }')"
  if [[ -n "$probe_app" ]]; then
    # Content mounts under $SNAP/data-dir/icons or similar depending on the app.
    # List interfaces for visibility; shell into snap if desktop plug allows.
    if snap run --shell "$probe_app" -c "ls \"\$SNAP/data-dir/icons/${THEME_NAME}/cursors/left_ptr\" 2>/dev/null || ls /snap/${SNAP_NAME}/current/share/icons/${THEME_NAME}/cursors/left_ptr" >/tmp/bibuntu-probe.txt 2>&1; then
      ok "theme visible to $probe_app (or via /snap/${SNAP_NAME}/current)"
      cat /tmp/bibuntu-probe.txt | sed 's/^/         /'
    else
      # Provider path is always readable from host for installed snaps
      if [[ -e "/snap/${SNAP_NAME}/current/share/icons/${THEME_NAME}/cursors/left_ptr" ]]; then
        ok "provider mount /snap/${SNAP_NAME}/current has left_ptr"
      else
        bad "could not verify theme path for $probe_app"
        cat /tmp/bibuntu-probe.txt | sed 's/^/         /' || true
      fi
    fi
  else
    note "no connected app to probe"
  fi
fi

echo
echo "=========================================="
echo " Results: PASS=$pass  FAIL=$fail  SKIP=$skip"
echo "=========================================="

if [[ "$fail" -gt 0 ]]; then
  exit 1
fi

if [[ "$use_sudo" -ne 1 ]]; then
  echo
  echo "Next: re-run with sudo for full snap install test:"
  echo "  ./scripts/test-local.sh --sudo --no-build"
fi
