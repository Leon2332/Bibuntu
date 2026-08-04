#!/usr/bin/env bash
# Connect every snap that plugs icon-themes to icon-theme-bibuntu.
# Safe to re-run. Does not disconnect gtk-common-themes (multi-slot OK).
set -euo pipefail

SLOT_SNAP="${1:-icon-theme-bibuntu}"
SLOT="${SLOT_SNAP}:icon-themes"

if ! command -v snap >/dev/null 2>&1; then
  echo "error: snap is not installed" >&2
  exit 1
fi

if ! snap list "$SLOT_SNAP" >/dev/null 2>&1; then
  echo "error: snap '$SLOT_SNAP' is not installed" >&2
  echo "  Pack and install:  make pack && sudo snap install --dangerous icon-theme-bibuntu_*.snap" >&2
  exit 1
fi

mapfile -t plugs < <(
  snap connections 2>/dev/null \
    | awk '$2 ~ /:icon-themes$/ { print $2 }' \
    | sort -u
)

if [[ ${#plugs[@]} -eq 0 ]]; then
  echo "No snaps with an icon-themes plug found."
  exit 0
fi

connected=0
skipped=0
failed=0
for plug in "${plugs[@]}"; do
  if snap connections 2>/dev/null \
    | awk -v p="$plug" -v s="$SLOT" '$2 == p && $3 == s { found = 1 } END { exit !found }'
  then
    echo "already connected: $plug → $SLOT"
    skipped=$((skipped + 1))
    continue
  fi
  echo "connect $plug → $SLOT"
  if sudo snap connect "$plug" "$SLOT"; then
    connected=$((connected + 1))
  else
    echo "  warning: failed to connect $plug" >&2
    failed=$((failed + 1))
  fi
done

echo
echo "Done. newly connected: $connected  already: $skipped  failed: $failed"
echo "Restart open snap apps (or log out/in) so they pick up Bibuntu cursors."
echo "Host apps still use the theme from ~/.local/share/icons or /usr/share/icons."
echo "New snap apps installed later need this script re-run (no auto-connect)."

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi
