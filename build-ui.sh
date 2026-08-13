#!/bin/bash
# build Neutron.app, the window you install from.
#   build-ui.sh [output-dir] [wine-bundle.zip]
# with a zip the app is self-contained and unpacks the engine on first install.
# without one it expects a wine already on the machine.
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$SELF/dist}"
WINE_ZIP="${2:-}"
APP="$OUT/Neutron.app"

command -v swiftc >/dev/null || { echo "need swiftc (xcode command line tools)" >&2; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/installer/src"

swiftc -O -parse-as-library -o "$APP/Contents/MacOS/Neutron" "$SELF/ui/NeutronApp.swift"

# icon + the mark the window draws. regenerate from Logo.png if they are stale
if [ -f "$SELF/Logo.png" ] && [ ! -f "$SELF/ui/assets/Neutron.icns" ]; then
    python3 "$SELF/make-icon.py" "$SELF/Logo.png" "$SELF/ui/assets" >/dev/null
fi
for a in Neutron.icns mark.png; do
    [ -f "$SELF/ui/assets/$a" ] && cp "$SELF/ui/assets/$a" "$APP/Contents/Resources/$a"
done

cp "$SELF/neutron" "$SELF/neutron-run" "$APP/Contents/Resources/installer/"
# the version markers: without them a fresh install records version 0 and
# tries to "update" itself on the first launch
cp "$SELF/VERSION" "$SELF/ENGINE" "$APP/Contents/Resources/installer/"
# all of src/ ships: the launch shim, watcher, LaunchAgent plist and js
rsync -a --exclude='__pycache__' "$SELF/src/" "$APP/Contents/Resources/installer/src/"

# the real dxvk dxgi, staged over the pack's wined3d one. without it the dxvk
# backend still renders but reports the wrong adapter.
[ -d "$SELF/vendor" ] && rsync -a "$SELF/vendor/" "$APP/Contents/Resources/installer/vendor/"
chmod +x "$APP/Contents/Resources/installer/neutron" \
         "$APP/Contents/Resources/installer/neutron-run" \
         "$APP/Contents/Resources/installer/src/neutron-launch" \
         "$APP/Contents/Resources/installer/src/neutron-play" \
         "$APP/Contents/Resources/installer/src/neutron-watch" \
         "$APP/Contents/Resources/installer/src/compat-entry" 2>/dev/null || true

# prebuild the steam stub so the target machine needs no compiler
if command -v x86_64-w64-mingw32-gcc >/dev/null; then
    mkdir -p "$APP/Contents/Resources/installer/prebuilt"
    x86_64-w64-mingw32-gcc -static -O2 \
        -o "$APP/Contents/Resources/installer/prebuilt/steam.exe" \
        "$SELF/src/steam_stub.c" -ladvapi32
    command -v i686-w64-mingw32-gcc >/dev/null && \
        i686-w64-mingw32-gcc -static -O2 \
            -o "$APP/Contents/Resources/installer/prebuilt/steam32.exe" \
            "$SELF/src/steam_stub.c" -ladvapi32
    echo "  prebuilt steam stub"
fi

if [ -n "$WINE_ZIP" ]; then
    [ -f "$WINE_ZIP" ] || { echo "no such wine bundle: $WINE_ZIP" >&2; exit 1; }
    echo "  adding engine ($(du -h "$WINE_ZIP" | cut -f1)), this takes a minute"
    cp "$WINE_ZIP" "$APP/Contents/Resources/wine-unified-bundle.zip"
    # the installer checks this before it spends minutes unpacking. a .dmg that
    # arrived truncated otherwise fails with a raw CRC dump from unzip, which
    # reads like a bug rather than a damaged download
    shasum -a 256 "$WINE_ZIP" | cut -d' ' -f1 \
        > "$APP/Contents/Resources/installer/ENGINE.sha256"
    echo "  engine sha256 $(cut -c1-16 < "$APP/Contents/Resources/installer/ENGINE.sha256")..."
fi

# stamp the real version, so Finder's Get Info and the about box agree with the
# VERSION we just shipped rather than a number frozen at 1.0
VER="$(tr -d ' \n' < "$SELF/VERSION" 2>/dev/null || true)"
[ -n "$VER" ] || VER="0"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Neutron</string>
    <key>CFBundleDisplayName</key><string>Neutron</string>
    <key>CFBundleIdentifier</key><string>com.mont127.neutron</string>
    <key>CFBundleVersion</key><string>$VER</string>
    <key>CFBundleShortVersionString</key><string>$VER</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>Neutron</string>
    <key>CFBundleIconFile</key><string>Neutron</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
</dict>
PLIST
echo "</plist>" >> "$APP/Contents/Info.plist"

# sign last: anything written into the bundle afterwards invalidates the seal
find "$APP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (unsigned, fine for local use)"
codesign --verify --deep "$APP" 2>&1 && echo "  signature ok"
echo "built: $APP"
