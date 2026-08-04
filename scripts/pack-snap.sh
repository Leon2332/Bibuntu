#!/usr/bin/env bash
# Pack icon-theme-bibuntu using `snap pack` (no snapcraft / LXD required).
# Output: icon-theme-bibuntu_<version>_all.snap in the project root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${VERSION:-0.1.0}"
SNAP_NAME="icon-theme-bibuntu"
THEME_NAME="Bibuntu"
OUT="${SNAP_NAME}_${VERSION}_all.snap"

do_build=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) do_build=0 ;;
    --version)
      if [[ $# -lt 2 ]]; then
        echo "error: --version requires an argument" >&2
        exit 1
      fi
      VERSION="$2"
      OUT="${SNAP_NAME}_${VERSION}_all.snap"
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--no-build] [--version X.Y.Z]"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ "$do_build" -eq 1 ]]; then
  echo "==> Building theme"
  python3 build_theme.py --no-install
fi

if [[ ! -d "build/$THEME_NAME" ]]; then
  echo "error: missing build/$THEME_NAME" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

# snap pack requires a world-readable tree (mktemp is 0700 by default).
chmod 755 "$STAGE"
mkdir -p "$STAGE/meta" "$STAGE/share/icons"
cp -a "build/$THEME_NAME" "$STAGE/share/icons/$THEME_NAME"
chmod -R a+rX "$STAGE"

cat > "$STAGE/meta/snap.yaml" <<EOF
name: ${SNAP_NAME}
version: ${VERSION}
summary: Bibuntu cursor theme for snap applications
description: |
  Content snap providing the Bibuntu XCursor theme to apps that
  plug the icon-themes content interface.
license: GPL-3.0
architectures:
  - all
base: bare
confinement: strict
grade: stable
slots:
  icon-themes:
    interface: content
    content: icon-themes
    source:
      read:
        - \$SNAP/share/icons/${THEME_NAME}
EOF
chmod 644 "$STAGE/meta/snap.yaml"

echo "==> Packing $OUT"
rm -f "${SNAP_NAME}"_*.snap
snap pack "$STAGE" .
# snap pack may name the file from metadata
if [[ ! -f "$OUT" ]]; then
  produced="$(ls -1t "${SNAP_NAME}"_*.snap | head -1)"
  if [[ -n "$produced" && "$produced" != "$OUT" ]]; then
    mv -f "$produced" "$OUT"
  fi
fi

ls -lh "$OUT"
echo "OK: $OUT"
echo "Install: sudo snap install --dangerous $OUT"
echo "Connect: ./scripts/connect-snap-apps.sh"
