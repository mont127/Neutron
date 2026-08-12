#!/bin/bash
# zip the unified wine into the runtime bundle the app ships.
#   build-wine-bundle.sh [wine-dir] [out.zip]
#
# about half the tree is object files, static libs and wine's per-dll test
# suites, none of it needed to run a game. dropping those takes 5.7 GB to 2.3 GB.
#
# nls/ and fonts/ are symlinks back into the wine source tree. shipped as links
# they dangle on another machine: wineserver fails on l_intl.nls and game
# windows come up tiny and fontless. so they get copied for real.
set -euo pipefail

SRC="${1:-$HOME/Library/Application Support/MacNCheese/deps/wine-unified}"
OUT="${2:-$(pwd)/dist/wine-unified-bundle.zip}"
STAGE="${TMPDIR:-/tmp}/neutron-wine-stage"

[ -x "$SRC/loader/wine" ] || { echo "not a wine build: $SRC" >&2; exit 1; }
command -v rsync >/dev/null || { echo "need rsync" >&2; exit 1; }

echo "staging from $SRC"
rm -rf "$STAGE"; mkdir -p "$STAGE" "$(dirname "$OUT")"
rsync -a \
    --exclude='*.o' --exclude='*.a' --exclude='*.lib' \
    --exclude='*_test.exe' --exclude='*.cross.o' \
    --exclude='.git' --exclude='*.log' \
    "$SRC/" "$STAGE/"

for d in nls fonts; do
    if [ -L "$SRC/$d" ]; then
        rm -rf "$STAGE/$d"
        cp -RL "$SRC/$d" "$STAGE/$d" 2>/dev/null || echo "  warning: could not deref $d"
        echo "  dereferenced $d"
    fi
done

# the graphics pack has to travel with it or no game renders
[ -d "$SRC/mnc-d3d" ] && echo "  mnc-d3d included ($(du -sh "$SRC/mnc-d3d" | cut -f1))"

echo "staged $(du -sh "$STAGE" | cut -f1), zipping (slow)..."
rm -f "$OUT"
( cd "$STAGE" && zip -r -q -y "$OUT" . )
rm -rf "$STAGE"
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1))"
