#!/bin/bash
# wrap Neutron.app into a disk image for release.
#   build-dmg.sh [version] [app] [out-dir]
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
VER="${1:-0.2}"
APP="${2:-$SELF/dist/Neutron.app}"
OUT="${3:-$SELF/dist}"
DMG="$OUT/Neutron-$VER.dmg"
STAGE="${TMPDIR:-/tmp}/neutron-dmg-$VER"

[ -d "$APP" ] || { echo "no app at $APP" >&2; exit 1; }
[ -x "$APP/Contents/MacOS/Neutron" ] || { echo "app has no binary" >&2; exit 1; }

codesign --verify --deep "$APP" 2>&1 || {
    echo "app signature is broken, refusing to ship it" >&2
    echo "(usually stray files written into the bundle after signing)" >&2
    exit 1
}

rm -rf "$STAGE"; mkdir -p "$STAGE"
# ditto, not cp: it keeps the signature and xattrs intact
ditto "$APP" "$STAGE/$(basename "$APP")"
ln -s /Applications "$STAGE/Applications"

cat > "$STAGE/Read me first.txt" <<'TXT'
Neutron

This app is not notarised by Apple, so the first open needs a right-click:
right-click Neutron, choose Open, then Open again in the warning. Double
clicking it the normal way will just say the developer cannot be verified.

Drag Neutron to Applications, open it once, and press Install. It puts itself
into Steam and then gets out of the way: Windows games appear in your library
with a working Play button, and Steam downloads and runs them itself.

The first install unpacks the engine, which takes a few minutes and only
happens once. After that you can delete this app if you like.

Mac games keep using their Mac version. Neutron only steps in when a game has
no Mac build.

Settings (renderer, Metal HUD) live in the Neutron app, and per game in Steam's
Launch Options, for example:  backend=opengl hud=1
TXT

rm -f "$DMG"
hdiutil create -volname "Neutron $VER" -srcfolder "$STAGE" \
    -ov -format UDZO -quiet "$DMG"
rm -rf "$STAGE"

codesign --force --sign - "$DMG" 2>/dev/null || true
echo "built: $DMG ($(du -h "$DMG" | cut -f1))"
