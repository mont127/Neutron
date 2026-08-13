#!/bin/bash
# zip the unified wine into the runtime bundle the app ships.
#   build-wine-bundle.sh [wine-dir] [out.zip]
#
# half the tree is object files, static libs and test suites: 5.7 GB to 2.3 GB.
# nls/ and fonts/ are symlinks into the wine source and would dangle elsewhere,
# so they get copied for real.
set -euo pipefail

SRC="${1:-$HOME/Library/Application Support/MacNCheese/deps/wine-unified}"
OUT="${2:-$(pwd)/dist/wine-unified-bundle.zip}"
STAGE="${TMPDIR:-/tmp}/neutron-wine-stage"

[ -x "$SRC/loader/wine" ] || { echo "not a wine build: $SRC" >&2; exit 1; }
command -v rsync >/dev/null || { echo "need rsync" >&2; exit 1; }

echo "staging from $SRC"
rm -rf "$STAGE"; mkdir -p "$STAGE" "$(dirname "$OUT")"
# D3DMetal is apple's and its licence forbids redistribution, so the toolkit's
# pieces are left out and the user points neutron at their own copy with
#   neutron d3dmetal <Evaluation_environment_for_Windows_games_*.dmg>
rsync -a \
    --exclude='*.o' --exclude='*.a' --exclude='*.lib' \
    --exclude='*_test.exe' --exclude='*.cross.o' \
    --exclude='.git' --exclude='*.log' \
    --exclude='mnc-d3d/D3DMetal.framework' \
    --exclude='mnc-d3d/libd3dshared.dylib' \
    --exclude='mnc-d3d/d3d11.dll' --exclude='mnc-d3d/d3d11_d3dm.dll' \
    --exclude='mnc-d3d/dxgi.dll' --exclude='mnc-d3d/dxgi_d3dm.dll' \
    --exclude='mnc-d3d/d3d12.dll' --exclude='mnc-d3d/d3d12_d3dm.dll' \
    --exclude='mnc-d3d/d3d10_d3dm.dll' \
    "$SRC/" "$STAGE/"

for d in nls fonts; do
    if [ -L "$SRC/$d" ]; then
        rm -rf "$STAGE/$d"
        cp -RL "$SRC/$d" "$STAGE/$d" 2>/dev/null || echo "  warning: could not deref $d"
        echo "  dereferenced $d"
    fi
done

# freetype, fontconfig, moltenvk and sdl travel with the engine too: without
# them a clean mac has no font rendering at all ("wine cannot find the freetype
# font library"), because the old dyld path pointed at macndcheese's deps and
# intel homebrew, neither of which a new machine has
for d in mnc-fonts mnc-tls mnc-vulkan mnc-sdl; do
    if [ -d "$(dirname "$SRC")/$d" ] && [ ! -d "$STAGE/$d" ]; then
        cp -R "$(dirname "$SRC")/$d" "$STAGE/$d"
        echo "  bundled $d ($(du -sh "$STAGE/$d" | cut -f1))"
    fi
done

# the graphics pack has to travel with it or no game renders
[ -d "$SRC/mnc-d3d" ] && echo "  mnc-d3d included ($(du -sh "$SRC/mnc-d3d" | cut -f1))"

echo "staged $(du -sh "$STAGE" | cut -f1), zipping (slow)..."
rm -f "$OUT"
( cd "$STAGE" && zip -r -q -y "$OUT" . )
rm -rf "$STAGE"
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1))"
