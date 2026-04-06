#!/usr/bin/env bash
# Pack the nix-built standalone CLI into a self-extracting single file.
#
# Usage: ./build/pack_onefile.sh [nix-result-path]
# Output: dist/TaskPlanner (single executable)
#
# Requires: nix build output at result/ or specified path

set -euo pipefail

RESULT="${1:-result}"

if [ ! -d "$RESULT/bin" ]; then
  echo "Error: $RESULT/bin not found. Run 'nix build' first." >&2
  exit 1
fi

mkdir -p dist

# Find the actual store path (resolve symlinks)
STORE_PATH=$(readlink -f "$RESULT")

# Create a self-extracting archive using a shell header + compressed tar
TMPARCHIVE=$(mktemp)
tar -cf - -C "$STORE_PATH/bin" . | zstd -19 -q > "$TMPARCHIVE"

cat > dist/TaskPlanner << 'HEADER'
#!/bin/sh
# Self-extracting TaskPlanner CLI
set -e
EXTRACT_DIR="${TASKPLANNER_EXTRACT_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/taskplanner-cli}"
MARKER="$EXTRACT_DIR/.version"
SELF=$(readlink -f "$0")
SELF_HASH=$(sha256sum "$SELF" | cut -c1-16)

# Extract only if not already extracted or hash changed
if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$SELF_HASH" ]; then
  chmod -R u+w "$EXTRACT_DIR" 2>/dev/null || true
  rm -rf "$EXTRACT_DIR"
  mkdir -p "$EXTRACT_DIR"
  SKIP=$(awk '/^__ARCHIVE__$/{print NR + 1; exit 0; }' "$SELF")
  tail -n +"$SKIP" "$SELF" | zstd -d -q | tar xf - -C "$EXTRACT_DIR"
  chmod -R u+w "$EXTRACT_DIR"
  echo "$SELF_HASH" > "$MARKER"
fi

exec "$EXTRACT_DIR/TaskPlanner" "$@"
__ARCHIVE__
HEADER

cat "$TMPARCHIVE" >> dist/TaskPlanner
chmod +x dist/TaskPlanner
rm "$TMPARCHIVE"

SIZE=$(du -h dist/TaskPlanner | cut -f1)
echo "Packed: dist/TaskPlanner ($SIZE)"
